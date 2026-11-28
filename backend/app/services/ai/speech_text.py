"""Write numbers and units as words; Supertonic garbles many of them when given digits."""
import re
import unicodedata

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.", "٬")
# (singular, plural)
_UNITS = {
    "en": {
        "km": ("kilometre", "kilometres"), "m": ("metre", "metres"),
        "cm": ("centimetre", "centimetres"), "min": ("minute", "minutes"),
        "°C": ("degree Celsius", "degrees Celsius"), "%": ("percent", "percent"),
        "$": ("dollar", "dollars"),
    },
    "fr": {
        "km": ("kilomètre", "kilomètres"), "m": ("mètre", "mètres"),
        "cm": ("centimètre", "centimètres"), "min": ("minute", "minutes"),
        "°C": ("degré Celsius", "degrés Celsius"), "%": ("pour cent", "pour cent"),
        "$": ("dollar", "dollars"),
    },
    "ar": {
        unit: (word, word) for unit, word in {
            "km": "كيلومتر", "كم": "كيلومتر", "m": "متر", "م": "متر", "cm": "سنتيمتر",
            "سم": "سنتيمتر", "min": "دقيقة", "°C": "درجة مئوية", "%": "بالمئة",
            "٪": "بالمئة", "$": "دولار",
        }.items()
    },
}
_AND = {"en": "and", "fr": "et", "ar": "و"}


def _number(value: str, language: str) -> str:
    from num2words import num2words

    whole, _, fraction = value.replace(",", ".").partition(".")
    # Phone numbers and codes are read digit by digit.
    if len(whole) > 7 or (len(whole) > 1 and whole.startswith("0")):
        words = " ".join(num2words(int(digit), lang=language) for digit in whole)
    else:
        words = num2words(int(whole), lang=language)
    if fraction:
        point = {"en": "point", "fr": "virgule", "ar": "فاصلة"}[language]
        digits = fraction if len(fraction) > 2 or fraction.startswith("0") else [fraction]
        words += f" {point} " + " ".join(num2words(int(part), lang=language) for part in digits)
    if language == "ar":
        words = words.replace(" و ", " و").replace("مئتا ", "مئتان ")
        words = re.sub("مئتا$", "مئتان", words)
    return words


def _measure(value: str, unit: str, language: str) -> str:
    singular, plural = _UNITS[language][unit]
    words = _number(value, language)
    if language == "fr" and value == "1" and unit == "min":
        words = "une"
    return f"{words} {singular if value == '1' else plural}"


def _time(hour: str, minute: str, language: str) -> str:
    hours, minutes = int(hour), int(minute)
    words = _number(str(hours), language)
    if language == "en":
        if not minutes:
            return f"{words} o'clock"
        oh = "oh " if minutes < 10 else ""
        return f"{words} {oh}{_number(str(minutes), language)}"
    if language == "fr":
        words = "une heure" if hours == 1 else f"{words} heures"
        return f"{words} {_number(str(minutes), language)}" if minutes else words
    return f"{words} و{_number(str(minutes), language)} دقيقة" if minutes else words


def spoken_text(text: str, language: str) -> str:
    from num2words import num2words

    text = text.translate(_DIGITS)
    separator = "," if language == "en" else "[   ]"
    text = re.sub(rf"(?<=\d){separator}(?=\d{{3}}(?!\d))", "", text)
    clock = r"(?<!\d)([01]?\d|2[0-3])\s?{}\s?([0-5]\d)(?!\d)"
    separators = ":" if language != "fr" else "(?::|h)"
    text = re.sub(clock.format(separators), lambda m: _time(m[1], m[2], language), text)
    number = r"\d+(?:[.,]\d+)?" if language != "en" else r"\d+(?:\.\d+)?"
    text = re.sub(rf"\$\s?({number})", lambda m: _measure(m[1], "$", language), text)
    units = "|".join(re.escape(unit) for unit in sorted(_UNITS[language], key=len, reverse=True))
    # A unit ends at anything that is not a letter or an Arabic vowel mark.
    text = re.sub(
        rf"({number})\s?({units})(?![^\W\d_]|[ً-ٟ])",
        lambda m: _measure(m[1], m[2], language), text,
    )
    suffix = {"en": "st|nd|rd|th", "fr": "ère|ème|er|re|e"}.get(language)
    if suffix:
        text = re.sub(
            rf"(\d+)(?:{suffix})(?!\w)",
            lambda m: num2words(int(m[1]), lang=language, to="ordinal"), text,
        )
    text = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", text)
    text = re.sub(number, lambda m: f"{_number(m[0], language)}", text)
    text = text.replace("&", _AND[language]).replace("#", "")
    # Emoji and other pictographs have no pronunciation.
    text = "".join(
        char for char in text if char == "°" or unicodedata.category(char) not in {"So", "Cs"}
    )
    return " ".join(text.replace("️", "").split())
