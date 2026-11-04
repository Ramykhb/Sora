"""Face detection and irreversible blur for retained images (no recognition)."""
from functools import lru_cache
from math import ceil, floor
from pathlib import Path
import threading

import cv2
import numpy as np

from app.core.errors import BackendError

PRIVACY_VERSION = "face_privacy_v1"
_lock = threading.Lock()


@lru_cache(maxsize=1)
def face_detector():
    path = Path(__file__).with_name("assets") / "face_detection_yunet_2023mar.onnx"
    return cv2.FaceDetectorYN.create(str(path), "", (320, 320), 0.65, 0.3, 5000)


def face_regions(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return padded, clipped boxes; scan all orientations, including sideways faces."""
    height, width = image.shape[:2]
    scale = min(1.0, 1280 / max(height, width))
    small = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))))
    # Exact axis ratios also handle rounding when a small image is resized.
    sh, sw = small.shape[:2]
    regions = []
    try:
        # YuNet mutates its input dimensions; serialize access across ingestion threads.
        with _lock:
            detector = face_detector()
            for rotation in range(4):
                rotated = np.ascontiguousarray(np.rot90(small, rotation))
                rh, rw = rotated.shape[:2]
                detector.setInputSize((rw, rh))
                _, faces = detector.detect(rotated)
                if faces is None:
                    continue
                for face in faces:
                    x, y, w, h = map(float, face[:4])
                    # Map the four bounding-box corners back to the upright image.
                    points = np.array([[x, y], [x + w, y], [x, y + h], [x + w, y + h]])
                    for _ in range(rotation):
                        points = np.column_stack((rh - points[:, 1], points[:, 0]))
                        rw, rh = rh, rw
                    # Reset dimensions for the next face in this rotation.
                    rh, rw = rotated.shape[:2]
                    points *= [width / sw, height / sh]
                    left, top = points.min(axis=0)
                    right, bottom = points.max(axis=0)
                    pad_x, pad_y = (right - left) * 0.25, (bottom - top) * 0.35
                    box = (max(0, floor(left - pad_x)), max(0, floor(top - pad_y)),
                           min(width, ceil(right + pad_x)), min(height, ceil(bottom + pad_y)))
                    if box[2] > box[0] and box[3] > box[1]:
                        regions.append(box)
    except Exception as exc:
        # Never silently store the original when privacy processing is unavailable.
        raise BackendError("Face privacy processing unavailable; image was not saved", 503,
                           "face_privacy_unavailable") from exc
    return regions


def blur_regions(image: np.ndarray, regions: list[tuple[int, int, int, int]]) -> np.ndarray:
    result = image.copy()
    for left, top, right, bottom in regions:
        roi = result[top:bottom, left:right]
        h, w = roi.shape[:2]
        # Destroy fine facial detail before smoothing; even a large close-up face
        # is reduced to at most 8x8 samples. Padding includes the face boundary.
        tiny = cv2.resize(roi, (max(1, min(8, w // 16)), max(1, min(8, h // 16))),
                          interpolation=cv2.INTER_AREA)
        smooth = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_LINEAR)
        result[top:bottom, left:right] = cv2.GaussianBlur(smooth, (0, 0), max(3, min(w, h) / 8))
    return result
