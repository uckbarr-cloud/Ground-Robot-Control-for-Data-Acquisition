import subprocess
from pathlib import Path

PI = "ugv@192.168.4.50"
PHOTO_DIR = Path(__file__).parent / "photos"


def _ffmpeg_cmd(remote_path, mjpeg):
    fmt = "-input_format mjpeg " if mjpeg else ""
    return (
        f"ffmpeg -y -loglevel error -f v4l2 {fmt}-video_size 1920x1080 "
        f"-i /dev/video0 -ss 1 -frames:v 1 -update 1 -q:v 2 {remote_path}"
    )


def capture_photo(name):
    """Take one photo on the Pi, copy it to ./photos/<name>.jpg, return the path."""
    PHOTO_DIR.mkdir(exist_ok=True)
    remote = f"/tmp/{name}.jpg"
    local = PHOTO_DIR / f"{name}.jpg"

    for mjpeg in (True, False):
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", PI, _ffmpeg_cmd(remote, mjpeg)],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            print("Captured using", "MJPEG mode" if mjpeg else "default mode")
            break
    else:
        raise RuntimeError("Capture failed: " + r.stderr)

    subprocess.run(["scp", "-q", f"{PI}:{remote}", str(local)], check=True)
    subprocess.run(["ssh", PI, f"rm {remote}"], check=True)
    return local


if __name__ == "__main__":
    print("Saved:", capture_photo("test_capture"))