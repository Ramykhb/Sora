import pytest
from app.services.ai.safety import UNKNOWN, guard_answer


@pytest.mark.parametrize(
    "language,text",
    [
        ("en", "It is safe to walk forward."),
        ("en", "The path is clear. Go ahead."),
        ("fr", "Vous pouvez avancer sans danger."),
        ("ar", "الطريق آمن ويمكنك العبور بأمان."),
    ],
)
def test_assurances_replaced_with_uncertainty(language, text):
    answer, uncertain = guard_answer(text, False, language, ["frame-1"])
    assert answer == UNKNOWN[language]
    assert uncertain is True


@pytest.mark.parametrize("language", ["en", "fr", "ar"])
def test_no_evidence_never_yields_confident_answer(language):
    answer, uncertain = guard_answer("A chair is in front of you.", False, language, [])
    assert answer == UNKNOWN[language] and uncertain


def test_weak_evidence_adds_explicit_uncertainty():
    answer, uncertain = guard_answer("There may be a chair.", True, "en", ["frame-1"])
    assert answer.startswith("I'm not sure.") and uncertain


def test_french_uncertainty_is_preserved():
    text = "Je ne suis pas sûr. Une chaise est visible."
    answer, uncertain = guard_answer(text, True, "fr", ["frame-1"])
    assert answer == text and uncertain


def test_diacritized_arabic_assurance_is_rejected():
    answer, uncertain = guard_answer("الطَّرِيقُ آمِنٌ.", False, "ar", ["frame-1"])
    assert answer == UNKNOWN["ar"] and uncertain
