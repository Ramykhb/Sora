import asyncio
import base64
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.ai import gemini_speech, speech_stream


@pytest.fixture(autouse=True)
def cloud(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-private-key"))
    monkeypatch.setattr(settings, "gemini_tts_enabled", True)
    gemini_speech._cache.clear()


def events(pcm):
    delta = {"event_type": "step.delta", "delta": {
        "type": "audio", "data": base64.b64encode(pcm).decode(),
    }}
    return ("event: step.delta\ndata: " + json.dumps(delta) + "\n\ndata: [DONE]\n\n").encode()


def test_pcm_stream_protocol_and_completed_prompt_cache(monkeypatch):
    pcm = b"\x00\x00" * 2400
    calls = []
    def handle(request):
        calls.append(request)
        assert request.headers["x-goog-api-key"] == "test-private-key"
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["response_format"]["mime_type"] == "audio/l16"
        return httpx.Response(200, content=events(pcm))
    original = httpx.AsyncClient
    monkeypatch.setattr(speech_stream.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    async def consume():
        return b"".join([chunk async for chunk in speech_stream.pcm_chunks("مرحبا")])
    assert asyncio.run(consume()) == pcm
    assert asyncio.run(consume()) == pcm
    assert len(calls) == 1


def test_pcm_is_yielded_before_provider_finishes(monkeypatch):
    async def exercise():
        finish = asyncio.Event()
        class Audio(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield events(b"\x00\x00" * 2400).split(b"data: [DONE]")[0]
                await finish.wait()
                yield b"data: [DONE]\n\n"
        original = httpx.AsyncClient
        monkeypatch.setattr(speech_stream.httpx, "AsyncClient", lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Audio())), **kwargs,
        ))
        audio = speech_stream.pcm_chunks("مرحبا")
        first = await asyncio.wait_for(anext(audio), 1)
        assert len(first) == 4800
        assert not finish.is_set()
        finish.set()
        assert [chunk async for chunk in audio] == []
    asyncio.run(exercise())


def test_incomplete_provider_stream_is_not_cached(monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(speech_stream.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=events(b"\x00\x00").split(b"data: [DONE]")[0])),
        **kwargs,
    ))
    async def consume():
        return [chunk async for chunk in speech_stream.pcm_chunks("مرحبا")]
    with pytest.raises(ValueError, match="Incomplete"):
        asyncio.run(consume())
    assert gemini_speech.cached_audio("مرحبا") is None


def test_playable_wav_frames_arrive_before_generation_finishes(monkeypatch):
    from io import BytesIO
    import wave
    async def exercise():
        stopped = asyncio.Event()
        async def pcm(_):
            try:
                yield b"\x00\x00" * 12000
                await asyncio.Event().wait()
            finally:
                stopped.set()
        monkeypatch.setattr(speech_stream, "pcm_chunks", pcm)
        audio = speech_stream.audio_frames("مرحبا")
        first = json.loads(await asyncio.wait_for(anext(audio), 1))
        with wave.open(BytesIO(base64.b64decode(first["data"])), "rb") as wav:
            assert wav.getnframes() == 6000
            assert wav.getframerate() == 24000
        assert not stopped.is_set()
        await audio.aclose()
        assert stopped.is_set()
    asyncio.run(exercise())


def test_authenticated_stream_filters_speech_and_emits_progressively(client, monkeypatch):
    from app.api.routes import speech
    api, _ = client
    heard = []
    async def audio(text):
        heard.append(text)
        yield b'{"type":"audio","data":"first"}\n'
        yield b'{"type":"done"}\n'
    monkeypatch.setattr(speech, "audio_frames", audio)
    response = api.post("/api/v1/speech/stream", json={"text": "الطريق آمن", "language": "ar"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert len(response.content.splitlines()) == 2
    assert heard == ["لا تتوفر صور واضحة كافية للإجابة."]
    assert api.post("/api/v1/speech/stream", json={"text": "Hello", "language": "en"}).status_code == 503
    assert api.post("/api/v1/speech/stream", json={"text": "مرحبا", "language": "ar"}, headers={"Authorization": ""}).status_code == 401


def test_disabled_speech_does_not_start_generation(client, monkeypatch):
    api, _ = client
    monkeypatch.setattr(settings, "gemini_tts_enabled", False)
    assert api.post("/api/v1/speech/stream", json={"text": "مرحبا", "language": "ar"}).status_code == 503
