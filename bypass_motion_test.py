"""
bypass_motion_test.py
Motion-only test of the bypass-and-rejoin path (no camera, no photos).
Distances are halved from the final target route so it fits a home corridor.
Turn timing uses direction-specific deg/sec, measured on tonight's kitchen
floor. Re-measure on the corridor before running this there.
"""
import time
from move_robot import move_forward, stop, turn_by_rate

FORWARD_SPEED = 0.3
TURN_RATE = 0.5
SETTLE = 5.0

# Measured tonight, kitchen floor. Re-measure on corridor before reuse there.
NEG_DEG_PER_SEC = 15.4   # negative angle commands (rate -0.5)
POS_DEG_PER_SEC = 13.9   # positive angle commands (rate +0.5)

TURN_AWAY_SIGN = -1   # confirmed tonight

def drive_m(distance_m):
    duration = abs(distance_m) / FORWARD_SPEED
    speed = FORWARD_SPEED if distance_m >= 0 else -FORWARD_SPEED
    try:
        move_forward(speed)
        time.sleep(duration)
    finally:
        stop()

def turn_deg(angle_deg):
    deg_per_sec = POS_DEG_PER_SEC if angle_deg > 0 else NEG_DEG_PER_SEC
    duration = abs(angle_deg) / deg_per_sec
    rate = TURN_RATE if angle_deg > 0 else -TURN_RATE
    turn_by_rate(rate, duration)

LEGS = [
    ("drive", 0.50,                    "Leg 1: 50 cm along the wall"),
    ("turn",  TURN_AWAY_SIGN * 90,     "Leg 2: turn 90 deg AWAY from the wall"),
    ("drive", 0.25,                    "Leg 3: 25 cm away from the wall"),
    ("turn",  -TURN_AWAY_SIGN * 90,    "Leg 4: turn 90 deg back to original heading"),
    ("drive", 0.50,                    "Leg 5: 50 cm parallel to wall (now offset)"),
    ("turn",  -TURN_AWAY_SIGN * 90,    "Leg 6: turn 90 deg TOWARD the wall"),
    ("drive", 0.25,                    "Leg 7: 25 cm toward wall, rejoining original line"),
    ("turn",  TURN_AWAY_SIGN * 90,     "Leg 8: turn 90 deg back to original heading"),
    ("drive", 1.00,                    "Leg 9: 100 cm continuing straight"),
]

if __name__ == "__main__":
    for kind, value, label in LEGS:
        print(label)
        input("  Press Enter to run this leg...")
        if kind == "drive":
            drive_m(value)
        else:
            turn_deg(value)
        time.sleep(SETTLE)
    print("Done. Check heading with the compass app: back to your starting heading?")