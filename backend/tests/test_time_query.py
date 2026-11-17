from datetime import datetime, timezone

import pytest

from app.services.ai.time_query import interpret_time
from app.services.ai.retrieval import resolve_scope


REFERENCE = datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("question", [
    "What did I see five minutes ago?",
    "Qu'ai-je vu il y a cinq minutes ?",
    "ماذا رأيت قبل خمس دقائق؟",
])
def test_relative_time_uses_server_clock_without_device_timezone(question):
    window = interpret_time(question, None, REFERENCE)
    assert window.target == datetime(2026, 11, 18, 20, 55, tzinfo=timezone.utc)
    assert window.since == datetime(2026, 11, 18, 20, 54, tzinfo=timezone.utc)
    assert window.until == datetime(2026, 11, 18, 20, 56, tzinfo=timezone.utc)


@pytest.mark.parametrize("question", [
    "Did I see a backpack in the last fifteen minutes?",
    "Qu'ai-je vu dans les quinze dernières minutes ?",
    "ماذا رأيت خلال آخر خمسة عشر دقيقة؟",
])
def test_last_interval_has_exact_utc_boundaries(question):
    window = interpret_time(question, None, REFERENCE)
    assert window.since == datetime(2026, 11, 18, 20, 45, tzinfo=timezone.utc)
    assert window.until == REFERENCE
    assert window.target is None


def test_local_clock_and_explicit_interval_convert_to_utc():
    around = interpret_time("What was on the sign around 2:30 PM?", "Asia/Beirut", REFERENCE)
    assert around.target == datetime(2026, 11, 18, 12, 30, tzinfo=timezone.utc)
    assert around.since == datetime(2026, 11, 18, 12, 25, tzinfo=timezone.utc)
    assert around.until == datetime(2026, 11, 18, 12, 35, tzinfo=timezone.utc)
    interval = interpret_time("What did I pass between 3 PM and 4 PM?", "Asia/Beirut", REFERENCE)
    assert interval.since == datetime(2026, 11, 18, 13, 0, tzinfo=timezone.utc)
    assert interval.until == datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)
    french = interpret_time("Qu'ai-je vu vers 14 h 30 ?", "Asia/Beirut", REFERENCE)
    assert french.target == around.target
    arabic = interpret_time("ماذا رأيت حوالي الساعة ٢:٣٠ مساءً؟", "Asia/Beirut", REFERENCE)
    assert arabic.target == around.target
    assert interpret_time("What was on the sign at 2:30 PM?", "Asia/Beirut", REFERENCE).target == around.target
    assert interpret_time("Qu'ai-je vu à 14 h 30 ?", "Asia/Beirut", REFERENCE).target == around.target
    assert interpret_time("ماذا رأيت الساعة ٢:٣٠ مساءً؟", "Asia/Beirut", REFERENCE).target == around.target


def test_cross_midnight_interval_uses_the_current_local_evening():
    reference = datetime(2026, 11, 18, 21, 30, tzinfo=timezone.utc)  # 11:30 PM Beirut
    window = interpret_time("What did I pass between 11 PM and 1 AM?", "Asia/Beirut", reference)
    assert window.since == datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc)
    assert window.until == reference


def test_ambiguous_clock_or_timezone_requires_clarification():
    assert interpret_time("around 2:30", "Asia/Beirut", REFERENCE).clarification == "time"
    assert interpret_time("at 2:30", "Asia/Beirut", REFERENCE).clarification == "time"
    assert interpret_time("between 3 and 4", "Asia/Beirut", REFERENCE).clarification == "time"
    assert interpret_time("between 3 PM and 3 PM", "Asia/Beirut", REFERENCE).clarification == "time"
    assert interpret_time("around 2:30 PM", None, REFERENCE).clarification == "timezone"
    assert interpret_time("around 2:30 PM", "Bad/Zone", REFERENCE).clarification == "timezone"
    assert interpret_time("What is in front of me?", None, REFERENCE) is None


@pytest.mark.parametrize("question", [
    "What's around me?",
    "What is around the corner?",
    "What about that chair?",
    "What is between the door and the chair?",
    "About how far is the door?",
    "What is between 2 doors and 3 chairs?",
    "Where is my backpack?",
    "Is it safe to walk around the chair?",
    "Qu'y a-t-il vers la porte ?",
    "Qu'y a-t-il entre la porte et la chaise ?",
    "ماذا يوجد حوالي الباب؟",
    "ماذا يوجد بين الباب والكرسي؟",
    "ماذا يوجد ضمن خمس دقايق؟",
])
def test_spatial_questions_have_no_time_window_or_clarification(question):
    assert interpret_time(question, None, REFERENCE) is None


@pytest.mark.parametrize("question", [
    "ماذا رأيت من خمس دقايق؟",
    "شو شفت قبل خمس دقايق؟",
    "شو شفت من ٥ دقايق؟",
])
def test_lebanese_arabic_relative_time(question):
    assert interpret_time(question, None, REFERENCE).target == datetime(2026, 11, 18, 20, 55, tzinfo=timezone.utc)


def test_repeated_dst_hour_is_not_guessed():
    after_fallback = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
    window = interpret_time("What did I see around 1:30 AM?", "America/New_York", after_fallback)
    assert window.clarification == "time"


@pytest.mark.parametrize("question,expected", [
    ("What is in front of me?", "recent"),
    ("Is there an obstacle before me?", "recent"),
    ("What is before the stairs?", "recent"),
    ("Is there a curb before the road?", "recent"),
    ("Qu'y a-t-il avant l'escalier ?", "recent"),
    ("شو في قبل الدرج؟", "recent"),
    ("Is there an obstacle ahead?", "recent"),
    ("Where is my backpack?", "recent"),
    ("Where was my backpack earlier?", "memory"),
    ("What did I pass earlier?", "memory"),
    ("What did I see before entering the room?", "memory"),
    ("What did I see before lunch?", "memory"),
    ("Where was my backpack five minutes ago?", "memory"),
    ("Qu'ai-je passé avant ?", "memory"),
    ("ماذا رأيت قبل قليل؟", "memory"),
])
def test_automatic_scope_preserves_current_and_historical_wording(question, expected):
    assert resolve_scope(question, "auto") == expected
    assert resolve_scope(question, "recent") == "recent"
    assert resolve_scope(question, "memory") == "memory"
