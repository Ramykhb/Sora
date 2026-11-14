"""Small playable WAV chunks from Gemini PCM, without waiting for the whole answer."""
import asyncio
import base64
from io import BytesIO
import json
import wave

import httpx

from app.core.config import settings
from app.core.errors import BackendError
from app.services.ai import gemini_speech


async def _provider_pcm(text: str, model: str):
    key = settings.gemini_api_key.get_secret_value()
    total = 0
    completed = False
    async with httpx.AsyncClient(timeout=settings.gemini_tts_timeout_seconds) as client:
        async with client.stream(
            "POST", "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": key}, json=gemini_speech.speech_request(text, stream=True, model=model),
        ) as response:
            if response.is_error:
                await response.aread()
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    completed = True
                    break
                event = json.loads(data)
                if event.get("event_type") in {"error", "interaction.failed"}:
                    raise ValueError("Speech stream failed")
                delta = event.get("delta", {})
                if event.get("event_type") == "step.delta" and delta.get("type") == "audio":
                    encoded = delta.get("data", "")
                    if len(encoded) > 8 * 1024 * 1024:
                        raise ValueError("Oversized audio chunk")
                    chunk = base64.b64decode(encoded, validate=True)
                    total += len(chunk)
                    if total > 24000 * 2 * 120:
                        raise ValueError("Audio exceeds duration limit")
                    if chunk:
                        yield chunk
    if not total or not completed or total % 2:
        raise ValueError("Incomplete speech stream")


async def pcm_chunks(text: str):
    if not settings.gemini_tts_enabled or not settings.gemini_api_key.get_secret_value():
        raise BackendError("Gemini Arabic speech is not enabled", 503, "tts_unavailable")
    for model in gemini_speech.speech_models(include_blocked=True):
        cached = gemini_speech.cached_audio(text, model)
        if cached is not None:
            with wave.open(BytesIO(cached), "rb") as wav:
                while chunk := wav.readframes(2400):
                    yield chunk
            return
    async with asyncio.timeout(settings.gemini_tts_timeout_seconds):
        for model in gemini_speech.speech_models():
            pcm = bytearray()
            source = _provider_pcm(text, model)
            try:
                async for chunk in source:
                    pcm.extend(chunk)
                    yield chunk
            except httpx.HTTPStatusError as exc:
                # Never replay an answer prefix after playback has already begun.
                if pcm or exc.response.status_code not in {429, 503}:
                    raise
                gemini_speech.block_model(model)
                continue
            finally:
                await source.aclose()
            if len(text) <= 250:
                output = BytesIO()
                with wave.open(output, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(pcm)
                gemini_speech.cache_audio(text, output.getvalue(), model)
            return
    raise BackendError("Gemini speech is temporarily unavailable", 503, "tts_unavailable")


async def audio_frames(text: str):
    pending = bytearray()
    segment_bytes = 12000  # Quarter-second frames keep the queue ahead without a full-file wait.
    source = pcm_chunks(text)

    def frame(content: bytes) -> bytes:
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(content)
        return (json.dumps({"type": "audio", "data": base64.b64encode(output.getvalue()).decode()}) + "\n").encode()

    try:
        async for chunk in source:
            pending.extend(chunk)
            while len(pending) >= segment_bytes:
                yield frame(bytes(pending[:segment_bytes]))
                del pending[:segment_bytes]
        if pending:
            yield frame(bytes(pending))
        yield b'{"type":"done"}\n'
    finally:
        await source.aclose()
