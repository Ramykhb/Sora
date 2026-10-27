import asyncio
import hashlib
from dataclasses import dataclass
from uuid import UUID
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from app.core.config import settings
from app.db.auth_models import AuthSession, User
from app.db.models import CaptureSession
from app.db.models.frame import now
from app.db.session import SessionFactory

bearer = HTTPBearer(auto_error=False)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def unauthorized():
    return HTTPException(
        401, "Invalid, expired or revoked credentials", headers={"WWW-Authenticate": "Bearer"}
    )


@dataclass(frozen=True)
class Principal:
    user: User
    session_id: UUID


async def authenticate(token: str | None) -> Principal:
    if not isinstance(token, str) or not 20 <= len(token) <= 512:
        raise unauthorized()
    async with SessionFactory() as db:
        result = (
            await db.execute(
                select(User, AuthSession)
                .join(AuthSession, User.id == AuthSession.user_id)
                .where(
                    AuthSession.access_hash == digest(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.access_expires_at > now(),
                    AuthSession.expires_at > now(),
                    User.is_active.is_(True),
                )
            )
        ).first()
        if not result:
            raise unauthorized()
        user, session = result
        if settings.auth_require_verified_email and not user.email_verified:
            raise HTTPException(403, "Verify your email before signing in")
        return Principal(user, session.id)


async def current_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return await authenticate(credentials.credentials)


async def current_user(principal: Principal = Depends(current_principal)) -> User:
    return principal.user


async def require_admin(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


async def check_ownership(session_id: UUID, user: User):
    async with SessionFactory() as db:
        row = await db.scalar(
            select(CaptureSession).where(
                CaptureSession.id == session_id,
                CaptureSession.expires_at > now(),
            )
        )
        if row is None or (user.role != "admin" and row.owner_id != user.id):
            raise HTTPException(404, "Session not found or expired")
        return row


async def owned_session(session_id: UUID, user: User = Depends(current_user)):
    return await check_ownership(session_id, user)


async def stop_user_streams(user_id):
    from app.services.streaming.session import streams

    async with SessionFactory() as db:
        ids = (
            await db.scalars(select(CaptureSession.id).where(CaptureSession.owner_id == user_id))
        ).all()
    await asyncio.gather(*(streams.stop(sid) for sid in ids))
