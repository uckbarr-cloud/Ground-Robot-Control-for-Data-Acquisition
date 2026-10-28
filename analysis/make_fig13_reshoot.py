"""
make_fig13_reshoot.py - figure of the self-check on site: verified matches at every
waypoint for the eight runs of 24 Oct, and the two re-shoot sequences.

Run from the project folder:  python3 analysis/make_fig13_reshoot.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("overlap_log.csv")
df = df[df["run_id"].astype(str).str.startswith("20261024")].copy()
df["trig"] = df["fill_triggered"].astype(str) == "True"
first = df.groupby(["run_id", "waypoint"], as_index=False).first()

LABELS = {
    "20261024_131254": "131254 (40 cm, sheets)",
    "20261024_132539": "132539 (40 cm, sheets)",
    "20261024_133911": "133911 (40 cm, sheets)",
    "20261024_141022": "141022 (40 cm, clean)",
    "20261024_142236": "142236 (40 cm, clean, stopped)",
    "20261024_142923": "142923 (40 cm, clean)",
    "20261024_144211": "144211 (40 cm, lens covered)",
    "20261024_145854": "145854 (60 cm, clean)",
}
THR = 25

fig, axes = plt.subplots(3, 1, figsize=(10, 12))

# Panel 1: all runs
ax = axes[0]
for rid, g in first.groupby("run_id"):
    ax.plot(g["waypoint"], g["verified_matches"], marker="o", ms=3,
            lw=1, alpha=0.8, label=LABELS.get(rid, rid))
ax.axhline(THR, color="red", ls="--", lw=1.5, label="Re-shoot threshold (25)")
ax.set_yscale("log")
ax.set_xlabel("Stop number")
ax.set_ylabel("Verified matches (log scale)")
ax.set_title("(a) Overlap check at every stop, all runs on 24 Oct")
ax.legend(fontsize=7, ncol=2)
ax.grid(alpha=0.3)

def zoom(ax, rid, title):
    g = first[first["run_id"] == rid]
    ax.plot(g["waypoint"], g["verified_matches"], marker="o", ms=4,
            lw=1.2, color="tab:blue", label="First check at each stop")
    t = df[(df["run_id"] == rid) & (df["trig"])]
    for _, row in t.iterrows():
        a = int(row["attempt"])
        rc = row["recheck_matches"]
        if pd.isna(rc):
            continue
        ok = str(row["fix_confirmed"]) == "True"
        ax.scatter(row["waypoint"], rc, s=70,
                   color="green" if ok else "orange",
                   edgecolor="black", zorder=5)
        ax.annotate("attempt %d: %d" % (a, int(rc)),
                    (row["waypoint"], rc), xytext=(34, -36 + 13 * a),
                    textcoords="offset points", fontsize=8, va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="gray"))
    for _, row in g[g["trig"]].iterrows():
        ax.scatter(row["waypoint"], row["verified_matches"], s=70,
                   color="red", edgecolor="black", zorder=6)
        ax.annotate("first check: %d" % int(row["verified_matches"]),
                    (row["waypoint"], row["verified_matches"]),
                    xytext=(34, -36), textcoords="offset points", fontsize=8,
                    va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.6, color="gray"))
    ax.axhline(THR, color="red", ls="--", lw=1.5, label="Re-shoot threshold (25)")
    ax.set_yscale("log")
    ax.set_ylim(2, None)
    ax.set_xlabel("Stop number")
    ax.set_ylabel("Verified matches (log scale)")
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

zoom(axes[1], "20261024_133911",
     "(b) Run 133911: natural re-shoot at stop 1 (fixed on attempt 3)")
zoom(axes[2], "20261024_144211",
     "(c) Run 144211: lens covered on purpose at stop 10")

plt.tight_layout()
out = "figures_24oct/fig13_reshoot_overlap.png"
plt.savefig(out, dpi=200)
print("Saved", out)

print()
print("%-17s %7s %9s %8s %8s" % ("RUN", "checks", "triggers", "min", "median"))
for rid, g in first.groupby("run_id"):
    print("%-17s %7d %9d %8d %8.0f" % (rid, len(g), int(g["trig"].sum()),
          g["verified_matches"].min(), g["verified_matches"].median()))
print()
print("Triggered rows:")
print(df[df["trig"]][["run_id", "waypoint", "verified_matches", "attempt",
                      "recheck_matches", "fix_confirmed"]].to_string(index=False))
