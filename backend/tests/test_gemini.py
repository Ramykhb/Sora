import asyncio
import base64
from datetime import timedelta
import json
from time import monotonic
from uuid import UUID

import cv2
import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.schemas import QuestionRequest
from app.services.ai import gemini
from app.services.ai.assistant import answer_question
from app.services.frames import processing
from app.services.streaming.session import streams
from test_api import create, image_bytes, upload


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(settings, "gemini_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-private-key"))


def mock_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_protocol_uses_header_key_inline_image_and_short_structured_response(cloud, monkeypatch):
    def handle(request):
        assert request.headers["x-goog-api-key"] == "test-private-key"
        assert "test-private-key" not in str(request.url)
        body = json.loads(request.content)
        assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
        assert body["generationConfig"]["maxOutputTokens"] == 256
        assert base64.b64decode(body["contents"][0]["parts"][1]["inlineData"]["data"]) == b"sanitized-jpeg"
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"thought": True, "text": "private reasoning"},
            {"text": '{"answer":"A chair is visible.","uncertain":false}'},
        ]}}]})
    mock_transport(monkeypatch, handle)
    answer = asyncio.run(gemini.ask_image(b"sanitized-jpeg", "Describe the scene", "en"))
    assert answer.answer == "A chair is visible."


@pytest.mark.parametrize("status,payload", [(429, {"error": "test-private-key"}), (200, {"candidates": []}), (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]})])
def test_provider_errors_are_sanitized(cloud, monkeypatch, status, payload):
    mock_transport(monkeypatch, lambda request: httpx.Response(status, json=payload))
    with pytest.raises(BackendError) as error:
        asyncio.run(gemini.ask_image(b"jpeg", "Question", "en"))
    assert error.value.code == "gemini_unavailable"
    assert "test-private-key" not in error.value.message


def test_no_request_without_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    with pytest.raises(BackendError, match="not configured"):
        asyncio.run(gemini.ask_image(b"jpeg", "Question", "en"))


def test_cloud_path_skips_ocr_detector_and_model_gate_and_sends_blurred_pixels(client, cloud, monkeypatch):
    import app.services.frames.ingestion as ingestion
    from app.services.ai.models import models

    api, _ = client
    sid = UUID(create(api))
    def forbidden(*args, **kwargs):
        raise AssertionError("Cloud current-view analysis must not queue on local analysis")
    monkeypatch.setattr(ingestion, "read_text", forbidden)
    monkeypatch.setattr(ingestion, "analyze_image", forbidden)
    monkeypatch.setattr(processing, "face_regions", lambda image: [(20, 20, 80, 80)])
    async def ask(image, question, language):
        pixels = cv2.imdecode(np.frombuffer(image, np.uint8), 1)
        assert pixels[25:75, 25:75].std() < 10
        assert pixels[85:95, 85:95].std() > 20
        return gemini.GeminiAnswer(answer="A patterned surface is visible.", uncertain=False)
    monkeypatch.setattr(gemini, "ask_image", ask)
    async def exercise():
        state = streams.start(sid, "test")
        state.latest, state.latest_at = image_bytes(), now()
        try:
            async with ingestion.session_lock(sid), models.gate.slot():
                return await answer_question(sid, QuestionRequest(question="Describe the current scene in detail", scope="recent"))
        finally:
            await streams.stop(sid)
    answer = api.portal.call(exercise)
    assert answer.answer == "A patterned surface is visible."
    assert answer.evidence_frame_ids
    stored = api.get(f"/api/v1/sessions/{sid}/frames").json()[0]
    assert stored["id"] == answer.evidence_frame_ids[0]
    assert "face_blur" in stored["enhancements"]


@pytest.mark.parametrize("question", ["Describe the current scene in detail", "Is it safe to walk?"])
def test_cloud_deadline_uses_local_fallback_instead_of_slow_local_vlm(client, cloud, monkeypatch, question):
    api, _ = client
    sid = UUID(create(api))
    monkeypatch.setattr(settings, "gemini_deadline_seconds", 1.2)
    async def stall(*args):
        await asyncio.Event().wait()
    monkeypatch.setattr(gemini, "ask_image", stall)
    async def exercise():
        state = streams.start(sid, "test")
        state.latest, state.latest_at = image_bytes(), now()
        state.observation_content = state.latest
        state.observation = {"captured_at": now().isoformat(), "expires_at": (now() + timedelta(seconds=2)).isoformat(),
                             "width": 100, "height": 100, "detected_objects": [{"label": "chair", "confidence": .9, "box": [20, 20, 80, 95]}]}
        try:
            return await answer_question(sid, QuestionRequest(question=question, scope="recent"))
        finally:
            await streams.stop(sid)
    start = monotonic()
    answer = api.portal.call(exercise)
    assert monotonic() - start < 1.5
    assert "local_detection_fallback" in answer.processing_warnings
    assert answer.uncertain
    if question == "Is it safe to walk?":
        assert answer.answer.startswith("The path ahead looks obstructed")


def test_cloud_walking_answer_cannot_declare_route_safe(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)
    async def unsafe(*args):
        return gemini.GeminiAnswer(answer="The path is clear, walk forward safely.", uncertain=False)
    monkeypatch.setattr(gemini, "ask_image", unsafe)
    answer = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Is it safe to walk?", "scope": "recent"}).json()
    assert answer["uncertain"] is True
    assert "path is clear" not in answer["answer"] and "safely" not in answer["answer"]


@pytest.mark.parametrize("assessment,reason,uncertain,distance,prefix", [
    ("unobstructed", "The floor ahead is visible with no apparent obstacles.", False, None, "The visible path appears unobstructed."),
    ("blocked", "A chair occupies the center of the walkway.", False, "about_1m", "An obstacle or hazard is visible in the path, about 1 meter away."),
    ("blocked", "A closed door blocks the passage directly ahead; the floor is out of view.", False, "unknown", "An obstacle or hazard is visible in the path; its distance is unclear."),
    ("blocked", "A wall blocks the forward passage; the ground is not visible.", True, None, "An obstacle or hazard is visible in the path; its distance is unclear."),
    ("unknown", "Only a TV and wall are visible; the ground is out of view.", False, None, "Not sure from this view."),
    ("unobstructed", "The ground is partly obscured by glare.", True, None, "Not sure from this view."),
])
def test_walking_cloud_assessment_uses_image_reason_without_stock_disclaimer(
    client, cloud, monkeypatch, assessment, reason, uncertain, distance, prefix,
):
    api, _ = client
    sid = create(api)
    upload(api, sid)

    async def assess(image, question, language):
        assert image and question == "Is it safe to walk?"
        return gemini.GeminiAnswer(
            answer=reason, uncertain=uncertain, visible_path=assessment,
            visible_path_distance=distance,
        )

    monkeypatch.setattr(gemini, "ask_image", assess)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Is it safe to walk?"})
    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == prefix + " " + reason
    assert result["uncertain"] == (assessment == "unknown" or uncertain)
    assert result["evidence_frame_ids"]
    assert "cannot confirm the route" not in result["answer"]


@pytest.mark.parametrize("assessment", ["unobstructed", "blocked", "unknown", None, "safe"])
def test_walking_protocol_requires_valid_visible_path(cloud, monkeypatch, assessment):
    def handle(request):
        body = json.loads(request.content)
        schema = body["generationConfig"]["responseJsonSchema"]
        assert "visible_path" in schema["required"] and "visible_path_distance" in schema["required"]
        assert schema["properties"]["visible_path"]["enum"] == ["unobstructed", "blocked", "unknown"]
        assert "unknown" in schema["properties"]["visible_path_distance"]["enum"]
        prompt = body["systemInstruction"]["parts"][0]["text"]
        assert "ground/walking surface" in prompt and "body and head height" in prompt
        assert "closed door" in prompt and "takes precedence over missing ground" in prompt
        assert "BOTH the ground and forward passage" in prompt and "side wall" in prompt
        assert "visible_path_distance" in prompt and "Never state a precise distance" in prompt
        result = {"answer": "The ground is visible.", "uncertain": False}
        if assessment is not None:
            result["visible_path"] = assessment
            result["visible_path_distance"] = "about_1m"
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": json.dumps(result)},
        ]}}]})

    mock_transport(monkeypatch, handle)
    if assessment in {None, "safe"}:
        with pytest.raises(BackendError) as error:
            asyncio.run(gemini.ask_image(b"jpeg", "Is it safe to walk?", "en"))
        assert error.value.code == "gemini_unavailable"
    else:
        result = asyncio.run(gemini.ask_image(b"jpeg", "Is it safe to walk?", "en"))
        assert result.visible_path == assessment


def test_walking_protocol_requires_a_distance_band(cloud, monkeypatch):
    def handle(request):
        result = {"answer": "A chair blocks the way.", "uncertain": False, "visible_path": "blocked"}
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": json.dumps(result)},
        ]}}]})

    mock_transport(monkeypatch, handle)
    with pytest.raises(BackendError) as error:
        asyncio.run(gemini.ask_image(b"jpeg", "Is it safe to walk?", "en"))
    assert error.value.code == "gemini_unavailable"


@pytest.mark.parametrize("elapsed", [3, 7])
def test_walking_cloud_result_age_allows_inference_but_remains_bounded(client, cloud, monkeypatch, elapsed):
    from app.services.ai import assistant, cloud_view

    api, _ = client
    sid = create(api)
    upload(api, sid)
    offset = [0]

    def clock():
        return now() + timedelta(seconds=offset[0])

    monkeypatch.setattr(cloud_view, "now", clock)
    monkeypatch.setattr(assistant, "now", clock)
    monkeypatch.setattr(settings, "gemini_walking_max_age_seconds", 6)

    async def assess(*args):
        offset[0] = elapsed
        return gemini.GeminiAnswer(
            answer="A table occupies the center of the walkway.",
            uncertain=False, visible_path="blocked",
        )

    monkeypatch.setattr(gemini, "ask_image", assess)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Is it safe to walk?"}).json()
    if elapsed == 3:
        assert result["answer"].startswith("An obstacle or hazard is visible in the path")
        assert result["evidence_frame_ids"]
        assert not result["uncertain"]
        assert "local_detection_fallback" not in result["processing_warnings"]
    else:
        assert result["uncertain"]
        assert "gemini_evidence_stale" in result["processing_warnings"]
        assert "A table occupies" not in result["answer"]


def test_walking_cloud_rejects_old_input_before_sending_image(client, cloud, monkeypatch):
    from sqlalchemy import update
    from app.db.models import Frame

    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def age():
        async with factory() as db:
            await db.execute(update(Frame).where(Frame.id == UUID(frame["id"])).values(
                captured_at=now() - timedelta(seconds=3),
            ))
            await db.commit()

    api.portal.call(age)

    async def forbidden(*args):
        raise AssertionError("Walking input must still be fresh before inference")

    monkeypatch.setattr(gemini, "ask_image", forbidden)
    result = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Is it safe to walk?"}).json()
    assert result["uncertain"] and not result["evidence_frame_ids"]
    assert "gemini_evidence_stale" in result["processing_warnings"]


def test_identity_requests_never_reach_gemini(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    def forbidden(*args):
        raise AssertionError("No image should leave the server for identity questions")
    monkeypatch.setattr(gemini, "ask_image", forbidden)
    answer = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Who is this person?", "scope": "recent"}).json()
    assert "don't identify" in answer["answer"]


def test_privacy_failure_never_sends_unblurred_image(client, cloud, monkeypatch):
    from app.services.ai import live_answer

    api, _ = client
    sid = UUID(create(api))
    def privacy_failure(*args):
        raise BackendError("Face privacy unavailable", 503, "face_privacy_unavailable")
    def forbidden(*args):
        raise AssertionError("Unredacted images must never reach Google")
    monkeypatch.setattr(processing, "face_regions", privacy_failure)
    monkeypatch.setattr(gemini, "ask_image", forbidden)
    # The fallback uses an imported detector reference. Keep this privacy test
    # independent of real model downloads and inference timing.
    monkeypatch.setattr(live_answer, "detect_live", lambda _: (100, 100, []))
    async def exercise():
        state = streams.start(sid, "test")
        state.latest, state.latest_at = image_bytes(), now()
        try:
            with pytest.raises(BackendError, match="Face privacy"):
                await answer_question(sid, QuestionRequest(question="Describe the scene in detail", scope="recent"))
        finally:
            await streams.stop(sid)
    api.portal.call(exercise)
    assert api.get(f"/api/v1/sessions/{sid}/frames").json() == []


def test_memory_queries_stay_local(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    upload(api, sid)
    def forbidden(*args):
        raise AssertionError("Stored memory must not be sent to Google by this current-view feature")
    monkeypatch.setattr(gemini, "ask_image", forbidden)
    response = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "What did I see earlier?", "scope": "memory"})
    assert response.status_code == 200
