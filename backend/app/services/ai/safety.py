import re
import unicodedata

UNKNOWN = {
    "en": "I don't have enough clear camera evidence to answer that.",
    "fr": "Les images disponibles ne permettent pas de répondre avec certitude.",
    "ar": "لا تتوفر صور واضحة كافية للإجابة.",
}
STALE = {
    "en": "I don't have a recent camera view. Please show the scene again.",
    "fr": "Je n’ai pas d’image récente. Montrez à nouveau la scène.",
    "ar": "لا تتوفر صورة حديثة. يرجى توجيه الكاميرا إلى المشهد مجدداً.",
}
# Block safety assurances and unsupported movement directions in all supported languages.
FORBIDDEN = re.compile(
    r"\bsafe(?:ly)?\b|\bsecure\b|\bs[ée]cur(?:is[ée]|it[ée])|sans danger|aucun danger|"
    r"(?:c.est|il est) s[ûu]r de|(?:trajet|chemin).{0,15}s[ûu]r|آمن|آمنة|بأمان|امان|أمان|لا خطر|"
    r"go ahead|walk forward|cross (?:now|the road)|path is clear|clear to (?:walk|go)|"
    r"avancez|traversez|الطريق خال|تقدم للأمام|اعبر الآن",
    re.I,
)
ASSURANCE = re.compile(
    r"\b(?:path|walkway|route|passage|road|way|hallway|corridor|aisle|sidewalk|pavement|crossing)\b"
    r"[^.!?;]{0,30}\b(?:is|looks?|seems?|appears?)\s+(?:to\s+be\s+)?"
    r"(?:(?:completely|perfectly|entirely|totally|fully|all)\s+)?clear\b|"
    r"\byou\s+(?:can|may|should|must)\s+(?:now\s+)?(?:proceed|walk|cross|advance|continue|go ahead)\b|"
    r"\b(?:no|without any|without)\s+(?:risk|danger)\b|\brisk[ -]?free\b|"
    r"\b(?:sans|aucun)\s+risque\b|"
    r"\bvous\s+pouvez\s+(?:marcher|avancer|traverser|continuer)\b|"
    r"\b(?:chemin|passage|trajet|voie|couloir)\b.{0,25}\best\s+(?:tout a fait\s+)?(?:sur|libre|degage)\b|"
    r"(?:يمكنك|بامكانك)\s+(?:المشي|العبور|التقدم)|بدون خطر|بلا خطر|"
    r"(?:الطريق|المسار|الممر)\s+(?:امن|امنة|خال(?:يا)?\s+من\s+العوائق)",
    re.I,
)


def blocked_text(text):
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if unicodedata.category(character) not in {"Mn", "Cf"}
    )
    normalized = " ".join(normalized.replace("ـ", "").split())
    if FORBIDDEN.search(text) or FORBIDDEN.search(normalized):
        return True
    for match in ASSURANCE.finditer(normalized):
        # A specific inability to confirm clearance is not an assurance. Only
        # exempt that claim, never a later "you can proceed" in the same answer.
        prefix = normalized[max(0, match.start() - 60):match.start()]
        if re.search(r"(?:cannot|can't|can not)\s+(?:confirm|establish|say|determine)\s+(?:that\s+)?(?:the\s+)?$", prefix, re.I):
            continue
        return True
    return False


def guard_answer(text, uncertain, language, evidence_ids):
    if not evidence_ids or blocked_text(text):
        return UNKNOWN[language], True
    # Keep evidence uncertainty in metadata and specific limitations in the answer,
    # rather than adding the same preface to every observation.
    text = re.sub(
        r"^(?:(?:I(?:['’]m| am) not sure|Je ne suis pas s[ûu]r|لست متأكداً)[.!]\s*)+",
        "", text.strip(), flags=re.I,
    )
    if not text:
        return UNKNOWN[language], True
    return text[:700], uncertain


def guard_caption(text, uncertain, language):
    """Captions are also user-visible speech, including outside the Q&A path."""
    if blocked_text(text):
        return UNKNOWN[language], True
    return text, uncertain


ROUTE_QUESTION = re.compile(
    r"safe|\bobstacles?\b|(?:can|should|may) i (?:walk|cross|proceed|move|go|continue)|"
    r"(?:path|route|way).{0,25}clear|(?:anything|obstacles?).{0,25}in my way|"
    r"(?:puis.je|peux.je|je peux).*(?:marcher|traverser|avancer)|sans danger|"
    r"هل.*(?:أمشي|امشي|العبور|آمن|المشي|المسار)|يمكنني.*(?:المشي|العبور)",
    re.I,
)

IDENTITY_QUESTION = re.compile(
    r"who is (?:this|that|the) (?:person|man|woman)|identify.*(?:person|face)|recognize.*face|"
    r"qui est (?:cette|cet|la|le)|reconna[iî]tre.*visage|من هذ[اه]|تعرف.*وجه",
    re.I,
)
IDENTITY_REFUSAL = {
    "en": "I can describe visible objects, but I don't identify people.",
    "fr": "Je peux décrire les objets visibles, mais je n’identifie pas les personnes.",
    "ar": "يمكنني وصف الأجسام الظاهرة، لكنني لا أحدد هوية الأشخاص.",
}
