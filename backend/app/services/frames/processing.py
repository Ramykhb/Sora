from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import threading
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract
from app.core.config import settings
from app.core.errors import BackendError


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
        with Image.open(BytesIO(content)) as source:
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
    from ultralytics import YOLO

    return YOLO(settings.yolo_model)


def warmup_detector():
    # Model weights are prepared explicitly; startup must not download anything.
    if Path(settings.yolo_model).is_file():
        with _detector_lock:
            detector().predict(
                np.zeros((640, 640, 3), dtype=np.uint8),
                conf=settings.yolo_confidence, device=settings.model_device, verbose=False,
            )


def analyze_image(prepared: PreparedImage, languages: str | None = None) -> Analysis:
    try:
        data = pytesseract.image_to_data(
            cv2.cvtColor(prepared.image, cv2.COLOR_BGR2RGB),
            lang=languages or settings.ocr_languages,
            output_type=pytesseract.Output.DICT,
            timeout=25,
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
    try:
        with _detector_lock:
            result = detector().predict(
                prepared.image,
                conf=settings.yolo_confidence,
                device=settings.model_device,
                verbose=False,
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
    return Analysis(" ".join(words), sum(confidences) / max(len(confidences), 1), objects)
