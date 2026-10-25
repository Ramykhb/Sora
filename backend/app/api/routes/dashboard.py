from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import func, select
from app.db.models import Alert, CaptureSession, Feedback, Frame, ObjectDeletion, QuestionAnswer
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.sessions import get_session
from app.services.streaming.session import streams
from app.workers.retention import cleanup_once, reconcile_orphans

router = APIRouter()


@router.get("/dashboard")
async def overview(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    async with SessionFactory() as db:
        sessions = (
            await db.scalars(
                select(CaptureSession)
                .where(CaptureSession.expires_at > now())
                .order_by(CaptureSession.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        items = []
        for session in sessions:
            count = await db.scalar(
                select(func.count(Frame.id)).where(
                    Frame.session_id == session.id, Frame.expires_at > now()
                )
            )
            questions = await db.scalar(
                select(func.count(QuestionAnswer.id)).where(
                    QuestionAnswer.session_id == session.id, QuestionAnswer.expires_at > now()
                )
            )
            items.append(
                {
                    "session_id": str(session.id),
                    "language": session.language,
                    "status": session.status,
                    "created_at": session.created_at,
                    "frame_count": count,
                    "question_count": questions,
                    "live": streams.status(session.id),
                }
            )
        return {"sessions": items}


@router.get("/metrics")
async def metrics():
    async with SessionFactory() as db:
        frames, processing = (
            await db.execute(
                select(func.count(Frame.id), func.avg(Frame.processing_ms)).where(
                    Frame.expires_at > now()
                )
            )
        ).one()
        questions, latency = (
            await db.execute(
                select(func.count(QuestionAnswer.id), func.avg(QuestionAnswer.latency_ms)).where(
                    QuestionAnswer.expires_at > now()
                )
            )
        ).one()
        ratings = (
            await db.execute(
                select(Feedback.rating, func.count(Feedback.id))
                .join(QuestionAnswer, Feedback.question_id == QuestionAnswer.id)
                .where(QuestionAnswer.expires_at > now())
                .group_by(Feedback.rating)
            )
        ).all()
        pending = await db.scalar(select(func.count(ObjectDeletion.key)))
    return {
        "retained_frames": frames,
        "retained_questions": questions,
        "mean_frame_processing_ms": processing,
        "mean_question_latency_ms": latency,
        "feedback": dict(ratings),
        "pending_object_deletions": pending,
        "live_sessions": len(streams.states),
    }


@router.get("/sessions/{session_id}/alerts")
async def alerts(
    session_id: UUID, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    await get_session(session_id)
    async with SessionFactory() as db:
        rows = (
            await db.scalars(
                select(Alert)
                .join(Frame, Alert.frame_id == Frame.id)
                .where(Alert.session_id == session_id, Frame.expires_at > now())
                .order_by(Alert.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "frame_id": str(row.frame_id),
                "label": row.label,
                "message": row.message,
                "created_at": row.created_at,
            }
            for row in rows
        ]


@router.post("/maintenance/cleanup")
async def cleanup():
    return await cleanup_once()


@router.post("/maintenance/reconcile")
async def reconcile():
    return await reconcile_orphans()
