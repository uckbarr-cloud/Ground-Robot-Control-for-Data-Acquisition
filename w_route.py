"""
w_route.py
Stretched-W path: straight legs with gentle turns between them, designed to
cover the FULL route length (target ~4m) rather than looping in place.
Camera correctly tracks the wall through turns (pan = BASE_PAN - cumulative_turn).
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
BASE_PAN = -90
DEG_PER_SEC = 11.4   # today's corridor-calibrated value, both directions

RUN_ID = time.strftime("%Y%m%d_%H%M%S")
OVERLAP_LOG_FILE = "overlap_log.csv"
cumulative_turn = 0.0


def log_overlap_check(wp_label, leg_m, matches, fill_triggered):
    new_file = not os.path.exists(OVERLAP_LOG_FILE)
    with open(OVERLAP_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["run_id", "waypoint", "leg_m", "verified_matches",
                             "threshold", "fill_triggered", "timestamp"])
        writer.writerow([RUN_ID, wp_label, leg_m, matches, MIN_VERIFIED_MATCHES,
                         fill_triggered, time.strftime("%Y-%m-%d %H:%M:%S")])


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
    duration = abs(angle_deg) / DEG_PER_SEC
    rate = TURN_RATE if angle_deg > 0 else -TURN_RATE
    turn_by_rate(rate, duration)
    cumulative_turn += angle_deg


def pan_for_wall():
    needed = BASE_PAN - cumulative_turn
    if -90 <= needed <= 90:
        return needed
    return None


def shoot(wp_label):
    pan = pan_for_wall()
    if pan is None:
        print("  %s: wall out of camera range, skipping photo" % wp_label)
        return None
    move_camera(pan, BASE_TILT)
    time.sleep(CAMERA_SETTLE)
    name = "%s_%s" % (wp_label, RUN_ID)
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
    return path


def check_and_fill(prev_photo, wp_label, leg_m):
    this_photo = shoot(wp_label + "_check")
    if this_photo is None or prev_photo is None:
        return this_photo
    matches = verified_matches(prev_photo, this_photo)
    print("  overlap check at %s: %d verified matches" % (wp_label, matches))
    fill_triggered = matches < MIN_VERIFIED_MATCHES
    log_overlap_check(wp_label, leg_m, matches, fill_triggered)
    if not fill_triggered:
        return this_photo
    print("  LOW OVERLAP - backing up to fill the gap")
    drive_m(-leg_m / 2)
    time.sleep(SETTLE)
    shoot(wp_label + "_fill")
    drive_m(leg_m / 2)
    time.sleep(SETTLE)
    return shoot(wp_label + "_reshoot")


# Gentle W: 5 legs of 0.8m = 4.0m total, turns of only 30/60 degrees, net zero
ROUTE = [
    ("drive", 0.8, "wp1"),
    ("turn",  30,  None),
    ("drive", 0.8, "wp2"),
    ("turn", -60,  None),
    ("drive", 0.8, "wp3"),
    ("turn",  60,  None),
    ("drive", 0.8, "wp4"),
    ("turn", -30,  None),
    ("drive", 0.8, "wp5"),
]

if __name__ == "__main__":
    print("Starting run", RUN_ID)
    last_photo = shoot("wp0")
    for kind, value, label in ROUTE:
        if kind == "turn":
            print("Turning %d deg" % value)
            turn_deg(value)
            time.sleep(SETTLE)
        else:
            print("Driving %.2f m to %s" % (value, label))
            drive_m(value)
            time.sleep(SETTLE)
            new_photo = check_and_fill(last_photo, label, value)
            if new_photo is not None:
                last_photo = new_photo
    print("Done.")