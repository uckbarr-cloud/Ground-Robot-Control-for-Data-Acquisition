import time
from move_robot import move_forward, stop, move_camera
from capture import capture_photo

SPEED = 0.3        # m/s, as in your earlier tests
STEP_TIME = 0.8    # seconds per step, roughly 20 cm
SETTLE = 1.5       # seconds for the robot to stop shaking before each photo
N_PHOTOS = 10
PAN = 90           # camera turns 90 degrees to the right; use -90 for the left

TILT = -7          # degrees; negative tilts the camera down


def drive_for(speed, duration):
    try:
        move_forward(speed)
        time.sleep(duration)
    finally:
        stop()   # always sent, even if something fails


import time as _time

if __name__ == "__main__":
    run_id = _time.strftime("%Y%m%d_%H%M%S")
    move_camera(PAN, TILT)
    time.sleep(2)   # give the camera time to turn
    for i in range(N_PHOTOS):
        time.sleep(SETTLE)
        print("Photo", i, capture_photo("route_%s_%02d" % (run_id, i)))
        if i < N_PHOTOS - 1:
            drive_for(SPEED, STEP_TIME)
    move_camera(0, 0)
    print("Done.")