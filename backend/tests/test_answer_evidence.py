import base64
from io import BytesIO
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from PIL import Image
import pytest

from app.core.config import settings
from app.services.ai.models import ModelAnswer, models
from app.db.models.frame import Frame, now
from app.services.frames.privacy import PRIVACY_VERSION
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


def test_memory_reads_only_processed_image_without_preparing_it_again(client, monkeypatch):
    import app.services.ai.assistant as assistant
    import app.services.frames.processing as processing

    api, _ = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]
    keys = []
    stored_get = assistant.get_image

    def read(key):
        keys.append(key)
        return stored_get(key)

    def forbidden(*_args):
        raise AssertionError("Stored memory must not run prepare_image again")

    async def inspect(messages, _schema):
        assert messages[-1]["images"]
        context = json.loads(messages[-1]["content"])["camera_observations"]
        assert context[0]["image_panel"] == 1
        return ModelAnswer(answer="The saved image shows an EXIT sign.", uncertain=False,
                           evidence_frame_ids=[frame["id"]])

    monkeypatch.setattr(assistant, "get_image", read)
    monkeypatch.setattr(processing, "prepare_image", forbidden)
    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What shape was visible earlier?", "scope": "auto",
    })
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"] == [frame["id"]]
    assert len(keys) == 1 and keys[0].endswith(f'{frame["id"]}/processed.jpg')


def test_unverified_or_corrupt_memory_images_never_reach_model(client, monkeypatch):
    import app.services.ai.assistant as assistant

    api, factory = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]

    async def set_marker(enabled):
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.enhancements = [PRIVACY_VERSION] if enabled else []
            await db.commit()

    async def forbidden_chat(*_args):
        raise AssertionError("Unverified image must not reach the model")

    api.portal.call(set_marker, False)
    monkeypatch.setattr(assistant, "get_image", lambda _key: (_ for _ in ()).throw(AssertionError("No unverified read")))
    monkeypatch.setattr(models, "chat", forbidden_chat)
    unverified = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see earlier?", "scope": "memory",
    }).json()
    assert not unverified["evidence_frame_ids"]
    assert "evidence_privacy_unverified" in unverified["processing_warnings"]

    api.portal.call(set_marker, True)
    monkeypatch.setattr(assistant, "get_image", lambda _key: b"corrupt-jpeg")
    corrupt = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see earlier?", "scope": "memory",
    }).json()
    assert not corrupt["evidence_frame_ids"]
    assert "evidence_image_unavailable" in corrupt["processing_warnings"]

    async def clear_processed_key():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame["id"]))
            row.processed_object_key = ""
            await db.commit()

    api.portal.call(clear_processed_key)
    monkeypatch.setattr(assistant, "get_image", lambda _key: (_ for _ in ()).throw(AssertionError("No missing-key read")))
    missing = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see earlier?", "scope": "memory",
    }).json()
    assert not missing["evidence_frame_ids"]
    assert "evidence_image_unavailable" in missing["processing_warnings"]


def test_time_question_uses_only_matching_saved_frames_and_explicit_bounds_win(client, monkeypatch):
    from sqlalchemy import update

    api, factory = client
    sid = create(api)
    frames = [api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }, data={"force": "true"}).json()["frame"] for _ in range(2)]
    older, current = frames
    captured = now() - timedelta(minutes=5)

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(older["id"])).values(captured_at=captured))
            await db.commit()

    api.portal.call(age)
    seen = []

    async def inspect(messages, _schema):
        payload = json.loads(messages[-1]["content"])
        ids = [item["frame_id"] for item in payload["camera_observations"]]
        seen.append(ids)
        assert payload["scope"] == "memory"
        assert payload["camera_observations"][0]["captured_at"]
        assert payload["requested_time_window"]["since"]
        return ModelAnswer(answer="A saved image shows an EXIT sign.", uncertain=False,
                           evidence_frame_ids=ids)

    monkeypatch.setattr(models, "chat", inspect)
    first = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see five minutes ago?", "scope": "auto",
    }).json()
    assert first["evidence_frame_ids"] == [older["id"]]
    assert seen[0] == [older["id"]]
    current_time = datetime.fromisoformat(current["captured_at"]).replace(tzinfo=timezone.utc).isoformat()
    second_response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see five minutes ago?", "scope": "auto",
        "since": current_time, "until": current_time,
    })
    assert second_response.status_code == 200, second_response.json()
    second = second_response.json()
    assert second["evidence_frame_ids"] == [current["id"]]
    assert seen[1] == [current["id"]]


@pytest.mark.parametrize("has_yesterday_frame", [True, False])
def test_yesterday_question_uses_only_previous_day_or_reports_missing_memory(client, monkeypatch, has_yesterday_frame):
    from sqlalchemy import update
    import app.services.ai.assistant as assistant

    api, factory = client
    sid = create(api)
    current = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("current.png", image_bytes(), "image/png"),
    }, data={"force": "true"}).json()["frame"]
    yesterday = None
    if has_yesterday_frame:
        yesterday = api.post(f"/api/v1/sessions/{sid}/frames", files={
            "image": ("yesterday.png", image_bytes(), "image/png"),
        }, data={"force": "true"}).json()["frame"]
        captured = now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)

        async def age():
            async with factory() as db:
                await db.execute(update(Frame).where(Frame.id == UUID(yesterday["id"])).values(captured_at=captured))
                await db.commit()

        api.portal.call(age)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("Yesterday must never use a live camera answer")

    async def inspect(messages, _schema):
        assert yesterday is not None, "No current frame may answer a missing historical day"
        payload = json.loads(messages[-1]["content"])
        assert payload["scope"] == "memory"
        ids = [item["frame_id"] for item in payload["camera_observations"]]
        assert ids == [yesterday["id"]]
        return ModelAnswer(answer="Yesterday's image shows an EXIT sign.", uncertain=False,
                           evidence_frame_ids=ids)

    monkeypatch.setattr(assistant, "answer_overview", forbidden)
    monkeypatch.setattr(assistant, "answer_cloud_view", forbidden)
    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see yesterday?", "scope": "auto", "timezone": "UTC",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert current["id"] not in result["evidence_frame_ids"]
    if yesterday:
        assert result["evidence_frame_ids"] == [yesterday["id"]]
    else:
        assert result["uncertain"] and not result["evidence_frame_ids"]
        assert "don't have a saved image" in result["answer"]


def test_spatial_question_uses_fresh_evidence_without_time_clarification(client, monkeypatch):
    api, _ = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]

    async def inspect(messages, _schema):
        payload = json.loads(messages[-1]["content"])
        assert payload["scope"] == "recent"
        assert payload["requested_time_window"]["since"] is None
        assert payload["camera_observations"][0]["frame_id"] == frame["id"]
        return ModelAnswer(answer="A chair is visible beside the door.", uncertain=False,
                           evidence_frame_ids=[frame["id"]])

    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What is between the door and the chair?", "scope": "auto",
    })
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"] == [frame["id"]]
    assert "time_clarification_needed" not in response.json()["processing_warnings"]


def test_time_question_without_matching_image_does_not_use_current_frame(client, monkeypatch):
    api, _ = client
    sid = create(api)
    api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    })

    async def forbidden_chat(*_args):
        raise AssertionError("No out-of-window frame may reach the model")

    monkeypatch.setattr(models, "chat", forbidden_chat)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see five minutes ago?", "scope": "auto",
    }).json()
    assert response["evidence_frame_ids"] == []
    assert "don't have a saved image" in response["answer"]


def test_historical_obstacle_question_never_uses_live_detection(client, monkeypatch):
    import app.services.ai.assistant as assistant

    api, _ = client
    sid = create(api)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("A past obstacle question must not use a live view")

    monkeypatch.setattr(assistant, "answer_overview", forbidden)
    monkeypatch.setattr(assistant, "answer_cloud_view", forbidden)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What obstacles did I pass five minutes ago?", "scope": "auto",
    })
    assert response.status_code == 200
    assert not response.json()["evidence_frame_ids"]
    assert "saved image" in response.json()["answer"]


def test_ambiguous_clock_question_asks_for_clarification_without_model(client, monkeypatch):
    api, _ = client
    sid = create(api)

    async def forbidden_chat(*_args):
        raise AssertionError("Ambiguous time must not reach the model")

    monkeypatch.setattr(models, "chat", forbidden_chat)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see around 2:30?", "scope": "auto", "timezone": "Asia/Beirut",
    }).json()
    assert response["uncertain"] and not response["evidence_frame_ids"]
    assert "time_clarification_needed" in response["processing_warnings"]


def test_audio_question_accepts_device_timezone_for_clock_memory(client, monkeypatch):
    import app.api.routes.questions as questions

    api, _ = client
    sid = create(api)
    monkeypatch.setattr(questions, "transcribe", lambda *_args: ("What did I see around 2:30 PM?", "en"))
    response = api.post(f"/api/v1/sessions/{sid}/questions/audio", files={
        "audio": ("question.wav", b"audio", "audio/wav"),
    }, data={"timezone": "Asia/Beirut"})
    assert response.status_code == 200
    assert "time_clarification_needed" not in response.json()["processing_warnings"]
    assert "saved image" in response.json()["answer"]


def test_time_retrieval_prefers_frames_nearest_requested_moment(client, monkeypatch):
    from sqlalchemy import update

    api, factory = client
    sid = create(api)
    frames = [api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }, data={"force": "true"}).json()["frame"] for _ in range(3)]
    center = now() - timedelta(minutes=5)

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frames[0]["id"])).values(captured_at=center))
            await db.execute(update(Frame).where(Frame.id == UUID(frames[1]["id"])).values(captured_at=center + timedelta(seconds=45)))
            await db.commit()

    api.portal.call(age)

    async def inspect(messages, _schema):
        context = json.loads(messages[-1]["content"])["camera_observations"]
        assert [item["frame_id"] for item in context] == [frames[0]["id"], frames[1]["id"]]
        return ModelAnswer(answer="The first saved frame shows an EXIT sign.", uncertain=False,
                           evidence_frame_ids=[frames[0]["id"]])

    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What did I see five minutes ago?", "scope": "auto",
    })
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"] == [frames[0]["id"]]


def test_time_based_text_question_uses_retained_ocr_without_loading_image(client, monkeypatch):
    import app.services.ai.assistant as assistant
    from sqlalchemy import update

    api, factory = client
    sid = create(api)
    frame = api.post(f"/api/v1/sessions/{sid}/frames", files={
        "image": ("test.png", image_bytes(), "image/png"),
    }).json()["frame"]

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(captured_at=now() - timedelta(minutes=5)))
            await db.commit()

    api.portal.call(age)
    monkeypatch.setattr(assistant, "get_image", lambda _key: (_ for _ in ()).throw(AssertionError("OCR needs no image")))

    async def inspect(messages, _schema):
        assert messages[-1]["images"] == []
        context = json.loads(messages[-1]["content"])["camera_observations"]
        assert context[0]["ocr"] == "EXIT"
        return ModelAnswer(answer="The saved sign reads EXIT.", uncertain=False,
                           evidence_frame_ids=[frame["id"]])

    monkeypatch.setattr(models, "chat", inspect)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What was written on the sign five minutes ago?", "scope": "auto",
    })
    assert response.status_code == 200
    assert response.json()["evidence_frame_ids"] == [frame["id"]]


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
@pytest.mark.parametrize("question", ["What is in front of me?", "What's around me?"])
def test_current_question_captures_a_fresh_stationary_view_but_never_retimes_old_evidence(client, stream_age, expected_count, question):
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
            "question": question, "scope": "auto",
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
