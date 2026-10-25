from datetime import timedelta
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.db.models import CaptureSession
from app.db.models.frame import now
from app.db.session import SessionFactory


async def get_session(session_id: UUID, active: bool = False) -> CaptureSession:
    async with SessionFactory() as db:
        row = await db.scalar(
            select(CaptureSession).where(
                CaptureSession.id == session_id, CaptureSession.expires_at > now()
            )
        )
        if row is None:
            raise HTTPException(404, "Session not found or expired")
        if active and row.status != "active":
            raise HTTPException(409, "Session is closed")
        return row


async def create_session(language="en", alerts_enabled=False):
    async with SessionFactory() as db:
        session = CaptureSession(
            language=language,
            consent=True,
            alerts_enabled=alerts_enabled,
            expires_at=now() + timedelta(hours=settings.frame_retention_hours),
        )
        db.add(session)
        await db.commit()
        return session
