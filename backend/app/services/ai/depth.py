"""Coarse monocular distance bands for detected objects.

A single camera frame has no depth channel. These estimates combine two rough
geometric cues: the typical real-world height of the detected class and the
ground-plane projection of the box's lower edge for an assumed, roughly level,
chest-height phone camera. Results are always spoken as wide bands, never as
precise measurements, and are omitted when the geometry is implausible.
"""
import math
from typing import Literal

from app.core.config import settings

_MIN_METERS = 0.2
_MAX_METERS = 30.0

# Typical heights in metres for the prepared detector's classes. These are
# population averages, so a band is the most that can be said from one frame.
_REAL_HEIGHTS = {
    "person": 1.7, "bicycle": 1.0, "car": 1.5, "motorcycle": 1.1,
    "bus": 3.0, "truck": 3.0, "traffic light": 0.9, "fire hydrant": 0.8,
    "stop sign": 0.75, "parking meter": 1.3, "bench": 0.85,
    "cat": 0.3, "dog": 0.5, "horse": 1.6, "sheep": 0.9, "cow": 1.4,
    "backpack": 0.45, "umbrella": 0.9, "handbag": 0.3, "suitcase": 0.65,
    "chair": 0.9, "couch": 0.85, "potted plant": 0.7, "bed": 0.6,
    "dining table": 0.75, "toilet": 0.75, "tv": 0.6, "laptop": 0.25,
    "microwave": 0.3, "oven": 0.9, "refrigerator": 1.8, "sink": 0.85,
    "bottle": 0.25, "wine glass": 0.2, "cup": 0.1, "bowl": 0.1,
    "book": 0.24, "clock": 0.3, "vase": 0.3, "teddy bear": 0.4,
}

BANDS = (
    "under_1m", "about_1m", "about_2m", "about_3m",
    "about_5m", "about_8m", "about_10m", "over_10m",
)
ObjectDistance = Literal[
    "under_1m", "about_1m", "about_2m", "about_3m",
    "about_5m", "about_8m", "about_10m", "over_10m",
]

# Upper metre bound for each band except the open-ended over_10m band.
_LIMITS = (1.0, 1.5, 2.5, 4.0, 6.5, 9.0, 13.0)

_PHRASES = {
    "en": {
        "under_1m": ("less than a meter in front of you", "less than a meter away"),
        "about_1m": ("about 1 meter in front of you", "about 1 meter away"),
        "about_2m": ("about 2 meters in front of you", "about 2 meters away"),
        "about_3m": ("about 3 meters in front of you", "about 3 meters away"),
        "about_5m": ("about 5 meters in front of you", "about 5 meters away"),
        "about_8m": ("about 8 meters in front of you", "about 8 meters away"),
        "about_10m": ("about 10 meters in front of you", "about 10 meters away"),
        "over_10m": ("more than 10 meters ahead of you", "more than 10 meters away"),
    },
    "fr": {
        "under_1m": ("à moins d’un mètre devant vous", "à moins d’un mètre"),
        "about_1m": ("à environ 1 mètre devant vous", "à environ 1 mètre"),
        "about_2m": ("à environ 2 mètres devant vous", "à environ 2 mètres"),
        "about_3m": ("à environ 3 mètres devant vous", "à environ 3 mètres"),
        "about_5m": ("à environ 5 mètres devant vous", "à environ 5 mètres"),
        "about_8m": ("à environ 8 mètres devant vous", "à environ 8 mètres"),
        "about_10m": ("à environ 10 mètres devant vous", "à environ 10 mètres"),
        "over_10m": ("à plus de 10 mètres devant vous", "à plus de 10 mètres"),
    },
    "ar": {
        "under_1m": ("على مسافة أقل من متر أمامك", "على مسافة أقل من متر"),
        "about_1m": ("على بعد نحو متر أمامك", "على بعد نحو متر"),
        "about_2m": ("على بعد نحو مترين أمامك", "على بعد نحو مترين"),
        "about_3m": ("على بعد نحو 3 أمتار أمامك", "على بعد نحو 3 أمتار"),
        "about_5m": ("على بعد نحو 5 أمتار أمامك", "على بعد نحو 5 أمتار"),
        "about_8m": ("على بعد نحو 8 أمتار أمامك", "على بعد نحو 8 أمتار"),
        "about_10m": ("على بعد نحو 10 أمتار أمامك", "على بعد نحو 10 أمتار"),
        "over_10m": ("على بعد أكثر من 10 أمتار أمامك", "على بعد أكثر من 10 أمتار"),
    },
}


def _focal(height):
    return (height / 2) / math.tan(math.radians(settings.depth_vertical_fov_degrees) / 2)


def _size_cue(label, box_height, height):
    real = _REAL_HEIGHTS.get(label)
    if real is None or box_height <= 0 or height <= 0:
        return None
    return _focal(height) * real / box_height


def _ground_cue(y2, height):
    below = y2 - height / 2
    if height <= 0 or below < 0.04 * height:
        # The lower edge is at or above the assumed horizon: no ground contact.
        return None
    return _focal(height) * settings.depth_camera_height_meters / below


def metres(label, box, width, height):
    """Approximate forward distance for one detection, or None."""
    if not settings.depth_estimation_enabled:
        return None
    try:
        x1, y1, x2, y2 = (float(value) for value in box)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        return None
    if width <= 0 or height <= 0 or x2 <= x1 or y2 <= y1:
        return None
    cues = [cue for cue in (_size_cue(label, y2 - y1, height), _ground_cue(y2, height)) if cue]
    if not cues:
        return None
    if len(cues) == 2 and max(cues) / min(cues) > 2.5:
        # Size and ground cues disagree (partial box, tilted camera, unusual
        # object): prefer the closer reading rather than overstate clearance.
        distance = min(cues)
    elif len(cues) == 2:
        distance = math.sqrt(cues[0] * cues[1])
    else:
        distance = cues[0]
    return distance if _MIN_METERS <= distance <= _MAX_METERS else None


def band(label, box, width, height):
    distance = metres(label, box, width, height)
    if distance is None:
        return None
    for limit, name in zip(_LIMITS, BANDS):
        if distance <= limit:
            return name
    return BANDS[-1]


def text(name, language, *, short=False):
    """Localized phrase for a band name; empty string when no band is known."""
    if name not in BANDS:
        return ""
    return _PHRASES[language][name][1 if short else 0]


def phrase(label, box, width, height, language, *, short=False):
    return text(band(label, box, width, height), language, short=short)
