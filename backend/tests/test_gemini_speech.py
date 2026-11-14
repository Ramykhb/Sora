import base64
from io import BytesIO
import json
import wave

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.core.errors import BackendError
from app.services.ai import gemini_speech, speech


def wav_bytes():
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 2400)
    return output.getvalue()


@pytest.fixture(autouse=True)
def cloud(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-private-key"))
    monkeypatch.setattr(settings, "gemini_tts_enabled", True)
    monkeypatch.setattr(settings, "gemini_tts_model", "gemini-3.8-flash-tts")
    monkeypatch.setattr(settings, "gemini_tts_voice", "Aoede")
    gemini_speech._cache.clear()
    gemini_speech._blocked_models.clear()


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(gemini_speech.httpx, "Client", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))


def response(audio=None):
    return {"status": "completed", "steps": [{"type": "model_output", "content": [{
        "type": "audio", "data": base64.b64encode(audio or wav_bytes()).decode(),
    }]}]}


def test_female_lebanese_speech_uses_header_key_and_verbatim_transcript(monkeypatch):
    def handle(request):
        assert request.url.path == "/v1beta/interactions"
        assert request.headers["x-goog-api-key"] == "test-private-key"
        assert "test-private-key" not in str(request.url)
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["generation_config"]["speech_config"] == [{"voice": "Aoede"}]
        content = body["input"][0]["content"][0]
        assert content["text"] == "اِبْدَأْ البث"
        assert "Lebanese" in content["annotations"][0]["style"]
        assert "female" in content["annotations"][0]["style"]
        return httpx.Response(200, json=response())
    transport(monkeypatch, handle)
    assert speech.synthesize("اِبْدَأْ البث", "ar") == wav_bytes()


def test_short_prompts_are_cached_but_changing_voice_invalidates_cache(monkeypatch):
    calls = []
    transport(monkeypatch, lambda request: calls.append(request) or httpx.Response(200, json=response()))
    for _ in range(2):
        gemini_speech.synthesize_arabic("مرحبا")
    assert len(calls) == 1
    monkeypatch.setattr(settings, "gemini_tts_voice", "Kore")
    gemini_speech.synthesize_arabic("مرحبا")
    assert len(calls) == 2


@pytest.mark.parametrize("status,payload", [
    (429, {"error": "test-private-key"}),
    (200, {"status": "failed"}),
    (200, {"status": "completed", "steps": []}),
    (200, response(b"invalid-wave")),
])
def test_provider_errors_and_invalid_audio_are_sanitized(monkeypatch, status, payload):
    transport(monkeypatch, lambda request: httpx.Response(status, json=payload))
    with pytest.raises(BackendError) as error:
        gemini_speech.synthesize_arabic("مرحبا")
    assert error.value.code == "tts_unavailable"
    assert "test-private-key" not in error.value.message


def test_missing_key_does_not_return_previously_cached_audio(monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json=response()))
    gemini_speech.synthesize_arabic("مرحبا")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(""))
    with pytest.raises(BackendError, match="not configured"):
        gemini_speech.synthesize_arabic("مرحبا")


def test_rate_limited_model_uses_same_voice_on_fallback_and_cools_down(monkeypatch):
    calls = []
    def handle(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        assert body["generation_config"]["speech_config"] == [{"voice": "Aoede"}]
        if body["model"] == settings.gemini_tts_model:
            return httpx.Response(429, json={"error": {"code": "too_many_requests"}})
        return httpx.Response(200, json=response())
    transport(monkeypatch, handle)
    assert gemini_speech.synthesize_arabic("مرحبا") == wav_bytes()
    assert calls == [settings.gemini_tts_model, settings.gemini_tts_fallback_model]
    assert gemini_speech.synthesize_arabic("مرحبا") == wav_bytes()
    assert len(calls) == 2
    gemini_speech.synthesize_arabic("ابدأ البث")
    assert calls[-1] == settings.gemini_tts_fallback_model
    assert len(calls) == 3


def test_existing_speech_safety_filter_runs_before_cloud_synthesis(monkeypatch):
    heard = []
    monkeypatch.setattr(gemini_speech, "synthesize_arabic", lambda text: heard.append(text) or b"wav")
    assert speech.synthesize("الطريق آمن", "ar") == b"wav"
    assert heard == ["لا تتوفر صور واضحة كافية للإجابة."]


def test_english_and_disabled_cloud_keep_existing_local_synthesis(monkeypatch):
    calls = []
    monkeypatch.setattr(speech.shutil, "which", lambda _: "espeak-ng")
    class Result:
        stdout = b"local-wave"
    monkeypatch.setattr(speech.subprocess, "run", lambda *args, **kwargs: calls.append(args) or Result())
    assert speech.synthesize("Hello", "en") == b"local-wave"
    monkeypatch.setattr(settings, "gemini_tts_enabled", False)
    assert speech.synthesize("مرحبا", "ar") == b"local-wave"
    assert len(calls) == 2
