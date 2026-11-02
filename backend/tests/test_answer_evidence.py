import base64
from io import BytesIO
import json
from datetime import timedelta
from uuid import UUID

from PIL import Image
import pytest

from app.core.config import settings
from app.services.ai.models import ModelAnswer, models
from app.db.models.frame import Frame, now
from app.services.streaming.session import streams
from test_api import create, image_bytes


def test_multiple_retrieved_views_use_one_bounded_image_with_explicit_panel_mapping(client, monkeypatch):
    api, _ = client
    sid = create(api)
    frames = [api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }, data={"force": "true"}).json()["frame"] for _ in range(3)]

    async def inspect(messages, schema):
        message = messages[-1]
        context = json.loads(message["content"])["camera_observations"]
        assert len(message["images"]) == 1
        with Image.open(BytesIO(base64.b64decode(message["images"][0]))) as image:
            assert max(image.size) == settings.vision_image_max_side
        assert {item["frame_id"] for item in context} == {frame["id"] for frame in frames}
        assert [item["image_panel"] for item in context] == [1, 2, 3]
        return ModelAnswer(answer="An EXIT sign is visible.", uncertain=False,
                           evidence_frame_ids=[context[2]["frame_id"]])

    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What signs were visible earlier?", "scope": "memory",
    })
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"]


@pytest.mark.parametrize("question,text_only", [
    ("What was written on the sign?", True),
    ("Qu'est-ce qui était écrit ?", True),
    ("ما المكتوب على اللافتة؟", True),
    ("What color is the written text?", False),
    ("Where is the sign?", False),
])
def test_text_reading_uses_ocr_without_another_visual_encoding(client, monkeypatch, question, text_only):
    api, _ = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]

    async def inspect(messages, schema):
        message = messages[-1]
        assert bool(message["images"]) is not text_only
        context = json.loads(message["content"])["camera_observations"]
        assert context[0]["ocr"] == "EXIT"
        return ModelAnswer(answer="EXIT", uncertain=False, evidence_frame_ids=[frame["id"]])

    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": question, "scope": "memory"})
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"] == [frame["id"]]


@pytest.mark.parametrize("stream_age,expected_count", [(0, 2), (10, 1)])
def test_current_question_captures_a_fresh_stationary_view_but_never_retimes_old_evidence(client, stream_age, expected_count):
    from sqlalchemy import update

    api, factory = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]
    old_timestamp = now() - timedelta(minutes=1)

    async def prepare():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(captured_at=old_timestamp))
            await db.commit()
        state = streams.start(UUID(sid), "test")
        state.latest = image_bytes()
        state.latest_at = now() - timedelta(seconds=stream_age)

    api.portal.call(prepare)
    try:
        response = api.post(f"/api/v1/sessions/{sid}/questions", json={
            "question": "What is in front of me?", "scope": "recent",
        })
        assert response.status_code == 200
        frames = api.get(f"/api/v1/sessions/{sid}/frames").json()
        assert len(frames) == expected_count
        original = next(item for item in frames if item["id"] == frame["id"])
        assert original["captured_at"].startswith(old_timestamp.isoformat()[:19])
        if stream_age == 0:
            assert response.json()["evidence_frame_ids"] == [frames[0]["id"]]
            assert frames[0]["id"] != frame["id"]
        else:
            assert not response.json()["evidence_frame_ids"]
    finally:
        api.portal.call(streams.stop, UUID(sid))
