from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, select
from app.core.auth import current_user, owned_session
from app.db.auth_models import User
from app.db.models import CaptureSession, Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import SessionCreate, SessionOut, SessionPatch
from app.services.events import events
from app.services.sessions import create_session, get_session
from app.services.streaming.session import streams
from app.workers.retention import drain_deletions, enqueue_frame_objects

router = APIRouter()


@router.post("", response_model=SessionOut, status_code=201)
async def create(request: SessionCreate, user: User = Depends(current_user)):
    return await create_session(request.language, request.alerts_enabled, owner_id=user.id)


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    own_only: bool = Query(False),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
):
    async with SessionFactory() as db:
        return list(
            (
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
        )


@router.get("/{session_id}", response_model=SessionOut, dependencies=[Depends(owned_session)])
async def detail(session_id: UUID):
    return await get_session(session_id)


@router.patch("/{session_id}", response_model=SessionOut, dependencies=[Depends(owned_session)])
async def update(session_id: UUID, request: SessionPatch):
    await get_session(session_id, active=True)
    async with SessionFactory() as db:
        row = await db.get(CaptureSession, session_id)
        for name, value in request.model_dump(exclude_none=True).items():
            setattr(row, name, value)
        await db.commit()
        events.publish(
            session_id,
            {"type": "session_updated", "session": SessionOut.model_validate(row).model_dump(mode="json")},
        )
        return row


@router.post(
    "/{session_id}/close", response_model=SessionOut, dependencies=[Depends(owned_session)]
)
async def close(session_id: UUID):
    await get_session(session_id)
    async with SessionFactory() as db:
        row = await db.get(CaptureSession, session_id)
        row.status = "closed"
        await db.commit()
    events.publish(
        session_id,
        {"type": "session_updated", "session": SessionOut.model_validate(row).model_dump(mode="json")},
    )
    await streams.stop(session_id)
    return row


@router.delete("/{session_id}", status_code=204, dependencies=[Depends(owned_session)])
async def remove(session_id: UUID):
    await get_session(session_id)
    await streams.stop(session_id)
    async with SessionFactory() as db:
        frames = list((await db.scalars(select(Frame).where(Frame.session_id == session_id))).all())
        await enqueue_frame_objects(db, frames)
        await db.execute(delete(CaptureSession).where(CaptureSession.id == session_id))
        await db.commit()
    await drain_deletions()
    return Response(status_code=204)
