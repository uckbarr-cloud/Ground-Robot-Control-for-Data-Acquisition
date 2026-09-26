"""
turn_calibration_test.py
Measures actual turn angle for a fixed rate/duration, one direction at a time.
Use the iPhone Compass app (laid flat on the robot's top plate) to read heading
before and after each turn. This isolates whether the two rotation directions
behave differently, the way forward and reverse trim did.

Usage: python3 turn_calibration_test.py 0.5 4.09
       (rate, duration - same numbers you'd use for a 90 deg turn)
"""
import sys
import time
from move_robot import turn_by_rate

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 turn_calibration_test.py <rate> <duration>")
        sys.exit(1)
    rate = float(sys.argv[1])
    duration = float(sys.argv[2])

    input("Lay phone flat on robot, open Compass app, note the heading. Press Enter to turn...")
    turn_by_rate(rate, duration)
    input("Turn done. Read the new compass heading, note it, then press Enter to finish.")
    print("Now compute: actual turn = new heading - old heading (adjust for wraparound past 360/0).")