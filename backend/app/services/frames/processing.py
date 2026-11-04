from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import threading
from time import perf_counter
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import open as open_image
import pytesseract
from app.core.config import settings
from app.core.errors import BackendError
from app.services.frames.privacy import PRIVACY_VERSION, blur_regions, face_regions


@dataclass
class PreparedImage:
    original: bytes
    processed: bytes
    image: np.ndarray
    width: int
    height: int
    sharpness: float
    brightness: float
    perceptual_hash: str
    enhancements: list[str]


@dataclass
class Analysis:
    ocr_text: str
    ocr_confidence: float
    objects: list[dict]


def jpeg(image):
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise BackendError("Could not encode image", 422, "invalid_image")
    return encoded.tobytes()


def prepare_image(content: bytes) -> PreparedImage:
    if not content or len(content) > settings.max_upload_mb * 1024 * 1024:
        raise BackendError("Image is empty or exceeds upload limit", 413, "upload_limit")
    try:
        # Bind Pillow's decoder before inference libraries patch Image.open with
        # optional format installers. Malformed uploads must never install code.
        with open_image(BytesIO(content), formats=("JPEG", "PNG", "WEBP")) as source:
            if source.width * source.height > settings.max_image_pixels:
                raise BackendError("Image exceeds pixel limit", 413, "pixel_limit")
            source = ImageOps.exif_transpose(source).convert("RGB")
            source.thumbnail((settings.max_image_side, settings.max_image_side))
            image = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BackendError(
            "Unreadable image; use JPEG, PNG, or WebP", 422, "invalid_image"
        ) from exc
    height, width = image.shape[:2]
    if min(width, height) < 32:
        raise BackendError("Image must be at least 32 by 32 pixels", 422, "invalid_image")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    small = cv2.resize(gray, (9, 8))
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    phash = f"{sum(int(bit) << index for index, bit in enumerate(bits)):016x}"
    enhanced = image.copy()
    steps = []
    if brightness < 100 or float(gray.std()) < 40:
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        light, a, b = cv2.split(lab)
        light = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(light)
        enhanced = cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)
        steps.append("clahe")
    if brightness < 60:
        enhanced = cv2.bilateralFilter(enhanced, 5, 20, 20)
        steps.append("denoise")
    if sharpness < 150:
        blur = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
        enhanced = cv2.addWeighted(enhanced, 1.35, blur, -0.35, 0)
        steps.append("unsharp_mask")
    # Detect on the decoded image, then redact AFTER enhancement so sharpening
    # cannot restore facial detail. Both saved variants and downstream AI/OCR
    # receive the redacted pixels; the raw source is never persisted.
    regions = face_regions(image)
    image = blur_regions(image, regions)
    enhanced = blur_regions(enhanced, regions)
    steps.append(PRIVACY_VERSION)
    if regions:
        steps.append("face_blur")
    return PreparedImage(
        jpeg(image), jpeg(enhanced), enhanced, width, height, sharpness, brightness, phash, steps
    )


_detector_lock = threading.Lock()


def vision_image(prepared: PreparedImage) -> bytes:
    height, width = prepared.image.shape[:2]
    side = settings.vision_image_max_side
    if max(width, height) <= side:
        return prepared.processed
    scale = side / max(width, height)
    resized = cv2.resize(
        prepared.image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return jpeg(resized)


@lru_cache
def detector():
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(settings.detector_threads)
    return YOLO(settings.yolo_model)


def warmup_detector():
    # Model weights are prepared explicitly; startup must not download anything.
    if Path(settings.yolo_model).is_file():
        with _detector_lock:
            detector().predict(
                np.zeros((640, 640, 3), dtype=np.uint8),
                conf=settings.yolo_confidence, device=settings.model_device, verbose=False,
                imgsz=settings.detection_image_size,
            )


def read_text(prepared: PreparedImage, languages: str | None = None) -> tuple[str, float]:
    started = perf_counter()
    rgb = cv2.cvtColor(prepared.image, cv2.COLOR_BGR2RGB)
    try:
        data = pytesseract.image_to_data(
            rgb,
            lang=languages or settings.ocr_languages,
            output_type=pytesseract.Output.DICT,
            timeout=25,
        )
        if not any(word.strip() for word in data["text"]):
            # Printed sign/table borders can make Tesseract treat the whole
            # region as a graphic. Remove only long straight rules on an OCR
            # copy; retain the stored image and original object observations.
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            height, width = gray.shape
            horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(64, width // 3)), np.uint8))
            vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(64, height // 3), 1), np.uint8))
            lines = cv2.bitwise_or(horizontal, vertical)
            if np.any(lines):
                clean = cv2.bitwise_not(cv2.subtract(ink, lines))
                remaining = 25 - (perf_counter() - started)
                if remaining > 0.1:
                    data = pytesseract.image_to_data(
                        clean, lang=languages or settings.ocr_languages, config="--psm 11",
                        output_type=pytesseract.Output.DICT, timeout=remaining,
                    )
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError) as exc:
        raise BackendError(
            "OCR failed; check Tesseract and installed language data", 503, "ocr_unavailable"
        ) from exc
    words, confidences = [], []
    for word, confidence in zip(data["text"], data["conf"]):
        if word.strip() and float(confidence) >= 0:
            words.append(word.strip())
            confidences.append(float(confidence))
    return " ".join(words), sum(confidences) / max(len(confidences), 1)


def detect_objects(image: np.ndarray) -> list[dict]:
    """Fast bounded-resolution detection; boxes remain in source-image coordinates."""
    try:
        with _detector_lock:
            result = detector().predict(
                image,
                conf=settings.yolo_confidence,
                device=settings.model_device,
                verbose=False,
                imgsz=settings.detection_image_size,
            )[0]
        objects = []
        for box in result.boxes:
            objects.append(
                {
                    "label": result.names[int(box.cls.item())],
                    "confidence": round(float(box.conf.item()), 4),
                    "box": [round(float(v), 1) for v in box.xyxy[0].tolist()],
                }
            )
    except Exception as exc:
        raise BackendError(
            "Object detection failed; check YOLO weights and device", 503, "detector_unavailable"
        ) from exc
    return objects


def detect_live(content: bytes) -> tuple[int, int, list[dict]]:
    # Live observations must not depend on OCR, deduplication or image enhancement.
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise BackendError("Cannot decode live image", 422, "invalid_image")
    height, width = image.shape[:2]
    if width * height > settings.max_image_pixels:
        raise BackendError("Image exceeds pixel limit", 413, "pixel_limit")
    return width, height, detect_objects(image)


def analyze_image(prepared: PreparedImage, languages: str | None = None) -> Analysis:
    objects = detect_objects(prepared.image)
    text, confidence = read_text(prepared, languages)
    return Analysis(text, confidence, objects)
