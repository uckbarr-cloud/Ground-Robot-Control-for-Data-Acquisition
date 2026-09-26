import time
import requests

ROBOT_IP = "192.168.4.1"

def send_command(json_command, retries=3):
    url = "http://" + ROBOT_IP + "/js?json=" + json_command
    for attempt in range(retries):
        try:
            return requests.get(url, timeout=3).text
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(0.3)

TRIM = 0.0325          # forward, calibrated on corridor floor
REVERSE_TRIM = 0.01    # reverse, calibrated on kitchen floor tonight - re-check on corridor tomorrow

def move_forward(speed=0.3, trim=None):
    if trim is None:
        trim = TRIM if speed >= 0 else REVERSE_TRIM
    left = round(speed * (1 + trim), 4)
    right = round(speed * (1 - trim), 4)
    command = '{"T":1,"L":' + str(left) + ',"R":' + str(right) + '}'
    return send_command(command)

def stop():
    return send_command('{"T":1,"L":0,"R":0}')

def turn(angle_speed=0.3):
    command = '{"T":1,"L":' + str(-angle_speed) + ',"R":' + str(angle_speed) + '}'
    return send_command(command)

def get_status():
    return send_command('{"T":130}')

def turn_by_rate(z=0.35, duration=1.0):
    command = '{"T":13,"X":0,"Z":' + str(z) + '}'
    try:
        send_command(command)
        time.sleep(duration)
    finally:
        stop()

def move_camera(x=0, y=0):
    command = '{"T":133,"X":' + str(x) + ',"Y":' + str(y) + ',"SPD":0,"ACC":0}'
    return send_command(command)

def get_wifi_info():
    return send_command('{"T":405}')

if __name__ == "__main__":
    print(get_wifi_info())