#!/usr/bin/env python3
"""
run_inspection.py - one command for a complete inspection.

1. Runs the route (waypoint_route.py).
2. When the run ends, for any reason, finds the photos it produced.
3. Generates the DRAFT condition report and opens it for review.

The robot run and the report are separate processes, so a problem in the
report step can never affect the robot or the photos already saved.

Usage:
    python3 run_inspection.py                  # camera 40 cm from the wall
    python3 run_inspection.py --distance 60    # camera 60 cm from the wall
"""
import argparse, glob, os, re, subprocess, sys, time

PHOTOS_DIR = "photos"                       # must match where capture.py saves photos
ROUTE_SCRIPT = "waypoint_route.py"
REPORT_SCRIPT = "generate_condition_report.py"


def main():
    ap = argparse.ArgumentParser(description="Run the inspection route, then write the draft report.")
    ap.add_argument("--distance", type=int, default=40, help="camera distance from the wall in cm (default 40)")
    a = ap.parse_args()

    started = time.strftime("%Y%m%d_%H%M%S")
    print("Mission start: %s at %s" % (ROUTE_SCRIPT, started))
    proc = subprocess.Popen([sys.executable, ROUTE_SCRIPT])
    try:
        code = proc.wait()
        status = "Completed" if code == 0 else "Ended with an error (exit code %d)" % code
    except KeyboardInterrupt:
        proc.wait()                         # the route script stops the motors itself
        status = "Stopped early by operator"
    print("Mission ended: %s" % status)

    runs = set()
    for p in glob.glob(os.path.join(PHOTOS_DIR, "**", "*wp*_*.jpg"), recursive=True):
        m = re.search(r"wp\d+_(\d{8}_\d{6})_", os.path.basename(p))
        if m and m.group(1) >= started:
            runs.add(m.group(1))
    if not runs:
        print("No photos from this run were found, so no report was generated.")
        return 1
    run_id = max(runs)
    print("Generating draft condition report for run %s ..." % run_id)
    return subprocess.call([sys.executable, REPORT_SCRIPT, PHOTOS_DIR, "--run", run_id,
                            "--status", status, "--distance", str(a.distance)])


if __name__ == "__main__":
    sys.exit(main())
