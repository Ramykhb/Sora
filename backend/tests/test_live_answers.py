import asyncio
from datetime import timedelta
from uuid import UUID

import pytest

from app.core.config import settings
from app.db.models.frame import now
from app.schemas import QuestionRequest
from app.services.ai.assistant import answer_question
from app.services.ai.live_answer import is_overview, object_overview, walking_observation
from app.services.ai.safety import ROUTE_QUESTION, blocked_text
from app.services.ai.models import models
from app.services.frames.ingestion import session_lock
from app.services.streaming.session import streams
from test_api import create, image_bytes, upload


@pytest.mark.parametrize("question,expected", [
    ("What is in front of me?", True), ("What's in front of me?", True),
    ("what object is in front of me", True), ("what us in front of me?", True),
    ("What objects are in front of me right now?", True),
    ("Please tell me what is in front of me", True),
    ("What is that thing infront of me?", True),
    ("What do you see right now?", True), ("Qu’y a-t-il devant moi ?", True),
    ("What objects does the camera detect?", True), ("What does the camera detect?", True),
    ("ماذا يوجد أمامي؟", True), ("What color is the chair?", False),
    ("What was written on the sign?", False), ("Is it safe to walk?", False),
    ("What color is the object in front of me?", False),
    ("What text is on the thing in front of me?", False),
    ("What was in front of me earlier?", False),
])
def test_overview_intent_is_narrow_and_multilingual(question, expected):
    assert is_overview(question) is expected


@pytest.mark.parametrize("language,word", [("en", "chair"), ("fr", "chaise"), ("ar", "كرسي")])
def test_object_overview_translates_labels_and_never_invents_a_route(language, word):
    text = object_overview([
        {"label": "chair", "confidence": .9}, {"label": "chair", "confidence": .8},
        {"label": "door", "confidence": .99}, {"label": "dog", "confidence": .01},
    ], language)
    assert not text.startswith(("I'm not sure", "Je ne suis pas sûr", "لست متأكداً"))
    assert text.count(word) == 1
    assert "door" not in text and "dog" not in text


@pytest.mark.parametrize("question", [
    "What is in front of me?", "what object is in front of me", "what us in front of me?",
    "Is it safe to walk?", "Can I walk forward?", "Is the path clear?",
    "Are there any obstacles?", "Est-ce que je peux marcher ?",
    "Puis-je marcher ?", "هل يمكنني المشي؟",
])
def test_overview_responds_while_ocr_and_generative_inference_are_busy(client, monkeypatch, question):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = UUID(create(api))

    def forbidden(*args, **kwargs):
        raise AssertionError("A live overview must not call OCR or generative inference")

    for name in ["read_text", "analyze_image"]:
        monkeypatch.setattr(ingestion, name, forbidden)
    for name in ["chat", "embed", "describe"]:
        monkeypatch.setattr(models, name, forbidden)

    async def exercise():
        state = streams.start(sid, "test")
        state.observation_content = image_bytes()
        state.observation = {
            "captured_at": now().isoformat(), "expires_at": (now() + timedelta(seconds=2)).isoformat(),
            "detected_objects": [{"label": "chair", "confidence": .9, "box": [20, 20, 80, 95]}],
        }
        try:
            async with session_lock(sid), models.gate.slot(), asyncio.timeout(2):
                return await answer_question(sid, QuestionRequest(question=question, scope="recent"))
        finally:
            await streams.stop(sid)

    answer = api.portal.call(exercise)
    assert "chair" in answer.answer and answer.uncertain
    assert answer.evidence_frame_ids
    assert "evidence_expired_during_inference" not in answer.processing_warnings
    assert "current_view_timeout" not in answer.processing_warnings
    if ROUTE_QUESTION.search(question):
        assert "center" in answer.answer
        assert "obstructed" in answer.answer
    frames = api.get(f"/api/v1/sessions/{sid}/frames").json()
    assert frames[0]["enrichment_status"] == "skipped"
    assert frames[0]["ocr_text"] == ""
    assert frames[0]["id"] == answer.evidence_frame_ids[0]


def test_detailed_current_question_times_out_including_model_queue_wait(client, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)
    cancelled = []

    async def stalled(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(settings, "current_answer_timeout_seconds", .05)
    monkeypatch.setattr(models, "chat", stalled)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "What color is the chair?", "scope": "recent",
    })
    assert result.status_code == 200
    answer = result.json()
    assert answer["uncertain"] and not answer["evidence_frame_ids"]
    assert answer["processing_warnings"] == ["current_view_timeout"]
    assert cancelled


def test_no_detections_does_not_assert_an_empty_or_clear_scene():
    text = object_overview([], "en")
    assert "not establish" in text and "No supported objects" in text


@pytest.mark.parametrize("language,word,blocked", [
    ("en", "center", "obstructed"), ("fr", "centre", "obstrué"), ("ar", "الوسط", "مسدود"),
])
def test_walking_answer_flags_a_center_detection_as_an_obstruction(language, word, blocked):
    objects = [
        {"label": "chair", "confidence": .9, "box": [40, 20, 60, 95]},
        {"label": "person", "confidence": .9, "box": [0, 10, 20, 80]},
        {"label": "bottle", "confidence": .9, "box": [80, 20, 100, 70]},
    ]
    answer = walking_observation(objects, 100, language)
    assert word in answer and blocked in answer
    assert not blocked_text(answer)
    empty = walking_observation([], 100, language)
    assert not blocked_text(empty)
    assert "safe" not in empty.casefold()


def test_walking_answer_without_a_center_detection_stays_uncertain():
    side_only = [{"label": "person", "confidence": .9, "box": [0, 10, 20, 80]}]
    answer = walking_observation(side_only, 100, "en")
    assert "Not sure about the walking path" in answer
    assert "obstructed" not in answer


def test_walking_obstruction_reports_a_coarse_distance():
    answer = walking_observation([{"label": "chair", "confidence": .9, "box": [40, 20, 60, 95]}], 100, "en", 100)
    assert "obstructed" in answer and "about 1 meter away" in answer


def test_walking_obstruction_without_depth_says_distance_is_unclear():
    answer = walking_observation([{"label": "chair", "confidence": .9, "box": [40, 20, 60, 95]}], 100, "en")
    assert "obstructed" in answer and "distance unclear" in answer


def test_walking_question_never_uses_old_memory_even_when_memory_scope_is_selected(client):
    from sqlalchemy import update
    from app.db.models.frame import Frame

    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(
                captured_at=now() - timedelta(seconds=5),
            ))
            await db.commit()

    api.portal.call(age)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={
        "question": "Is it safe to walk?", "scope": "memory",
    }).json()
    assert result["uncertain"] and not result["evidence_frame_ids"]
    assert "recent camera view" in result["answer"]
