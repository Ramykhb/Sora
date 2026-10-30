from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from app.core.auth import current_user, owned_session, require_admin
from app.db.auth_models import User
from app.db.models import Alert, CaptureSession, Feedback, Frame, ObjectDeletion, QuestionAnswer
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.sessions import get_session
from app.services.streaming.session import streams
from app.workers.retention import cleanup_once, reconcile_orphans

router = APIRouter()


@router.get("/dashboard")
async def overview(
    limit: int = Query(50, ge=1, le=200),
    own_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
):
    async with SessionFactory() as db:
        sessions = (
            await db.scalars(
                select(CaptureSession)
                .where(
                    CaptureSession.expires_at > now(),
                    True
                    if user.role == "admin" and not own_only
                    else CaptureSession.owner_id == user.id,
                )
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


@router.get("/dashboard/statistics")
@router.get("/metrics")
async def metrics(own_only: bool = Query(False), user: User = Depends(current_user)):
    async with SessionFactory() as db:
        owned_ids = select(CaptureSession.id).where(CaptureSession.expires_at > now())
        if user.role != "admin" or own_only:
            owned_ids = owned_ids.where(CaptureSession.owner_id == user.id)
        ids = list((await db.scalars(owned_ids)).all())
        frames, processing = (
            await db.execute(
                select(func.count(Frame.id), func.avg(Frame.processing_ms)).where(
                    Frame.expires_at > now(), Frame.session_id.in_(ids)
                )
            )
        ).one()
        questions, latency = (
            await db.execute(
                select(func.count(QuestionAnswer.id), func.avg(QuestionAnswer.latency_ms)).where(
                    QuestionAnswer.expires_at > now(), QuestionAnswer.session_id.in_(ids)
                )
            )
        ).one()
        ratings = (
            await db.execute(
                select(Feedback.rating, func.count(Feedback.id))
                .join(QuestionAnswer, Feedback.question_id == QuestionAnswer.id)
                .where(QuestionAnswer.expires_at > now(), QuestionAnswer.session_id.in_(ids))
                .group_by(Feedback.rating)
            )
        ).all()
        pending = (
            await db.scalar(select(func.count(ObjectDeletion.key)))
            if user.role == "admin" and not own_only
            else None
        )
    return {
        "retained_frames": frames,
        "retained_questions": questions,
        "mean_frame_processing_ms": processing,
        "mean_question_latency_ms": latency,
        "feedback": dict(ratings),
        "pending_object_deletions": pending,
        "live_sessions": sum(sid in streams.states for sid in ids),
    }


@router.get("/sessions/{session_id}/alerts", dependencies=[Depends(owned_session)])
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


@router.post("/maintenance/cleanup", dependencies=[Depends(require_admin)])
async def cleanup():
    return await cleanup_once()


@router.post("/maintenance/reconcile", dependencies=[Depends(require_admin)])
async def reconcile():
    return await reconcile_orphans()
