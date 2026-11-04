"""Optional single-process image worker, isolated from live video and immediate capture."""
import asyncio
import logging
from time import perf_counter

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut
from app.services.events import events
from app.services.ai.models import models
from app.services.frames.ocr import recognize_text
from app.services.frames.processing import jpeg
from app.services.frames.upscaling import UPSCALE_MARKER, enhance_saved_image, upscaler
from app.services.storage.object_store import get_image, put_image

logger = logging.getLogger(__name__)
OCR_MARKER = "ocr_after_upscale"


async def enhance_frame(frame_id):
    import cv2
    import numpy as np

    async with SessionFactory() as db:
        frame = await db.get(Frame, frame_id)
        if frame is None or OCR_MARKER in frame.enhancements:
            return False
        enhancements = list(frame.enhancements)
        already_upscaled = UPSCALE_MARKER in enhancements
        key = frame.processed_object_key if already_upscaled else frame.original_object_key
    content = await asyncio.to_thread(get_image, key)
    if already_upscaled:
        image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Cannot decode upscaled image")
        encoded, method = None, None
    else:
        image, method = await asyncio.to_thread(enhance_saved_image, content, enhancements)
        encoded = await asyncio.to_thread(jpeg, image)
    # Read the actual 200% pixels, without resizing them back down to the usual
    # camera OCR bound. Preserve immediate source OCR until this finishes.
    ocr_warning = None
    try:
        text, confidence = await asyncio.to_thread(
            recognize_text, image, rescale=False, timeout_seconds=settings.upscale_ocr_timeout_seconds,
        )
    except BackendError as exc:
        text, confidence = "", 0
        ocr_warning = exc.code
    changed = bool(text.strip()) and (not frame.ocr_text.strip() or confidence >= frame.ocr_confidence)
    candidate_search = " ".join([frame.caption, text, " ".join(obj["label"] for obj in frame.detected_objects)]).strip()
    embedding = None
    if changed and text != frame.ocr_text:
        try:
            embedding = await models.embed(candidate_search)
        except BackendError:
            # Lexical search still uses the new OCR; never retain a stale vector.
            pass
    # Re-check after slow inference; deletion must not resurrect an object.
    async with SessionFactory() as db:
        row = await db.scalar(select(Frame).where(Frame.id == frame_id, Frame.expires_at > now()).with_for_update())
        if row is None or OCR_MARKER in row.enhancements:
            return False
        if encoded is not None:
            await asyncio.to_thread(put_image, row.processed_object_key, encoded)
            row.enhancements = [*row.enhancements, UPSCALE_MARKER, method]
        row.enhancements = [*row.enhancements, OCR_MARKER]
        if text.strip() and (not row.ocr_text.strip() or confidence >= row.ocr_confidence):
            old_text = row.ocr_text
            row.ocr_text, row.ocr_confidence = text, confidence
            row.search_text = " ".join([row.caption, text, " ".join(obj["label"] for obj in row.detected_objects)]).strip()
            if old_text != text:
                row.embedding = embedding if row.search_text == candidate_search else None
                row.embedding_model = settings.embedding_model if row.embedding is not None else None
                row.processing_warnings = list(dict.fromkeys([*row.processing_warnings, "ocr_from_upscaled_image"]))
        if ocr_warning:
            row.processing_warnings = list(dict.fromkeys([*row.processing_warnings, ocr_warning]))
        await db.commit()
        output = FrameOut.model_validate(row)
    events.publish(row.session_id, {"type": "frame_updated", "frame": output.model_dump(mode="json")})
    return True


async def next_frame():
    async with SessionFactory() as db:
        # Iterate metadata in bounded pages. Latest captures take priority over
        # old history; no video frames or inference jobs are queued in memory.
        query = select(Frame).where(Frame.expires_at > now()).order_by(Frame.created_at.desc(), Frame.id.desc())
        offset = 0
        while True:
            rows = list((await db.scalars(query.limit(100).offset(offset))).all())
            if not rows:
                return None
            for row in rows:
                if OCR_MARKER not in row.enhancements and "upscale_failed" not in row.processing_warnings:
                    return row.id
            offset += len(rows)


async def main():
    # A missing/incompatible model fails explicitly at startup. Do not download
    # weights or silently substitute an unrelated model.
    await asyncio.to_thread(upscaler)
    logger.info("Real-ESRGAN ready; saved-image worker running at 2x")
    while True:
        frame_id = await next_frame()
        if frame_id is None:
            await asyncio.sleep(5)
            continue
        started = perf_counter()
        try:
            logger.info("Starting 2x enhancement for %s", frame_id)
            applied = await enhance_frame(frame_id)
            logger.info("Image 2x enhancement %s: applied=%s seconds=%.2f", frame_id, applied, perf_counter() - started)
        except Exception:
            logger.exception("Image 2x enhancement failed for %s", frame_id)
            async with SessionFactory() as db:
                row = await db.get(Frame, frame_id)
                if row:
                    row.processing_warnings = list(dict.fromkeys([*row.processing_warnings, "upscale_failed"]))
                    await db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
