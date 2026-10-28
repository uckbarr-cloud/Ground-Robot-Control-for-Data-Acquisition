"""
waypoint_route.py - the inspection route.

The robot drives along the wall in short legs. At every waypoint it takes three
photos of the wall (three pan angles), checks that the middle photo overlaps
enough with the previous waypoint, and if not, backs up and re-shoots.
Every overlap check is written to overlap_log.csv.

Normally started through run_inspection.py, which also writes the report.
"""
import csv
import os
import time
import json
from move_robot import move_forward, stop, turn_by_rate, move_camera, get_status
from capture import capture_photo
from self_check import is_blurry, verified_matches, MIN_VERIFIED_MATCHES

FORWARD_SPEED = 0.3
DEG_PER_SEC = 11.4         # measured turn rate at TURN_RATE
TURN_RATE = 0.5

SETTLE = 7.0               # seconds to wait after driving, so the robot is still for the photos
CAMERA_SETTLE = 1.2        # seconds to wait after moving the camera

BASE_TILT = -7             # tilt for the fill-in photos taken while backed up
TILT_VARIANTS = [-5, 10]   # alternate between these by waypoint
PAN_ANGLES = [-90, -70, -50]   # wall on the left: square-on, then two angles looking along the wall
EXTRA_TILT_WAYPOINTS = set()
EXTRA_TILT = 12

CEILING_ENABLED = False    # extra upward photo of the soffit at each waypoint
CEILING_TILT = 85          # positive is up; +90 is straight up, -30 is the down limit

MIN_BATTERY_V = 10.3       # end the run cleanly before the battery gets too low

MAX_RESHOOT_ATTEMPTS = 3   # back up 0.1, 0.2 and then 0.3 m

OVERLAP_LOG_FILE = "overlap_log.csv"
UNRESOLVED_PREFIX = "UNRESOLVED_"    # added to a waypoint's photos if the overlap could not be fixed

# 25 legs of 0.2 m = 5.0 m of wall. Short legs keep the overlap between
# neighbouring waypoints high; change the count to match the wall length.
ROUTE = [{"forward_m": 0.2, "turn_deg": 0} for _ in range(25)]

RUN_ID = time.strftime("%Y%m%d_%H%M%S")
cumulative_turn = 0.0                # how far the robot body has turned in total


def log_overlap_check(wp_index, leg_m, matches, fill_triggered, attempt=0,
                       recheck_matches=None, fix_confirmed=None, escalated=False):
    new_file = not os.path.exists(OVERLAP_LOG_FILE)
    with open(OVERLAP_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["run_id", "waypoint", "leg_m", "verified_matches",
                             "threshold", "fill_triggered", "attempt",
                             "recheck_matches", "fix_confirmed", "escalated",
                             "timestamp"])
        writer.writerow([RUN_ID, wp_index, leg_m, matches, MIN_VERIFIED_MATCHES,
                         fill_triggered, attempt, recheck_matches, fix_confirmed,
                         escalated, time.strftime("%Y-%m-%d %H:%M:%S")])


def tag_files_unresolved(paths):
    """Renames a waypoint's photo files with the UNRESOLVED_ prefix, so they
    stand out in the photos folder and are checked before photogrammetry."""
    tagged = []
    for path in paths:
        directory, filename = os.path.split(path)
        if filename.startswith(UNRESOLVED_PREFIX):
            tagged.append(path)
            continue
        new_path = os.path.join(directory, UNRESOLVED_PREFIX + filename)
        try:
            os.rename(path, new_path)
            tagged.append(new_path)
        except OSError as e:
            print("  WARNING: could not tag file %s (%s)" % (path, e))
            tagged.append(path)
    return tagged


def battery_ok():
    try:
        s = json.loads(get_status())
        v = s.get("v", 0) / 100.0
        if v < 5.0:                  # implausible while the robot is running; treat as a bad read
            return True, None
        return v >= MIN_BATTERY_V, v
    except Exception:
        return True, None            # don't block the run over one bad reading


def drive_forward_m(distance_m):
    """Drives a distance in metres, timed from the speed. A negative distance backs up."""
    duration = abs(distance_m) / FORWARD_SPEED
    speed = FORWARD_SPEED if distance_m >= 0 else -FORWARD_SPEED
    try:
        move_forward(speed)
        time.sleep(duration)
    finally:
        stop()


def turn_deg(angle):
    global cumulative_turn
    if angle == 0:
        return
    duration = abs(angle) / DEG_PER_SEC
    rate = TURN_RATE if angle > 0 else -TURN_RATE
    turn_by_rate(rate, duration)
    cumulative_turn += angle


def wall_facing_pan(base_pan):
    return max(-90, min(90, base_pan))


def shoot_pass(wp_index, tilt, pass_label):
    paths = []
    for a_index, pan in enumerate(PAN_ANGLES):
        move_camera(wall_facing_pan(pan), tilt)
        time.sleep(CAMERA_SETTLE)
        name = "wp%02d_%s_%s_a%02d" % (wp_index, RUN_ID, pass_label, a_index)

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
    return paths


def ceiling_pass(wp_index):
    """Extra upward photo of the soffit at this waypoint (camera pan 0)."""
    if not CEILING_ENABLED:
        return
    print("  ceiling pass at waypoint %d" % wp_index)
    move_camera(0, CEILING_TILT)
    time.sleep(CAMERA_SETTLE)
    name = "wp%02d_%s_ceiling" % (wp_index, RUN_ID)
    path = capture_photo(name)
    print("  photo", name, path)
    move_camera(0, 0)


def capture_at_waypoint(wp_index):
    """Takes the photos at one waypoint. Returns (middle photo, all photos):
    the middle photo (pan -70) is used for the overlap check."""
    tilt = TILT_VARIANTS[wp_index % len(TILT_VARIANTS)]
    paths = shoot_pass(wp_index, tilt, "base")
    if wp_index in EXTRA_TILT_WAYPOINTS:
        shoot_pass(wp_index, EXTRA_TILT, "high")
    ceiling_pass(wp_index)
    move_camera(0, 0)
    return paths[1], paths  # paths[1] is the middle wall shot (pan -70)


def check_overlap_and_fill(prev_photo, this_photo, wp_index, leg_m):
    """
    The self-check. Compares this waypoint's middle photo with the previous one.
    If there are too few verified matches, the robot backs up, takes fill-in
    photos, comes back and re-shoots, then checks again against the same
    previous photo. Each attempt backs up further (0.1, 0.2, 0.3 m). If the
    overlap is still too low after MAX_RESHOOT_ATTEMPTS, the photos are tagged
    UNRESOLVED_ and the run continues.

    Returns the new middle photo if a re-shoot happened, otherwise None.
    """
    matches = verified_matches(prev_photo, this_photo)
    print("  overlap check: %d verified matches" % matches)

    fill_triggered = matches < MIN_VERIFIED_MATCHES

    if not fill_triggered:
        log_overlap_check(wp_index, leg_m, matches, fill_triggered)
        return None  # caller keeps using the original base photo, nothing changed

    current_photo = None
    current_all_paths = None
    fix_confirmed = False
    recheck_matches = None

    for attempt in range(1, MAX_RESHOOT_ATTEMPTS + 1):
        backup_distance = (leg_m / 2) * attempt  # escalate the correction each retry
        print("  LOW OVERLAP (attempt %d/%d) - backing up %.2fm to fill the gap" %
              (attempt, MAX_RESHOOT_ATTEMPTS, backup_distance))
        drive_forward_m(-backup_distance)
        time.sleep(SETTLE)
        shoot_pass(wp_index, BASE_TILT, "fill_a%d" % attempt)
        drive_forward_m(backup_distance)
        time.sleep(SETTLE)

        print("  re-shooting waypoint %d (attempt %d)" % (wp_index, attempt))
        current_photo, current_all_paths = capture_at_waypoint(wp_index)

        recheck_matches = verified_matches(prev_photo, current_photo)
        fix_confirmed = recheck_matches >= MIN_VERIFIED_MATCHES
        print("  post-reshoot check: %d verified matches (%s)" %
              (recheck_matches, "FIXED" if fix_confirmed else "still low"))

        escalated = (attempt == MAX_RESHOOT_ATTEMPTS and not fix_confirmed)
        log_overlap_check(wp_index, leg_m, matches, fill_triggered, attempt,
                           recheck_matches, fix_confirmed, escalated)

        if fix_confirmed:
            break

    if not fix_confirmed:
        print("  *** WAYPOINT %d UNRESOLVED after %d attempts - tagging files, continuing route ***" %
              (wp_index, MAX_RESHOOT_ATTEMPTS))
        tagged_paths = tag_files_unresolved(current_all_paths)
        current_photo = tagged_paths[1]

    return current_photo


if __name__ == "__main__":
    ok, v = battery_ok()
    print("Battery: %.2f V" % v if v else "Battery: unknown")

    print("Waypoint 0")
    time.sleep(SETTLE)
    last_photo, _ = capture_at_waypoint(0)

    for i, leg in enumerate(ROUTE, start=1):
        ok, v = battery_ok()
        if not ok:
            print("Battery low (%.2f V) - stopping run cleanly before waypoint %d" % (v, i))
            break

        print("Driving %.2f m" % leg["forward_m"])
        drive_forward_m(leg["forward_m"])
        time.sleep(SETTLE)
        if leg["turn_deg"]:
            print("Turning %d deg" % leg["turn_deg"])
            turn_deg(leg["turn_deg"])
            time.sleep(SETTLE)

        print("Waypoint", i)
        this_photo, _ = capture_at_waypoint(i)
        fixed_photo = check_overlap_and_fill(last_photo, this_photo, i, leg["forward_m"])
        last_photo = fixed_photo if fixed_photo is not None else this_photo

    print("Done.")