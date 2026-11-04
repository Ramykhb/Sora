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
