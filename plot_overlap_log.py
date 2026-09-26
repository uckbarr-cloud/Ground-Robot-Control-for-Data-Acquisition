"""
plot_overlap_log.py
Reads overlap_log.csv and plots verified matches, split into separate
charts by actual run type, matched by exact run_id, not by label guessing.
"""
import csv
import matplotlib.pyplot as plt
from collections import defaultdict

LOG_FILE = "overlap_log.csv"
THRESHOLD = 25

# Exact run_id timestamps for each real route today, from the terminal logs
STRAIGHT_RUN_IDS = {"20260923_103336", "20260923_105100", "20260923_110922"}
ARM_RUN_IDS = {"20260923_123218", "20260923_124111", "20260923_124437"}

straight_runs = defaultdict(list)
arm_runs = defaultdict(list)

with open(LOG_FILE, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        run_id = row["run_id"]
        waypoint = row["waypoint"]
        matches = int(row["verified_matches"])
        fill_triggered = row["fill_triggered"].strip().lower() == "true"

        if run_id in STRAIGHT_RUN_IDS:
            straight_runs[run_id].append((waypoint, matches, fill_triggered))
        elif run_id in ARM_RUN_IDS:
            arm_runs[run_id].append((waypoint, matches, fill_triggered))


def plot_group(runs, title, filename):
    if not runs:
        print("No data for", title)
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.tab10.colors
    for i, (run_id, points) in enumerate(runs.items()):
        points_sorted = sorted(points, key=lambda p: int(p[0]))
        x_labels = [str(p[0]) for p in points_sorted]
        x = list(range(len(points_sorted)))
        y = [p[1] for p in points_sorted]
        fill_flags = [p[2] for p in points_sorted]
        color = colors[i % len(colors)]
        ax.plot(x, y, marker="o", label=run_id, color=color, alpha=0.8)
        for xi, yi, flagged in zip(x, y, fill_flags):
            if flagged:
                ax.scatter([xi], [yi], marker="x", s=150, color="red", zorder=5)
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels, rotation=45, ha="right")
    ax.axhline(y=THRESHOLD, color="gray", linestyle="--", label="Fill threshold (%d)" % THRESHOLD)
    ax.set_xlabel("Waypoint")
    ax.set_ylabel("Verified matches")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.show()
    print("Saved chart to", filename)


plot_group(straight_runs, "Straight-run self-check results\n(red X = reshoot triggered)", "overlap_log_straight.png")
plot_group(arm_runs, "W/fan-run self-check results\n(red X = reshoot triggered)", "overlap_log_arms.png")