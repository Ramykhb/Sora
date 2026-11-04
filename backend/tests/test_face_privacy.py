import asyncio
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
import pytest

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import Frame
from app.services.frames import privacy, processing
from app.services.storage.object_store import get_image, put_image
from test_api import create, image_bytes

FIXTURE = Path(__file__).with_name("fixtures") / "astronaut.jpg"


@pytest.mark.parametrize("rotation", range(4))
def test_real_face_detector_finds_faces_in_all_orientations(rotation):
    image = cv2.copyMakeBorder(cv2.imread(str(FIXTURE)), 0, 0, 0, 180, cv2.BORDER_CONSTANT)
    image = np.ascontiguousarray(np.rot90(image, rotation))
    regions = privacy.face_regions(image)
    assert regions, "Bundled detector must actually detect the fixture's face"
    # The face is around (225, 120) in the upright NASA image.
    point = np.zeros((512, 692), np.uint8)
    point[120, 225] = 1
    y, x = np.argwhere(np.rot90(point, rotation))[0]
    assert any(left <= x < right and top <= y < bottom for left, top, right, bottom in regions)


def test_all_saved_and_ai_variants_are_blurred_after_enhancement(monkeypatch):
    monkeypatch.setattr(processing, "face_regions", lambda _: [(20, 20, 80, 80), (0, 0, 10, 10)])
    content = image_bytes()
    prepared = processing.prepare_image(content)
    assert "face_blur" in prepared.enhancements
    assert privacy.PRIVACY_VERSION in prepared.enhancements
    for image in [prepared.image, cv2.imdecode(np.frombuffer(prepared.original, np.uint8), 1),
                  cv2.imdecode(np.frombuffer(prepared.processed, np.uint8), 1)]:
        assert image[25:75, 25:75].std() < 10
        assert image[85:95, 85:95].std() > 20, "Background detail should survive"


def test_detector_failure_prevents_storage_even_for_forced_uploads(client, monkeypatch):
    api, _ = client
    sid = create(api)

    def fail():
        raise RuntimeError("Missing/corrupt detector")

    monkeypatch.setattr(privacy, "face_detector", fail)
    response = api.post(f"/api/v1/sessions/{sid}/frames", data={"force": "true"},
                        files={"image": ("test.png", image_bytes(), "image/png")})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "face_privacy_unavailable"
    assert not list(settings.local_storage_dir.rglob("*.jpg"))


@pytest.mark.parametrize("objects_only", [False, True])
def test_ingestion_and_image_api_never_store_or_serve_unblurred_face(client, objects_only):
    from app.services.frames.ingestion import ingest_bytes

    api, _ = client
    sid = create(api)
    kwargs = {"force": True, "defer_enrichment": True}
    if objects_only:
        kwargs.update(objects_only=True, detected_objects=[])
    result = api.portal.call(lambda: ingest_bytes(FIXTURE.read_bytes(), UUID(sid), **kwargs))
    assert result.status == "stored"
    assert "face_blur" in result.frame.enhancements
    source = cv2.imread(str(FIXTURE))
    for original in [False, True]:
        response = api.get(f"/api/v1/sessions/{sid}/frames/{result.frame.id}/image",
                           params={"original": str(original).lower()})
        assert response.status_code == 200
        saved = cv2.imdecode(np.frombuffer(response.content, np.uint8), 1)
        # Facial texture must be removed in both persisted variants.
        raw_detail = cv2.Laplacian(source[80:150, 190:260], cv2.CV_64F).var()
        saved_detail = cv2.Laplacian(saved[80:150, 190:260], cv2.CV_64F).var()
        assert saved_detail < raw_detail / 10
    assert len(list(settings.local_storage_dir.rglob("*.jpg"))) == 2


def test_backfill_redacts_both_existing_objects_and_is_resumable(client, monkeypatch):
    from app.services.frames.ingestion import ingest_bytes
    from scripts import blur_saved_faces
    main = blur_saved_faces.main

    api, factory = client
    sid = create(api)
    result = api.portal.call(lambda: ingest_bytes(FIXTURE.read_bytes(), UUID(sid), force=True, defer_enrichment=True))

    async def legacy_frame():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            row.enhancements = []
            keys = [row.original_object_key, row.processed_object_key]
            for key in keys:
                put_image(key, FIXTURE.read_bytes())
            await db.commit()
            return keys

    monkeypatch.setattr(blur_saved_faces, "SessionFactory", factory)
    keys = asyncio.run(legacy_frame())
    asyncio.run(main())
    first = [get_image(key) for key in keys]
    assert all(content != FIXTURE.read_bytes() for content in first)
    asyncio.run(main())
    assert [get_image(key) for key in keys] == first, "A second run must not recompress/redact again"


def test_face_blur_failure_is_not_treated_as_no_faces(monkeypatch):
    monkeypatch.setattr(privacy, "face_detector", lambda: None)
    with pytest.raises(BackendError, match="Face privacy"):
        privacy.face_regions(np.zeros((100, 100, 3), np.uint8))


def test_multiple_faces_are_all_blurred():
    face = cv2.imread(str(FIXTURE))
    scene = np.hstack((face, face))
    regions = privacy.face_regions(scene)
    for x in (225, 225 + 512):
        assert any(left <= x < right and top <= 120 < bottom for left, top, right, bottom in regions)
    blurred = privacy.blur_regions(scene, regions)
    for x in (190, 190 + 512):
        assert cv2.Laplacian(blurred[80:150, x:x + 70], cv2.CV_64F).var() < 10
