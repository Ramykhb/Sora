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


def test_cloud_deadline_uses_local_fallback_instead_of_slow_local_vlm(client, cloud, monkeypatch):
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
            return await answer_question(sid, QuestionRequest(question="Describe the current scene in detail", scope="recent"))
        finally:
            await streams.stop(sid)
    start = monotonic()
    answer = api.portal.call(exercise)
    assert monotonic() - start < 1.5
    assert "local_detection_fallback" in answer.processing_warnings
    assert answer.uncertain


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


def test_identity_requests_never_reach_gemini(client, cloud, monkeypatch):
    api, _ = client
    sid = create(api)
    def forbidden(*args):
        raise AssertionError("No image should leave the server for identity questions")
    monkeypatch.setattr(gemini, "ask_image", forbidden)
    answer = api.post(f"/api/v1/sessions/{sid}/questions", json={"question": "Who is this person?", "scope": "recent"}).json()
    assert "don't identify" in answer["answer"]


def test_privacy_failure_never_sends_unblurred_image(client, cloud, monkeypatch):
    api, _ = client
    sid = UUID(create(api))
    def privacy_failure(*args):
        raise BackendError("Face privacy unavailable", 503, "face_privacy_unavailable")
    def forbidden(*args):
        raise AssertionError("Unredacted images must never reach Google")
    monkeypatch.setattr(processing, "face_regions", privacy_failure)
    monkeypatch.setattr(gemini, "ask_image", forbidden)
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
