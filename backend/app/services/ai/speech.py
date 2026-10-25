from functools import lru_cache
from io import BytesIO
import shutil
import subprocess
import threading
from app.core.config import settings
from app.core.errors import BackendError

_whisper_lock = threading.Lock()


@lru_cache
def whisper():
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.whisper_model, device="cpu", compute_type=settings.whisper_compute_type
    )


def decode_audio_bounded(content: bytes):
    try:
        import av
    except ImportError as exc:
        raise BackendError("Audio runtime is not installed", 503, "media_unavailable") from exc
    import numpy as np

    parts, count = [], 0
    try:
        with av.open(BytesIO(content)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for decoded in container.decode(audio=0):
                for frame in resampler.resample(decoded):
                    chunk = frame.to_ndarray().reshape(-1)
                    count += len(chunk)
                    if count > settings.max_audio_seconds * 16000:
                        raise BackendError("Audio exceeds duration limit", 413, "audio_limit")
                    parts.append(chunk)
            for frame in resampler.resample(None):
                chunk = frame.to_ndarray().reshape(-1)
                count += len(chunk)
                parts.append(chunk)
        if count > settings.max_audio_seconds * 16000:
            raise BackendError("Audio exceeds duration limit", 413, "audio_limit")
        if count < 1600:
            raise BackendError("Audio is too short", 422, "invalid_audio")
        return np.concatenate(parts).astype(np.float32) / 32768.0
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError("Could not decode the audio upload", 422, "invalid_audio") from exc


def transcribe(content: bytes, language: str | None = None) -> tuple[str, str]:
    samples = decode_audio_bounded(content)
    try:
        with _whisper_lock:
            segments, info = whisper().transcribe(
                samples,
                language=language,
                vad_filter=True,
                beam_size=3,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise BackendError("No speech could be recognized", 422, "no_speech")
        if info.language not in {"en", "fr", "ar"}:
            raise BackendError("Please use English, French, or Arabic", 422, "language_unsupported")
        return text[:2000], info.language
    except BackendError:
        raise
    except Exception as exc:
        raise BackendError(
            "Speech recognition failed; check Whisper model installation", 503, "speech_unavailable"
        ) from exc


def synthesize(text: str, language: str) -> bytes:
    if language not in {"en", "fr", "ar"}:
        raise BackendError("Unsupported speech language", 422, "language_unsupported")
    from app.services.ai.safety import UNKNOWN, blocked_text

    if blocked_text(text):
        text = UNKNOWN[language]
    binary = shutil.which(settings.espeak_binary)
    if not binary:
        raise BackendError("eSpeak NG is not installed", 503, "tts_unavailable")
    try:
        result = subprocess.run(
            [binary, "--stdout", "--stdin", "-v", language, "-s", "155"],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
            timeout=20,
        )
        return result.stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise BackendError("Speech synthesis failed", 503, "tts_unavailable") from exc
