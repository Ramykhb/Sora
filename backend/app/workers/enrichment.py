"""One durable, bounded worker; saving frames never waits for the vision model."""

import asyncio
import logging
from datetime import timezone
from time import perf_counter
from sqlalchemy import select, update
from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import CaptureSession, Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut
from app.services.ai.models import models
from app.services.events import events
from app.services.frames.processing import prepare_image, vision_image
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
        if "processing_warnings" in values:
            values["processing_warnings"] = list(dict.fromkeys([*frame.processing_warnings, *values["processing_warnings"]]))
        for key, value in values.items():
            setattr(frame, key, value)
        await db.commit()
        output = FrameOut.model_validate(frame)
        events.publish(frame.session_id, {"type": "frame_updated", "frame": output.model_dump(mode="json")})
        return frame


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
    caption, flags = "", []
    try:
        content = await asyncio.to_thread(get_image, frame.original_object_key)
        prepared = await asyncio.to_thread(prepare_image, content)
        scene = await models.describe(await asyncio.to_thread(vision_image, prepared))
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


async def enrichment_loop():
    # Recover a single-process worker interrupted by a server restart.
    async with SessionFactory() as db:
        await db.execute(update(Frame).where(
            Frame.enrichment_status == "processing"
        ).values(enrichment_status="pending"))
        await db.commit()
    while True:
        try:
            async with SessionFactory() as db:
                frame_id = await db.scalar(
                    select(Frame.id)
                    .where(Frame.enrichment_status == "pending", Frame.expires_at > now())
                    .order_by(Frame.captured_at.desc())
                    .limit(1)
                )
                if frame_id is not None:
                    await db.execute(update(Frame).where(
                        Frame.id == frame_id, Frame.enrichment_status == "pending"
                    ).values(enrichment_status="processing"))
                    await db.commit()
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
