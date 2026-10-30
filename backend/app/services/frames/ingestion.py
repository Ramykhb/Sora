import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4
from weakref import WeakValueDictionary
from sqlalchemy import select
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut, IngestResult
from app.services.ai.models import models
from app.services.events import events
from app.services.frames.processing import analyze_image, prepare_image, vision_image
from app.services.frames.selection import rejection_reason
from app.services.sessions import create_session, get_session
from app.services.storage.object_store import delete_image, put_image

logger = logging.getLogger(__name__)
_locks = WeakValueDictionary()


def session_lock(session_id):
    lock = _locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[session_id] = lock
    return lock


async def ingest_bytes(
    content: bytes,
    session_id: UUID,
    *,
    filename="camera.jpg",
    force=False,
    captured_at: datetime | None = None,
    ocr_language: str | None = None,
    defer_enrichment: bool = False,
) -> IngestResult:
    async with session_lock(session_id):
        start = perf_counter()
        session = await get_session(session_id, active=True)
        timestamp = captured_at or now()
        if timestamp.tzinfo is None:
            raise BackendError("captured_at must include a timezone", 422, "invalid_timestamp")
        if timestamp > now() + timedelta(seconds=30) or timestamp < now() - timedelta(
            hours=settings.frame_retention_hours
        ):
            raise BackendError(
                "captured_at outside the retained time window", 422, "invalid_timestamp"
            )
        prepared = await asyncio.to_thread(prepare_image, content)
        async with SessionFactory() as db:
            previous = await db.scalar(
                select(Frame)
                .where(Frame.session_id == session_id, Frame.expires_at > now())
                .order_by(Frame.captured_at.desc())
                .limit(1)
            )
        reason = rejection_reason(prepared, previous.perceptual_hash if previous else None, force)
        if reason:
            events.publish(session_id, {"type": "frame_rejected", "reason": reason})
            return IngestResult(status="rejected", reason=reason)
        analysis = await asyncio.to_thread(analyze_image, prepared, ocr_language)
        warnings = []
        caption = ""
        scene_flags = []
        if not defer_enrichment:
            try:
                scene = await models.describe(await asyncio.to_thread(vision_image, prepared))
                caption = scene.caption
                if scene.central_closed_door and not scene.uncertain:
                    scene_flags.append("central_closed_door")
                if scene.uncertain:
                    warnings.append("scene_uncertain")
            except BackendError as exc:
                warnings.append(exc.code)
        text = " ".join(
            [caption, analysis.ocr_text, " ".join(obj["label"] for obj in analysis.objects)]
        ).strip()
        if not text and not force and not defer_enrichment:
            return IngestResult(status="rejected", reason="uninformative")
        embedding = None
        if text and not defer_enrichment:
            try:
                embedding = await models.embed(text)
            except BackendError as exc:
                warnings.append(exc.code)
        if force and rejection_reason(prepared, None):
            warnings.append("quality_override")
        await get_session(session_id, active=True)
        frame_id = uuid4()
        keys = [
            f"images/{session_id}/{frame_id}/original.jpg",
            f"images/{session_id}/{frame_id}/processed.jpg",
        ]
        uploaded = []
        try:
            for key, data in zip(keys, [prepared.original, prepared.processed]):
                await asyncio.to_thread(put_image, key, data, "image/jpeg")
                uploaded.append(key)
            session_expiry = session.expires_at
            if session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            frame = Frame(
                id=frame_id,
                session_id=session_id,
                source_filename=Path(filename).name[:512],
                original_object_key=keys[0],
                processed_object_key=keys[1],
                content_type="image/jpeg",
                width=prepared.width,
                height=prepared.height,
                sharpness=prepared.sharpness,
                brightness=prepared.brightness,
                perceptual_hash=prepared.perceptual_hash,
                ocr_text=analysis.ocr_text,
                ocr_confidence=analysis.ocr_confidence,
                detected_objects=analysis.objects,
                caption=caption,
                scene_flags=scene_flags,
                enhancements=prepared.enhancements,
                search_text=text,
                embedding=embedding,
                embedding_model=settings.embedding_model if embedding else None,
                processing_warnings=warnings,
                processing_ms=(perf_counter() - start) * 1000,
                enrichment_status="pending" if defer_enrichment else "complete",
                captured_at=timestamp,
                expires_at=min(
                    session_expiry, timestamp + timedelta(hours=settings.frame_retention_hours)
                ),
            )
            async with SessionFactory() as db:
                db.add(frame)
                await db.commit()
                await db.refresh(frame)
        except BaseException:
            for key in uploaded:
                try:
                    await asyncio.to_thread(delete_image, key)
                except Exception:
                    logger.exception("Upload compensation failed for %s", key)
            raise
        output = FrameOut.model_validate(frame)
        events.publish(
            session_id, {"type": "frame_stored", "frame": output.model_dump(mode="json")}
        )
        if session.alerts_enabled:
            from app.services.alerts import generate_alert

            try:
                await generate_alert(frame, session.language)
            except Exception:
                logger.exception("Alert generation failed after frame was stored")
        return IngestResult(status="stored", frame=output)


async def ingest_image(image_path: Path, *, ocr_language=None, session_id=None, force=False):
    image_path = image_path.expanduser().resolve()
    if not image_path.is_file():
        raise BackendError(f"Image does not exist: {image_path}", 422, "invalid_path")
    if image_path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
        raise BackendError("Image exceeds upload limit", 413, "upload_limit")
    if session_id is None:
        session_id = (await create_session()).id
    content = await asyncio.to_thread(image_path.read_bytes)
    return await ingest_bytes(
        content, session_id, filename=image_path.name, ocr_language=ocr_language, force=force
    )
