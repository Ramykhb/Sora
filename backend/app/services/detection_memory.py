"""Durable account-owned targets, consumed only alongside a persisted alert."""
import hashlib
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.core.errors import BackendError
from app.db.auth_models import User
from app.db.models import Alert, CaptureSession, DetectionWatch
from app.db.models.frame import now
from app.db.session import SessionFactory
from app.services.ai import gemini
from app.services.sessions import get_session

MAX_PENDING = 20


def request_target(question):
    text = question.strip().rstrip(".!?؟ ")
    patterns = [
        r"(?:please\s+)?(?:(?:alert|notify|tell|warn)\s+me|let\s+me\s+know)\s+(?:when|if)\s+(?:you\s+)?(?:detect|see|spot|notice|find)\s*(.*)",
        r"(?:please\s+)?(?:alert|notify|tell|warn)\s+me\s+(?:when|if)\s+(.+?)\s+(?:is|are)\s+(?:detected|seen|spotted)",
        r"(?:alerte[- ]moi|préviens[- ]moi|previens[- ]moi|avertis[- ]moi)\s+(?:quand|si|lorsque)\s+(?:tu\s+)?(?:détectes?|detectes?|vois|repères?|reperes?)\s*(.*)",
        r"(?:نبهني|نبّهني|أخبرني|اخبرني|حذرني)\s+(?:عندما|إذا|اذا|لما)\s+(?:تكتشف|ترى|تري|تشوف|تلاحظ)\s*(.*)",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if match:
            target = re.sub(r"\s+please$", "", match[1], flags=re.I)
            return " ".join(target.split())
    return None


def target_key(target):
    text = " ".join(unicodedata.normalize("NFKC", target).casefold().split())
    text = re.sub(r"^(?:a|an|the)\s+", "", text)
    return hashlib.sha256(text.encode()).hexdigest()


async def remember(session_id, target, language, requester_id=None):
    session = await get_session(session_id, active=True)
    if session.owner_id is None or (requester_id is not None and requester_id != session.owner_id):
        raise BackendError("Alert memory belongs to the session owner", 403, "alert_memory_forbidden")
    if not target or len(target) > 200:
        return {
            "en": "What should I watch for? Name an object or sign in under 200 characters.",
            "fr": "Que dois-je surveiller ? Nommez un objet ou un panneau en moins de 200 caractères.",
            "ar": "ما الذي تريد مني مراقبته؟ سمّ جسماً أو علامة بأقل من 200 حرف.",
        }[language], True, [], []
    if not gemini.obstacles_configured():
        return {
            "en": "Automatic detection is not configured. Set GEMINI_API_KEY_2 on the server first.",
            "fr": "La détection automatique n’est pas configurée. Configurez GEMINI_API_KEY_2 sur le serveur.",
            "ar": "الكشف التلقائي غير مهيأ. اضبط GEMINI_API_KEY_2 على الخادم أولاً.",
        }[language], True, [], ["gemini_not_configured"]
    key = target_key(target)
    async with SessionFactory() as db:
        # Serialize registration per account, including the pending-target limit.
        await db.scalar(select(User.id).where(User.id == session.owner_id).with_for_update())
        existing = await db.scalar(select(DetectionWatch).where(
            DetectionWatch.owner_id == session.owner_id, DetectionWatch.target_key == key,
        ))
        if existing is None:
            count = await db.scalar(select(func.count()).select_from(DetectionWatch).where(
                DetectionWatch.owner_id == session.owner_id,
            ))
            if count >= MAX_PENDING:
                return {
                    "en": "You already have 20 pending alerts. Wait for a target to be detected before adding another.",
                    "fr": "Vous avez déjà 20 alertes en attente. Attendez une détection avant d’en ajouter une autre.",
                    "ar": "لديك بالفعل 20 تنبيهاً معلقاً. انتظر اكتشاف أحد الأهداف قبل إضافة آخر.",
                }[language], True, [], ["alert_memory_full"]
            db.add(DetectionWatch(owner_id=session.owner_id, target=target, target_key=key))
            await db.commit()
    confirmation = {
        "en": f"I'll alert you once when I detect {target}, then remove that request from memory.",
        "fr": f"Je vous alerterai une fois lorsque je détecterai {target}, puis j’effacerai cette demande de la mémoire.",
        "ar": f"سأنبهك مرة واحدة عندما أكتشف {target}، ثم سأحذف هذا الطلب من الذاكرة.",
    }[language]
    if not session.alerts_enabled:
        confirmation += " " + {
            "en": "Detection is off. Turn on Detect obstacles to start checking.",
            "fr": "La détection est désactivée. Activez Détecter les obstacles pour lancer les vérifications.",
            "ar": "الكشف متوقف. فعّل كشف العوائق لبدء الفحص.",
        }[language]
    return confirmation, False, [], []


async def pending(owner_id):
    if owner_id is None:
        return []
    async with SessionFactory() as db:
        rows = (await db.scalars(select(DetectionWatch).where(
            DetectionWatch.owner_id == owner_id,
        ).order_by(DetectionWatch.created_at, DetectionWatch.id).limit(MAX_PENDING))).all()
        return [{"id": str(row.id), "target": row.target} for row in rows]


async def fulfill(owner_id, session_id, matched_ids, captured_at, expires_at, is_current, obstacle_message=None):
    if not matched_ids or owner_id is None:
        return None
    from uuid import UUID

    async with SessionFactory() as db:
        session = await db.scalar(select(CaptureSession).where(
            CaptureSession.id == session_id, CaptureSession.owner_id == owner_id,
            CaptureSession.status == "active", CaptureSession.alerts_enabled.is_(True),
            CaptureSession.expires_at > now(),
        ).with_for_update())
        if session is None or not is_current() or now() >= expires_at:
            return None
        # DELETE RETURNING is the atomic claim, even across simultaneous streams.
        # Rollback preserves requests if alert persistence fails.
        rows = (await db.execute(delete(DetectionWatch).where(
            DetectionWatch.owner_id == owner_id,
            DetectionWatch.id.in_([UUID(value) for value in matched_ids]),
        ).returning(DetectionWatch.id, DetectionWatch.target))).all()
        if not rows or not is_current() or now() >= expires_at:
            return None
        targets = "; ".join(row.target for row in rows)
        message = {
            "en": f"Detected: {targets}.",
            "fr": f"Détection : {targets}.",
            "ar": f"تم اكتشاف: {targets}.",
        }[session.language]
        if obstacle_message:
            message += " " + obstacle_message
        alert = {
            "type": "alert", "id": str(uuid4()), "frame_id": None,
            "label": "remembered_detection", "message": message, "language": session.language,
            "captured_at": captured_at.isoformat(), "expires_at": expires_at.isoformat(),
            "created_at": now().isoformat(), "latency_ms": round((now() - captured_at).total_seconds() * 1000, 1),
        }
        db.add(Alert(
            id=UUID(alert["id"]), session_id=session_id, frame_id=None,
            label=alert["label"], message=message, captured_at=captured_at,
        ))
        await db.commit()
    return alert
