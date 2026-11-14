"""Server-only Arabic speech, with a bounded in-memory cache of short prompts."""
import base64
from collections import OrderedDict
from io import BytesIO
import logging
import threading
from time import monotonic
import wave

import httpx

from app.core.config import settings
from app.core.errors import BackendError

STYLE = (
    "A warm, natural female voice with a Lebanese Arabic accent, conversational and clear. "
    "Read the supplied Arabic text verbatim; do not translate, paraphrase, or add words. "
    "Use a comfortable conversational pace. Pronounce the imperative ابدأ as ib-daʔ "
    "(اِبْدَأْ), never أبداً (abadan)."
)
_cache: OrderedDict[tuple[str, str, str], bytes] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_BYTES = 8 * 1024 * 1024
_blocked_models: dict[str, float] = {}
logger = logging.getLogger(__name__)


def cached_audio(text: str, model: str | None = None) -> bytes | None:
    cache_key = (model or settings.gemini_tts_model, settings.gemini_tts_voice, text)
    with _cache_lock:
        audio = _cache.get(cache_key)
        if audio is not None:
            _cache.move_to_end(cache_key)
        return audio


def cache_audio(text: str, audio: bytes, model: str | None = None):
    if len(text) <= 250 and len(audio) <= _CACHE_BYTES:
        cache_key = (model or settings.gemini_tts_model, settings.gemini_tts_voice, text)
        with _cache_lock:
            _cache[cache_key] = audio
            _cache.move_to_end(cache_key)
            while sum(map(len, _cache.values())) > _CACHE_BYTES:
                _cache.popitem(last=False)


def speech_models(*, include_blocked: bool = False) -> list[str]:
    models = list(dict.fromkeys(filter(None, [settings.gemini_tts_model, settings.gemini_tts_fallback_model])))
    with _cache_lock:
        return [model for model in models if include_blocked or _blocked_models.get(model, 0) <= monotonic()]


def block_model(model: str):
    # Avoid retrying a rejected model on every app confirmation and question.
    with _cache_lock:
        _blocked_models[model] = monotonic() + 60


def speech_request(text: str, *, stream: bool = False, model: str | None = None):
    return {
        "model": model or settings.gemini_tts_model,
        "store": False,
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": STYLE}],
        }]}],
        "response_format": {"type": "audio", "mime_type": "audio/l16" if stream else "audio/wav"},
        "generation_config": {"speech_config": [{"voice": settings.gemini_tts_voice}]},
        **({"stream": True} if stream else {}),
    }


def synthesize_arabic(text: str) -> bytes:
    key = settings.gemini_api_key.get_secret_value()
    if not key:
        raise BackendError("Gemini speech is not configured", 503, "tts_unavailable")
    for model in speech_models(include_blocked=True):
        cached = cached_audio(text, model)
        if cached is not None:
            return cached
    try:
        for model in speech_models():
            try:
                with httpx.Client(timeout=settings.gemini_tts_timeout_seconds) as client:
                    response = client.post(
                        "https://generativelanguage.googleapis.com/v1beta/interactions",
                        headers={"x-goog-api-key": key}, json=speech_request(text, model=model),
                    )
                    if response.status_code in {429, 503}:
                        block_model(model)
                        logger.warning("Gemini speech model rejected request: model=%s status=%s", model, response.status_code)
                        continue
                    response.raise_for_status()
            except httpx.TransportError as exc:
                block_model(model)
                logger.warning("Gemini speech connection failed: model=%s reason=%s", model, type(exc).__name__)
                continue
            payload = response.json()
            if payload.get("status") != "completed":
                raise ValueError("Incomplete speech response")
            blocks = [
                block for step in payload.get("steps", []) if step.get("type") == "model_output"
                for block in step.get("content", []) if block.get("type") == "audio"
            ]
            if not blocks or len(blocks[-1].get("data", "")) > 12 * 1024 * 1024:
                raise ValueError("Missing or oversized audio")
            audio = base64.b64decode(blocks[-1]["data"], validate=True)
            with wave.open(BytesIO(audio), "rb") as wav:
                if wav.getnframes() == 0 or wav.getnframes() / wav.getframerate() > 120:
                    raise ValueError("Invalid audio duration")
            cache_audio(text, audio, model)
            return audio
        raise ValueError("All speech models are temporarily unavailable")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, wave.Error, EOFError) as exc:
        raise BackendError("Gemini speech is unavailable. Please try again.", 503, "tts_unavailable") from exc
