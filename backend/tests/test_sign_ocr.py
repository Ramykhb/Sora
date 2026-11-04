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


@pytest.mark.parametrize("dark,text", [(False, "Platform 7"), (True, "SORTIE 215")])
def test_small_sparse_camera_text_and_dark_screens(dark, text):
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    if not shutil.which("tesseract"):
        pytest.skip("System Tesseract not installed")
    background, foreground = ((25, 220) if dark else (230, 35))
    image = Image.new("RGB", (700, 450), (background,) * 3)
    ImageDraw.Draw(image).text((150, 190), text, fill=(foreground,) * 3,
                              font=ImageFont.truetype("DejaVuSans.ttf", 14))
    output = BytesIO()
    image.save(output, format="PNG")
    prepared = prepare_image(output.getvalue())
    recognized, confidence = read_text(prepared, "eng+fra")
    assert all(token.lower() in recognized.lower() for token in text.split()), recognized
    assert confidence >= 60
