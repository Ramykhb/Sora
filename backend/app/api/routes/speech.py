import asyncio
from fastapi import APIRouter, File, Form, Response, UploadFile
from app.api.dependencies import read_upload
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
    audio = await asyncio.to_thread(synthesize, request.text, request.language)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
