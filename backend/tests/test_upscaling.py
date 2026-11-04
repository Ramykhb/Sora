import asyncio
import sqlite3
from uuid import UUID

import cv2
import numpy as np
import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import Frame
from app.services.frames import upscaling
from app.services.storage.object_store import delete_image
from test_api import create, image_bytes, upload


def test_tiled_scaling_produces_exact_200_percent_without_seams(monkeypatch):
    import torch

    monkeypatch.setattr(settings, "upscale_tile_size", 32)
    image = np.full((71, 95, 3), [25, 110, 210], np.uint8)
    def model(tensor):
        return torch.nn.functional.interpolate(tensor, scale_factor=4, mode="nearest")
    result = upscaling.tiled_upscale(image, model)
    assert result.shape == (142, 190, 3)
    assert np.max(np.abs(result.astype(int) - np.tile([25, 110, 210], (142, 190, 1)))) <= 1


def test_previously_blurred_faces_never_enter_the_generative_model(monkeypatch):
    def forbidden():
        raise AssertionError("Privacy blur must not be fed through generative enhancement")
    monkeypatch.setattr(upscaling, "upscaler", forbidden)
    image, method = upscaling.enhance_saved_image(image_bytes(), ["face_blur"])
    assert image.shape == (200, 200, 3)
    assert method == "upscale_lanczos_privacy"


def test_checkpoint_reader_rejects_unrelated_or_partial_sqlite(tmp_path):
    path = tmp_path / "model.ckpt"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tensors(name,format,datatype,dim,data)")
    with pytest.raises(ValueError, match="Incomplete"):
        upscaling.checkpoint_weights(path)


def test_background_enhancement_updates_only_processed_variant_and_runs_once(client, monkeypatch):
    from app.workers import upscaling as worker

    api, factory = client
    monkeypatch.setattr(worker, "SessionFactory", factory)
    sid = create(api)
    frame = upload(api, sid)
    path = f"/api/v1/sessions/{sid}/frames/{frame['id']}/image"
    original = api.get(path, params={"original": "true"}).content
    calls = []
    def enhance(content, steps):
        calls.append(True)
        image = cv2.imdecode(np.frombuffer(content, np.uint8), 1)
        return cv2.resize(image, None, fx=2, fy=2), "realesrgan_x4plus_2x"
    monkeypatch.setattr(worker, "enhance_saved_image", enhance)
    assert api.portal.call(worker.enhance_frame, UUID(frame["id"])) is True
    processed = cv2.imdecode(np.frombuffer(api.get(path).content, np.uint8), 1)
    assert processed.shape[:2] == (200, 200)
    assert api.get(path, params={"original": "true"}).content == original
    assert api.portal.call(worker.enhance_frame, UUID(frame["id"])) is False
    assert len(calls) == 1


def test_deleted_frame_cannot_be_resurrected_after_slow_upscaling(client, monkeypatch):
    from app.workers import upscaling as worker

    api, factory = client
    monkeypatch.setattr(worker, "SessionFactory", factory)
    frame = upload(api, create(api))
    async def remove():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            for key in [row.original_object_key, row.processed_object_key]:
                delete_image(key)
            await db.execute(delete(Frame).where(Frame.id == row.id))
            await db.commit()
    def enhance(*args):
        asyncio.run(remove())
        return np.zeros((200, 200, 3), np.uint8), "realesrgan_x4plus_2x"
    monkeypatch.setattr(worker, "enhance_saved_image", enhance)
    assert api.portal.call(worker.enhance_frame, UUID(frame["id"])) is False
    assert not list(settings.local_storage_dir.rglob("*.jpg"))


@pytest.fixture(autouse=True)
def deterministic_worker_ocr(monkeypatch):
    from app.workers import upscaling as worker
    monkeypatch.setattr(worker, "recognize_text", lambda *args, **kwargs: ("EXIT", 95))


def test_ocr_runs_after_upscaling_and_updates_search_and_embedding(client, monkeypatch):
    from app.workers import upscaling as worker

    api, factory = client
    monkeypatch.setattr(worker, "SessionFactory", factory)
    frame = upload(api, create(api))
    async def low_confidence():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.ocr_text, row.ocr_confidence = "unclear", 40
            await db.commit()
    api.portal.call(low_confidence)
    monkeypatch.setattr(worker, "enhance_saved_image", lambda *args: (np.zeros((200, 200, 3), np.uint8), "realesrgan_x4plus_2x"))
    def recognize(image, **kwargs):
        assert image.shape == (200, 200, 3)
        assert kwargs["rescale"] is False
        return "PLATFORM 7", 96
    monkeypatch.setattr(worker, "recognize_text", recognize)
    api.portal.call(worker.enhance_frame, UUID(frame["id"]))
    async def verify():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            assert row.ocr_text == "PLATFORM 7" and row.ocr_confidence == 96
            assert "PLATFORM 7" in row.search_text
            assert row.embedding is not None
            assert worker.OCR_MARKER in row.enhancements
    api.portal.call(verify)


def test_lower_confidence_upscaled_ocr_keeps_original_reading(client, monkeypatch):
    from app.workers import upscaling as worker

    api, factory = client
    monkeypatch.setattr(worker, "SessionFactory", factory)
    frame = upload(api, create(api))
    monkeypatch.setattr(worker, "enhance_saved_image", lambda *args: (np.zeros((200, 200, 3), np.uint8), "realesrgan_x4plus_2x"))
    monkeypatch.setattr(worker, "recognize_text", lambda *args, **kwargs: ("wrong reading", 65))
    api.portal.call(worker.enhance_frame, UUID(frame["id"]))
    value = api.get(f"/api/v1/sessions/{frame['session_id']}/frames/{frame['id']}").json()
    assert value["ocr_text"] == "EXIT" and value["ocr_confidence"] == 95


def test_existing_200_percent_images_get_ocr_without_being_upscaled_again(client, monkeypatch):
    from app.workers import upscaling as worker
    from app.services.storage.object_store import put_image
    from app.services.frames.processing import jpeg

    api, factory = client
    monkeypatch.setattr(worker, "SessionFactory", factory)
    frame = upload(api, create(api))
    async def legacy_upscale():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.enhancements = [*row.enhancements, upscaling.UPSCALE_MARKER]
            put_image(row.processed_object_key, jpeg(np.zeros((200, 200, 3), np.uint8)))
            await db.commit()
    api.portal.call(legacy_upscale)
    def forbidden(*args):
        raise AssertionError("Previously upscaled images need only the OCR stage")
    monkeypatch.setattr(worker, "enhance_saved_image", forbidden)
    assert api.portal.call(worker.enhance_frame, UUID(frame["id"])) is True
    assert api.portal.call(worker.enhance_frame, UUID(frame["id"])) is False
