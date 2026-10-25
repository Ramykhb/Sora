import asyncio
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from app.api.dependencies import read_upload
from app.db.models import Feedback, QuestionAnswer
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import AnswerOut, FeedbackRequest, Language, QuestionRequest
from app.services.ai.assistant import answer_question
from app.services.ai.speech import synthesize, transcribe
from app.services.sessions import get_session

router = APIRouter()


@router.post("", response_model=AnswerOut)
async def ask(session_id: UUID, request: QuestionRequest):
    return await answer_question(session_id, request)


@router.post("/audio", response_model=AnswerOut)
async def ask_audio(
    session_id: UUID,
    audio: UploadFile = File(...),
    language: Language | None = Form(None),
    scope: Literal["auto", "recent", "memory"] = Form("auto"),
):
    await get_session(session_id)
    content = await read_upload(audio)
    text, detected_language = await asyncio.to_thread(transcribe, content, language)
    request = QuestionRequest(question=text, language=language or detected_language, scope=scope)
    return await answer_question(session_id, request, source="audio")


@router.get("", response_model=list[AnswerOut])
async def history(
    session_id: UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    await get_session(session_id)
    async with SessionFactory() as db:
        return list(
            (
                await db.scalars(
                    select(QuestionAnswer)
                    .where(
                        QuestionAnswer.session_id == session_id, QuestionAnswer.expires_at > now()
                    )
                    .order_by(QuestionAnswer.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )


async def get_question(session_id, question_id):
    await get_session(session_id)
    async with SessionFactory() as db:
        row = await db.scalar(
            select(QuestionAnswer).where(
                QuestionAnswer.id == question_id,
                QuestionAnswer.session_id == session_id,
                QuestionAnswer.expires_at > now(),
            )
        )
        if row is None:
            raise HTTPException(404, "Question not found or expired")
        return row


@router.get("/{question_id}", response_model=AnswerOut)
async def detail(session_id: UUID, question_id: UUID):
    return await get_question(session_id, question_id)


@router.get("/{question_id}/audio")
async def spoken_answer(session_id: UUID, question_id: UUID):
    row = await get_question(session_id, question_id)
    audio = await asyncio.to_thread(synthesize, row.answer, row.language)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.post("/{question_id}/feedback", status_code=201)
async def feedback(session_id: UUID, question_id: UUID, request: FeedbackRequest):
    await get_question(session_id, question_id)
    async with SessionFactory() as db:
        row = Feedback(question_id=question_id, **request.model_dump())
        db.add(row)
        await db.commit()
        return {"id": str(row.id), "rating": row.rating}
