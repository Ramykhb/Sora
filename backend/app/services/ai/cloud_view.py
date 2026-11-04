"""Fresh, retained, privacy-blurred evidence for bounded cloud questions."""
import asyncio
from datetime import timezone

import cv2
import numpy as np

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services.ai import gemini
from app.services.ai.retrieval import retrieve_frames
from app.services.ai.safety import STALE, guard_answer
from app.services.frames.ingestion import ingest_bytes
from app.services.frames.privacy import PRIVACY_VERSION
from app.services.frames.processing import jpeg, prepare_image
from app.services.storage.object_store import get_image
from app.services.streaming.session import streams


def cloud_image(content, privacy_checked):
    if not privacy_checked:
        content = prepare_image(content).processed
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise BackendError("Camera image unavailable", 422, "invalid_image")
    scale = min(1, settings.gemini_image_max_side / max(image.shape[:2]))
    if scale < 1:
        image = cv2.resize(image, (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    return jpeg(image)


async def answer_cloud_view(session_id, request, language, *, walking=False):
    snapshot = streams.fresh_snapshot(session_id) if not (request.since or request.until) else None
    warnings = []
    if snapshot:
        # Retain evidence through the shared privacy path. Object-only saves do
        # not wait for OCR, detector inference, embeddings or the local model gate.
        result = await ingest_bytes(
            snapshot[0], session_id, captured_at=snapshot[1], filename="cloud-view.jpg",
            force=True, objects_only=True, detected_objects=[], emit_alerts=False,
        )
        frame = result.frame
    else:
        frames, warnings, _ = await retrieve_frames(session_id, request.question, "recent", request.since, request.until)
        frame = frames[0] if frames else None
    if frame is None:
        return STALE[language], True, [], warnings
    timestamp = frame.captured_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    max_age = settings.detection_max_age_seconds if walking else settings.recent_evidence_seconds
    if (now() - timestamp).total_seconds() > max_age:
        raise BackendError("Camera evidence is stale", 409, "gemini_evidence_stale")
    # Fetch the exact retained, redacted processed variant. The API owns the
    # evidence ID; the external model cannot invent IDs or storage locations.
    from app.db.models import Frame
    from app.db.session import SessionFactory
    async with SessionFactory() as db:
        row = await db.get(Frame, frame.id)
        if row is None:
            return STALE[language], True, [], warnings
        content = await asyncio.to_thread(get_image, row.processed_object_key)
    image = await asyncio.to_thread(cloud_image, content, PRIVACY_VERSION in frame.enhancements)
    result = await gemini.ask_image(image, request.question, language)
    if (now() - timestamp).total_seconds() > max_age:
        raise BackendError("Camera evidence became stale", 409, "gemini_evidence_stale")
    text = result.answer
    if walking:
        text += " " + {
            "en": "I cannot confirm the route; hazards outside this view may be missed.",
            "fr": "Je ne peux pas confirmer le passage ; des dangers hors image peuvent échapper à la détection.",
            "ar": "لا يمكنني تأكيد حالة المسار؛ قد لا تُكتشف المخاطر خارج الصورة.",
        }[language]
    evidence = [str(frame.id)]
    answer, uncertain = guard_answer(text, result.uncertain or walking or "quality_override" in frame.processing_warnings, language, evidence)
    return answer, uncertain, evidence, warnings
