"""
calib_capture.py - photos of a printed checkerboard for checking the camera lens.

The robot is placed by hand at five positions in front of the board. At each
position the camera takes 9 photos (3 pan x 3 tilt angles), 45 photos in total,
saved as photos/calib_*.jpg. These are meant for a lens calibration that is
independent of the photogrammetry software.
"""
import time
from capture import capture_photo
from move_robot import move_camera

PANS = [-25, 0, 25]
TILTS = [-12, 0, 12]
POSITIONS = [
    ("d35",  "35 cm from the wall, robot square to the sheet, board in the middle"),
    ("d25",  "25 cm from the wall, robot square to the sheet"),
    ("d45",  "45 cm from the wall, robot square to the sheet"),
    ("d35L", "35 cm away, robot turned about 30 degrees LEFT by hand"),
    ("d35R", "35 cm away, robot turned about 30 degrees RIGHT by hand"),
]

total = 0
for label, text in POSITIONS:
    input("\nPLACE: %s\nKeep the robot still, then press Enter... " % text)
    for tilt in TILTS:
        for pan in PANS:
            move_camera(pan, tilt)
            time.sleep(1.5)
            name = "calib_%s_pan%d_tilt%d" % (label, pan, tilt)
            capture_photo(name)
            total += 1
            print("  %d photos so far" % total)
    move_camera(0, 0)
print("\nDone,", total, "photos saved as photos/calib_*.jpg")
