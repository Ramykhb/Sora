"""Current-frame object requests and bounded, camera-relative object locations."""
import math
import re
import unicodedata
from dataclasses import dataclass

from app.core.config import settings
from app.services.ai.live_answer import LABELS


def normalized(value):
    value = "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                    if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[^\W_]+", value))


@dataclass(frozen=True)
class ObjectQuery:
    target: str
    detector_label: str | None


def query(question):
    # Historical and proximity questions retain their existing retrieval/search.
    if re.search(r"\b(?:earlier|yesterday|previous|before|ago|nearest|closest|nearby|restaurant|pharmacy|hospital|hier|proche)\b|أقرب|اقرب|بالقرب|سابق|أمس", question, re.I):
        return None
    text = question.strip().rstrip(".?!؟ ")
    patterns = [
        r"(?:(?:please|can you|could you)\s+)*(?:help me\s+)?(?:find|locate)\s+(.+)",
        r"where(?:\s+(?:is|are)|['’]s)\s+(.+)",
        r"(?:can|could)\s+you\s+(?:see|spot|find)\s+(.+)",
        r"(?:help me\s+)?look\s+for\s+(.+)",
        r"(?:aide[- ]moi [àa] |aidez[- ]moi [àa] |peux[- ]tu |pouvez[- ]vous )?(?:trouver|trouve|trouvez|localiser|cherche|chercher)\s+(.+)",
        r"o[ùu]\s+(?:est|sont)\s+(.+)",
        r"(?:ساعدني\s+(?:في\s+)?(?:العثور على|إيجاد|ايجاد)|ابحث عن|أين|اين)\s+(.+)",
    ]
    target = None
    for pattern in patterns:
        if match := re.fullmatch(pattern, text, re.I):
            target = re.sub(r"(?:\s+(?:please|right now|in (?:this|the) (?:image|view)|in front of me))+$", "", match[1], flags=re.I).strip()
            break
    if not target or len(target) > 160:
        return None
    simple = normalized(target)
    simple = re.sub(r"^(?:my|the|a|an|mon|ma|mes|le|la|les|un|une)\s+", "", simple)
    aliases = {normalized(name): label for label, languages in LABELS.items() for name in languages.values()}
    aliases.update({normalized(label): label for label in LABELS})
    aliases.update({"phone": "cell phone", "mobile phone": "cell phone", "rucksack": "backpack", "knapsack": "backpack", "purse": "handbag", "sofa": "couch", "table": "dining table", "حقيبة ظهري": "backpack"})
    label = aliases.get(simple) or (aliases.get(simple[:-1]) if simple.endswith("s") else None)
    # Exact label aliases only: a red backpack, keys, or a specific person's
    # belongings require visual interpretation rather than a class-only guess.
    return ObjectQuery(target, label)


_POSITIONS = {
    "en": ["near the top left", "near the top center", "near the top right", "on the left", "in the center", "on the right", "near the bottom left", "near the bottom center", "near the bottom right"],
    "fr": ["en haut à gauche", "en haut au centre", "en haut à droite", "à gauche", "au centre", "à droite", "en bas à gauche", "en bas au centre", "en bas à droite"],
    "ar": ["في أعلى اليسار", "في أعلى الوسط", "في أعلى اليمين", "على اليسار", "في الوسط", "على اليمين", "في أسفل اليسار", "في أسفل الوسط", "في أسفل اليمين"],
}


def position(horizontal, vertical, language):
    column = ("left", "center", "right").index(horizontal)
    row = ("top", "middle", "bottom").index(vertical)
    return _POSITIONS[language][row * 3 + column]


def unknown(language):
    return {
        "en": "I can't identify the requested object confidently in this camera view. Try a clearer, well-lit view.",
        "fr": "Je ne peux pas identifier cet objet avec certitude dans cette image. Essayez une vue plus claire et mieux éclairée.",
        "ar": "لا أستطيع تحديد الجسم المطلوب بثقة في هذه الصورة. جرّب صورة أوضح وبإضاءة أفضل.",
    }[language]


def cloud_prefix(status, horizontal, vertical, language):
    if status == "visible" and horizontal != "unknown" and vertical != "unknown":
        location = position(horizontal, vertical, language)
        return {
            "en": f"A matching object is visible {location} in the camera view.",
            "fr": f"Un objet correspondant est visible {location} de l’image.",
            "ar": f"يوجد جسم مطابق {location} في الصورة.",
        }[language]
    if status == "not_visible":
        return {
            "en": "I can't identify the requested object in this camera view.",
            "fr": "Je ne repère pas l’objet demandé dans cette image.",
            "ar": "لا أرى الجسم المطلوب بوضوح في هذه الصورة.",
        }[language]
    return {
        "en": "I can't locate the requested object confidently in this view.",
        "fr": "Je ne peux pas localiser l’objet demandé avec certitude dans cette image.",
        "ar": "لا أستطيع تحديد مكان الجسم المطلوب بثقة في هذه الصورة.",
    }[language]


def detection_answer(finding, objects, width, height, language, quality_uncertain=False):
    if finding.detector_label is None or quality_uncertain or width <= 0 or height <= 0:
        return unknown(language), True
    matches = []
    for item in objects:
        if item.get("label") != finding.detector_label:
            continue
        try:
            confidence = float(item["confidence"])
            x1, y1, x2, y2 = map(float, item["box"])
            if not all(math.isfinite(v) for v in (confidence, x1, y1, x2, y2)):
                continue
            if confidence < settings.yolo_confidence or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        x, y = (x1 + x2) / (2 * width), (y1 + y2) / (2 * height)
        horizontal = "left" if x < 1 / 3 else "right" if x > 2 / 3 else "center"
        vertical = "top" if y < 1 / 3 else "bottom" if y > 2 / 3 else "middle"
        matches.append((confidence, position(horizontal, vertical, language)))
    if not matches:
        return {
            "en": "I can't identify the requested object in this camera view. It may be obscured or outside the image.",
            "fr": "Je ne repère pas l’objet demandé dans cette image. Il peut être masqué ou hors champ.",
            "ar": "لا أستطيع تحديد الجسم المطلوب في هذه الصورة؛ قد يكون محجوباً أو خارجها.",
        }[language], True
    matches.sort(reverse=True)
    label = LABELS[finding.detector_label][language]
    if len(matches) > 1:
        locations = "; ".join(location for _, location in matches[:3])
        return {
            "en": f"Multiple possible matches for {label} are visible: {locations} in the camera view. I can't tell which one you mean.",
            "fr": f"Plusieurs objets possibles ({label}) sont visibles : {locations} de l’image. Je ne peux pas déterminer lequel vous cherchez.",
            "ar": f"توجد عدة أجسام محتملة ({label}): {locations} في الصورة. لا أستطيع تحديد أيها تقصد.",
        }[language], True
    confidence, location = matches[0]
    if confidence < max(settings.yolo_confidence, .65):
        return {
            "en": f"A possible match ({label}) appears {location} in the camera view; I can't identify it confidently.",
            "fr": f"Un objet possible ({label}) apparaît {location} de l’image, sans identification certaine.",
            "ar": f"يظهر جسم محتمل ({label}) {location} في الصورة، لكن لا يمكنني تحديده بثقة.",
        }[language], True
    article = "some" if finding.detector_label in {"scissors", "skis"} else "an" if label[0] in "aeiou" else "a"
    return {
        "en": f"I can see {article} {label} {location} in the camera view.",
        "fr": f"Un objet correspondant ({label}) est visible {location} de l’image.",
        "ar": f"أرى جسماً مطابقاً ({label}) {location} في الصورة.",
    }[language], False
