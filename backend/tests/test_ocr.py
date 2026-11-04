import numpy as np
import pytest
from app.services.frames import ocr
from app.core.config import settings


def data(words, confidences):
    return {"text": words, "conf": confidences, "block_num": [1] * len(words),
            "par_num": [1] * len(words), "line_num": list(range(len(words)))}


def test_noise_and_low_confidence_words_are_not_presented_as_text():
    text, confidence, _ = ocr.transcription(data(["EXIT", "~~~", "garbled", "x", "215"], [95, 96, 22, 70, 92]))
    assert text == "EXIT\n215"
    assert confidence > 90
    assert ocr.transcription(data(["à"], [90])) == ("", 0, 0)


def test_sparse_layout_retry_wins_over_nonempty_bad_page_result(monkeypatch):
    calls = []
    def recognize(image, **kwargs):
        calls.append(kwargs)
        if "--psm 11" in kwargs["config"]:
            return data(["ROOM", "215"], [96, 94])
        return data(["garbled"], [20])
    monkeypatch.setattr(ocr.pytesseract, "image_to_data", recognize)
    image = np.full((100, 200, 3), 255, np.uint8)
    result = ocr.recognize_text(image, "fra")
    assert result[0] == "ROOM\n215"
    assert all(call["lang"] == "fra" for call in calls)
    assert len(calls) <= 3
    assert all(0 < call["timeout"] <= settings.ocr_timeout_seconds for call in calls)


def test_retry_timeout_keeps_successful_text(monkeypatch):
    calls = 0
    def recognize(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return data(["EXIT"], [95])
        raise RuntimeError("Tesseract process timeout")
    monkeypatch.setattr(ocr.pytesseract, "image_to_data", recognize)
    assert ocr.recognize_text(np.full((100, 200, 3), 255, np.uint8))[0] == "EXIT"


@pytest.mark.parametrize("shape", [(100, 200), (1920, 1080), (4096, 2048)])
def test_preprocessing_is_bounded_and_does_not_mutate_saved_pixels(shape):
    image = np.full((*shape, 3), 120, np.uint8)
    original = image.copy()
    candidate = ocr.ocr_image(image)
    assert max(candidate.shape) <= 2560
    assert np.array_equal(image, original)
