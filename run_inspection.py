#!/usr/bin/env python3
"""
run_inspection.py - one command for a complete inspection mission.

1. Runs the route script (waypoint_route.py by default, or e.g. reverse.py).
2. When the mission ends, for any reason, finds the photos it produced.
3. Automatically generates the DRAFT condition report and opens it for review.

The robot run and the analysis are separate processes, so a failure in the
report step can never affect the robot or the photos already on disk.

Usage:
    python3 run_inspection.py              # main route
    python3 run_inspection.py reverse.py   # stress-test route
"""
import glob, os, re, subprocess, sys, time

PHOTOS_DIR = "photos"                       # must match where capture.py saves photos
REPORT_SCRIPT = "generate_condition_report.py"


def main():
    route = sys.argv[1] if len(sys.argv) > 1 else "waypoint_route.py"
    started = time.strftime("%Y%m%d_%H%M%S")
    print("Mission start: %s at %s" % (route, started))
    proc = subprocess.Popen([sys.executable, route])
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
        print("No photos from this mission were found, so no report was generated.")
        return 1
    run_id = max(runs)
    print("Generating draft condition report for run %s ..." % run_id)
    return subprocess.call([sys.executable, REPORT_SCRIPT, PHOTOS_DIR, "--run", run_id, "--status", status])


if __name__ == "__main__":
    sys.exit(main())