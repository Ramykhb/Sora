"""On-server Arabic, French, and English speech with Supertonic 3."""
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
import logging
import os
import re
import threading
import wave

from app.core.config import settings
from app.core.errors import BackendError
from app.services.ai.speech_text import spoken_text

logger = logging.getLogger(__name__)
_FIRST_LIMIT = 80  # A short opening segment lets playback start sooner.
_SEGMENT_LIMIT = 160
_CACHE_BYTES = 16 * 1024 * 1024
_cache: OrderedDict[tuple[str, int, str, str], bytes] = OrderedDict()
_cache_lock = threading.Lock()
_engine_lock = threading.Lock()


def threads() -> int:
    # Six threads generated speech about 30% faster than ONNX Runtime's own choice.
    return settings.supertonic_threads or min(6, os.cpu_count() or 1)


@lru_cache
def engine():
    from supertonic import TTS

    # Weights come from scripts.prepare_models; a request never waits for a download.
    if not (settings.supertonic_model_dir / "onnx").is_dir():
        raise FileNotFoundError("Supertonic weights are not prepared")
    return TTS(
        model_dir=settings.supertonic_model_dir, auto_download=False,
        intra_op_num_threads=threads(),
    )


def ready() -> bool:
    from importlib.util import find_spec

    return bool(find_spec("supertonic")) and (settings.supertonic_model_dir / "onnx").is_dir()


def prepare():
    directory = settings.supertonic_model_dir
    # The downloader replaces its target folder, so it must be dedicated to this model.
    if directory.is_dir() and any(directory.iterdir()) and not (directory / "onnx").is_dir():
        raise RuntimeError("SUPERTONIC_MODEL_DIR must be a new or empty folder")
    from supertonic import TTS

    directory.parent.mkdir(parents=True, exist_ok=True)
    TTS(model_dir=directory, auto_download=True)


def synthesize(text: str, language: str) -> bytes:
    """Return a mono 16-bit WAV, or raise so that another voice can be used."""
    voice, steps = settings.supertonic_voice, settings.supertonic_steps
    key = (voice, steps, language, text)
    with _cache_lock:
        if (cached := _cache.get(key)) is not None:
            _cache.move_to_end(key)
            return cached
    try:
        with _engine_lock:  # One synthesis at a time keeps CPU use predictable.
            tts = engine()
            words = spoken_text(text, language)
            _, unsupported = tts.model.text_processor.validate_text(words)
            spoken = " ".join(words.translate({ord(char): " " for char in unsupported}).split())
            if not spoken:
                raise ValueError("No speakable text")
            samples, _ = tts.synthesize(
                spoken, voice_style=tts.get_voice_style(voice), total_steps=steps, lang=language,
            )
        pcm = (samples.reshape(-1).clip(-1, 1) * 32767).astype("<i2").tobytes()
        output = BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(tts.sample_rate)
            wav.writeframes(pcm)
        audio = output.getvalue()
    except Exception as exc:
        logger.warning("Supertonic speech failed: reason=%s", type(exc).__name__)
        raise BackendError("Speech synthesis failed", 503, "tts_unavailable") from exc
    if len(text) <= 250 and len(audio) <= _CACHE_BYTES:
        with _cache_lock:
            _cache[key] = audio
            while sum(map(len, _cache.values())) > _CACHE_BYTES:
                _cache.popitem(last=False)
    return audio


def _cut(text: str, limit: int, earliest: bool) -> int:
    """Where to split: a pause within the limit (the first one to start sooner), else a space."""
    pauses = [match.end() for match in re.finditer(r"[,،;؛:](?=\s)", text[:limit])]
    pauses = [end for end in pauses if end >= 12]
    if pauses:
        return pauses[0 if earliest else -1]
    space = text.rfind(" ", 0, limit + 1)
    return space if space > 0 else limit


def segments(text: str) -> list[str]:
    """Split an answer into sentences small enough to generate while earlier ones play."""
    parts: list[str] = []
    marker = ""
    for piece in re.split(r"(?<=[.!?؟…])\s+|\n+", text):
        piece = f"{marker} {piece}".strip()
        marker = ""
        if re.fullmatch(r"\d+\.", piece):  # Keep a list number with its step.
            marker = piece
            continue
        while piece:
            limit = _SEGMENT_LIMIT if parts else _FIRST_LIMIT
            if len(piece) <= limit:
                parts.append(piece)
                break
            end = _cut(piece, limit, earliest=not parts)
            parts.append(piece[:end].strip())
            piece = piece[end:].strip()
    if marker:
        parts.append(marker)
    return parts
