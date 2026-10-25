import asyncio
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from app.api.dependencies import read_upload
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.schemas import FrameOut, IngestResult
from app.services.ai.retrieval import retrieve_frames
from app.services.frames.ingestion import ingest_bytes
from app.services.sessions import get_session
from app.services.storage.object_store import get_image
from app.workers.retention import drain_deletions, enqueue_frame_objects

router = APIRouter()


@router.post("", response_model=IngestResult)
async def upload(
    session_id: UUID,
    image: UploadFile = File(...),
    force: bool = Form(False),
    captured_at: datetime | None = Form(None),
):
    await get_session(session_id, active=True)
    data = await read_upload(image)
    return await ingest_bytes(
        data,
        session_id,
        filename=image.filename or "upload.jpg",
        force=force,
        captured_at=captured_at,
    )


@router.get("", response_model=list[FrameOut])
async def timeline(
    session_id: UUID,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    await get_session(session_id)
    for value in (since, until):
        if value is not None and value.tzinfo is None:
            raise BackendError("Timestamps must include timezone", 422, "invalid_timestamp")
    if since and until and since > until:
        raise BackendError("since must precede until", 422, "invalid_time_range")
    filters = [Frame.session_id == session_id, Frame.expires_at > now()]
    if since:
        filters.append(Frame.captured_at >= since)
    if until:
        filters.append(Frame.captured_at <= until)
    async with SessionFactory() as db:
        return list(
            (
                await db.scalars(
                    select(Frame)
                    .where(*filters)
                    .order_by(Frame.captured_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        )


@router.get("/search")
async def search(
    session_id: UUID,
    q: str = Query(min_length=1, max_length=2000),
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(3, ge=1, le=10),
):
    await get_session(session_id)
    for value in (since, until):
        if value is not None and value.tzinfo is None:
            raise BackendError("Timestamps must include timezone", 422, "invalid_timestamp")
    frames, warnings, _ = await retrieve_frames(session_id, q, "memory", since, until, limit)
    return {"frames": [FrameOut.model_validate(f) for f in frames], "warnings": warnings}


async def get_frame(session_id, frame_id):
    await get_session(session_id)
    async with SessionFactory() as db:
        row = await db.scalar(
            select(Frame).where(
                Frame.id == frame_id, Frame.session_id == session_id, Frame.expires_at > now()
            )
        )
        if row is None:
            raise HTTPException(404, "Frame not found or expired")
        return row


@router.get("/{frame_id}", response_model=FrameOut)
async def detail(session_id: UUID, frame_id: UUID):
    return await get_frame(session_id, frame_id)


@router.get("/{frame_id}/image")
async def image(session_id: UUID, frame_id: UUID, original: bool = False):
    row = await get_frame(session_id, frame_id)
    content = await asyncio.to_thread(
        get_image, row.original_object_key if original else row.processed_object_key
    )
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.delete("/{frame_id}", status_code=204)
async def remove(session_id: UUID, frame_id: UUID):
    row = await get_frame(session_id, frame_id)
    async with SessionFactory() as db:
        row = await db.get(Frame, row.id)
        if row:
            await enqueue_frame_objects(db, [row])
            await db.delete(row)
            await db.commit()
    await drain_deletions()
    return Response(status_code=204)
