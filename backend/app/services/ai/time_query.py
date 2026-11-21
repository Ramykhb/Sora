"""Small, deterministic time windows for questions about retained camera frames."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# A point-in-time question needs a bounded tolerance for the frame sampler.
RELATIVE_RADIUS = timedelta(minutes=1)
CLOCK_RADIUS = timedelta(minutes=5)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40,
    "خمس": 5, "خمسة": 5, "عشر": 10, "عشرة": 10, "عشره": 10,
    "خمس عشر": 15, "خمسة عشر": 15, "عشرون": 20, "ثلاثون": 30,
}
NUMBER = r"(?:\d+|" + "|".join(re.escape(word) for word in sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
UNIT = r"(?:minutes?|mins?|heures?|hours?|دقائق|دقيقة|دقايق|ساعات|ساعة)"
RELATIVE = re.compile(
    rf"(?<!\w)(?:(?:il y a|قبل|منذ|من)\s+(?P<before>{NUMBER})\s*(?P<before_unit>{UNIT})"
    rf"|(?P<after>{NUMBER})\s*(?P<after_unit>{UNIT})\s*(?:ago|plus tot))\b"
)
RECENT = re.compile(
    rf"(?:(?:in|within|over)\s+)?(?:the\s+)?last\s+(?P<en>{NUMBER})\s*(?P<en_unit>{UNIT})\b"
    rf"|(?:dans|pendant|au cours des?)\s+(?:les?\s+)?(?P<fr>{NUMBER})\s+"
    rf"dernieres?\s+(?P<fr_unit>{UNIT})\b"
    rf"|(?:خلال|في)\s+(?:اخر|ال)\s*(?P<ar>{NUMBER})\s*(?P<ar_unit>{UNIT})\b"
)
CLOCK = re.compile(
    r"(?P<hour>\d{1,2})(?:(?:\s*:\s*|\s*h\s*)(?P<minute>\d{1,2})?)?\s*"
    r"(?P<period>a\.?m\.?|p\.?m\.?|صباحا?|مساء|مساءا|du matin|de l'apres-midi|du soir)?\b"
)
AROUND = re.compile(r"\b(?:around|about|vers|aux alentours de|حوالي|نحو)\s+(?:at\s+|الساعة\s+)?")
BETWEEN = re.compile(r"\b(?:between|entre|بين)\s+(?:الساعة\s+)?")
AT = re.compile(r"\b(?:at|a|الساعة)\s+")
SEPARATOR = re.compile(r"\s*(?:and|et|و|الى|إلى|حتى)\s+(?:الساعة\s+)?")
DAY_REFERENCE = re.compile(r"\b(?:yesterday|tomorrow|hier|demain|امس|البارحة|غدا)\b")
YESTERDAY = {"yesterday", "hier", "امس", "البارحة"}


@dataclass(frozen=True)
class TimeQuery:
    since: datetime | None = None
    until: datetime | None = None
    target: datetime | None = None
    clarification: str | None = None


def _normalize(question: str) -> str:
    text = unicodedata.normalize("NFKD", question).casefold().replace("’", "'")
    text = "".join(str(unicodedata.digit(char)) if char.isdecimal() else char for char in text)
    text = "".join(char for char in text if not unicodedata.combining(char) and char != "ـ")
    return re.sub(r"\s+", " ", text)


def _duration(number: str, unit: str) -> timedelta | None:
    amount = int(number) if number.isdigit() else NUMBER_WORDS.get(number)
    if not amount or amount > 10080:
        return None
    return timedelta(hours=amount) if unit.startswith(("hour", "heure", "ساع")) else timedelta(minutes=amount)


def _clock(text: str) -> tuple[time | None, int]:
    match = CLOCK.match(text)
    if not match:
        return None, 0
    hour, minute = int(match["hour"]), int(match["minute"] or 0)
    period = match["period"]
    if minute > 59 or hour > 23:
        return None, match.end()
    if period:
        if hour < 1 or hour > 12:
            return None, match.end()
        pm = period.startswith("p") or period.startswith("مساء") or period in ("du soir", "de l'apres-midi")
        hour = hour % 12 + (12 if pm else 0)
    elif 1 <= hour <= 12:
        return None, match.end()  # AM/PM cannot be inferred from a 12-hour clock.
    return time(hour, minute), match.end()


def _clock_phrase(body: str, consumed: int, interval_start: bool) -> bool:
    """Reject numbers describing objects while retaining bare ambiguous clock phrases."""
    if not consumed:
        return False
    match = CLOCK.match(body)
    if match["minute"] is not None or match["period"] or "h" in body[:consumed]:
        return True
    tail = body[consumed:].lstrip()
    return not tail or tail[0] in "?.,!" or (interval_start and bool(SEPARATOR.match(tail)))


def _local_utc(day, clock: time, zone: ZoneInfo) -> datetime | None:
    naive = datetime.combine(day, clock)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    valid = [candidate for candidate in (first, second)
             if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive]
    if not valid or (len(valid) == 2 and valid[0].utcoffset() != valid[1].utcoffset()):
        return None  # A nonexistent or repeated local clock time needs clarification.
    return valid[0].astimezone(timezone.utc)


def interpret_time(question: str, timezone_name: str | None, reference: datetime) -> TimeQuery | None:
    """Interpret supported phrases using the server's UTC clock and the device's timezone."""
    text = _normalize(question)
    reference = reference.astimezone(timezone.utc)
    day_reference = DAY_REFERENCE.search(text)
    match = RELATIVE.search(text)
    if match:
        duration = _duration(match["before"] or match["after"], match["before_unit"] or match["after_unit"])
        if duration is None:
            return TimeQuery(clarification="time")
        target = reference - duration
        return TimeQuery(target - RELATIVE_RADIUS, min(reference, target + RELATIVE_RADIUS), target)
    match = RECENT.search(text)
    if match:
        duration = _duration(match["en"] or match["fr"] or match["ar"],
                             match["en_unit"] or match["fr_unit"] or match["ar_unit"])
        return TimeQuery(reference - duration, reference) if duration else TimeQuery(clarification="time")
    candidates = sorted(
        ((match, kind) for pattern, kind in ((BETWEEN, "between"), (AROUND, "around"), (AT, "at"))
         for match in pattern.finditer(text)),
        key=lambda item: item[0].start(),
    )
    for match, kind in candidates:
        body = text[match.end():].lstrip()
        start_clock, consumed = _clock(body)
        if _clock_phrase(body, consumed, kind == "between"):
            break
    else:
        if day_reference is None:
            return None
        if day_reference[0] not in YESTERDAY:
            return TimeQuery(clarification="time")
        if not timezone_name:
            return TimeQuery(clarification="timezone")
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return TimeQuery(clarification="timezone")
        today = reference.astimezone(zone).date()
        since = _local_utc(today - timedelta(days=1), time.min, zone)
        next_day = _local_utc(today, time.min, zone)
        if since is None or next_day is None:
            return TimeQuery(clarification="time")
        # Retrieval bounds are inclusive; exclude the first instant of today.
        return TimeQuery(since, next_day - timedelta(microseconds=1))
    if day_reference:
        return TimeQuery(clarification="time")
    if start_clock is None:
        return TimeQuery(clarification="time")
    if kind == "between":
        separator = SEPARATOR.match(body[consumed:])
        if not separator:
            return TimeQuery(clarification="time")
        end_body = body[consumed + separator.end():]
        end_clock, end_consumed = _clock(end_body)
        if not _clock_phrase(end_body, end_consumed, False):
            return None
        if end_clock is None or end_clock == start_clock:
            return TimeQuery(clarification="time")
    if not timezone_name:
        return TimeQuery(clarification="timezone")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return TimeQuery(clarification="timezone")
    local_now = reference.astimezone(zone)
    if kind == "between":
        candidates = []
        for offset in (-1, 0, 1):
            end_day = local_now.date() - timedelta(days=offset)
            start_day = end_day - timedelta(days=start_clock > end_clock)
            since, until = _local_utc(start_day, start_clock, zone), _local_utc(end_day, end_clock, zone)
            if offset == 0 and (since is None or until is None):
                return TimeQuery(clarification="time")
            if since and until and since <= reference:
                candidates.append((since, min(until, reference)))
        if not candidates:
            return TimeQuery(clarification="time")
        since, until = max(candidates, key=lambda window: window[0])
        return TimeQuery(since, until)
    for offset in (0, 1):
        day = local_now.date() - timedelta(days=offset)
        target = _local_utc(day, start_clock, zone)
        if offset == 0 and target is None:
            return TimeQuery(clarification="time")
        if target and target <= reference:
            return TimeQuery(target - CLOCK_RADIUS, min(reference, target + CLOCK_RADIUS), target)
    return TimeQuery(clarification="time")
