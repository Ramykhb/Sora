from io import BytesIO
import numpy as np
from PIL import Image
import pytest
from app.core.config import settings
from app.core.errors import BackendError
from app.services.frames.processing import prepare_image, vision_image
from app.services.frames.selection import rejection_reason


def encode(array):
    out = BytesIO()
    Image.fromarray(array).save(out, format="PNG")
    return out.getvalue()


def test_invalid_image_rejected():
    with pytest.raises(BackendError) as error:
        prepare_image(b"this is not an image")
    assert error.value.code == "invalid_image"


def test_black_frame_rejected_and_can_be_forced():
    image = prepare_image(encode(np.zeros((100, 100, 3), dtype=np.uint8)))
    assert rejection_reason(image, None) == "too_dark"
    assert rejection_reason(image, None, force=True) is None
    assert "clahe" in image.enhancements
    assert image.processed.startswith(b"\xff\xd8")


def test_duplicate_and_novel_frame_selection():
    rng = np.random.default_rng(42)
    first = prepare_image(encode(rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)))
    second = prepare_image(encode(rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)))
    assert rejection_reason(first, first.perceptual_hash) == "duplicate"
    assert rejection_reason(second, first.perceptual_hash) is None


def test_pixel_and_byte_limits(monkeypatch):
    monkeypatch.setattr(settings, "max_image_pixels", 1000)
    with pytest.raises(BackendError) as error:
        prepare_image(encode(np.zeros((100, 100, 3), dtype=np.uint8)))
    assert error.value.status_code == 413


def test_original_is_sanitized_jpeg_and_resized(monkeypatch):
    monkeypatch.setattr(settings, "max_image_side", 320)
    image = prepare_image(encode(np.full((500, 1000, 3), 80, dtype=np.uint8)))
    assert image.width == 320 and image.height == 160
    assert image.original.startswith(b"\xff\xd8")
    assert image.brightness == pytest.approx(80)


@pytest.mark.parametrize("size", [(1280, 720), (720, 1280)])
def test_caption_image_is_smaller_without_reducing_ocr_or_saved_images(monkeypatch, size):
    monkeypatch.setattr(settings, "max_image_side", 1280)
    monkeypatch.setattr(settings, "vision_image_max_side", 448)
    source = BytesIO()
    Image.new("RGB", size, "white").save(source, format="JPEG")
    prepared = prepare_image(source.getvalue())
    caption = Image.open(BytesIO(vision_image(prepared)))
    assert max(caption.size) == 448
    assert caption.width / caption.height == pytest.approx(size[0] / size[1], abs=0.01)
    assert (prepared.width, prepared.height) == size
    assert Image.open(BytesIO(prepared.original)).size == size
    assert Image.open(BytesIO(prepared.processed)).size == size
    assert prepared.image.shape[:2] == (size[1], size[0])


def test_caption_image_does_not_upscale_small_frames(monkeypatch):
    monkeypatch.setattr(settings, "vision_image_max_side", 448)
    prepared = prepare_image(encode(np.full((100, 200, 3), 80, dtype=np.uint8)))
    assert vision_image(prepared) is prepared.processed


def test_actual_tesseract_reads_test_sign(monkeypatch):
    import shutil
    from PIL import ImageDraw, ImageFont
    import app.services.frames.processing as processing

    if not shutil.which("tesseract"):
        pytest.skip("System Tesseract not installed")

    class EmptyResult:
        boxes = []
        names = {}

    class EmptyDetector:
        def predict(self, *args, **kwargs):
            return [EmptyResult()]

    monkeypatch.setattr(processing, "detector", lambda: EmptyDetector())
    image = Image.new("RGB", (500, 180), "white")
    ImageDraw.Draw(image).text(
        (30, 50), "EXIT 123", fill="black", font=ImageFont.load_default(size=50)
    )
    output = BytesIO()
    image.save(output, format="PNG")
    analysis = processing.analyze_image(processing.prepare_image(output.getvalue()), "eng")
    assert "EXIT" in analysis.ocr_text and "123" in analysis.ocr_text
    assert analysis.ocr_confidence > 0
