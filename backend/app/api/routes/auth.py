from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from app.auth_schemas import (
    AdminUserPatch,
    Credentials,
    DeleteAccount,
    EmailRequest,
    PasswordChange,
    ProfilePatch,
    RefreshRequest,
    Registration,
    ResetRequest,
    TokenPair,
    TokenRequest,
    UserOut,
)
from app.core.auth import (
    Principal,
    current_principal,
    current_user,
    require_admin,
    stop_user_streams,
    unauthorized,
)
from app.core.config import settings
from app.db.auth_models import AccountToken, AuthSession, User
from app.db.models import CaptureSession, Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.authentication import (
    DUMMY_HASH,
    consume_account_token,
    hash_password,
    issue_pair,
    request_account_email,
    require_mail,
    revoke_all,
    rotate,
    throttle,
    verify_password,
)
from app.workers.retention import drain_deletions, enqueue_frame_objects

router = APIRouter(prefix="/auth", tags=["authentication"])
ACK = {"message": "If the account is eligible, an email will be sent."}


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: Registration, request: Request, tasks: BackgroundTasks):
    await throttle(request, "register", limit=5)
    if not settings.auth_registration_enabled:
        raise HTTPException(403, "Registration is disabled")
    if settings.auth_require_verified_email:
        require_mail()
    password_hash = await hash_password(body.password.get_secret_value())
    async with SessionFactory() as db:
        user = User(email=body.email, display_name=body.display_name, password_hash=password_hash)
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(409, "Unable to register with these details") from None
    if settings.smtp_host and settings.smtp_from:
        tasks.add_task(request_account_email, user.email, "verify")
    return user


@router.post("/login", response_model=TokenPair)
async def login(body: Credentials, request: Request):
    await throttle(request, "login", body.email)
    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.email == body.email).with_for_update())
        valid = await verify_password(
            body.password.get_secret_value(), user.password_hash if user else DUMMY_HASH
        )
        if not user or not valid or not user.is_active:
            raise unauthorized()
        if settings.auth_require_verified_email and not user.email_verified:
            raise HTTPException(403, "Verify your email before signing in")
        pair = await issue_pair(db, user)
        await db.commit()
        return pair


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request):
    await throttle(request, "refresh", limit=60)
    return await rotate(body.refresh_token)


@router.post("/logout", status_code=204)
async def logout(principal: Principal = Depends(current_principal)):
    async with SessionFactory() as db:
        await db.execute(
            update(AuthSession)
            .where(AuthSession.id == principal.session_id)
            .values(revoked_at=now())
        )
        await db.commit()
    await stop_user_streams(principal.user.id)
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
async def logout_all(user: User = Depends(current_user)):
    async with SessionFactory() as db:
        await db.scalar(select(User).where(User.id == user.id).with_for_update())
        await revoke_all(db, user.id)
        await db.commit()
    await stop_user_streams(user.id)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
async def profile(body: ProfilePatch, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        row = await db.get(User, user.id)
        row.display_name = body.display_name
        await db.commit()
        return row


@router.post("/change-password", status_code=204)
async def change_password(
    body: PasswordChange, request: Request, user: User = Depends(current_user)
):
    await throttle(request, "password", str(user.id), limit=5)
    async with SessionFactory() as db:
        row = await db.scalar(select(User).where(User.id == user.id).with_for_update())
        if not await verify_password(body.current_password.get_secret_value(), row.password_hash):
            raise unauthorized()
        row.password_hash = await hash_password(body.new_password.get_secret_value())
        await revoke_all(db, row.id)
        await db.execute(delete(AccountToken).where(AccountToken.user_id == row.id))
        await db.commit()
    await stop_user_streams(user.id)
    return Response(status_code=204)


@router.post("/forgot-password", status_code=202)
async def forgot(body: EmailRequest, request: Request, tasks: BackgroundTasks):
    await throttle(request, "recovery", body.email, limit=5)
    require_mail()
    tasks.add_task(request_account_email, body.email, "reset")
    return ACK


@router.post("/reset-password", status_code=204)
async def reset(body: ResetRequest, request: Request):
    await throttle(request, "reset", limit=10)
    await consume_account_token(body.token, "reset", body.new_password.get_secret_value())
    return Response(status_code=204)


@router.post("/resend-verification", status_code=202)
async def resend(body: EmailRequest, request: Request, tasks: BackgroundTasks):
    await throttle(request, "verify-send", body.email, limit=5)
    require_mail()
    tasks.add_task(request_account_email, body.email, "verify")
    return ACK


@router.post("/verify-email", status_code=204)
async def verify(body: TokenRequest, request: Request):
    await throttle(request, "verify", limit=10)
    await consume_account_token(body.token, "verify")
    return Response(status_code=204)


@router.delete("/me", status_code=204)
async def delete_account(body: DeleteAccount, request: Request, user: User = Depends(current_user)):
    await throttle(request, "delete", str(user.id), limit=5)
    async with SessionFactory() as db:
        row = await db.scalar(select(User).where(User.id == user.id).with_for_update())
        if row.role == "admin":
            raise HTTPException(403, "Demote this administrator using another administrator first")
        if not await verify_password(body.password.get_secret_value(), row.password_hash):
            raise unauthorized()
        frames = (
            await db.scalars(
                select(Frame).join(CaptureSession).where(CaptureSession.owner_id == row.id)
            )
        ).all()
        await enqueue_frame_objects(db, frames)
        # Stop before the cascading delete removes the session IDs used for lookup.
        await stop_user_streams(row.id)
        await db.delete(row)
        await db.commit()
    await drain_deletions()
    return Response(status_code=204)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
async def users(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    async with SessionFactory() as db:
        return (
            await db.scalars(
                select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()


@router.patch("/users/{user_id}", response_model=UserOut)
async def manage_user(user_id: UUID, body: AdminUserPatch, admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(400, "Use another administrator to change your own role or status")
    async with SessionFactory() as db:
        row = await db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not row:
            raise HTTPException(404, "User not found")
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        await revoke_all(db, row.id)
        await db.commit()
    await stop_user_streams(user_id)
    return row


@router.get("/sessions")
async def login_sessions(principal: Principal = Depends(current_principal)):
    async with SessionFactory() as db:
        rows = (
            await db.scalars(
                select(AuthSession)
                .where(
                    AuthSession.user_id == principal.user.id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now(),
                )
                .order_by(AuthSession.created_at.desc())
                .limit(100)
            )
        ).all()
        return [
            {
                "id": row.id,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "is_current": row.id == principal.session_id,
            }
            for row in rows
        ]


@router.delete("/sessions/{login_session_id}", status_code=204)
async def revoke_login_session(login_session_id: UUID, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        result = await db.execute(
            update(AuthSession)
            .where(AuthSession.id == login_session_id, AuthSession.user_id == user.id)
            .values(revoked_at=now())
        )
        if not result.rowcount:
            raise HTTPException(404, "Login session not found")
        await db.commit()
    await stop_user_streams(user.id)
    return Response(status_code=204)
