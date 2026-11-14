import asyncio
from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import StreamingResponse
from app.api.dependencies import read_upload
from app.core.config import settings
from app.core.errors import BackendError
from app.schemas import Language, SpeechRequest
from app.services.ai.speech import synthesize, transcribe
from app.services.ai.speech_stream import audio_frames
from app.services.ai.safety import UNKNOWN, blocked_text

router = APIRouter()


@router.post("/transcriptions")
async def transcription(audio: UploadFile = File(...), language: Language | None = Form(None)):
    content = await read_upload(audio)
    text, detected = await asyncio.to_thread(transcribe, content, language)
    return {"text": text, "language": detected}


@router.post("/synthesis")
async def synthesis(request: SpeechRequest):
    if request.provider == "gemini" and (request.language != "ar" or not settings.gemini_tts_enabled):
        raise BackendError("Gemini Arabic speech is not enabled", 503, "tts_unavailable")
    audio = await asyncio.to_thread(synthesize, request.text, request.language)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.post("/stream")
async def streamed_synthesis(request: SpeechRequest):
    if request.language != "ar" or not settings.gemini_tts_enabled:
        raise BackendError("Gemini Arabic speech is not enabled", 503, "tts_unavailable")
    text = UNKNOWN["ar"] if blocked_text(request.text) else request.text
    audio = audio_frames(text)
    try:
        first = await anext(audio)
    except Exception as exc:
        await audio.aclose()
        raise BackendError("Gemini speech is unavailable. Please try again.", 503, "tts_unavailable") from exc

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
