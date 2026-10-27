import asyncio
from datetime import timedelta
from email.message import EmailMessage
import secrets
import smtplib
import ssl
from time import time
from urllib.parse import urlencode
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError
from fastapi import HTTPException, Request
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.auth_schemas import TokenPair, UserOut
from app.core.auth import digest, stop_user_streams, unauthorized
from app.core.config import settings
from app.db.auth_models import AccountToken, AuthRateLimit, AuthSession, UsedRefresh, User
from app.db.models.frame import now
from app.db.session import SessionFactory

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


async def hash_password(password):
    return await asyncio.to_thread(hasher.hash, password)


async def verify_password(password, encoded):
    def verify():
        try:
            return hasher.verify(encoded, password)
        except (VerificationError, InvalidHash):
            return False

    return await asyncio.to_thread(verify)


async def throttle(request: Request, purpose: str, email: str = "", limit=10):
    """Atomic, database-backed limits. Do not trust client-supplied forwarding headers."""
    address = request.client.host if request.client else "unknown"
    window = int(time() // 900)
    keys = [f"{purpose}:ip:{address}:{window}"]
    if email:
        keys.append(f"{purpose}:account:{email}:{window}")
    async with SessionFactory() as db:
        insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
        blocked = False
        for key in keys:
            stmt = (
                insert(AuthRateLimit)
                .values(key=digest(key), attempts=1, expires_at=now() + timedelta(minutes=30))
                .on_conflict_do_update(
                    index_elements=[AuthRateLimit.key],
                    set_={"attempts": AuthRateLimit.attempts + 1},
                )
                .returning(AuthRateLimit.attempts)
            )
            attempts = await db.scalar(stmt)
            blocked |= attempts > limit
        await db.commit()
    if blocked:
        raise HTTPException(
            429,
            "Too many attempts; try again later",
            headers={"Retry-After": str(900 - int(time()) % 900)},
        )


async def issue_pair(db, user):
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    expiry = now() + timedelta(days=settings.auth_refresh_days)
    row = AuthSession(
        user_id=user.id,
        access_hash=digest(access),
        refresh_hash=digest(refresh),
        access_expires_at=now() + timedelta(minutes=settings.auth_access_minutes),
        expires_at=expiry,
    )
    db.add(row)
    await db.flush()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.auth_access_minutes * 60,
        refresh_expires_at=expiry,
        user=UserOut.model_validate(user),
    )


async def rotate(refresh):
    key = digest(refresh)
    async with SessionFactory() as db:
        # Lock the user first everywhere credentials are issued or revoked. The CAS below
        # also protects rotation on SQLite, where FOR UPDATE is unavailable.
        owner = await db.scalar(select(AuthSession.user_id).where(AuthSession.refresh_hash == key))
        used = await db.get(UsedRefresh, key) if owner is None else None
        if used:
            await db.execute(
                update(AuthSession)
                .where(AuthSession.id == used.session_id)
                .values(revoked_at=now())
            )
            await db.commit()
            raise unauthorized()
        if owner is None:
            raise unauthorized()
        user = await db.scalar(select(User).where(User.id == owner).with_for_update())
        if (
            not user
            or not user.is_active
            or (settings.auth_require_verified_email and not user.email_verified)
        ):
            raise unauthorized()
        row = await db.scalar(
            select(AuthSession).where(
                AuthSession.refresh_hash == key,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now(),
            )
        )
        if not row:
            # A concurrent request consumed the same token while we waited for the lock.
            used = await db.get(UsedRefresh, key)
            if used:
                await db.execute(
                    update(AuthSession)
                    .where(AuthSession.id == used.session_id)
                    .values(revoked_at=now())
                )
                await db.commit()
            raise unauthorized()
        login_id = row.id
        access, replacement = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        result = await db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == login_id,
                AuthSession.refresh_hash == key,
                AuthSession.revoked_at.is_(None),
            )
            .values(
                access_hash=digest(access),
                refresh_hash=digest(replacement),
                access_expires_at=now() + timedelta(minutes=settings.auth_access_minutes),
            )
        )
        if result.rowcount != 1:
            await db.rollback()
            await db.execute(
                update(AuthSession).where(AuthSession.id == login_id).values(revoked_at=now())
            )
            await db.commit()
            raise unauthorized()
        db.add(UsedRefresh(token_hash=key, session_id=login_id))
        await db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=replacement,
            expires_in=settings.auth_access_minutes * 60,
            refresh_expires_at=row.expires_at,
            user=UserOut.model_validate(user),
        )


async def revoke_all(db, user_id):
    await db.execute(
        update(AuthSession).where(AuthSession.user_id == user_id).values(revoked_at=now())
    )


def require_mail():
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(503, "Email delivery is not configured")


async def send_account_email(email, token, purpose):
    require_mail()
    path = "reset-password" if purpose == "reset" else "verify-email"
    link = settings.auth_public_url.rstrip("/") + "/" + path + "?" + urlencode({"token": token})
    message = EmailMessage()
    message["From"], message["To"] = settings.smtp_from, email
    message["Subject"] = (
        "Reset your Sora password" if purpose == "reset" else "Verify your Sora email"
    )
    message.set_content(
        f"Open this link to {'reset your password' if purpose == 'reset' else 'verify your email'}:\n\n{link}\n\nIf the app is not connected yet, submit this one-time token to the API:\n{token}\n\nThis link expires in 30 minutes. Ignore this email if you did not request it."
    )

    def send():
        connection = (
            smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=10,
                context=ssl.create_default_context(),
            )
            if settings.smtp_security == "ssl"
            else smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        )
        with connection as smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)

    await asyncio.to_thread(send)


async def request_account_email(email, purpose):
    require_mail()
    token = secrets.token_urlsafe(48)
    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if not user or (purpose == "verify" and user.email_verified):
            return
        row = AccountToken(
            token_hash=digest(token),
            user_id=user.id,
            purpose=purpose,
            expires_at=now() + timedelta(minutes=30),
        )
        db.add(row)
        await db.commit()
    try:
        await send_account_email(email, token, purpose)
    except Exception:
        # Leave the public response identical for unknown addresses and failed delivery.
        # Never log the token, email body or SMTP credentials.
        import logging

        logging.getLogger(__name__).error("Account email delivery failed; check SMTP configuration")
        async with SessionFactory() as db:
            await db.execute(delete(AccountToken).where(AccountToken.token_hash == digest(token)))
            await db.commit()


async def consume_account_token(token, purpose, new_password=None):
    async with SessionFactory() as db:
        row = await db.get(AccountToken, digest(token))
        if not row or row.purpose != purpose:
            raise HTTPException(400, "Invalid or expired token")
        user = await db.scalar(select(User).where(User.id == row.user_id).with_for_update())
        if not user or not user.is_active:
            raise HTTPException(400, "Invalid or expired token")
        result = await db.execute(
            delete(AccountToken)
            .where(
                AccountToken.token_hash == digest(token),
                AccountToken.purpose == purpose,
                AccountToken.expires_at > now(),
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise HTTPException(400, "Invalid or expired token")
        if purpose == "reset":
            user.password_hash = await hash_password(new_password)
            await revoke_all(db, user.id)
            await db.execute(delete(AccountToken).where(AccountToken.user_id == user.id))
        else:
            user.email_verified = True
        await db.commit()
    if purpose == "reset":
        await stop_user_streams(user.id)
