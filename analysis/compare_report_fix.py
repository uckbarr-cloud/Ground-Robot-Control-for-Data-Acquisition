"""
compare_report_fix.py - measures the effect of the three report rules (v3) on
the site runs, by running the crack model once per run and counting the
findings with the old rules (v2) and with each new rule added in turn.

Run from the project folder (it needs best_v2.pt and the photos/ folder):
    python3 analysis/compare_report_fix.py

Prints a table and saves analysis/report_fix_results.csv.
Note: rules 2 and 3 were worked out from these same runs, so the "after"
numbers show what the rules do on this data, not how well they would work
on new runs.
"""
import csv, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project folder
import generate_condition_report as g

PHOTOS_DIR = "photos"
OUT_CSV = os.path.join("analysis", "report_fix_results.csv")

# run ID: (setup, camera distance in cm)
RUNS = {
    "20261021_102341": ("100 cm", 100), "20261021_103316": ("100 cm", 100), "20261021_105514": ("100 cm", 100),
    "20261021_110823": ("100 cm", 100), "20261021_112033": ("100 cm", 100), "20261021_112857": ("100 cm", 100),
    "20261021_113949": ("100 cm", 100), "20261021_115023": ("100 cm", 100), "20261021_115147": ("100 cm", 100),
    "20261021_115951": ("100 cm", 100), "20261021_121357": ("100 cm", 100), "20261021_122205": ("100 cm", 100),
    "20261024_131254": ("40 cm, test sheets", 40), "20261024_132539": ("40 cm, test sheets", 40),
    "20261024_133911": ("40 cm, test sheets", 40), "20261024_141022": ("40 cm, clean wall", 40),
    "20261024_142236": ("40 cm, clean wall", 40), "20261024_142923": ("40 cm, clean wall", 40),
    "20261024_144211": ("40 cm, clean wall", 40), "20261024_145854": ("60 cm, clean wall", 60),
}

# The known features (rule 3) were found in the 40 cm runs, so they are only applied there.
STEPS = [
    ("before", dict(check_width=False, skip_far_zone=False, known={})),
    ("rule1", dict(check_width=True, skip_far_zone=False, known={})),
    ("rule12", dict(check_width=True, skip_far_zone=True, known={})),
    ("rule123", dict(check_width=True, skip_far_zone=True, known=None)),
]


def rating(defects):
    worst = next((s for s in g.SEV_ORDER if any(f["severity"] == s for f in defects)), None)
    return g.RATING[worst]


def main():
    rows = []
    for run, (setup, dist) in RUNS.items():
        _, photos = g.collect_photos(PHOTOS_DIR, run)
        if not photos:
            print("%s: no photos found, skipped" % run)
            continue
        t0 = time.time()
        raw = g.detect(photos, g.WALL_MM_PER_PX[dist], keep_images=False)
        secs = time.time() - t0
        row = {"run": run, "setup": setup, "distance_cm": dist, "photos": len(photos),
               "detections": len(raw), "in_far_zone": sum(g.in_far_zone(d) for d in raw),
               "model_seconds": round(secs, 1)}
        for name, opts in STEPS:
            opts = dict(opts)
            if name == "rule123" and dist != 40:
                opts["known"] = {}
            defects, known = g.build_findings(raw, None, **opts)
            row[name + "_findings"] = len(defects)
            row[name + "_high"] = sum(f["severity"] == "High" for f in defects)
            row[name + "_known"] = len(known)
            row[name + "_rating"] = rating(defects)
        rows.append(row)
        print("%s  %-20s  findings %2d -> %2d -> %2d -> %2d   High %2d -> %2d   %s -> %s   (%.0f s)" % (
            run, setup, row["before_findings"], row["rule1_findings"], row["rule12_findings"],
            row["rule123_findings"], row["before_high"], row["rule123_high"],
            row["before_rating"], row["rule123_rating"], secs))

    if not rows:
        sys.exit("No runs found in %s/." % PHOTOS_DIR)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\nTotals by setup (findings: before -> rule 1 -> rules 1+2 -> rules 1+2+3)")
    for setup in sorted({r["setup"] for r in rows}):
        rs = [r for r in rows if r["setup"] == setup]
        t = lambda k: sum(r[k] for r in rs)
        print("  %-20s %2d runs  findings %3d -> %3d -> %3d -> %3d   High %3d -> %3d   known %d   "
              "reports saying SIGNIFICANT DEFECTS %d -> %d" % (
                  setup, len(rs), t("before_findings"), t("rule1_findings"), t("rule12_findings"),
                  t("rule123_findings"), t("before_high"), t("rule123_high"), t("rule123_known"),
                  sum(r["before_rating"] == "SIGNIFICANT DEFECTS" for r in rs),
                  sum(r["rule123_rating"] == "SIGNIFICANT DEFECTS" for r in rs)))
    t = lambda k: sum(r[k] for r in rows)
    print("  %-20s %2d runs  findings %3d -> %3d -> %3d -> %3d   High %3d -> %3d" % (
        "ALL", len(rows), t("before_findings"), t("rule1_findings"), t("rule12_findings"),
        t("rule123_findings"), t("before_high"), t("rule123_high")))
    print("  model time: %.0f s for %d photos (%.2f s per photo)" % (
        t("model_seconds"), t("photos"), t("model_seconds") / max(t("photos"), 1)))
    print("\nSaved %s" % OUT_CSV)


if __name__ == "__main__":
    main()
