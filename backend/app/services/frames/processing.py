from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import threading
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import open as open_image
from app.core.config import settings
from app.core.errors import BackendError
from app.services.frames.privacy import PRIVACY_VERSION, blur_regions, face_regions


@dataclass
class ImageQuality:
    """Unenhanced grayscale metrics: intensity/std in 0..255, percentages in 0..1."""
    brightness: float
    sharpness: float  # Variance of the grayscale Laplacian; nonnegative.
    contrast: float  # Standard deviation of grayscale intensity.
    shadow_fraction: float  # Pixels below intensity 40.
    highlight_fraction: float  # Pixels above intensity 215.


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
    quality: ImageQuality | None = None


@dataclass
class Analysis:
    ocr_text: str
    ocr_confidence: float
    objects: list[dict]
    warnings: list[str] = field(default_factory=list)


def jpeg(image):
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise BackendError("Could not encode image", 422, "invalid_image")
    return encoded.tobytes()


def measure_quality(gray: np.ndarray) -> ImageQuality:
    """Measure the decoded image once, before any enhancement or face blur."""
    return ImageQuality(
        brightness=float(gray.mean()),
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        contrast=float(gray.std()),
        shadow_fraction=float(np.count_nonzero(gray < 40) / gray.size),
        highlight_fraction=float(np.count_nonzero(gray > 215) / gray.size),
    )


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
    quality = measure_quality(gray)
    sharpness, brightness = quality.sharpness, quality.brightness
    small = cv2.resize(gray, (9, 8))
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    phash = f"{sum(int(bit) << index for index, bit in enumerate(bits)):016x}"
    enhanced = image.copy()
    steps = []
    if 25 <= brightness < 100 and quality.shadow_fraction > 0.15:
        gamma = max(0.72, min(0.95, 1 - (100 - brightness) / 300))
        table = np.clip((np.arange(256) / 255.0) ** gamma * 255, 0, 255).astype(np.uint8)
        enhanced = cv2.LUT(enhanced, table)
        steps.append("gamma")
    if brightness < 100 or (quality.contrast < 40 and brightness < 180):
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        light, a, b = cv2.split(lab)
        light = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(light)
        enhanced = cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)
        steps.append("clahe")
    # Bilateral filtering is edge-preserving; low light is the conservative
    # trigger when a reliable noise estimate is unavailable.
    if brightness < 60:
        enhanced = cv2.bilateralFilter(enhanced, 5, 20, 20)
        steps.append("denoise")
    if 15 <= sharpness < 150 and quality.contrast >= 25 and brightness >= 45:
        blur = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
        enhanced = cv2.addWeighted(enhanced, 1.25, blur, -0.25, 0)
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
        jpeg(image), jpeg(enhanced), enhanced, width, height, sharpness, brightness, phash, steps,
        quality,
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


def vision_image_from_processed(content: bytes) -> bytes:
    """Validate and resize a stored privacy-processed JPEG without enhancing it again."""
    if not content or len(content) > settings.max_upload_mb * 1024 * 1024:
        raise BackendError("Stored processed image exceeds size limit", 413, "processed_image_invalid")
    try:
        with open_image(BytesIO(content), formats=("JPEG",)) as source:
            width, height = source.size
            if width * height > settings.max_image_pixels:
                raise BackendError("Stored processed image exceeds pixel limit", 413,
                                   "processed_image_invalid")
            if min(width, height) < 32:
                raise BackendError("Stored processed image is too small", 422,
                                   "processed_image_invalid")
            source.load()
            if max(width, height) <= settings.vision_image_max_side:
                return content
            source = source.convert("RGB")
            image = cv2.cvtColor(np.asarray(source), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BackendError("Stored processed image is unreadable", 422,
                           "processed_image_invalid") from exc
    scale = settings.vision_image_max_side / max(width, height)
    resized = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))),
                         interpolation=cv2.INTER_AREA)
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
    from app.services.frames.ocr import recognize_text

    return recognize_text(prepared.image, languages)


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
    result = read_text(prepared, languages)
    text, confidence = result
    return Analysis(text, confidence, objects, list(getattr(result, "warnings", ())))
