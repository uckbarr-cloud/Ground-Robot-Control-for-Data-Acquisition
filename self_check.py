import cv2
import numpy as np

_sift = cv2.SIFT_create(3000)
_bf = cv2.BFMatcher()

# Both tuned from tonight's kitchen photos (30-140 matches between good
# neighbors). Recalibrate on the real site before trusting the numbers,
# see the calibration check in waypoint_route.py.
BLUR_THRESHOLD = 25.0
MIN_VERIFIED_MATCHES = 25


def is_blurry(photo_path):
    img = cv2.imread(str(photo_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    score = cv2.Laplacian(gray, cv2.CV_64F).var()
    return score < BLUR_THRESHOLD, score


def verified_matches(photo_path_a, photo_path_b):
    img_a = cv2.imread(str(photo_path_a))
    img_b = cv2.imread(str(photo_path_b))
    gray_a = cv2.createCLAHE(2.0, (8, 8)).apply(cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY))
    gray_b = cv2.createCLAHE(2.0, (8, 8)).apply(cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY))
    k1, d1 = _sift.detectAndCompute(gray_a, None)
    k2, d2 = _sift.detectAndCompute(gray_b, None)
    if d1 is None or d2 is None:
        return 0
    matches = _bf.knnMatch(d1, d2, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    if len(good) < 12:
        return len(good)
    p1 = np.float32([k1[m.queryIdx].pt for m in good])
    p2 = np.float32([k2[m.trainIdx].pt for m in good])
    _, mask = cv2.findFundamentalMat(p1, p2, cv2.FM_RANSAC, 2.0, 0.99)
    return int(mask.sum()) if mask is not None else 0