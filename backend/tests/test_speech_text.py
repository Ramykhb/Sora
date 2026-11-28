import pytest

from app.services.ai.speech_text import spoken_text


@pytest.mark.parametrize("text,expected", [
    ("Walk 250 m, then turn left.", "Walk two hundred and fifty metres, then turn left."),
    ("About 1.5 km (20 min).", "About one point five kilometres (twenty minutes)."),
    ("It is 1 m away.", "It is one metre away."),
    ("It's 3:45 PM.", "It's three forty-five PM."),
    ("Meet at 9:05, or 10:00.", "Meet at nine oh five, or ten o'clock."),
    ("Price: $12 & 50% off #1", "Price: twelve dollars and fifty percent off one"),
    ("Turn onto 5th Ave.", "Turn onto fifth Ave."),
    ("It is 1,500 m.", "It is one thousand, five hundred metres."),
    ("Call 03123456.", "Call zero three one two three four five six."),
    ("Gate B12 🙂", "Gate B twelve"),
])
def test_english_numbers_and_units_are_written_as_words(text, expected):
    assert spoken_text(text, "en") == expected


@pytest.mark.parametrize("text,expected", [
    ("Marchez 1,5 km.", "Marchez un virgule cinq kilomètres."),
    ("Continuez 250 m.", "Continuez deux cent cinquante mètres."),
    ("Il est 15 h 45.", "Il est quinze heures quarante-cinq."),
    ("À 1:00, 21 °C.", "À une heure, vingt et un degrés Celsius."),
    ("1 500 m, 1 min, 5 %", "mille cinq cents mètres, une minute, cinq pour cent"),
    ("Prenez la 2e rue.", "Prenez la deuxième rue."),
])
def test_french_numbers_and_units_are_written_as_words(text, expected):
    assert spoken_text(text, "fr") == expected


@pytest.mark.parametrize("text,expected", [
    ("المسافة ٢٥ متراً.", "المسافة خمسة وعشرون متراً."),
    ("على بعد 200 م", "على بعد مئتان متر"),
    ("بعد 1.5 كم", "بعد واحد فاصلة خمسة كيلومتر"),
    ("بعد ١٫٥ كم", "بعد واحد فاصلة خمسة كيلومتر"),
    ("الساعة 3:45.", "الساعة ثلاثة وخمسة وأربعون دقيقة."),
    ("خصم 50%", "خصم خمسون بالمئة"),
])
def test_arabic_numbers_and_units_are_written_as_words(text, expected):
    assert spoken_text(text, "ar") == expected


@pytest.mark.parametrize("language,text", [
    ("en", "A chair is ahead."),
    ("fr", "Je vois une porte à votre gauche."),
    ("ar", "اِبْدَأْ البث، ثم قل «يا سورا»."),
])
def test_ordinary_sentences_are_unchanged(language, text):
    assert spoken_text(text, language) == text
