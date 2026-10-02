#!/usr/bin/env python3
"""
generate_condition_report.py - automated structure condition report (v2)

Scans the robot photos of one inspection run, runs the crack-segmentation
model, merges overlapping views of the same defect, sizes each defect,
grades it, and writes a complete Word report. Every number, table row and
sentence is generated from the data. The report is always issued as a
DRAFT: it becomes valid only after a named person reviews and signs it.

Usage:
    python3 generate_condition_report.py                    # latest run in ./photos
    python3 generate_condition_report.py photos --run 20261004_101500
"""
import argparse, csv, datetime, glob, os, re, subprocess, sys
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ============================ CONFIGURATION ============================
MODEL_PATH = "best_v2.pt"
LOGO_PATH = "department_seal.png"
OVERLAP_LOG = "overlap_log.csv"
CONF_THRESHOLD = 0.25
GENERATOR = "generate_condition_report.py v2.0"

ASSET = {
    "Asset": "Björkskataleden underpass",
    "Asset ID": "Not assigned",
    "Location": "Luleå, Sweden",
    "Structure type": "Pedestrian and cycle underpass, concrete with textured wall finish",
    "Section inspected": "One wall and soffit, 5.0 m section",
}
INSPECTION = {
    "Inspection type": "Automated routine visual inspection (robotic)",
    "Platform": "Waveshare UGV-01 tracked robot, pan-tilt USB camera, 1920 x 1080",
    "Operator": "Akbar Ali Khan",
    "Organisation": "Luleå University of Technology, MSc Maintenance Engineering",
}
ROUTE_SPACING_M = 0.2
ROUTE_WAYPOINTS = 25

# Pixel to millimetre scale. PLACEHOLDERS until calibrated from a photo of a
# tape-measured object at the standard distance: mm_per_px = mm / pixels.
MM_PER_PX = {"Wall": 0.50, "Soffit": 1.15}
MM_PER_PX_OVERRIDE = {}          # e.g. {"wp07": 0.42} from a visible reference
SCALE_CALIBRATED = False         # set True once the values above are calibrated

SEVERITY_RULES = [(1.0, "Low"), (3.0, "Medium")]   # mean width limits (mm); above = High
ACTIONS = {
    "High":       ("Engineer assessment", "Within 1 month"),
    "Medium":     ("Engineer review, then re-inspect", "Within 12 months"),
    "Low":        ("Monitor", "Next scheduled inspection"),
    "Unverified": ("Manual review of image", "Before report release"),
}
RATING = {  # overall indicative condition from the worst finding
    "High": "SIGNIFICANT DEFECTS", "Medium": "MODERATE DEFECTS",
    "Low": "MINOR DEFECTS", "Unverified": "REVIEW REQUIRED", None: "NO DEFECTS DETECTED",
}
# ========================================================================

FONT = "Calibri"
HEX = {"navy": "1B2A41", "accent": "0B6E99", "light": "EEF2F6", "grey": "5F6B7A",
       "line": "C9D1DB", "High": "C62828", "Medium": "E08E0B", "Low": "2E7D32",
       "Unverified": "7A7A7A", None: "2E7D32", "amber_bg": "FFF4E0"}
rgb = lambda h: RGBColor.from_string(h)
SEV_ORDER = ["High", "Medium", "Low", "Unverified"]

NAME_RE = re.compile(r"^(?P<flag>UNRESOLVED_)?wp(?P<wp>\d+)_(?P<run>\d{8}_\d{6})_(?P<rest>.+)\.(jpe?g|png)$", re.I)


# ------------------------------ data ------------------------------
def parse_photo(path):
    m = NAME_RE.match(os.path.basename(path))
    if not m:
        return None  # skips check_ photos and anything not named by the route scripts
    rest = m.group("rest").lower()
    return {"path": path, "wp": int(m.group("wp")), "run": m.group("run"),
            "surface": "Soffit" if rest.startswith("ceiling") else "Wall",
            "unresolved": bool(m.group("flag"))}


def collect_photos(folder, run_id=None):
    items = [p for p in (parse_photo(f) for f in glob.glob(os.path.join(folder, "**", "*.*"), recursive=True)) if p]
    runs = sorted({i["run"] for i in items})
    if not runs:
        return None, []
    run = run_id or runs[-1]
    return run, sorted([i for i in items if i["run"] == run], key=lambda i: (i["wp"], i["path"]))


def mm_per_px(photo):
    return MM_PER_PX_OVERRIDE.get("wp%02d" % photo["wp"], MM_PER_PX[photo["surface"]])


def measure(mask, scale):
    """Length = long side of the rotated bounding box. Mean width = mask area / length,
    which follows curved cracks better than the box's short side."""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, None
    c = max(cnts, key=cv2.contourArea)
    (_, (a, b), _) = cv2.minAreaRect(c)
    length_px = max(a, b)
    if length_px <= 0:
        return None, None
    width_px = cv2.contourArea(c) / length_px
    return round(width_px * scale, 1), round(length_px * scale)


def detect(photos):
    from ultralytics import YOLO   # imported here so the report part runs without it
    model = YOLO(MODEL_PATH)
    raw = []
    for ph in photos:
        r = model(ph["path"], conf=CONF_THRESHOLD, verbose=False)[0]
        if r.boxes is None or len(r.boxes) == 0:
            continue
        plotted = r.plot()
        for i in range(len(r.boxes)):
            w = l = None
            if r.masks is not None:
                m = cv2.resize(r.masks.data[i].cpu().numpy(), (r.orig_shape[1], r.orig_shape[0]))
                w, l = measure(m > 0.5, mm_per_px(ph))
            raw.append(dict(ph, conf=float(r.boxes.conf[i]), width_mm=w, length_mm=l, plotted=plotted))
    return raw


def severity(width):
    if not width:
        return "Unverified"
    for limit, label in SEVERITY_RULES:
        if width < limit:
            return label
    return "High"


def build_findings(raw, out_dir):
    """Overlapping photos show the same defect several times. Detections at the
    same waypoint and surface are merged into one finding (strongest view kept)."""
    groups = {}
    for d in raw:
        groups.setdefault((d["wp"], d["surface"]), []).append(d)
    findings = []
    for n, key in enumerate(sorted(groups), start=1):
        views = groups[key]
        best = max(views, key=lambda d: d["conf"])
        fid = "F-%02d" % n
        img = best["plotted"]
        if img.shape[1] > 1400:
            img = cv2.resize(img, (1400, int(img.shape[0] * 1400 / img.shape[1])))
        img_path = os.path.join(out_dir, "annotated", "%s_%s.jpg" % (fid, os.path.splitext(os.path.basename(best["path"]))[0]))
        cv2.imwrite(img_path, img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        sev = severity(best["width_mm"])
        findings.append({
            "id": fid, "wp": best["wp"], "surface": best["surface"],
            "dist": round(best["wp"] * ROUTE_SPACING_M, 2), "photo": os.path.basename(best["path"]),
            "conf": best["conf"], "width": best["width_mm"], "length": best["length_mm"],
            "severity": sev, "action": ACTIONS[sev][0], "due": ACTIONS[sev][1],
            "views": len({d["path"] for d in views}), "image": img_path,
            "scale": "override" if ("wp%02d" % best["wp"]) in MM_PER_PX_OVERRIDE else "default",
        })
    return findings


def selfcheck_stats(run):
    """Reads overlap_log.csv (long-format rows written by waypoint_route.py)."""
    s = {"available": False, "checked": set(), "triggered": set(), "resolved": set(), "escalated": set()}
    if os.path.exists(OVERLAP_LOG):
        with open(OVERLAP_LOG, newline="") as f:
            for row in csv.reader(f):
                if len(row) < 11 or row[0] != run:
                    continue
                s["available"] = True
                wp = row[1]
                s["checked"].add(wp)
                if row[5] == "True": s["triggered"].add(wp)
                if row[8] == "True": s["resolved"].add(wp)
                if row[9] == "True": s["escalated"].add(wp)
    return {k: (len(v) if isinstance(v, set) else v) for k, v in s.items()}


# ------------------------------ charts ------------------------------
def chart_route(findings, path):
    length = ROUTE_WAYPOINTS * ROUTE_SPACING_M
    fig, ax = plt.subplots(figsize=(7.2, 2.1), dpi=200)
    for y, h, name, col in ((1.75, 0.22, "SOFFIT", "#E4E8EE"), (1.0, 0.26, "WALL", "#D5DBE3")):
        ax.add_patch(Rectangle((0, y), length, h, color=col, lw=0))
        ax.text(-0.08, y + h / 2, name, ha="right", va="center", fontsize=6.5, color="#5F6B7A", fontweight="bold")
    ax.plot([0, length], [0.42, 0.42], color="#1B2A41", lw=1.4)
    for i in range(ROUTE_WAYPOINTS + 1):
        ax.plot(i * ROUTE_SPACING_M, 0.42, marker="|", color="#1B2A41", ms=5 if i % 5 else 9)
    for x in np.arange(0, length + 1e-6, 1.0):
        ax.text(x, 0.18, "%g m" % x, ha="center", fontsize=6.5, color="#5F6B7A")
    ax.text(-0.08, 0.42, "ROUTE", ha="right", va="center", fontsize=6.5, color="#5F6B7A", fontweight="bold")
    for f in findings:
        y = 1.13 if f["surface"] == "Wall" else 1.86
        ax.plot([f["dist"], f["dist"]], [0.42, y], color="#9AA5B1", lw=0.6, ls=":", zorder=1)
        ax.scatter(f["dist"], y, s=70, color="#" + HEX[f["severity"]], edgecolor="white", lw=1, zorder=3)
        ax.annotate(f["id"], (f["dist"], y), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=6.5, fontweight="bold", color="#1B2A41")
    ax.set_xlim(-0.7, length + 0.2)
    ax.set_ylim(0, 2.25)
    ax.axis("off")
    fig.tight_layout(pad=0.2)
    fig.savefig(path)
    plt.close(fig)


def chart_severity(findings, path):
    counts = [sum(f["severity"] == s for f in findings) for s in SEV_ORDER]
    fig, ax = plt.subplots(figsize=(3.6, 2.0), dpi=200)
    ax.barh(SEV_ORDER[::-1], counts[::-1], color=["#" + HEX[s] for s in SEV_ORDER[::-1]], height=0.6)
    for i, c in enumerate(counts[::-1]):
        ax.text(c + 0.05, i, str(c), va="center", fontsize=8, color="#1B2A41")
    ax.set_xlim(0, max(counts + [1]) * 1.25)
    ax.set_xticks([])
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", labelsize=8, length=0)
    ax.set_title("Findings by severity", fontsize=8.5, color="#1B2A41", loc="left")
    fig.tight_layout(pad=0.3)
    fig.savefig(path)
    plt.close(fig)


# ------------------------------ docx helpers ------------------------------
def _insert_before(parent, el, successors):
    for tag in successors:
        found = parent.find(qn(tag))
        if found is not None:
            found.addprevious(el)
            return
    parent.append(el)


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_color)
    _insert_before(tcPr, shd, ("w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark"))


def borders(table, color=None, size=4, inside=True):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement("w:" + edge)
        if color is None or (not inside and edge.startswith("inside")):
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(size)); el.set(qn("w:color"), color)
        b.append(el)
    _insert_before(tblPr, b, ("w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook"))


def widths(table, cm):
    """Sets both the table grid and each cell, so Word and LibreOffice agree."""
    table.autofit = False
    for gc, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), cm):
        gc.set(qn("w:w"), str(int(round(w / 2.54 * 1440))))
    for row in table.rows:
        for i, w in enumerate(cm):
            row.cells[i].width = Cm(w)


def write(cell, text, size=9, bold=False, color="1B2A41", align="left", italic=False):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
                   "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    p.paragraph_format.space_after = Pt(0)
    for i, line in enumerate(str(text).split("\n")):
        r = p.add_run(("\n" if i else "") + line)
        r.font.size = Pt(size); r.bold = bold; r.italic = italic; r.font.color.rgb = rgb(color)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    return p


def para(doc, text="", size=10, bold=False, color="1B2A41", italic=False, after=4, align="left"):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if text:
        r = p.add_run(text)
        r.font.size = Pt(size); r.bold = bold; r.italic = italic; r.font.color.rgb = rgb(color)
    return p


def field(run, instr):
    for kind in ("begin", None, "separate", "text", "end"):
        if kind is None:
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = instr
        elif kind == "text":
            el = OxmlElement("w:t"); el.text = "1"
        else:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind)
        run._r.append(el)


def force_font(style, size, bold=False, color=None):
    style.font.size = Pt(size); style.font.bold = bold
    if color:
        style.font.color.rgb = rgb(color)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
    for att in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rf.get(qn(att)) is not None:
            del rf.attrib[qn(att)]
    for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(att), FONT)


def kv_table(doc_or_cell, rows, w=(4.6, 12.8), size=9):
    t = doc_or_cell.add_table(rows=len(rows), cols=2)
    borders(t, HEX["line"])
    for i, (k, v) in enumerate(rows):
        write(t.rows[i].cells[0], k, size=size, bold=True, color=HEX["grey"]); shade(t.rows[i].cells[0], HEX["light"])
        write(t.rows[i].cells[1], v, size=size)
    widths(t, w)
    keep_together(t)
    return t


def grid(doc, head, rows, w, size=8, sev_col=None, center=()):
    t = doc.add_table(rows=1 + len(rows), cols=len(head))
    borders(t, HEX["line"])
    for i, h in enumerate(head):
        c = t.rows[0].cells[i]; write(c, h, size=size, bold=True, color="FFFFFF", align="center"); shade(c, HEX["navy"])
    for ri, row in enumerate(rows, start=1):
        for i, v in enumerate(row):
            c = t.rows[ri].cells[i]
            is_sev = sev_col is not None and i == sev_col
            write(c, v, size=size, bold=is_sev, color=HEX.get(v, HEX["navy"]) if is_sev else HEX["navy"],
                  align="center" if i in center else "left")
            if ri % 2 == 0:
                shade(c, "F7F9FB")
    rpr = t.rows[0]._tr.get_or_add_trPr()
    hdr = OxmlElement("w:tblHeader"); hdr.set(qn("w:val"), "true"); rpr.append(hdr)
    widths(t, w)
    keep_together(t)
    return t


def keep_together(table):
    rows = table.rows
    for i, row in enumerate(rows):
        trPr = row._tr.get_or_add_trPr()
        if trPr.find(qn("w:cantSplit")) is None:
            cs = OxmlElement("w:cantSplit"); cs.set(qn("w:val"), "true"); trPr.insert(0, cs)
        if i < len(rows) - 1:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True


fmt = lambda v, unit="": "-" if v in (None, 0) else ("%s%s" % (v, unit))


# ------------------------------ report ------------------------------
def build_report(findings, photos, run, stats, status, out_dir):
    now = datetime.datetime.now()
    report_id = "CR-%s" % run
    worst = next((s for s in SEV_ORDER if any(f["severity"] == s for f in findings)), None)
    rating = RATING[worst]
    prov = "" if SCALE_CALIBRATED else " (provisional)"
    n_wall = sum(p["surface"] == "Wall" for p in photos)
    n_soffit = len(photos) - n_wall
    wps = sorted({p["wp"] for p in photos})
    mtimes = [os.path.getmtime(p["path"]) for p in photos]
    t0, t1 = (datetime.datetime.fromtimestamp(min(mtimes)), datetime.datetime.fromtimestamp(max(mtimes)))
    run_date = datetime.datetime.strptime(run, "%Y%m%d_%H%M%S")

    charts = os.path.join(out_dir, "charts")
    chart_route(findings, os.path.join(charts, "route.png"))
    chart_severity(findings, os.path.join(charts, "severity.png"))

    doc = Document()
    zoom = doc.settings.element.find(qn("w:zoom"))
    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.8)
    sec.top_margin, sec.bottom_margin = Cm(1.6), Cm(1.5)
    sec.different_first_page_header_footer = True
    st = doc.styles
    force_font(st["Normal"], 10)
    st["Normal"].paragraph_format.space_after = Pt(4)
    for name, size, color in (("Heading 1", 14, HEX["navy"]), ("Heading 2", 11, HEX["accent"])):
        force_font(st[name], size, True, color)
        st[name].paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
        st[name].paragraph_format.space_after = Pt(6)
    ppr = st["Heading 1"].element.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr"); bot = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "8"), ("w:space", "3"), ("w:color", HEX["accent"])):
        bot.set(qn(k), v)
    bdr.append(bot)
    _insert_before(ppr, bdr, ("w:shd", "w:tabs", "w:spacing", "w:ind", "w:jc", "w:outlineLvl", "w:rPr"))
    force_font(st["List Bullet"], 10)

    # running header / footer (pages 2+)
    ht = sec.header.add_table(1, 2, Cm(17.4))
    borders(ht, None)
    write(ht.rows[0].cells[0], "STRUCTURE CONDITION REPORT  |  %s" % ASSET["Asset"], size=8, bold=True, color=HEX["grey"])
    write(ht.rows[0].cells[1], report_id, size=8, color=HEX["grey"], align="right")
    widths(ht, (12.4, 5.0))
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for txt in ("DRAFT - pending engineer review   |   Page ", "PAGE", " of ", "NUMPAGES"):
        r = fp.add_run()
        r.font.size = Pt(8); r.font.color.rgb = rgb(HEX["grey"])
        field(r, txt) if txt.isupper() else r.add_text(txt)

    # ================= COVER =================
    top = doc.add_table(1, 2)
    borders(top, None)
    lc = top.rows[0].cells[0]
    if os.path.exists(LOGO_PATH):
        logo = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED)
        small = os.path.join(out_dir, "charts", "logo_small.png")
        cv2.imwrite(small, cv2.resize(logo, (360, int(logo.shape[0] * 360 / logo.shape[1]))))
        lc.paragraphs[0].add_run().add_picture(small, width=Cm(2.8))
    write(top.rows[0].cells[1], "Luleå University of Technology\nMSc Maintenance Engineering\nD7016B Industrial AI and eMaintenance",
          size=9, color=HEX["grey"], align="right")
    widths(top, (4.0, 13.4))
    para(doc, after=40)
    bar = para(doc, after=10)
    pb = OxmlElement("w:pBdr"); tb = OxmlElement("w:top")
    for k, v in (("w:val", "single"), ("w:sz", "24"), ("w:space", "1"), ("w:color", HEX["accent"])):
        tb.set(qn(k), v)
    pb.append(tb)
    _insert_before(bar._p.get_or_add_pPr(), pb, ("w:shd", "w:tabs", "w:spacing", "w:ind", "w:jc", "w:rPr"))
    para(doc, "STRUCTURE CONDITION REPORT", 26, True, HEX["navy"], after=2)
    para(doc, "Automated robotic visual inspection", 13, False, HEX["grey"], after=18)
    para(doc, ASSET["Asset"], 17, True, HEX["navy"], after=2)
    para(doc, ASSET["Location"], 11, False, HEX["grey"], after=22)
    kv_table(doc, [("Report ID", report_id), ("Inspection date", run_date.strftime("%d %B %Y")),
                   ("Capture window", "%s - %s" % (t0.strftime("%H:%M"), t1.strftime("%H:%M"))),
                   ("Inspection type", INSPECTION["Inspection type"]), ("Run status", status),
                   ("Report generated", now.strftime("%d %B %Y, %H:%M"))], w=(4.6, 12.8), size=10)
    para(doc, after=14)
    badge = doc.add_table(1, 2)
    borders(badge, None)
    write(badge.rows[0].cells[0], "OVERALL INDICATIVE CONDITION", size=10, bold=True, color="FFFFFF"); shade(badge.rows[0].cells[0], HEX["navy"])
    write(badge.rows[0].cells[1], rating, size=14, bold=True, color="FFFFFF", align="center"); shade(badge.rows[0].cells[1], HEX[worst])
    widths(badge, (7.0, 10.4))
    para(doc, after=10)
    warn = doc.add_table(1, 1)
    borders(warn, HEX["Medium"], 8)
    write(warn.rows[0].cells[0], "STATUS: DRAFT. Generated automatically from robot imagery. Not valid until reviewed "
          "and approved in Section 9. Findings are screening results, not a certified structural assessment.",
          size=9, color="7A4B00"); shade(warn.rows[0].cells[0], HEX["amber_bg"])
    widths(warn, (17.4,))
    para(doc, after=16)
    dc = grid(doc, ["", "Prepared", "Reviewed", "Approved"],
              [["Name", "Automated system", "", ""], ["Date", now.strftime("%Y-%m-%d"), "", ""]],
              (3.0, 4.8, 4.8, 4.8), size=8)
    doc.add_page_break()

    # ================= 1. EXECUTIVE SUMMARY =================
    doc.add_heading("1. Executive summary", 1)
    kpi = doc.add_table(2, 5)
    borders(kpi, "FFFFFF", 18)
    vals = [(str(len(wps)), "WAYPOINTS"), (str(len(photos)), "IMAGES ANALYSED"), (str(len(findings)), "FINDINGS"),
            (worst or "None", "HIGHEST SEVERITY"),
            (str(stats["triggered"]) if stats["available"] else "n/a", "SELF-CHECK RESHOOTS")]
    for i, (v, lab) in enumerate(vals):
        write(kpi.rows[0].cells[i], v, size=18, bold=True, color=HEX.get(v, HEX["navy"]) if i == 3 else HEX["navy"], align="center")
        write(kpi.rows[1].cells[i], lab, size=7, bold=True, color=HEX["grey"], align="center")
        shade(kpi.rows[0].cells[i], HEX["light"]); shade(kpi.rows[1].cells[i], HEX["light"])
    widths(kpi, (3.48,) * 5)
    para(doc, after=6)

    counts = {s: sum(f["severity"] == s for f in findings) for s in SEV_ORDER}
    summary = ("On %s the robot inspected a %.1f m section of %s along %d waypoints. %d images of the wall and soffit "
               "were screened by the crack-detection model. " %
               (run_date.strftime("%d %B %Y"), ROUTE_WAYPOINTS * ROUTE_SPACING_M, ASSET["Asset"], len(wps), len(photos)))
    if findings:
        top_f = sorted(findings, key=lambda f: (SEV_ORDER.index(f["severity"]), -f["conf"]))[0]
        summary += ("%d finding(s) were recorded: %d high, %d medium, %d low and %d unverified. The most significant is %s, "
                    "a %s-severity crack on the %s at waypoint %02d (about %.1f m along the route)%s. Recommended action: %s, %s." %
                    (len(findings), counts["High"], counts["Medium"], counts["Low"], counts["Unverified"], top_f["id"],
                     top_f["severity"].lower(), top_f["surface"].lower(), top_f["wp"], top_f["dist"],
                     (", mean width %.1f mm%s" % (top_f["width"], prov)) if top_f["width"] else "",
                     top_f["action"].lower(), top_f["due"].lower()))
    else:
        summary += "No defects were detected above the %.0f%% confidence threshold." % (CONF_THRESHOLD * 100)
    if stats["available"]:
        summary += (" The overlap self-check triggered %d reshoot(s); %d waypoint(s) remained unresolved." %
                    (stats["triggered"], stats["escalated"]))
    para(doc, summary, after=8)

    doc.add_heading("Areas of concern", 2)
    concern = [f for f in findings if f["severity"] in ("High", "Medium")]
    if concern:
        for f in sorted(concern, key=lambda f: SEV_ORDER.index(f["severity"])):
            p = doc.add_paragraph(style="List Bullet")
            r = p.add_run("%s  %s  " % (f["id"], f["severity"].upper())); r.bold = True; r.font.color.rgb = rgb(HEX[f["severity"]])
            p.add_run("%s, waypoint %02d (%.1f m), %s mean width%s. %s, %s." %
                      (f["surface"], f["wp"], f["dist"], fmt(f["width"], " mm"), prov, f["action"], f["due"].lower()))
    else:
        para(doc, "No high or medium severity findings were identified by the automated screening.")
    doc.add_heading("Recommended next inspection", 2)
    nxt = {"High": "Follow-up inspection within 1 month, after engineer assessment of the high-severity finding(s).",
           "Medium": "Follow-up inspection within 12 months.",
           "Unverified": "Complete the manual image review before scheduling the next inspection."}
    para(doc, nxt.get(worst, "Next routine inspection cycle. No follow-up is required on the basis of this screening."))

    # ================= 2. ASSET AND INSPECTION DETAILS =================
    doc.add_heading("2. Asset and inspection details", 1)
    kv_table(doc, list(ASSET.items()) + list(INSPECTION.items()) +
             [("Run ID", run), ("Route", "%d waypoints, %.1f m spacing, %.1f m total" %
                                (ROUTE_WAYPOINTS, ROUTE_SPACING_M, ROUTE_WAYPOINTS * ROUTE_SPACING_M)),
              ("Detection model", "YOLO segmentation (%s), confidence threshold %.0f%%" % (MODEL_PATH, CONF_THRESHOLD * 100))])

    # ================= 3. FINDINGS OVERVIEW =================
    doc.add_heading("3. Findings overview", 1)
    doc.add_picture(os.path.join(charts, "route.png"), width=Cm(17.4))
    para(doc, "Figure 1. Finding locations along the inspected route. Positions are approximate, derived from the waypoint index.",
         8.5, italic=True, color=HEX["grey"], after=10)
    ov = doc.add_table(1, 2)
    borders(ov, None)
    ov.rows[0].cells[0].paragraphs[0].add_run().add_picture(os.path.join(charts, "severity.png"), width=Cm(8.0))
    inner = ov.rows[0].cells[1].add_table(len(SEV_ORDER) + 1, 3)
    borders(inner, HEX["line"])
    for i, h in enumerate(("Severity", "Wall", "Soffit")):
        write(inner.rows[0].cells[i], h, size=8, bold=True, color="FFFFFF", align="center"); shade(inner.rows[0].cells[i], HEX["navy"])
    for ri, s in enumerate(SEV_ORDER, start=1):
        write(inner.rows[ri].cells[0], s, size=8, bold=True, color=HEX[s])
        for ci, surf in ((1, "Wall"), (2, "Soffit")):
            write(inner.rows[ri].cells[ci], str(sum(f["severity"] == s and f["surface"] == surf for f in findings)), size=8, align="center")
    widths(inner, (3.2, 2.3, 2.3))
    widths(ov, (8.6, 8.8))

    # ================= 4. FINDINGS REGISTER =================
    doc.add_heading("4. Findings register", 1)
    if findings:
        grid(doc, ["ID", "Location", "Surface", "Defect", "Width\n(mm)", "Length\n(mm)", "Conf.", "Severity", "Action", "Due"],
             [[f["id"], "WP %02d\n%.1f m" % (f["wp"], f["dist"]), f["surface"], "Crack", fmt(f["width"]), fmt(f["length"]),
               "%.0f%%" % (f["conf"] * 100), f["severity"], f["action"], f["due"]] for f in findings],
             (1.1, 1.5, 1.3, 1.2, 1.2, 1.3, 1.1, 1.8, 3.6, 3.3), size=8, sev_col=7, center=(0, 1, 4, 5, 6, 7))
        para(doc, "Widths and lengths are estimated from the segmentation mask%s. Detections of the same defect in "
                  "overlapping photos are merged into one finding." % prov, 8.5, italic=True, color=HEX["grey"])
    else:
        para(doc, "No findings.")

    # ================= 5. FINDING DETAILS =================
    if findings:
        doc.add_page_break()   # details section: two complete findings per page
    doc.add_heading("5. Finding details", 1)
    if not findings:
        para(doc, "No findings to detail.")
    for n, f in enumerate(findings):
        if n and n % 2 == 0:
            doc.add_page_break()
        doc.add_heading("%s  |  Crack, %s, waypoint %02d (%.1f m)" % (f["id"], f["surface"].lower(), f["wp"], f["dist"]), 2)
        card = doc.add_table(1, 2)
        borders(card, None)
        card.rows[0].cells[0].paragraphs[0].add_run().add_picture(f["image"], width=Cm(10.2))
        kv_table(card.rows[0].cells[1], [
            ("Severity", f["severity"] + prov), ("Confidence", "%.0f%%" % (f["conf"] * 100)),
            ("Mean width", fmt(f["width"], " mm")), ("Length", fmt(f["length"], " mm")),
            ("Views merged", str(f["views"])), ("Scale", f["scale"]), ("Source photo", f["photo"].replace("_", "_\u200b")),
            ("Action", "%s, %s" % (f["action"], f["due"].lower()))], w=(2.4, 4.4), size=8)
        widths(card, (10.4, 7.0))
        para(doc, "Photo %s. Crack detected on the %s at waypoint %02d, about %.1f m along the route%s." %
             (f["id"], f["surface"].lower(), f["wp"], f["dist"],
              (", mean width %.1f mm%s" % (f["width"], prov)) if f["width"] else ", size not measurable"),
             8.5, italic=True, color=HEX["grey"], after=4)
        rv = doc.add_table(2, 2)
        borders(rv, HEX["line"])
        write(rv.rows[0].cells[0], "Reviewer verdict:    \u2610 Confirmed     \u2610 False positive     \u2610 Site visit needed",
              size=8.5, color=HEX["grey"])
        write(rv.rows[0].cells[1], "Initials:", size=8.5, color=HEX["grey"])
        write(rv.rows[1].cells[0], "Notes:", size=8.5, color=HEX["grey"])
        shade(rv.rows[0].cells[0], HEX["light"]); shade(rv.rows[0].cells[1], HEX["light"])
        widths(rv, (13.4, 4.0))
        rv.rows[1].cells[0].merge(rv.rows[1].cells[1])
        rv.rows[1].height = Cm(0.8)
        para(doc, after=6)

    # ================= 6. RECOMMENDATIONS =================
    doc.add_heading("6. Recommendations", 1)
    recs = [[ACTIONS[s][0], ", ".join(f["id"] for f in findings if f["severity"] == s), ACTIONS[s][1], s]
            for s in SEV_ORDER if any(f["severity"] == s for f in findings)]
    if recs:
        grid(doc, ["Action", "Findings", "Timeframe", "Severity"], recs, (5.6, 4.6, 4.4, 2.8), size=9, sev_col=3, center=(3,))
    else:
        para(doc, "No maintenance actions arise from this screening.")
    para(doc, after=4)
    para(doc, "Next inspection: " + nxt.get(worst, "next routine inspection cycle."))

    # ================= 7. DATA QUALITY AND LIMITATIONS =================
    doc.add_heading("7. Data quality and limitations", 1)
    rows = [("Waypoints photographed", "%d of %d planned" % (len(wps), ROUTE_WAYPOINTS + 1)),
            ("Images analysed", "%d (wall %d, soffit %d)" % (len(photos), n_wall, n_soffit)),
            ("Run status", status)]
    if stats["available"]:
        rows += [("Overlap checks", "%d waypoints checked" % stats["checked"]),
                 ("Reshoots triggered", str(stats["triggered"])),
                 ("Resolved after reshoot", str(stats["resolved"])),
                 ("Unresolved (flagged)", str(stats["escalated"]))]
    else:
        rows += [("Overlap self-check", "No log entries found for this run")]
    rows += [("Scale calibration", "Calibrated" if SCALE_CALIBRATED else "NOT calibrated - all sizes and grades provisional")]
    kv_table(doc, rows)
    doc.add_heading("Not inspected and known limitations", 2)
    for txt in ["The floor, the opposite wall and everything beyond the %.1f m route were not inspected." % (ROUTE_WAYPOINTS * ROUTE_SPACING_M),
                "The model detects cracks only. Spalling, staining, efflorescence and exposed reinforcement are not assessed.",
                "Findings at the same waypoint and surface are merged, so two separate cracks there may appear as one.",
                "Widths below about two pixels at the capture distance cannot be resolved reliably.",
                "Positions along the route are derived from the waypoint index and share the robot's positioning drift."]:
        doc.add_paragraph(txt, style="List Bullet")

    # ================= 8. METHODOLOGY =================
    doc.add_heading("8. Methodology", 1)
    para(doc, "The robot stopped at each waypoint, photographed the wall at three pan angles and the soffit once, and checked "
              "overlap with the previous waypoint, re-shooting when overlap was insufficient. Each photo was screened by a YOLO "
              "segmentation model trained on a public crack dataset (4,029 images) and fine-tuned with 50 crack-free images of "
              "this site to suppress false detections on the engraved wall pattern. Crack length is taken from the rotated "
              "bounding box of the mask and mean width as mask area divided by length, converted to millimetres with a "
              "per-surface scale (wall %.2f mm/px, soffit %.2f mm/px%s)." %
              (MM_PER_PX["Wall"], MM_PER_PX["Soffit"], "" if SCALE_CALIBRATED else ", not yet calibrated"))
    grid(doc, ["Severity", "Mean crack width", "Action", "Timeframe"],
         [["Low", "under 1.0 mm", ACTIONS["Low"][0], ACTIONS["Low"][1]],
          ["Medium", "1.0 to 3.0 mm", ACTIONS["Medium"][0], ACTIONS["Medium"][1]],
          ["High", "over 3.0 mm", ACTIONS["High"][0], ACTIONS["High"][1]],
          ["Unverified", "not measurable", ACTIONS["Unverified"][0], ACTIONS["Unverified"][1]]],
         (2.8, 3.6, 6.0, 5.0), size=8.5, sev_col=0)
    para(doc, "Severity thresholds are a project convention for screening, not a certified standard.", 8.5, italic=True, color=HEX["grey"])

    # ================= 9. REVIEW AND APPROVAL =================
    doc.add_page_break()
    doc.add_heading("9. Review and approval", 1)
    para(doc, "This report was generated automatically. It becomes valid only after a competent person has reviewed every "
              "finding in Section 5, recorded a verdict, and signed below.")
    grid(doc, ["Role", "Name", "Signature", "Date"],
         [["Prepared by", "Automated system (%s)" % GENERATOR, "n/a", now.strftime("%Y-%m-%d")],
          ["Reviewed by", "", "", ""], ["Approved by", "", "", ""]], (3.2, 6.0, 4.6, 3.6), size=9)
    for row in doc.tables[-1].rows[1:]:
        row.height = Cm(1.1)
    doc.add_heading("Revision history", 2)
    grid(doc, ["Rev.", "Date", "Description", "By"],
         [["0.1", now.strftime("%Y-%m-%d"), "Automatically generated draft", "System"], ["", "", "", ""]],
         (1.6, 3.0, 9.2, 3.6), size=9)

    path = os.path.join(out_dir, "Condition_Report_%s.docx" % run)
    doc.save(path)
    return path


def main():
    ap = argparse.ArgumentParser(description="Generate an automated condition report (draft) for one run.")
    ap.add_argument("folder", nargs="?", default="photos")
    ap.add_argument("--run", default=None, help="run ID, e.g. 20261004_101500 (default: latest found)")
    ap.add_argument("--status", default="Completed", help="run status text shown in the report")
    ap.add_argument("--no-open", action="store_true", help="do not open the report when finished")
    a = ap.parse_args()

    run, photos = collect_photos(a.folder, a.run)
    if not photos:
        sys.exit("No route photos found in %s%s." % (a.folder, " for run %s" % a.run if a.run else ""))
    out_dir = os.path.join("reports", run)
    os.makedirs(os.path.join(out_dir, "annotated"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "charts"), exist_ok=True)
    print("Run %s: %d photos. Running detection ..." % (run, len(photos)))
    findings = build_findings(detect(photos), out_dir)
    print("%d finding(s) after merging overlapping views." % len(findings))
    path = build_report(findings, photos, run, selfcheck_stats(run), a.status, out_dir)
    print("Draft report written: %s" % path)
    if sys.platform == "darwin" and not a.no_open:
        subprocess.run(["open", path])


if __name__ == "__main__":
    main()