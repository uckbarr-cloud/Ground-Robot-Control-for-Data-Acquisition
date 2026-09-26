import time
from move_robot import move_forward, stop
from capture import capture_photo

SPEED = 0.3      # m/s, same as your accuracy test
DURATION = 2.0   # seconds, about 60 cm
SETTLE = 1.5     # seconds for the robot to stop shaking before the photo


def drive_for(speed, duration):
    try:
        move_forward(speed)
        time.sleep(duration)
    finally:
        stop()   # always runs, even if something fails or you press Ctrl+C


if __name__ == "__main__":
    print("Photo at start:", capture_photo("wp0_start"))
    print("Driving...")
    drive_for(SPEED, DURATION)
    time.sleep(SETTLE)
    print("Photo at end:", capture_photo("wp1_end"))
    print("Done. Measure how far the robot moved.")
    