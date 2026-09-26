import time
from move_robot import get_status

print("Rotate the robot by hand, slowly, left and right.")
print("Watch for any value below that changes as you turn it.")
print("Ctrl+C to stop.\n")

try:
    while True:
        print(get_status())
        time.sleep(0.5)
except KeyboardInterrupt:
    print("\nStopped.")