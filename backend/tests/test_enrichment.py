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
