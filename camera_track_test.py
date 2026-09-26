import time
from move_robot import turn_by_rate, move_camera
from capture import capture_photo

DEG_PER_SEC = 11.4
TURN_RATE = 0.5
SETTLE = 5.0
BASE_TILT = -7
BASE_PAN = -90

TEST_TURN_DEG = -30

def turn_deg(angle):
    duration = abs(angle) / DEG_PER_SEC
    rate = TURN_RATE if angle > 0 else -TURN_RATE
    turn_by_rate(rate, duration)
    return angle

if __name__ == "__main__":
    move_camera(BASE_PAN, BASE_TILT)
    time.sleep(1.5)
    capture_photo("track_test_before")
    print("Photo taken before turn.")

    input("Press Enter to turn %d degrees..." % TEST_TURN_DEG)
    cumulative_turn = turn_deg(TEST_TURN_DEG)
    time.sleep(SETTLE)

    pan_guess = max(-90, min(90, BASE_PAN - cumulative_turn))
    move_camera(pan_guess, BASE_TILT)
    time.sleep(1.5)
    capture_photo("track_test_after")
    print("Turned %d deg, tried pan %.0f deg." % (cumulative_turn, pan_guess))