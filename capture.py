"""
capture.py - takes one photo with the robot's camera and copies it to the Mac.

The camera is on the Raspberry Pi. The photo is taken there with ffmpeg over
SSH, copied to ./photos/ with scp, then deleted from the Pi.
Run on its own for a test photo:
    python3 capture.py
"""
import subprocess
from pathlib import Path

PI = "ugv@192.168.4.50"
PHOTO_DIR = Path(__file__).parent / "photos"

BRIGHTNESS = 0   # camera brightness (-64 to 64). The camera starts at 64, which over-exposes bright scenes.


def _ffmpeg_cmd(remote_path, mjpeg):
    fmt = "-input_format mjpeg " if mjpeg else ""
    return (
        "pkill -x ffmpeg >/dev/null 2>&1; sleep 0.3; "
        f"v4l2-ctl -d /dev/video0 --set-ctrl=brightness={BRIGHTNESS} >/dev/null 2>&1; "
        f"ffmpeg -y -loglevel error -f v4l2 {fmt}-video_size 1920x1080 "
        f"-i /dev/video0 -ss 1 -frames:v 1 -update 1 -q:v 2 {remote_path}"
    )


def capture_photo(name):
    """Takes one photo on the Pi, copies it to ./photos/<name>.jpg and returns the path.
    Tries MJPEG mode twice, then the camera's default mode."""
    PHOTO_DIR.mkdir(exist_ok=True)
    remote = f"/tmp/{name}.jpg"
    local = PHOTO_DIR / f"{name}.jpg"

    r = None
    for mjpeg in (True, True, False):
        try:
            r = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=10", PI, _ffmpeg_cmd(remote, mjpeg)],
                capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            print("  capture timed out (stalled SSH session), retrying...")
            continue
        if r.returncode == 0:
            print("Captured using", "MJPEG mode" if mjpeg else "default mode")
            break
    else:
        raise RuntimeError("Capture failed: " + (r.stderr if r else "no response (timed out)"))

    try:
        subprocess.run(["scp", "-q", f"{PI}:{remote}", str(local)], check=True, timeout=15)
        subprocess.run(["ssh", PI, f"rm {remote}"], check=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Copying the photo off the Pi stalled (timed out)")
    return local


if __name__ == "__main__":
    print("Saved:", capture_photo("test_capture"))
