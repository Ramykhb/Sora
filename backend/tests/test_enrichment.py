from functools import partial
from uuid import UUID
from sqlalchemy import delete
from app.core.errors import BackendError
from app.db.models import Frame
from app.services.ai.models import Scene, models
from app.services.frames.ingestion import ingest_bytes
from app.services.frames.processing import Analysis
from app.workers.enrichment import enrich_frame
from test_api import create, image_bytes


def save_fast(api, sid):
    return api.portal.call(partial(ingest_bytes, image_bytes(), UUID(sid), defer_enrichment=True))


def test_fast_capture_persists_without_waiting_for_any_model(client, monkeypatch):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = create(api)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Fast capture must not wait for captioning or embeddings")

    monkeypatch.setattr(models, "describe", forbidden)
    monkeypatch.setattr(models, "embed", forbidden)
    # A clear frame with no OCR/detections can still become useful after captioning.
    monkeypatch.setattr(ingestion, "analyze_image", lambda *args: Analysis("", 0, []))
    result = save_fast(api, sid)
    assert result.status == "stored"
    frame = api.get(f"/api/v1/sessions/{sid}/frames").json()[0]
    assert frame["enrichment_status"] == "pending"
    assert frame["enrichment_ms"] is None
    assert frame["caption"] == ""
    assert api.get(f"/api/v1/sessions/{sid}/frames/{frame['id']}/image").status_code == 200


def test_enrichment_reads_durable_work_and_updates_the_same_saved_frame(client):
    api, factory = client
    sid = create(api)
    result = save_fast(api, sid)
    saved_ms = result.frame.processing_ms
    with api.websocket_connect(f"/api/v1/sessions/{sid}/events") as socket:
        socket.send_json({"access_token": api.headers["Authorization"].split(" ", 1)[1]})
        assert socket.receive_json()["type"] == "ready"
        api.portal.call(enrich_frame, result.frame.id)
        update = socket.receive_json()
        assert update["type"] == "frame_updated"
        assert update["frame"]["id"] == str(result.frame.id)
        assert update["frame"]["enrichment_status"] == "complete"
        assert update["frame"]["caption"] == "A chair beside an EXIT sign"
        assert update["frame"]["processing_ms"] == saved_ms
        assert update["frame"]["enrichment_ms"] is not None

    async def check_vector():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            assert row.embedding is not None
            assert "EXIT" in row.search_text

    api.portal.call(check_vector)
    assert len(api.get(f"/api/v1/sessions/{sid}/frames").json()) == 1


def test_enrichment_uses_processed_image_without_reprocessing(client, monkeypatch):
    import app.services.frames.processing as processing
    import app.workers.enrichment as enrichment
    from app.services.storage.object_store import get_image
    from PIL import Image
    from io import BytesIO

    api, _ = client
    result = save_fast(api, create(api))
    keys = []
    original_get = get_image

    def read(key):
        keys.append(key)
        return original_get(key)

    def forbidden(*_args):
        raise AssertionError("Enrichment must not repeat image preparation")

    async def describe(content):
        image = Image.open(BytesIO(content))
        assert max(image.size) <= 448
        return Scene(caption="A chair", uncertain=False)

    monkeypatch.setattr(enrichment, "get_image", read)
    monkeypatch.setattr(processing, "prepare_image", forbidden)
    monkeypatch.setattr(models, "describe", describe)
    api.portal.call(enrich_frame, result.frame.id)
    assert len(keys) == 1 and keys[0].endswith("/processed.jpg")
    updated = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()[0]
    assert updated["caption"] == "A chair"
    assert updated["ocr_text"] == result.frame.ocr_text
    assert updated["detected_objects"] == result.frame.detected_objects


def test_enrichment_fails_closed_without_privacy_marker_or_processed_object(client, monkeypatch):
    from app.services.storage.object_store import get_image
    import app.workers.enrichment as enrichment

    api, factory = client
    result = save_fast(api, create(api))

    async def remove_marker():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            row.enhancements = []
            await db.commit()

    api.portal.call(remove_marker)
    monkeypatch.setattr(enrichment, "get_image", lambda *_: (_ for _ in ()).throw(AssertionError("no read")))
    api.portal.call(enrich_frame, result.frame.id)
    frame = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()[0]
    assert frame["enrichment_status"] == "failed"
    assert "face_privacy_unavailable" in frame["processing_warnings"]

    second = api.portal.call(partial(ingest_bytes, image_bytes(), result.frame.session_id,
                                     defer_enrichment=True, force=True))

    async def missing_image():
        async with factory() as db:
            row = await db.get(Frame, second.frame.id)
            row.processed_object_key = "missing/processed.jpg"
            await db.commit()

    api.portal.call(missing_image)
    monkeypatch.setattr(enrichment, "get_image", get_image)
    api.portal.call(enrich_frame, second.frame.id)
    frames = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()
    failed = next(frame for frame in frames if frame["id"] == str(second.frame.id))
    assert failed["enrichment_status"] == "failed"
    assert "processed_image_unavailable" in failed["processing_warnings"]


def test_enrichment_failure_keeps_saved_ocr_and_reports_the_failure(client, monkeypatch):
    api, _ = client
    sid = create(api)
    result = save_fast(api, sid)

    async def unavailable(*args):
        raise BackendError("Offline", 503, "vision_unavailable")

    monkeypatch.setattr(models, "describe", unavailable)
    api.portal.call(enrich_frame, result.frame.id)
    frame = api.get(f"/api/v1/sessions/{sid}/frames").json()[0]
    assert frame["ocr_text"] == "EXIT"
    assert frame["enrichment_status"] == "failed"
    assert "vision_unavailable" in frame["processing_warnings"]


def test_deletion_during_enrichment_cannot_resurrect_an_image(client, monkeypatch):
    api, factory = client
    sid = create(api)
    result = save_fast(api, sid)

    async def deleted_during_inference(*args):
        async with factory() as db:
            await db.execute(delete(Frame).where(Frame.id == result.frame.id))
            await db.commit()
        return Scene(caption="A door", uncertain=False, central_closed_door=True)

    monkeypatch.setattr(models, "describe", deleted_during_inference)
    api.portal.call(enrich_frame, result.frame.id)
    assert api.get(f"/api/v1/sessions/{sid}/frames").json() == []


def test_delayed_caption_preserves_updated_ocr_in_search(client, monkeypatch):
    api, factory = client
    result = save_fast(api, create(api))
    async def describe(_):
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            row.ocr_text = "PLATFORM 7"
            await db.commit()
        return Scene(caption="A sign", uncertain=False)
    monkeypatch.setattr(models, "describe", describe)
    api.portal.call(enrich_frame, result.frame.id)
    async def verify():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            assert row.ocr_text == "PLATFORM 7"
            assert "PLATFORM 7" in row.search_text and "EXIT" not in row.search_text
            assert row.embedding is None
    api.portal.call(verify)
