import asyncio
from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import StreamingResponse
from app.api.dependencies import read_upload
from app.core.auth import current_user
from app.core.config import settings
from app.core.errors import BackendError
from app.db.auth_models import User
from app.schemas import Language, SpeechRequest
from app.services.ai.speech import synthesize, transcribe
from app.services.ai.speech_stream import audio_frames, local_frames
from app.services.ai.safety import UNKNOWN, blocked_text

router = APIRouter()


@router.post("/transcriptions")
async def transcription(audio: UploadFile = File(...), language: Language | None = Form(None)):
    content = await read_upload(audio)
    text, detected = await asyncio.to_thread(transcribe, content, language)
    return {"text": text, "language": detected}


@router.post("/synthesis")
async def synthesis(request: SpeechRequest, user: User = Depends(current_user)):
    if request.provider == "gemini" and (request.language != "ar" or not settings.gemini_tts_enabled):
        raise BackendError("Gemini Arabic speech is not enabled", 503, "tts_unavailable")
    audio = await asyncio.to_thread(
        synthesize, request.text, request.language, request.provider == "fast", str(user.id)
    )
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


async def _started(source):
    """Wait for the first frame, so that a failing voice can still be replaced."""
    try:
        return source, await anext(source)
    except Exception as exc:
        await source.aclose()
        raise BackendError("Speech is unavailable. Please try again.", 503, "tts_unavailable") from exc


@router.post("/stream")
async def streamed_synthesis(request: SpeechRequest, user: User = Depends(current_user)):
    gemini = request.language == "ar" and settings.gemini_tts_enabled
    if not settings.supertonic_enabled and not gemini:
        raise BackendError("Streamed speech is not enabled", 503, "tts_unavailable")
    text = UNKNOWN[request.language] if blocked_text(request.text) else request.text
    started = None
    if settings.supertonic_enabled:
        try:
            started = await _started(local_frames(text, request.language, str(user.id)))
        except BackendError:
            if not gemini:
                raise
    audio, first = started or await _started(audio_frames(text))

    async def content():
        try:
            yield first
            async for chunk in audio:
                yield chunk
        finally:
            await audio.aclose()

    return StreamingResponse(content(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })
