import shutil

import pytest

from app.services.frames.processing import prepare_image, read_text
from scripts.acceptance import sign_image


@pytest.mark.parametrize("text", ["EXIT 123", "ROOM 215"])
def test_actual_tesseract_reads_bordered_sign_without_changing_stored_image(text):
    if not shutil.which("tesseract"):
        pytest.skip("System Tesseract not installed")
    prepared = prepare_image(sign_image(text))
    saved = prepared.processed
    recognized, confidence = read_text(prepared, "eng")
    assert all(token in recognized for token in text.split())
    assert confidence > 0
    assert prepared.processed == saved
