"""API + real SQLite/object storage integration; model inference is replaced deterministically."""

import asyncio
from datetime import timedelta
from io import BytesIO
import numpy as np
from PIL import Image
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")
from app.core.config import settings
from app.db.models import Frame
from app.db.models.frame import now
from app.services.ai.models import ModelAnswer, Scene, models


def image_bytes():
    out = BytesIO()
    image = np.random.default_rng(2).integers(0, 255, (100, 100, 3), dtype=np.uint8)
    Image.fromarray(image).save(out, format="PNG")
    return out.getvalue()


def create(api):
    response = api.post("/api/v1/sessions", json={"consent": True, "alerts_enabled": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(api, session_id):
    response = api.post(
        f"/api/v1/sessions/{session_id}/frames",
        files={"image": ("test.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "stored", response.text
    return response.json()["frame"]


def test_auth_and_consent(client):
    api, _ = client
    assert api.get("/api/v1/sessions", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert api.post("/api/v1/sessions", json={"consent": False}).status_code == 422
    assert api.get("/health").status_code == 200


def test_end_to_end_memory_answers_history_alerts_feedback_delete(client):
    api, _ = client
    sid = create(api)
    frame = upload(api, sid)
    base = f"/api/v1/sessions/{sid}"
    assert api.get(base + "/frames/" + frame["id"] + "/image").content.startswith(b"\xff\xd8")
    assert (
        api.get(base + "/frames/search", params={"q": "EXIT"}).json()["frames"][0]["id"]
        == frame["id"]
    )
    duplicate = api.post(
        base + "/frames", files={"image": ("test.png", image_bytes(), "image/png")}
    )
    assert duplicate.json()["reason"] == "duplicate"
    answer = api.post(base + "/questions", json={"question": "What is in front of me?"}).json()
    assert answer["evidence_frame_ids"] == [frame["id"]]
    assert not answer["uncertain"]
    assert api.get(base + "/questions").json()[0]["id"] == answer["id"]
    assert (
        api.post(
            base + "/questions/" + answer["id"] + "/feedback", json={"rating": "correct"}
        ).status_code
        == 201
    )
    assert len(api.get(base + "/alerts").json()) == 1
    assert api.get("/api/v1/metrics").json()["feedback"]["correct"] == 1
    assert api.delete(base).status_code == 204
    assert api.get(base + "/frames/" + frame["id"] + "/image").status_code == 404
    assert not any(settings.local_storage_dir.rglob("*.jpg"))


def test_recent_evidence_does_not_reuse_stale_frames(client):
    api, factory = client
    from uuid import UUID

    sid = create(api)
    frame = upload(api, sid)

    async def age():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.captured_at = now() - timedelta(minutes=10)
            await db.commit()

    asyncio.run(age())
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What is in front of me?"}
    ).json()
    assert answer["uncertain"] and answer["evidence_frame_ids"] == []
    memory = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What did I pass earlier?"}
    ).json()
    assert memory["evidence_frame_ids"] == [frame["id"]]


def test_expiration_deletes_database_and_objects(client):
    api, factory = client
    from uuid import UUID

    sid = create(api)
    frame = upload(api, sid)

    async def expire():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.expires_at = now() - timedelta(seconds=1)
            await db.commit()

    asyncio.run(expire())
    assert api.get(f"/api/v1/sessions/{sid}/frames/{frame['id']}/image").status_code == 404
    report = api.post("/api/v1/maintenance/cleanup").json()
    assert report["frames_deleted"] == 1 and report["objects_deleted"] == 2
    assert not any(settings.local_storage_dir.rglob("*.jpg"))


def test_cross_session_frame_access_is_rejected(client):
    api, _ = client
    first, second = create(api), create(api)
    frame = upload(api, first)
    assert api.get(f"/api/v1/sessions/{second}/frames/{frame['id']}/image").status_code == 404


def test_processing_warnings_and_uncertain_answer_when_models_fail(client, monkeypatch):
    from app.core.errors import BackendError

    api, _ = client
    sid = create(api)

    async def broken(*args, **kwargs):
        raise BackendError("Unavailable", code="vision_unavailable")

    monkeypatch.setattr(models, "describe", broken)
    monkeypatch.setattr(models, "embed", broken)
    monkeypatch.setattr(models, "chat", broken)
    frame = upload(api, sid)
    assert frame["ocr_text"] == "EXIT" and frame["processing_warnings"]
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What is visible?"}
    ).json()
    assert answer["uncertain"] and "vision_unavailable" in answer["processing_warnings"]


def test_retryable_object_deletion_outbox(client, monkeypatch):
    from app.core.errors import BackendError
    import app.workers.retention as retention

    api, _ = client
    sid = create(api)
    frame = upload(api, sid)
    original = retention.delete_image

    def unavailable(key):
        raise BackendError("Storage down")

    monkeypatch.setattr(retention, "delete_image", unavailable)
    assert api.delete(f"/api/v1/sessions/{sid}/frames/{frame['id']}").status_code == 204
    assert api.get("/api/v1/metrics").json()["pending_object_deletions"] == 2
    monkeypatch.setattr(retention, "delete_image", original)
    assert api.post("/api/v1/maintenance/cleanup").json()["objects_deleted"] == 2
    assert not any(settings.local_storage_dir.rglob("*.jpg"))


def test_failed_second_upload_compensates_first(client, monkeypatch):
    import app.services.frames.ingestion as ingestion
    from app.core.errors import BackendError

    api, _ = client
    sid = create(api)
    original = ingestion.put_image

    def fail_second(key, content, kind):
        if key.endswith("processed.jpg"):
            raise BackendError("Storage failed")
        original(key, content, kind)

    monkeypatch.setattr(ingestion, "put_image", fail_second)
    result = api.post(
        f"/api/v1/sessions/{sid}/frames", files={"image": ("test.png", image_bytes())}
    )
    assert result.status_code == 503
    assert not any(settings.local_storage_dir.rglob("*.jpg"))
    assert api.get(f"/api/v1/sessions/{sid}/frames").json() == []


def test_websocket_auth_and_frame_to_event_flow(client):
    api, _ = client
    sid = create(api)
    path = f"/api/v1/sessions/{sid}"
    with api.websocket_connect(path + "/events") as event_socket:
        event_socket.send_json({"access_token": api.headers["Authorization"].split(" ", 1)[1]})
        assert event_socket.receive_json()["type"] == "ready"
        with api.websocket_connect(path + "/stream/frames") as producer:
            producer.send_json({"access_token": api.headers["Authorization"].split(" ", 1)[1]})
            assert producer.receive_json()["type"] == "ready"
            assert event_socket.receive_json()["type"] == "stream_started"
            source = Image.open(BytesIO(image_bytes()))
            out = BytesIO()
            source.save(out, format="JPEG")
            producer.send_bytes(out.getvalue())
            event = event_socket.receive_json()
            assert event["type"] == "frame_stored", event
            assert event["frame"]["ocr_text"] == "EXIT"
            assert api.get(path + "/stream/status").json()["frames_received"] == 1
    assert api.get(path + "/stream/status").json()["streaming"] is False


def test_voice_question_and_spoken_reply_contract(client, monkeypatch):
    import app.api.routes.questions as routes

    api, _ = client
    sid = create(api)
    upload(api, sid)
    monkeypatch.setattr(routes, "transcribe", lambda *args: ("What is visible?", "en"))
    monkeypatch.setattr(routes, "synthesize", lambda *args: b"RIFFtest-wave")
    result = api.post(
        f"/api/v1/sessions/{sid}/questions/audio", files={"audio": ("question.wav", b"audio")}
    )
    assert result.status_code == 200, result.text
    answer = result.json()
    assert answer["source"] == "audio" and answer["question"] == "What is visible?"
    response = api.get(f"/api/v1/sessions/{sid}/questions/{answer['id']}/audio")
    assert response.headers["content-type"] == "audio/wav" and response.content.startswith(b"RIFF")


def test_closed_door_alert_and_cooldown(client, monkeypatch):
    api, _ = client

    async def describe(_):
        return Scene(caption="A closed door", uncertain=False, central_closed_door=True)

    monkeypatch.setattr(models, "describe", describe)
    sid = create(api)
    frame = upload(api, sid)
    assert "central_closed_door" in frame["scene_flags"]
    alerts = api.get(f"/api/v1/sessions/{sid}/alerts").json()
    assert alerts[0]["label"] == "closed_door"


def test_invalid_evidence_ids_cannot_support_an_answer(client, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)

    async def hallucinated(*args):
        return ModelAnswer(answer="A spaceship.", uncertain=False, evidence_frame_ids=["invented"])

    monkeypatch.setattr(models, "chat", hallucinated)
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What is visible?"}
    ).json()
    assert answer["uncertain"] and not answer["evidence_frame_ids"]
    assert "spaceship" not in answer["answer"]


def test_evidence_that_ages_during_inference_is_not_called_current(client, monkeypatch):
    from uuid import UUID

    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def slow_response(*args):
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.captured_at = now() - timedelta(minutes=10)
            await db.commit()
        return ModelAnswer(
            answer="A chair is visible.", uncertain=False, evidence_frame_ids=[frame["id"]]
        )

    monkeypatch.setattr(models, "chat", slow_response)
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "What is in front of me?"}
    ).json()
    assert answer["uncertain"] and not answer["evidence_frame_ids"]
    assert "evidence_expired_during_inference" in answer["processing_warnings"]


def test_orphan_reconciliation_preserves_referenced_images(client):
    import os
    import time

    api, _ = client
    sid = create(api)
    frame = upload(api, sid)
    orphan = settings.local_storage_dir / "images" / "orphan" / "image.jpg"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"orphan-image")
    old = time.time() - 3600
    os.utime(orphan, (old, old))
    report = api.post("/api/v1/maintenance/reconcile").json()
    assert report["orphan_objects_queued"] == 1 and not orphan.exists()
    assert api.get(f"/api/v1/sessions/{sid}/frames/{frame['id']}/image").status_code == 200


def test_identity_requests_are_refused_without_model_identification(client, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)

    async def should_not_run(*args):
        raise AssertionError("Identity query must not reach vision answer generation")

    monkeypatch.setattr(models, "chat", should_not_run)
    answer = api.post(
        f"/api/v1/sessions/{sid}/questions", json={"question": "Who is this person?"}
    ).json()
    assert answer["uncertain"] and "don't identify people" in answer["answer"]
