"""Server-only Arabic speech, with a bounded in-memory cache of short prompts."""
import base64
from collections import OrderedDict
from io import BytesIO
import threading
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


def synthesize_arabic(text: str) -> bytes:
    key = settings.gemini_api_key.get_secret_value()
    if not key:
        raise BackendError("Gemini speech is not configured", 503, "tts_unavailable")
    cache_key = (settings.gemini_tts_model, settings.gemini_tts_voice, text)
    with _cache_lock:
        if cache_key in _cache:
            _cache.move_to_end(cache_key)
            return _cache[cache_key]
    try:
        with httpx.Client(timeout=settings.gemini_tts_timeout_seconds) as client:
            response = client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key},
                json={
                    "model": settings.gemini_tts_model,
                    "store": False,
                    "input": [{"type": "user_input", "content": [{
                        "type": "text", "text": text,
                        "annotations": [{"type": "speech_metadata", "style": STYLE}],
                    }]}],
                    "response_format": {"type": "audio", "mime_type": "audio/wav"},
                    "generation_config": {"speech_config": [{"voice": settings.gemini_tts_voice}]},
                },
            )
            response.raise_for_status()
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
    except (httpx.HTTPError, ValueError, KeyError, TypeError, wave.Error, EOFError) as exc:
        raise BackendError("Gemini speech is unavailable. Please try again.", 503, "tts_unavailable") from exc
    # Repeated app prompts stay quick; long answers aren't retained in the cache.
    if len(text) <= 250 and len(audio) <= _CACHE_BYTES:
        with _cache_lock:
            _cache[cache_key] = audio
            _cache.move_to_end(cache_key)
            while sum(map(len, _cache.values())) > _CACHE_BYTES:
                _cache.popitem(last=False)
    return audio
