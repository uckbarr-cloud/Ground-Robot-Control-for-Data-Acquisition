"""
bypass_route.py
Bypass-and-rejoin maneuver with camera tracking, photo capture, blur retry,
and overlap-check-and-fill. Distances are still halved (kitchen-scale) -
double them back to the full route once confirmed on the corridor.

Turn timing (NEG_DEG_PER_SEC / POS_DEG_PER_SEC) and REVERSE_TRIM (in
move_robot.py) are KITCHEN FLOOR placeholders. Re-run turn_calibration_test.py
and reverse_trim_test.py on the corridor first, then update the numbers below
before trusting this on real data.
"""
import csv
import os
import time
from move_robot import move_forward, stop, turn_by_rate, move_camera
from capture import capture_photo
from self_check import is_blurry, verified_matches, MIN_VERIFIED_MATCHES

FORWARD_SPEED = 0.3
TURN_RATE = 0.5
SETTLE = 5.0
CAMERA_SETTLE = 1.2

BASE_TILT = -7
BASE_PAN = -90          # wall is 90 deg to the left at the start heading
PAN_ANGLES_OFFSET = [0, -20]   # extra angles around BASE_PAN at each stop, if you want more than one shot

TURN_AWAY_SIGN = -1     # confirmed last night

# --- KITCHEN FLOOR PLACEHOLDERS - replace after corridor calibration ---
NEG_DEG_PER_SEC = 11.4
POS_DEG_PER_SEC = 11.4
# -------------------------------------------------------------------

RUN_ID = time.strftime("%Y%m%d_%H%M%S")
OVERLAP_LOG_FILE = "overlap_log.csv"
cumulative_turn = 0.0


def log_overlap_check(wp_label, leg_m, matches, fill_triggered, pan_status):
    new_file = not os.path.exists(OVERLAP_LOG_FILE)
    with open(OVERLAP_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["run_id", "waypoint", "leg_m", "verified_matches",
                             "threshold", "fill_triggered", "pan_status", "timestamp"])
        writer.writerow([RUN_ID, wp_label, leg_m, matches, MIN_VERIFIED_MATCHES,
                         fill_triggered, pan_status, time.strftime("%Y-%m-%d %H:%M:%S")])


def drive_m(distance_m):
    duration = abs(distance_m) / FORWARD_SPEED
    speed = FORWARD_SPEED if distance_m >= 0 else -FORWARD_SPEED
    try:
        move_forward(speed)
        time.sleep(duration)
    finally:
        stop()


def turn_deg(angle_deg):
    global cumulative_turn
    if angle_deg == 0:
        return
    deg_per_sec = POS_DEG_PER_SEC if angle_deg > 0 else NEG_DEG_PER_SEC
    duration = abs(angle_deg) / deg_per_sec
    rate = TURN_RATE if angle_deg > 0 else -TURN_RATE
    turn_by_rate(rate, duration)
    cumulative_turn += angle_deg


def pan_for_wall():
    """Returns the pan angle needed to face the wall given the current
    cumulative turn, or None if the wall is out of the camera's reach."""
    needed = BASE_PAN - cumulative_turn
    if -90 <= needed <= 90:
        return needed
    return None


def shoot_at_current_position(wp_label):
    """Takes photos if the wall is reachable from the current heading.
    Returns the straight-on photo path, or None if no photo was possible."""
    pan = pan_for_wall()
    if pan is None:
        print("  %s: wall out of camera range (needed pan out of -90..90), skipping photo" % wp_label)
        return None

    paths = []
    for offset in PAN_ANGLES_OFFSET:
        this_pan = max(-90, min(90, pan + offset))
        move_camera(this_pan, BASE_TILT)
        time.sleep(CAMERA_SETTLE)
        name = "%s_%s_p%d" % (wp_label, RUN_ID, offset)

        for attempt in range(3):
            path = capture_photo(name)
            blurry, score = is_blurry(path)
            if not blurry:
                break
            print("  blurry (score %.0f), retaking..." % score)
            time.sleep(1.0)
        else:
            print("  still blurry after 3 tries, keeping it anyway")

        print("  photo", name, path)
        paths.append(path)
    move_camera(0, 0)
    return paths[0]  # primary (offset 0) shot, used for overlap checks


def check_overlap_and_fill(prev_photo, wp_label, leg_m):
    if prev_photo is None:
        return None  # nothing to compare against (e.g. after a no-photo leg)

    this_photo = shoot_at_current_position(wp_label + "_check")
    if this_photo is None:
        return None

    matches = verified_matches(prev_photo, this_photo)
    print("  overlap check at %s: %d verified matches" % (wp_label, matches))
    fill_triggered = matches < MIN_VERIFIED_MATCHES
    log_overlap_check(wp_label, leg_m, matches, fill_triggered, "ok")

    if not fill_triggered:
        return this_photo

    print("  LOW OVERLAP - backing up to fill the gap")
    drive_m(-leg_m / 2)
    time.sleep(SETTLE)
    shoot_at_current_position(wp_label + "_fill")
    drive_m(leg_m / 2)
    time.sleep(SETTLE)
    print("  re-shooting %s at its real position" % wp_label)
    return shoot_at_current_position(wp_label + "_reshoot")


# Route: (kind, value, label). "drive_photo"=drive then attempt photo/check.
# "drive_only"=drive with no photo attempt (out-of-range leg). "turn"=pivot.
ROUTE = [
    ("drive_photo", 0.50, "wp1"),
    ("turn",  TURN_AWAY_SIGN * 90,  None),
    ("drive_only", 0.25, None),
    ("turn",  -TURN_AWAY_SIGN * 90, None),
    ("drive_photo", 0.50, "wp2"),
    ("turn",  -TURN_AWAY_SIGN * 90, None),
    ("drive_photo", 0.25, "wp3"),
    ("turn",  TURN_AWAY_SIGN * 90,  None),
    ("drive_photo", 1.00, "wp4"),
]

if __name__ == "__main__":
    print("Starting run", RUN_ID)
    last_photo = shoot_at_current_position("wp0")

    for kind, value, label in ROUTE:
        if kind == "turn":
            print("Turning %d deg" % value)
            turn_deg(value)
            time.sleep(SETTLE)
        elif kind == "drive_only":
            print("Driving %.2f m (no photo expected)" % value)
            drive_m(value)
            time.sleep(SETTLE)
        elif kind == "drive_photo":
            print("Driving %.2f m to %s" % (value, label))
            drive_m(value)
            time.sleep(SETTLE)
            new_photo = check_overlap_and_fill(last_photo, label, value)
            if new_photo is not None:
                last_photo = new_photo

    print("Done.")