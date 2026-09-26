import sys
from move_robot import turn_by_rate

RATE = 0.5  # same turn rate as the first test

if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 3.14
    print("Turning at rate", RATE, "for", duration, "seconds")
    turn_by_rate(RATE, duration)
    print("Done. Do not touch the robot yet, measure first.")