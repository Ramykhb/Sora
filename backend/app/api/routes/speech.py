import asyncio
from fastapi import APIRouter, File, Form, Response, UploadFile
from app.api.dependencies import read_upload
from app.core.config import settings
from app.core.errors import BackendError
from app.schemas import Language, SpeechRequest
from app.services.ai.speech import synthesize, transcribe

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
