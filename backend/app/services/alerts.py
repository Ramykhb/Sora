from datetime import timedelta
from sqlalchemy import select
from app.core.config import settings
from app.db.models import Alert
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.events import events


async def generate_alert(frame, language):
    candidates = []
    if "central_closed_door" in frame.scene_flags:
        candidates.append(
            (
                "closed_door",
                {
                    "en": "A closed door appears in the center of the camera view.",
                    "fr": "Une porte fermée semble se trouver au centre de l’image.",
                    "ar": "يبدو أن هناك باباً مغلقاً في وسط صورة الكاميرا.",
                }[language],
            )
        )
    labels = {
        "person",
        "car",
        "truck",
        "bus",
        "bicycle",
        "motorcycle",
        "chair",
        "bench",
        "couch",
        "bed",
    }
    for obj in frame.detected_objects:
        x1, y1, x2, y2 = obj["box"]
        center = (x1 + x2) / 2 / frame.width
        area = (x2 - x1) * (y2 - y1) / (frame.width * frame.height)
        if obj["label"] in labels and 0.3 < center < 0.7 and area >= 0.15:
            candidates.append(
                (
                    obj["label"],
                    {
                        "en": "An object occupies the center of the camera view. I can't judge the whole route.",
                        "fr": "Un objet occupe le centre de l’image. Je ne peux pas évaluer tout le trajet.",
                        "ar": "يوجد جسم في وسط صورة الكاميرا. لا يمكنني تقييم المسار كاملاً.",
                    }[language],
                )
            )
    for label, message in candidates:
        async with SessionFactory() as db:
            recent = await db.scalar(
                select(Alert.id).where(
                    Alert.session_id == frame.session_id,
                    Alert.label == label,
                    Alert.created_at > now() - timedelta(seconds=settings.alert_cooldown_seconds),
                )
            )
            if recent:
                continue
            row = Alert(
                session_id=frame.session_id, frame_id=frame.id, label=label, message=message
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            events.publish(
                frame.session_id,
                {
                    "type": "alert",
                    "id": str(row.id),
                    "frame_id": str(frame.id),
                    "message": message,
                    "language": language,
                },
            )
        break
