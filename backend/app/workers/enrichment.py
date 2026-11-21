"""One durable, bounded worker; saving frames never waits for the vision model."""

import asyncio
import logging
from datetime import timedelta, timezone
from time import perf_counter
from sqlalchemy import and_, case, or_, select, update
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import CaptureSession, Frame, QuestionAnswer
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut
from app.services.ai.models import models
from app.services.events import events
from app.services.frames.privacy import PRIVACY_VERSION
from app.services.frames.processing import vision_image_from_processed
from app.services.storage.object_store import get_image

logger = logging.getLogger(__name__)


async def update_frame(frame_id, **values):
    # A delayed caption must preserve OCR and warnings updated while model
    # inference was running.
    async with SessionFactory() as db:
        frame = await db.scalar(select(Frame).where(
            Frame.id == frame_id, Frame.expires_at > now(),
            Frame.enrichment_status.in_(["pending", "processing"]),
        ).with_for_update())
        if frame is None:
            return None
        if "search_text" in values:
            current_text = " ".join([
                values.get("caption", frame.caption), frame.ocr_text,
                " ".join(obj["label"] for obj in frame.detected_objects),
            ]).strip()
            if current_text != values["search_text"]:
                values.update(search_text=current_text, embedding=None, embedding_model=None)
                if current_text:
                    values["enrichment_status"] = "failed"
                    values["processing_warnings"] = [*values.get("processing_warnings", []), "embedding_stale"]
        if "processing_warnings" in values:
            values["processing_warnings"] = list(dict.fromkeys([*frame.processing_warnings, *values["processing_warnings"]]))
        if values.get("enrichment_status") == "complete":
            resolved = {"information_check_pending", "enrichment_superseded", "enrichment_failed",
                        "vision_unavailable", "embedding_unavailable", "embedding_stale"}
            values["processing_warnings"] = [warning for warning in values.get("processing_warnings", frame.processing_warnings)
                                            if warning not in resolved]
            values["enrichment_retry_at"] = None
        elif values.get("enrichment_status") == "failed":
            values["enrichment_retry_at"] = (
                now() + timedelta(seconds=settings.enrichment_retry_seconds * 2 ** max(0, frame.enrichment_attempts - 1))
                if frame.enrichment_attempts < settings.enrichment_max_attempts else None
            )
        for key, value in values.items():
            setattr(frame, key, value)
        await db.commit()
        output = FrameOut.model_validate(frame)
        events.publish(frame.session_id, {"type": "frame_updated", "frame": output.model_dump(mode="json")})
        return frame


async def discard_uninformative(frame_id):
    """Remove provisional empty memory through the durable storage-deletion outbox."""
    from app.workers.retention import drain_deletions, enqueue_frame_objects

    async with SessionFactory() as db:
        frame = await db.scalar(select(Frame).where(
            Frame.id == frame_id, Frame.enrichment_status.in_(["pending", "processing"]),
        ).with_for_update())
        if frame is None or frame.ocr_text.strip() or frame.detected_objects:
            return False
        if "information_check_pending" not in frame.processing_warnings:
            return False
        evidence = await db.scalars(select(QuestionAnswer.evidence_frame_ids).where(
            QuestionAnswer.session_id == frame.session_id, QuestionAnswer.expires_at > now(),
        ))
        if any(str(frame_id) in ids for ids in evidence):
            return False  # An answer makes this otherwise-empty image useful evidence.
        sid = frame.session_id
        await enqueue_frame_objects(db, [frame])
        await db.delete(frame)
        await db.commit()
    events.publish(sid, {"type": "frame_deleted", "frame_id": str(frame_id), "reason": "uninformative"})
    await drain_deletions()
    return True


async def enrich_frame(frame_id):
    async with SessionFactory() as db:
        frame = await db.scalar(
            select(Frame).where(
                Frame.id == frame_id, Frame.expires_at > now(),
                Frame.enrichment_status.in_(["pending", "processing"])
            )
        )
        if frame is None:
            return
    start = perf_counter()
    warnings = list(frame.processing_warnings)
    failed = False
    caption, flags = frame.caption, list(frame.scene_flags)
    try:
        if PRIVACY_VERSION not in (frame.enhancements or []):
            raise BackendError("Stored frame lacks verified face privacy processing", 503,
                               "face_privacy_unavailable")
        if not frame.processed_object_key:
            raise BackendError("Stored processed image is unavailable", 404,
                               "processed_image_unavailable")
        try:
            content = await asyncio.to_thread(get_image, frame.processed_object_key)
        except BackendError as exc:
            if exc.code == "image_unavailable":
                raise BackendError("Stored processed image is unavailable", 404,
                                   "processed_image_unavailable") from exc
            raise
        scene = await models.describe(await asyncio.to_thread(vision_image_from_processed, content))
        if (not scene.informative or not scene.caption.strip()) and not scene.uncertain and await discard_uninformative(frame_id):
            return
        caption = scene.caption
        if scene.uncertain:
            warnings.append("scene_uncertain")
        elif scene.central_closed_door:
            flags.append("central_closed_door")
    except BackendError as exc:
        warnings.append(exc.code)
        failed = True
    text = " ".join(
        [caption, frame.ocr_text, " ".join(obj["label"] for obj in frame.detected_objects)]
    ).strip()
    embedding = None
    if text:
        try:
            embedding = await models.embed(text)
        except BackendError as exc:
            warnings.append(exc.code)
            failed = True
    updated = await update_frame(
        frame_id,
        caption=caption, scene_flags=flags, search_text=text,
        embedding=embedding, embedding_model=settings.embedding_model if embedding else None,
        processing_warnings=list(dict.fromkeys(warnings)),
        enrichment_status="failed" if failed else "complete",
        enrichment_ms=(perf_counter() - start) * 1000,
    )
    # Never turn a delayed caption into an alert about the user's current view.
    captured_at = frame.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    if updated and flags and (now() - captured_at).total_seconds() <= settings.recent_evidence_seconds:
        async with SessionFactory() as db:
            session = await db.get(CaptureSession, updated.session_id)
        if session and session.status == "active" and session.alerts_enabled:
            from app.services.alerts import generate_alert

            await generate_alert(updated, session.language)


async def claim_enrichment():
    """Prefer live admission; backfill superseded work and due failures when idle."""
    async with SessionFactory() as db:
        eligible = [Frame.expires_at > now(), Frame.enrichment_attempts < settings.enrichment_max_attempts]
        frame = await db.scalar(select(Frame).where(
            *eligible, Frame.enrichment_status == "pending",
        ).order_by(Frame.captured_at.desc()).limit(1).with_for_update(skip_locked=True))
        if frame is None:
            frame = await db.scalar(select(Frame).where(
                *eligible,
                or_(
                    and_(Frame.enrichment_status == "failed", or_(Frame.enrichment_retry_at.is_(None), Frame.enrichment_retry_at <= now())),
                    and_(Frame.enrichment_status == "skipped", Frame.enrichment_retry_at <= now()),
                ),
            ).order_by(Frame.captured_at).limit(1).with_for_update(skip_locked=True))
        if frame is None:
            return None
        frame.enrichment_status = "processing"
        frame.enrichment_attempts += 1
        await db.commit()
        return frame.id


async def enrichment_loop():
    # Recover a single-process worker interrupted by a server restart.
    async with SessionFactory() as db:
        await db.execute(update(Frame).where(
            Frame.enrichment_status == "processing"
        ).values(enrichment_status="pending", enrichment_attempts=case(
            (Frame.enrichment_attempts > 0, Frame.enrichment_attempts - 1), else_=0,
        )))
        await db.commit()
    while True:
        try:
            frame_id = await claim_enrichment()
            if frame_id is None:
                await asyncio.sleep(0.5)
                continue
            try:
                await enrich_frame(frame_id)
            except Exception:
                logger.exception("Background frame enrichment failed")
                await update_frame(
                    frame_id, enrichment_status="failed", processing_warnings=["enrichment_failed"]
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Background frame enrichment worker unavailable")
            await asyncio.sleep(1)
