"""Extractive object overviews: no generative inference or OCR on this path."""

import re
import unicodedata
from datetime import datetime, timezone

from app.core.config import settings
from app.db.models.frame import now
from app.services.ai.retrieval import retrieve_frames
from app.services.ai.safety import STALE
from app.services.frames.ingestion import ingest_bytes
from app.services.frames.processing import detect_live
from app.services.streaming.session import streams


def is_overview(question):
    text = "".join(c for c in unicodedata.normalize("NFKD", question.casefold())
                   if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split()).replace("أ", "ا").replace("إ", "ا")
    text = re.sub(r"\binfront\b", "in front", text)
    # Recognize natural object-overview wording, rather than requiring one
    # exact sentence. Attribute, text-reading and route questions contain words
    # outside this vocabulary and keep their separate evidence/model path.
    overview_words = set("what is are s us in front of me ahead around here there right now currently object objects thing things this that those these the a an do does you camera see detect can could tell describe my surroundings please".split())
    if (
        (text.startswith(("what ", "describe ", "can you ", "could you ", "please ", "tell me ")))
        and re.search(r"\b(?:in front of me|ahead of me|around me)\b", text)
        and set(text.split()) <= overview_words
    ):
        return True
    return bool(re.fullmatch(
        r"(?:what (?:objects? )?(?:is|are|s|us) (?:right )?(?:in front of me|ahead of me|around me|here)|"
        r"what do you (?:see|detect)(?: (?:in front of me|around me|right now))?|"
        r"what (?:objects (?:do you|does the camera)|does the camera|can you) (?:see|detect)|"
        r"what objects are (?:in front of me|around me|visible)|"
        r"describe (?:my surroundings|the (?:current )?scene|what is in front of me)|"
        r"qu (?:est ce qu il y a|y a t il) (?:devant moi|autour de moi)|"
        r"qu est ce que (?:tu vois|vous voyez)|decris (?:la scene|mon environnement)|"
        r"ماذا (?:يوجد|ترى|تري) (?:امامي|حولي)|ما (?:الذي|الموجود) امامي|ماذا امامي|صف ما امامي)",
        text,
    ))


# The prepared detector's taxonomy. Unknown labels are never copied into speech.
_NAMES = """
person|personne|شخص
bicycle|vélo|دراجة هوائية
car|voiture|سيارة
motorcycle|moto|دراجة نارية
airplane|avion|طائرة
bus|bus|حافلة
train|train|قطار
truck|camion|شاحنة
boat|bateau|قارب
traffic light|feu de circulation|إشارة مرور
fire hydrant|borne d'incendie|صنبور إطفاء
stop sign|panneau stop|لافتة توقف
parking meter|parcmètre|عداد وقوف
bench|banc|مقعد
bird|oiseau|طائر
cat|chat|قطة
dog|chien|كلب
horse|cheval|حصان
sheep|mouton|خروف
cow|vache|بقرة
elephant|éléphant|فيل
bear|ours|دب
zebra|zèbre|حمار وحشي
giraffe|girafe|زرافة
backpack|sac à dos|حقيبة ظهر
umbrella|parapluie|مظلة
handbag|sac à main|حقيبة يد
tie|cravate|ربطة عنق
suitcase|valise|حقيبة سفر
frisbee|frisbee|قرص طائر
skis|skis|زلاجات
snowboard|snowboard|لوح تزلج على الثلج
sports ball|ballon|كرة
kite|cerf-volant|طائرة ورقية
baseball bat|batte de baseball|مضرب بيسبول
baseball glove|gant de baseball|قفاز بيسبول
skateboard|skateboard|لوح تزلج
surfboard|planche de surf|لوح ركوب الأمواج
tennis racket|raquette de tennis|مضرب تنس
bottle|bouteille|زجاجة
wine glass|verre à vin|كأس
cup|tasse|كوب
fork|fourchette|شوكة
knife|couteau|سكين
spoon|cuillère|ملعقة
bowl|bol|وعاء
banana|banane|موزة
apple|pomme|تفاحة
sandwich|sandwich|شطيرة
orange|orange|برتقالة
broccoli|brocoli|بروكلي
carrot|carotte|جزرة
hot dog|hot-dog|شطيرة نقانق
pizza|pizza|بيتزا
donut|beignet|كعكة محلاة
cake|gâteau|كعكة
chair|chaise|كرسي
couch|canapé|أريكة
potted plant|plante en pot|نبتة في أصيص
bed|lit|سرير
dining table|table à manger|طاولة طعام
toilet|toilettes|مرحاض
tv|téléviseur|تلفاز
laptop|ordinateur portable|حاسوب محمول
mouse|souris d'ordinateur|فأرة حاسوب
remote|télécommande|جهاز تحكم
keyboard|clavier|لوحة مفاتيح
cell phone|téléphone portable|هاتف محمول
microwave|micro-ondes|ميكروويف
oven|four|فرن
toaster|grille-pain|محمصة خبز
sink|évier|حوض
refrigerator|réfrigérateur|ثلاجة
book|livre|كتاب
clock|horloge|ساعة
vase|vase|مزهرية
scissors|ciseaux|مقص
teddy bear|ours en peluche|دمية دب
hair drier|sèche-cheveux|مجفف شعر
toothbrush|brosse à dents|فرشاة أسنان
"""
LABELS = {parts[0]: dict(zip(("en", "fr", "ar"), parts))
          for line in _NAMES.strip().splitlines() if (parts := line.split("|"))}


def object_overview(objects, language):
    labels = list(dict.fromkeys(
        obj["label"] for obj in sorted(objects, key=lambda o: o.get("confidence", 0), reverse=True)
        if obj.get("confidence", 0) >= settings.yolo_confidence and obj.get("label") in LABELS
    ))[:5]
    if not labels:
        return {
            "en": "No supported objects were identified; that does not establish a clear route.",
            "fr": "Aucun objet reconnu n’a été détecté ; cela ne confirme pas un passage libre.",
            "ar": "لم يتم تحديد أجسام مدعومة؛ هذا لا يؤكد خلو الطريق.",
        }[language]
    names = ", ".join(LABELS[label][language] for label in labels)
    return {
        "en": f"The camera detects {names}; other objects may be missed.",
        "fr": f"La caméra détecte {names} ; d’autres objets peuvent manquer.",
        "ar": f"تكتشف الكاميرا {names}؛ قد لا تُكتشف أجسام أخرى.",
    }[language]


def walking_observation(objects, width, language):
    """Camera-relative locations, never a judgment about navigable space."""
    supported = [obj for obj in objects if obj.get("label") in LABELS
                 and obj.get("confidence", 0) >= settings.yolo_confidence]

    def position(obj):
        center = (obj["box"][0] + obj["box"][2]) / (2 * width)
        return "left" if center < .3 else "right" if center > .7 else "center"

    supported.sort(key=lambda obj: (position(obj) != "center", -obj["confidence"]))
    places = {
        "en": {"left": "left", "center": "center", "right": "right"},
        "fr": {"left": "gauche", "center": "centre", "right": "droite"},
        "ar": {"left": "اليسار", "center": "الوسط", "right": "اليمين"},
    }[language]
    names = list(dict.fromkeys(
        f"{LABELS[obj['label']][language]} ({places[position(obj)]})" for obj in supported
    ))[:5]
    if names:
        observed = {
            "en": "The camera detects " + ", ".join(names) + " in its view.",
            "fr": "La caméra détecte " + ", ".join(names) + " dans son image.",
            "ar": "تكتشف الكاميرا " + "، ".join(names) + " في الصورة.",
        }[language]
    else:
        observed = {
            "en": "No supported objects were detected in the camera view.",
            "fr": "Aucun objet reconnu n’a été détecté dans l’image.",
            "ar": "لم يتم اكتشاف أجسام مدعومة في صورة الكاميرا.",
        }[language]
    limits = {
        "en": "Not sure about the walking path: object detection alone can't confirm the ground or passage.",
        "fr": "Le passage reste indéterminé : la détection d’objets seule ne permet pas d’évaluer le sol ou le passage.",
        "ar": "حالة المسار غير محددة؛ كشف الأجسام وحده لا يكفي لتقييم الأرض أو الممر.",
    }[language]
    return limits + " " + observed


async def answer_overview(session_id, request, language, *, walking=False):
    import asyncio

    snapshot = streams.fresh_detected_snapshot(session_id) if not (request.since or request.until) else None
    if snapshot is None and not (request.since or request.until) and (raw := streams.fresh_snapshot(session_id)):
        width, height, objects = await asyncio.to_thread(detect_live, raw[0])
        snapshot = raw[0], {"captured_at": raw[1].isoformat(), "detected_objects": objects,
                            "width": width, "height": height}
    if snapshot:
        content, observation = snapshot
        scale = min(1, settings.max_image_side / max(observation.get("width", 1), observation.get("height", 1)))
        objects = [{**obj, "box": [round(value * scale, 1) for value in obj["box"]]}
                   for obj in observation["detected_objects"]]
        result = await ingest_bytes(
            content, session_id, captured_at=datetime.fromisoformat(observation["captured_at"]),
            filename="live-overview.jpg", force=True, objects_only=True,
            detected_objects=objects, emit_alerts=False,
        )
        frame, warnings = result.frame, []
    else:
        frames, warnings, _ = await retrieve_frames(
            session_id, request.question, "recent", request.since, request.until,
        )
        frame = frames[0] if frames else None
    if frame is None:
        return STALE[language], True, [], warnings
    timestamp = frame.captured_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if walking and (now() - timestamp).total_seconds() > settings.detection_max_age_seconds:
        return STALE[language], True, [], warnings
    answer = walking_observation(frame.detected_objects, frame.width, language) if walking else object_overview(frame.detected_objects, language)
    return answer, True, [str(frame.id)], warnings
