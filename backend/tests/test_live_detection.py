import asyncio
from datetime import timedelta
from functools import partial
from uuid import UUID

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services.events import events
from app.services.streaming.session import LiveState, streams
from test_api import create, image_bytes


def test_live_alerts_continue_while_memory_is_blocked_and_are_saved_without_frame(client, monkeypatch):
    api, _ = client
    sid = UUID(create(api))
    import app.services.frames.ingestion as ingestion

    async def exercise():
        blocked = asyncio.Event()
        entered = asyncio.Event()

        async def stalled(*args, **kwargs):
            entered.set()
            await blocked.wait()

        monkeypatch.setattr(ingestion, "ingest_bytes", stalled)
        async with events.subscribe(sid) as queue:
            state = streams.start(sid, "test")
            try:
                streams.enqueue_detection(state, b"jpeg", now())
                messages = []
                while not any(item["type"] == "alert" for item in messages):
                    messages.append(await asyncio.wait_for(queue.get(), 2))
                alert = next(item for item in messages if item["type"] == "alert")
                assert alert["frame_id"] is None and alert["expires_at"]
                await asyncio.wait_for(entered.wait(), 2)
                await asyncio.wait_for(state.history_queue.join(), 2)
                # Continued detection is independent of the blocked memory worker.
                streams.enqueue_detection(state, b"jpeg", now())
                while True:
                    message = await asyncio.wait_for(queue.get(), 2)
                    if message["type"] == "observation":
                        assert message["id"] != alert["id"]
                        break
                return alert
            finally:
                await streams.stop(sid)

    alert = api.portal.call(exercise)
    retained = api.get(f"/api/v1/sessions/{sid}/alerts").json()
    assert retained[0]["id"] == alert["id"]
    assert retained[0]["frame_id"] is None
    assert api.get(f"/api/v1/sessions/{sid}/frames").json() == []


def test_expired_samples_are_not_announced_or_persisted(client):
    api, _ = client
    sid = UUID(create(api))

    async def exercise():
        state = streams.start(sid, "test")
        try:
            streams.enqueue_detection(state, b"jpeg", now() - timedelta(seconds=10))
            await asyncio.wait_for(state.detection_queue.join(), 2)
            assert state.observation is None
            assert state.history_queue.empty()
        finally:
            await streams.stop(sid)

    api.portal.call(exercise)


def test_latest_detection_queue_discards_old_waiting_frames():
    state = LiveState(source="test")
    streams.enqueue_detection(state, b"old", now())
    streams.enqueue_detection(state, b"new", now())
    assert state.detection_queue.qsize() == 1
    assert state.detection_queue.get_nowait()[0] == b"new"
    assert state.detection_dropped == 1


def test_live_memory_retains_objects_even_if_ocr_fails(client, monkeypatch):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = UUID(create(api))

    def failed(*args):
        raise BackendError("Unavailable", 503, "ocr_unavailable")

    monkeypatch.setattr(ingestion, "read_text", failed)
    result = api.portal.call(partial(
        ingestion.ingest_bytes, image_bytes(), sid, defer_enrichment=True,
        detected_objects=[{"label": "chair", "confidence": 0.9, "box": [20, 20, 80, 95]}],
        emit_alerts=False,
    ))
    assert result.frame.detected_objects[0]["label"] == "chair"
    assert "ocr_unavailable" in result.frame.processing_warnings


def test_enrichment_admission_is_bounded_and_preserves_memory(client):
    from app.services.frames.ingestion import ingest_bytes

    api, _ = client
    sid = UUID(create(api))
    for _ in range(settings.max_pending_enrichments + 3):
        api.portal.call(partial(
            ingest_bytes, image_bytes(), sid, force=True, defer_enrichment=True,
        ))
    frames = api.get(f"/api/v1/sessions/{sid}/frames").json()
    assert sum(f["enrichment_status"] == "pending" for f in frames) == settings.max_pending_enrichments
    skipped = [f for f in frames if f["enrichment_status"] == "skipped"]
    assert len(skipped) == 3
    assert all(f["ocr_text"] == "EXIT" and f["detected_objects"] for f in skipped)


def test_current_view_retrieval_does_not_wait_for_embeddings(client, monkeypatch):
    from test_api import upload
    api, _ = client
    sid = create(api)
    frame = upload(api, sid)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Current-view lookup must not call embeddings")

    monkeypatch.setattr("app.services.ai.models.models.embed", forbidden)
    answer = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What is in front of me?", "scope": "recent",
    })
    assert answer.status_code == 200
    assert answer.json()["evidence_frame_ids"] == [frame["id"]]
