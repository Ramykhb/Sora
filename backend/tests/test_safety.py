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


def test_weak_evidence_retains_uncertainty_without_repetitive_preface():
    answer, uncertain = guard_answer("There may be a chair.", True, "en", ["frame-1"])
    assert answer == "There may be a chair." and uncertain


def test_model_preface_is_removed_without_changing_uncertainty():
    text = "Je ne suis pas sûr. Une chaise est visible."
    answer, uncertain = guard_answer(text, True, "fr", ["frame-1"])
    assert answer == "Une chaise est visible." and uncertain


def test_diacritized_arabic_assurance_is_rejected():
    answer, uncertain = guard_answer("الطَّرِيقُ آمِنٌ.", False, "ar", ["frame-1"])
    assert answer == UNKNOWN["ar"] and uncertain


@pytest.mark.parametrize("text,expected", [
    ("I'm not sure. A laptop is visible.", "A laptop is visible."),
    ("I’m not sure. I am not sure. A laptop is visible.", "A laptop is visible."),
    ("لست متأكداً. يظهر حاسوب محمول.", "يظهر حاسوب محمول."),
])
def test_stock_uncertainty_preface_is_removed(text, expected):
    answer, uncertain = guard_answer(text, True, "en", ["frame-1"])
    assert answer == expected
    assert uncertain is True


def test_empty_model_answer_after_preface_uses_specific_missing_evidence_message():
    answer, uncertain = guard_answer("I'm not sure.", True, "en", ["frame-1"])
    assert answer == UNKNOWN["en"] and uncertain
    assert not answer.startswith("I'm not sure")
