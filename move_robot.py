"""
move_robot.py - sends movement and camera commands to the UGV-01 robot.

The robot's ESP32 controller takes JSON commands over HTTP on its own Wi-Fi
hotspot. Run this file on its own to check the connection:
    python3 move_robot.py
"""
import time
import requests

ROBOT_IP = "192.168.4.1"

TRIM = 0.0325          # forward: left track slightly faster to drive straight (tested indoors and on site)
REVERSE_TRIM = 0.01    # reverse: tested on site
MAX_SPEED = 0.5        # safety limit; the route itself uses 0.3
MAX_TRIM = 0.2


def send_command(json_command, retries=3):
    url = "http://" + ROBOT_IP + "/js?json=" + json_command
    for attempt in range(retries):
        try:
            return requests.get(url, timeout=3).text
        except requests.exceptions.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(0.3)


def move_forward(speed=0.3, *, trim=None):
    """Starts driving and keeps driving until stop() is called. A negative speed
    drives backwards. trim must be given by name, e.g. move_forward(0.3, trim=0.03)."""
    if trim is None:
        trim = TRIM if speed >= 0 else REVERSE_TRIM
    if abs(speed) > MAX_SPEED:
        raise ValueError("speed %s is outside -%s to %s" % (speed, MAX_SPEED, MAX_SPEED))
    if abs(trim) > MAX_TRIM:
        raise ValueError("trim %s is outside -%s to %s" % (trim, MAX_TRIM, MAX_TRIM))
    left = round(speed * (1 + trim), 4)
    right = round(speed * (1 - trim), 4)
    command = '{"T":1,"L":' + str(left) + ',"R":' + str(right) + '}'
    return send_command(command)


def stop():
    return send_command('{"T":1,"L":0,"R":0}')


def drive_for(speed, seconds):
    """Drives for a fixed time, then always stops, even after an error or Ctrl+C.
    Example: python3 -c 'from move_robot import drive_for; drive_for(0.3, 2)'"""
    try:
        move_forward(speed)
        time.sleep(seconds)
    finally:
        stop()


def turn_by_rate(z=0.35, duration=1.0):
    """Turns on the spot at rate z for a fixed time, then stops."""
    command = '{"T":13,"X":0,"Z":' + str(z) + '}'
    try:
        send_command(command)
        time.sleep(duration)
    finally:
        stop()


def move_camera(x=0, y=0):
    """Points the pan-tilt camera: x = pan in degrees (negative is left), y = tilt (positive is up)."""
    command = '{"T":133,"X":' + str(x) + ',"Y":' + str(y) + ',"SPD":0,"ACC":0}'
    return send_command(command)


def get_status():
    """Returns the robot's status as JSON text, including the battery voltage."""
    return send_command('{"T":130}')


def get_wifi_info():
    return send_command('{"T":405}')


if __name__ == "__main__":
    print(get_wifi_info())
