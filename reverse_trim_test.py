"""
reverse_trim_test.py
Calibrates REVERSE_TRIM, the left/right speed offset used when backing up.
Same method as the forward TRIM calibration (drive_test.py), but driving
backward in short bursts that match the self-check back-up maneuver.

Usage:  python3 reverse_trim_test.py 0.0325
"""
import csv
import os
import sys
import time
from datetime import datetime

from move_robot import send_command, stop

SPEED = 0.3      # same as FORWARD_SPEED in waypoint_route.py
BURST = 0.5      # seconds per burst, same length as one real back-up (0.15 m)
PAUSE = 0.5      # pause between bursts, same as the forward test
BURSTS = 13      # 13 x 0.5 s x 0.3 m/s = about 2 m total
START_CM = 60
LOG_FILE = "reverse_trim_log.csv"


def reverse_burst(k):
    left = round(-SPEED * (1 + k), 4)
    right = round(-SPEED * (1 - k), 4)
    send_command('{"T":1,"L":%s,"R":%s}' % (left, right))
    time.sleep(BURST)
    stop()
    return left, right


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 reverse_trim_test.py <k>")
        sys.exit(1)
    k = float(sys.argv[1])

    input("Robot parallel to wall, front and rear at %d cm, 2 m clear behind. "
          "Press Enter to start..." % START_CM)
    try:
        for i in range(BURSTS):
            left, right = reverse_burst(k)
            print("burst %d/%d  L=%s R=%s" % (i + 1, BURSTS, left, right))
            time.sleep(PAUSE)
    finally:
        stop()

    front = input("Front (camera end) distance from wall, cm: ")
    rear = input("Rear distance from wall, cm: ")
    notes = input("Notes (floor, anything odd), or Enter to skip: ")

    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["time", "k", "bursts", "burst_s", "start_cm",
                             "front_cm", "rear_cm", "notes"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), k, BURSTS,
                         BURST, START_CM, front, rear, notes])
    print("Saved to", LOG_FILE)


if __name__ == "__main__":
    main()