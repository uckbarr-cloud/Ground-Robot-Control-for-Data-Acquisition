"""
plot_overlap_log.py
Plots the self-check log, one chart per run.

Usage (Mac Terminal, project folder):
    python3 plot_overlap_log.py                      # all runs in overlap_log.csv
    python3 plot_overlap_log.py --run 20261004_101500
    python3 plot_overlap_log.py --file overlap_log_sept.csv
    python3 plot_overlap_log.py --no-show            # save PNGs only

What is drawn for each run:
  - blue line     : verified matches at each waypoint (first check)
  - red X         : the first check was below threshold, so a reshoot was triggered
  - green circle  : a re-check after the reshoot passed (fix confirmed)
  - red circle    : a re-check after the reshoot still failed
  - black diamond : escalated, waypoint left UNRESOLVED after all attempts
  - grey dashed   : threshold

Old-format logs (no re-check columns) are still accepted; they just show
the line and the red X markers.
"""
import argparse
import csv
import re
from collections import defaultdict

import matplotlib
import matplotlib.pyplot as plt


def to_bool(value):
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def to_int(value):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def wp_number(label):
    """'wp07', '7' or 7 -> 7"""
    m = re.search(r"\d+", str(label))
    return int(m.group()) if m else None


def load(path):
    runs = defaultdict(lambda: defaultdict(list))  # run_id -> wp -> rows
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            wp = wp_number(row.get("waypoint"))
            if wp is None or to_int(row.get("verified_matches")) is None:
                continue
            runs[row["run_id"]][wp].append(row)
    return runs


def plot_run(run_id, wps, show_names=True):
    waypoints = sorted(wps)
    x = list(range(len(waypoints)))
    first = [wps[w][0] for w in waypoints]
    y = [to_int(r["verified_matches"]) for r in first]
    threshold = to_int(first[0].get("threshold")) or 25

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(x, y, marker="o", color="tab:blue", alpha=0.85, label="First check")
    ax.axhline(threshold, color="gray", linestyle="--",
               label="Threshold (%d)" % threshold)

    n_fill = n_fixed = n_failed = n_escalated = 0
    seen = set()

    def lab(name):
        if name in seen:
            return None
        seen.add(name)
        return name

    for xi, w in zip(x, waypoints):
        rows = wps[w]
        if any(to_bool(r.get("fill_triggered")) for r in rows):
            n_fill += 1
            ax.scatter([xi], [to_int(rows[0]["verified_matches"])], marker="x",
                       s=160, color="red", zorder=5, label=lab("Reshoot triggered"))
        for r in rows:
            rc = to_int(r.get("recheck_matches"))
            if rc is None:
                continue
            attempt = to_int(r.get("attempt")) or 1
            if to_bool(r.get("fix_confirmed")):
                n_fixed += 1
                ax.scatter([xi], [rc], marker="o", s=110, facecolors="none",
                           edgecolors="green", linewidths=2.5, zorder=6,
                           label=lab("Re-check passed"))
            else:
                n_failed += 1
                ax.scatter([xi], [rc], marker="o", s=110, facecolors="none",
                           edgecolors="red", linewidths=2.5, zorder=6,
                           label=lab("Re-check failed"))
            ax.annotate("a%d" % attempt, (xi, rc), textcoords="offset points",
                        xytext=(7, 5), fontsize=8)
        if any(to_bool(r.get("escalated")) for r in rows):
            n_escalated += 1
            ax.scatter([xi], [to_int(rows[0]["verified_matches"])], marker="D",
                       s=90, color="black", zorder=7,
                       label=lab("Escalated (UNRESOLVED)"))

    ax.set_xticks(x)
    ax.set_xticklabels(["wp%02d" % w for w in waypoints], rotation=45, ha="right")
    ax.set_xlabel("Waypoint")
    ax.set_ylabel("Verified matches")
    ax.set_title("Self-check results, run %s\n%d reshoots, %d re-checks passed, "
                 "%d re-checks failed, %d escalated"
                 % (run_id, n_fill, n_fixed, n_failed, n_escalated))
    ax.legend(loc="best", fontsize=8)
    plt.tight_layout()
    out = "overlap_%s.png" % run_id
    plt.savefig(out, dpi=150)
    print("Saved", out)
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="overlap_log.csv")
    ap.add_argument("--run", default=None, help="only this run_id")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    if args.no_show:
        matplotlib.use("Agg")

    runs = load(args.file)
    if args.run:
        runs = {k: v for k, v in runs.items() if k == args.run}
    if not runs:
        print("No matching runs found in", args.file)
        return
    for run_id in sorted(runs):
        plot_run(run_id, runs[run_id])
    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
