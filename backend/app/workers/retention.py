import asyncio
import logging
from datetime import timedelta
from time import monotonic
from sqlalchemy import delete, select
from app.core.config import settings
from app.db.auth_models import AccountToken, AuthRateLimit, AuthSession
from app.db.models import CaptureSession, Frame, ObjectDeletion, QuestionAnswer
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.storage.object_store import delete_image

logger = logging.getLogger(__name__)
_cleanup_lock = asyncio.Lock()


async def enqueue_frame_objects(db, frames):
    for frame in frames:
        for key in (frame.original_object_key, frame.processed_object_key):
            if await db.get(ObjectDeletion, key) is None:
                db.add(ObjectDeletion(key=key))


async def drain_deletions():
    async with SessionFactory() as db:
        pending = list((await db.scalars(select(ObjectDeletion).limit(1000))).all())
        removed = 0
        for item in pending:
            try:
                await asyncio.to_thread(delete_image, item.key)
                await db.delete(item)
                removed += 1
            except Exception as exc:
                item.attempts += 1
                item.last_error = type(exc).__name__
        await db.commit()
        return removed


async def cleanup_once():
    async with _cleanup_lock:
        from app.services.streaming.session import streams

        async with SessionFactory() as db:
            expired_sessions = list(
                (
                    await db.scalars(
                        select(CaptureSession.id).where(CaptureSession.expires_at <= now())
                    )
                ).all()
            )
            for session_id in expired_sessions:
                await streams.stop(session_id)
            frames = list(
                (
                    await db.scalars(
                        select(Frame).where(
                            (Frame.expires_at <= now()) | Frame.session_id.in_(expired_sessions)
                        )
                    )
                ).all()
            )
            await enqueue_frame_objects(db, frames)
            if frames:
                await db.execute(delete(Frame).where(Frame.id.in_([frame.id for frame in frames])))
            await db.execute(delete(QuestionAnswer).where(QuestionAnswer.expires_at <= now()))
            if expired_sessions:
                await db.execute(
                    delete(CaptureSession).where(CaptureSession.id.in_(expired_sessions))
                )
            for model in (AccountToken, AuthRateLimit, AuthSession):
                await db.execute(delete(model).where(model.expires_at <= now()))
            await db.commit()
        objects_removed = await drain_deletions()
        return {
            "frames_deleted": len(frames),
            "sessions_deleted": len(expired_sessions),
            "objects_deleted": objects_removed,
        }


async def reconcile_orphans():
    # Upload compensation can fail during simultaneous DB/storage outages. Reconcile
    # old unreferenced objects as a backstop without touching in-flight uploads.
    from app.services.storage.object_store import list_objects

    async with _cleanup_lock:
        objects = await asyncio.to_thread(list_objects)
        async with SessionFactory() as db:
            keys = (
                await db.execute(select(Frame.original_object_key, Frame.processed_object_key))
            ).all()
            referenced = {key for pair in keys for key in pair}
            count = 0
            for key, modified in objects:
                if key not in referenced and modified < now() - timedelta(minutes=10):
                    if await db.get(ObjectDeletion, key) is None:
                        db.add(ObjectDeletion(key=key))
                        count += 1
            await db.commit()
        await drain_deletions()
        return {"orphan_objects_queued": count}


async def retention_loop():
    last_reconciled = -3600
    while True:
        try:
            await cleanup_once()
            if monotonic() - last_reconciled >= 3600:
                await reconcile_orphans()
                last_reconciled = monotonic()
        except Exception:
            logger.exception("Retention cleanup failed; retry scheduled")
        await asyncio.sleep(settings.cleanup_interval_seconds)
