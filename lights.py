import sys
from move_robot import send_command

if __name__ == "__main__":
    io4 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    io5 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    print(send_command('{"T":132,"IO4":%d,"IO5":%d}' % (io4, io5)))