"""Optional single-process image worker, isolated from live video and OCR."""
import asyncio
import logging
from time import perf_counter

from sqlalchemy import select

from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut
from app.services.events import events
from app.services.frames.processing import jpeg
from app.services.frames.upscaling import UPSCALE_MARKER, enhance_saved_image, upscaler
from app.services.storage.object_store import get_image, put_image

logger = logging.getLogger(__name__)


async def enhance_frame(frame_id):
    async with SessionFactory() as db:
        frame = await db.get(Frame, frame_id)
        if frame is None or UPSCALE_MARKER in frame.enhancements:
            return False
        key, enhancements = frame.original_object_key, list(frame.enhancements)
    content = await asyncio.to_thread(get_image, key)
    image, method = await asyncio.to_thread(enhance_saved_image, content, enhancements)
    encoded = await asyncio.to_thread(jpeg, image)
    # Re-check ownership of the object after slow inference. Lock before writing
    # so deletion/expiry cannot complete and then have its object resurrected.
    async with SessionFactory() as db:
        row = await db.scalar(select(Frame).where(Frame.id == frame_id, Frame.expires_at > now()).with_for_update())
        if row is None or UPSCALE_MARKER in row.enhancements:
            return False
        await asyncio.to_thread(put_image, row.processed_object_key, encoded)
        row.enhancements = [*row.enhancements, UPSCALE_MARKER, method]
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
                if UPSCALE_MARKER not in row.enhancements and "upscale_failed" not in row.processing_warnings:
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
