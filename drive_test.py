import sys
import time
from move_robot import send_command, stop

SPEED = 0.3
STEP_TIME = 0.8
N_STEPS = 9
PAUSE = 0.5


def drive_trimmed(speed, duration, k):
    left = round(speed * (1 + k), 3)
    right = round(speed * (1 - k), 3)
    try:
        send_command('{"T":1,"L":%s,"R":%s}' % (left, right))
        time.sleep(duration)
    finally:
        stop()


if __name__ == "__main__":
    k = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    print("trim k =", k)
    for i in range(N_STEPS):
        drive_trimmed(SPEED, STEP_TIME, k)
        time.sleep(PAUSE)
    print("Done. Measure how far to the side it ended up.")