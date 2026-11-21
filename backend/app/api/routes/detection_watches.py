from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.auth import current_user
from app.core.config import settings
from app.db.auth_models import User
from app.db.models import DetectionWatch
from app.db.session import SessionFactory
from app.services.detection_memory import oldest_active, target_key

router = APIRouter()


class WatchEdit(BaseModel):
    target: str = Field(min_length=1, max_length=200)

    @field_validator("target")
    @classmethod
    def meaningful(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name an object or sign to watch for")
        return value


@router.get("")
async def list_watches(user: User = Depends(current_user)):
    async with SessionFactory() as db:
        rows = (await db.scalars(select(DetectionWatch).where(
            DetectionWatch.owner_id == user.id, DetectionWatch.created_at >= oldest_active(),
        ).order_by(DetectionWatch.created_at, DetectionWatch.id))).all()
        return [{"id": row.id, "target": row.target, "created_at": row.created_at,
                 "expires_at": row.created_at + timedelta(days=settings.detection_watch_retention_days)} for row in rows]


@router.put("/{watch_id}", status_code=204)
async def edit_watch(watch_id: UUID, body: WatchEdit, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
        row = await db.scalar(select(DetectionWatch).where(
            DetectionWatch.id == watch_id, DetectionWatch.owner_id == user.id,
            DetectionWatch.created_at >= oldest_active(),
        ).with_for_update())
        if row is None:
            raise HTTPException(404, "Request not found or expired")
        # Replace the ID so an in-flight assessment of the old target cannot consume the edit.
        created = row.created_at
        await db.delete(row)
        await db.flush()
        db.add(DetectionWatch(owner_id=user.id, target=body.target, target_key=target_key(body.target), created_at=created))
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "You already have this pending request") from exc
    return Response(status_code=204)


@router.delete("", status_code=204)
async def clear_watches(user: User = Depends(current_user)):
    async with SessionFactory() as db:
        await db.execute(delete(DetectionWatch).where(DetectionWatch.owner_id == user.id))
        await db.commit()
    return Response(status_code=204)


@router.delete("/{watch_id}", status_code=204)
async def cancel_watch(watch_id: UUID, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        result = await db.execute(delete(DetectionWatch).where(
            DetectionWatch.id == watch_id, DetectionWatch.owner_id == user.id,
        ))
        if not result.rowcount:
            raise HTTPException(404, "Request not found")
        await db.commit()
    return Response(status_code=204)
