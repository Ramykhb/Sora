import re
import unicodedata

UNKNOWN = {
    "en": "I'm not sure. I don't have enough clear camera evidence to answer that.",
    "fr": "Je ne suis pas sûr. Les images disponibles ne permettent pas de répondre avec certitude.",
    "ar": "لست متأكداً. لا تتوفر صور واضحة كافية للإجابة.",
}
STALE = {
    "en": "I'm not sure. I don't have a recent camera view. Please show the scene again.",
    "fr": "Je ne suis pas sûr. Je n’ai pas d’image récente. Montrez à nouveau la scène.",
    "ar": "لست متأكداً. لا تتوفر صورة حديثة. يرجى توجيه الكاميرا إلى المشهد مجدداً.",
}
# Block safety assurances and unsupported movement directions in all supported languages.
FORBIDDEN = re.compile(
    r"\bsafe(?:ly)?\b|\bsecure\b|\bs[ée]cur(?:is[ée]|it[ée])|sans danger|aucun danger|"
    r"(?:c.est|il est) s[ûu]r de|(?:trajet|chemin).{0,15}s[ûu]r|آمن|آمنة|بأمان|امان|أمان|لا خطر|"
    r"go ahead|walk forward|cross (?:now|the road)|path is clear|clear to (?:walk|go)|"
    r"avancez|traversez|الطريق خال|تقدم للأمام|اعبر الآن",
    re.I,
)


def blocked_text(text):
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", text)
        if unicodedata.category(character) != "Mn"
    )
    return bool(FORBIDDEN.search(normalized))


def guard_answer(text, uncertain, language, evidence_ids):
    if not evidence_ids or blocked_text(text):
        return UNKNOWN[language], True
    if uncertain:
        prefix = {"en": "I'm not sure. ", "fr": "Je ne suis pas sûr. ", "ar": "لست متأكداً. "}[
            language
        ]
        if not text.startswith(prefix.strip()):
            text = prefix + text
    return text[:700], uncertain


ROUTE_QUESTION = re.compile(
    r"safe|can i (?:walk|cross|proceed)|puis.je.*(?:marcher|traverser)|sans danger|"
    r"هل.*(?:أمشي|امشي|العبور|آمن)|يمكنني.*(?:المشي|العبور)",
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
