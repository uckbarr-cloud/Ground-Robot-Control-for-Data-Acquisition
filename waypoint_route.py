import csv
import os
import time
import json
from move_robot import move_forward, stop, turn_by_rate, move_camera, get_status
from capture import capture_photo
from self_check import is_blurry, verified_matches, MIN_VERIFIED_MATCHES

FORWARD_SPEED = 0.3
DEG_PER_SEC = 11.4
TURN_RATE = 0.5

SETTLE = 7.0
CAMERA_SETTLE = 1.2

BASE_TILT = -7
TILT_VARIANTS = [-15, 10]   # alternate between these by waypoint
PAN_ANGLES = [-90, -70, -50]       # left, center, right at every stop
EXTRA_TILT_WAYPOINTS = set()
EXTRA_TILT = 12

CEILING_ENABLED = True     # set False if the tilt hardware can't reach this angle
CEILING_TILT = -55         # steep upward tilt - unconfirmed hardware limit, test carefully

MIN_BATTERY_V = 10.3                 # stop cleanly before the low-battery line

MAX_RESHOOT_ATTEMPTS = 3             # initial fill + up to 2 escalating retries

OVERLAP_LOG_FILE = "overlap_log.csv"
UNRESOLVED_PREFIX = "UNRESOLVED_"    # tag applied to a waypoint's photos if escalation never resolved

# Fill this in on-site from the actual room/wall you're using.
ROUTE = [
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
    {"forward_m": 0.3, "turn_deg": 0},
]

RUN_ID = time.strftime("%Y%m%d_%H%M%S")
cumulative_turn = 0.0                # tracks how far the CHASSIS has turned


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
    """Renames a waypoint's photo files in place, prefixing each with
    UNRESOLVED_, so they stand out in the photos folder and don't get fed
    into photogrammetry by accident without a second look."""
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
        return v >= MIN_BATTERY_V, v
    except Exception:
        return True, None            # don't block the run over one bad reading


def drive_forward_m(distance_m):
    """distance_m can be negative to back up (used by the self-check fill-in)."""
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
    """Extra upward-facing shot(s) at this waypoint, for the underpass
    ceiling/soffit. Uses the same RGB camera - no new hardware required.
    Only the pan center angle is used (0), since the ceiling doesn't need
    the left/right sweep the wall does."""
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
    """Returns (straight_ahead_path, all_paths) - callers that only care
    about the overlap-check photo use the first value; callers that may
    need to tag every file for this waypoint (e.g. on unresolved escalation)
    use the second."""
    tilt = TILT_VARIANTS[wp_index % len(TILT_VARIANTS)]
    paths = shoot_pass(wp_index, tilt, "base")
    if wp_index in EXTRA_TILT_WAYPOINTS:
        shoot_pass(wp_index, EXTRA_TILT, "high")
    ceiling_pass(wp_index)
    move_camera(0, 0)
    return paths[1], paths  # paths[1] is the straight-ahead (pan=0) shot


def check_overlap_and_fill(prev_photo, wp_index, leg_m):
    """
    Checks overlap against the previous waypoint. If it's too low, backs up,
    fills the gap, and re-shoots. Then RE-CHECKS the reshoot against the same
    reference photo, rather than trusting it blindly. If the fix didn't work,
    tries again with a larger back-up distance, up to MAX_RESHOOT_ATTEMPTS
    total attempts. If it still hasn't fixed itself after that, this
    waypoint's photo files are renamed with an UNRESOLVED_ prefix so they
    stand out in the photos folder before you ever open Metashape, and the
    run continues rather than halting over one bad waypoint.

    Returns the straight-ahead photo path to use going forward as "the real
    photo at this waypoint" (renamed if unresolved), or None if no fill was
    ever triggered, meaning the caller should keep using its original photo.
    """
    matches = verified_matches(prev_photo, capture_photo("check_%s_wp%02d" % (RUN_ID, wp_index)))
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
        fixed_photo = check_overlap_and_fill(last_photo, i, leg["forward_m"])
        last_photo = fixed_photo if fixed_photo is not None else this_photo

    print("Done.")