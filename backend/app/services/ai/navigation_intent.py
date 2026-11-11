"""Extract explicit route targets without asking a language model to guess nicknames."""
import re
from typing import NamedTuple


class RouteTarget(NamedTuple):
    nickname: str
    saved_only: bool


def route_target(question):
    text = re.sub(r"^(?:(?:please|can you|could you)\s+)+", "", question.strip(), flags=re.I)
    patterns = [
        r"(?:route|navigate)(?:\s+me)?(?:\s+(?P<to>to))?\s+(?P<target>.+)",
        r"(?:take|guide|direct)\s+me(?:\s+(?P<to>to))?\s+(?P<target>.+)",
        r"(?:go|let['’]s go)(?:\s+(?P<to>to))?\s+(?P<target>.+)",
        r"(?:(?:give|show)\s+me\s+)?(?:walking\s+)?directions(?:\s+(?P<to>to))?\s+(?P<target>.+)",
        r"(?:start|begin|plan)\s+(?:(?:a|my|the)\s+)?(?:walking\s+)?(?:trip|route)\s+(?P<to>to|towards?|for)\s+(?P<target>.+)",
        r"how\s+(?:do|can)\s+i\s+get\s+(?P<to>to)\s+(?P<target>.+)",
        r"(?:itin[ée]raire|trajet)\s+(?P<to>vers|pour)\s+(?P<target>.+)",
        r"(?:خذني|(?:ابدأ|ابدا)\s+(?:رحلة|مسار)|مسار|اتجاهات)\s+(?P<to>إلى|الى)\s+(?P<target>.+)",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if match:
            nickname = re.sub(r"\s+please[.!?]*$", "", match["target"], flags=re.I).strip().rstrip(".!?؟").strip()
            if not nickname:
                return None
            explicit = re.match(r"^(?:saved\s+(?:destination\s+)?)(.+)$", nickname, re.I)
            if explicit:
                return RouteTarget(explicit[1].strip(), True)
            return RouteTarget(nickname, match["to"] is None or nickname.casefold() in {"home", "my home"})
    return None
