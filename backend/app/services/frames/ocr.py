"""Bounded camera-text OCR using only the already face-redacted image."""
from time import perf_counter
import unicodedata

import cv2
import numpy as np
import pytesseract

from app.core.config import settings
from app.core.errors import BackendError


def transcription(data):
    """Keep credible words and line order; never turn every texture into text."""
    lines, scores = [], []
    previous = None
    quality = 0.0
    for index, (raw, confidence) in enumerate(zip(data["text"], data["conf"])):
        word = raw.strip()
        confidence = float(confidence)
        letters = sum(char.isalnum() for char in word)
        if not letters or confidence < settings.ocr_min_word_confidence:
            continue
        # Camera keyboards/background textures often produce isolated glyphs.
        if letters == 1 and confidence < 85:
            continue
        word = "".join(char for char in word if unicodedata.category(char) != "Cf")
        line = tuple(data[key][index] for key in ("block_num", "par_num", "line_num"))
        if line != previous:
            lines.append([])
        lines[-1].append(word)
        previous = line
        scores.append((confidence, letters))
        quality += letters * (confidence / 100) ** 2
    weight = sum(length for _, length in scores)
    mean = sum(confidence * length for confidence, length in scores) / max(weight, 1)
    text = "\n".join(" ".join(line) for line in lines)
    if weight < 2:
        return "", 0.0, 0.0
    return text, mean, quality


def ocr_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Larger glyphs help screen/sign text. Cap work even for large uploads.
    scale = min(2.0, 2560 / max(gray.shape))
    if scale != 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return gray


def without_rules(gray):
    # Only remove long straight rules, on an OCR copy. Invert dark scenes first
    # so the same operation also works on light text from a dark-mode screen.
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if np.mean(ink > 0) > 0.5:
        ink = cv2.bitwise_not(ink)
    height, width = gray.shape
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(80, width // 3)), np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((max(80, height // 3), 1), np.uint8))
    return cv2.bitwise_not(cv2.subtract(ink, cv2.bitwise_or(horizontal, vertical)))


def recognize_tesseract(image, languages=None):
    started = perf_counter()
    gray = ocr_image(image)
    budget = settings.ocr_timeout_seconds
    best = ("", 0.0, 0.0)
    try:
        # Sparse layout is suited to signs/screens; automatic page layout also
        # handles uploaded documents. Compare whole passes instead of combining
        # competing guesses. All passes share one wall-clock budget.
        for candidate, mode in ((gray, 11), (gray, 3), (None, 11)):
            remaining = budget - (perf_counter() - started)
            if remaining < 0.1:
                break
            if candidate is None:
                # A high-quality result needs no destructive threshold fallback.
                if best[1] >= 85 and best[2] >= 10:
                    break
                candidate = without_rules(gray)
            try:
                data = pytesseract.image_to_data(
                    candidate, lang=languages or settings.ocr_languages,
                    config=f"--oem 1 --psm {mode} -c user_defined_dpi=300",
                    output_type=pytesseract.Output.DICT, timeout=remaining,
                )
            except RuntimeError:
                # An optional retry timing out must not discard a successful pass.
                if best[0]:
                    break
                raise
            result = transcription(data)
            if result[2] > best[2]:
                best = result
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError) as exc:
        raise BackendError("OCR failed; check Tesseract and installed language data", 503,
                           "ocr_unavailable") from exc
    return best[0], best[1]


def recognize_text(image, languages=None):
    if settings.ocr_engine == "tesseract":
        return recognize_tesseract(image, languages)
    from app.services.frames.paddle_client import paddle_ocr

    return paddle_ocr.recognize(image, languages or settings.ocr_languages)
