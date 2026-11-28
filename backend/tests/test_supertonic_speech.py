import asyncio
import base64
from io import BytesIO
import json
import wave

import numpy as np
import pytest

from app.core.config import Settings, settings
from app.core.errors import BackendError
from app.services.ai import gemini_speech, speech, speech_stream, supertonic_speech


class Processor:
    def validate_text(self, text):
        unsupported = sorted(set(text) & {"🙂", "§"})
        return not unsupported, unsupported


class Engine:
    sample_rate = 44100

    def __init__(self):
        self.calls = []
        self.fail = False
        self.model = type("Model", (), {"text_processor": Processor()})()

    def synthesize(self, text, voice_style, total_steps, lang):
        if self.fail:
            raise RuntimeError("private runtime detail")
        self.calls.append((text, voice_style, total_steps, lang))
        return np.full((1, 22050), 0.5, dtype=np.float32), np.array([0.5])

    def get_voice_style(self, name):
        return name


@pytest.fixture
def engine(monkeypatch):
    fake = Engine()
    monkeypatch.setattr(settings, "supertonic_enabled", True)
    monkeypatch.setattr(settings, "supertonic_voice", "F1")
    monkeypatch.setattr(settings, "supertonic_steps", 8)
    monkeypatch.setattr(supertonic_speech, "engine", lambda: fake)
    supertonic_speech._cache.clear()
    return fake


def local_espeak(monkeypatch):
    monkeypatch.setattr(speech.shutil, "which", lambda _: "espeak-ng")
    result = type("Result", (), {"stdout": b"espeak-wave"})()
    monkeypatch.setattr(speech.subprocess, "run", lambda *args, **kwargs: result)


def test_supertonic_is_the_default_voice():
    defaults = Settings(_env_file=None)
    fields = Settings.model_fields
    assert fields["supertonic_enabled"].default is True
    assert defaults.supertonic_voice == "F1"
    assert defaults.supertonic_steps == 8


@pytest.mark.parametrize("language,text", [
    ("ar", "انعطف يميناً."), ("fr", "Tournez à droite."), ("en", "Turn right."),
])
def test_all_languages_return_playable_wav_from_the_configured_voice(engine, language, text):
    audio = speech.synthesize(text, language)
    with wave.open(BytesIO(audio), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 44100)
        assert wav.getnframes() == 22050
        assert abs(int.from_bytes(wav.readframes(1), "little", signed=True) - 16383) <= 1
    assert engine.calls == [(text, "F1", 8, language)]


def test_arabic_prefers_supertonic_over_gemini(engine, monkeypatch):
    monkeypatch.setattr(settings, "gemini_tts_enabled", True)
    monkeypatch.setattr(gemini_speech, "synthesize_arabic", lambda _: pytest.fail("cloud used"))
    assert speech.synthesize("مرحبا", "ar").startswith(b"RIFF")


def test_short_prompts_are_cached_per_voice_and_language(engine, monkeypatch):
    speech.synthesize("Stream paused.", "en", owner="first")
    speech.synthesize("Stream paused.", "en", owner="first")
    assert len(engine.calls) == 1
    speech.synthesize("Stream paused.", "fr", owner="first")
    monkeypatch.setattr(settings, "supertonic_voice", "F3")
    speech.synthesize("Stream paused.", "en", owner="first")
    assert len(engine.calls) == 3


def test_one_account_never_reuses_audio_cached_for_another(engine):
    for owner in ("first", "second", "first", "second"):
        speech.synthesize("The pharmacy is on your left.", "en", owner=owner)
    assert len(engine.calls) == 2


def test_speech_without_a_known_owner_is_not_cached(engine):
    speech.synthesize("Stream paused.", "en")
    speech.synthesize("Stream paused.", "en")
    assert len(engine.calls) == 2
    assert not supertonic_speech._cache


@pytest.mark.parametrize("path", ["/api/v1/speech/stream", "/api/v1/speech/synthesis"])
def test_speech_routes_cache_per_signed_in_account(client, engine, path):
    api, _ = client
    body = {"text": "Stream paused.", "language": "en"}
    for _ in range(2):
        assert api.post(path, json=body).status_code == 200
    assert len(engine.calls) == 1
    account = {"email": "other@example.com", "password": "another-valid-password"}
    registered = api.post("/api/v1/auth/register", json={**account, "display_name": "Other"})
    assert registered.status_code == 201, registered.text
    token = api.post("/api/v1/auth/login", json=account).json()["access_token"]
    other = api.post(path, json=body, headers={"Authorization": "Bearer " + token})
    assert other.status_code == 200
    assert len(engine.calls) == 2


def test_unsupported_characters_are_removed_instead_of_failing(engine):
    speech.synthesize("Café ahead 🙂 §", "en")
    assert engine.calls[0][0] == "Café ahead"


def test_unsafe_text_is_replaced_before_synthesis(engine):
    speech.synthesize("الطريق آمن", "ar")
    assert engine.calls[0][0] == "لا تتوفر صور واضحة كافية للإجابة."


@pytest.mark.parametrize("text,fail", [("Hello", True), ("🙂", False)])
def test_failure_falls_back_to_espeak(engine, monkeypatch, text, fail):
    local_espeak(monkeypatch)
    engine.fail = fail
    assert speech.synthesize(text, "en") == b"espeak-wave"


def test_arabic_failure_falls_back_to_gemini_when_enabled(engine, monkeypatch):
    engine.fail = True
    monkeypatch.setattr(settings, "gemini_tts_enabled", True)
    monkeypatch.setattr(gemini_speech, "synthesize_arabic", lambda _: b"gemini-wave")
    assert speech.synthesize("مرحبا", "ar") == b"gemini-wave"


def test_fast_requests_skip_supertonic_for_urgent_warnings(engine, monkeypatch):
    local_espeak(monkeypatch)
    assert speech.synthesize("Obstacle ahead.", "en", fast=True) == b"espeak-wave"
    assert engine.calls == []


def test_missing_model_is_reported_without_downloading(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "supertonic_model_dir", tmp_path / "absent")
    supertonic_speech.engine.cache_clear()
    with pytest.raises(BackendError) as error:
        supertonic_speech.synthesize("Hello", "en")
    assert error.value.code == "tts_unavailable"
    assert not (tmp_path / "absent").exists()


def test_prepare_never_replaces_an_unrelated_folder(monkeypatch, tmp_path):
    (tmp_path / "yolo11n.pt").write_bytes(b"weights")
    monkeypatch.setattr(settings, "supertonic_model_dir", tmp_path)
    with pytest.raises(RuntimeError, match="empty folder"):
        supertonic_speech.prepare()
    assert (tmp_path / "yolo11n.pt").read_bytes() == b"weights"


def test_long_answers_split_into_short_ordered_segments():
    text = (
        "I can see a door on your left, a long table in the middle of the room, and two "
        "chairs beside it. The path looks clear.\n1. Walk 1.5 km. 2. Turn left! ثم توقف؟ نعم."
    )
    parts = supertonic_speech.segments(text)
    assert parts[0] == "I can see a door on your left,"
    assert "".join(parts).replace(" ", "") == text.replace(" ", "").replace("\n", "")
    assert all(0 < len(part) <= 160 for part in parts)
    assert not any(part.strip(" .").isdigit() for part in parts)
    assert "The path looks clear." in parts


def test_text_without_punctuation_is_split_between_words():
    parts = supertonic_speech.segments("word " * 100)
    assert all(len(part) <= 160 for part in parts)
    assert " ".join(parts).split() == ["word"] * 100


async def collect(source):
    return [json.loads(line) async for line in source]


def test_stream_sends_first_sentence_before_generating_the_next(engine):
    async def exercise():
        source = speech_stream.local_frames("First sentence. Second sentence.", "en")
        first = json.loads(await anext(source))
        assert [call[0] for call in engine.calls] == ["First sentence."]
        rest = await collect(source)
        return [first, *rest]

    frames = asyncio.run(exercise())
    assert frames[-1] == {"type": "done"}
    total = 0
    for frame in frames[:-1]:
        # The mobile player rejects frames longer than 100000 characters.
        assert len(frame["data"]) <= 100000
        with wave.open(BytesIO(base64.b64decode(frame["data"])), "rb") as wav:
            assert wav.getframerate() == 44100
            total += wav.getnframes()
    # Two half-second sentences plus one short pause between them.
    assert 44100 < total < 44100 * 1.5
    assert [call[0] for call in engine.calls] == ["First sentence.", "Second sentence."]


@pytest.mark.parametrize("language", ["ar", "fr", "en"])
def test_stream_route_serves_every_language_without_gemini(client, engine, language):
    api, _ = client
    response = api.post("/api/v1/speech/stream", json={"text": "Bonjour.", "language": language})
    assert response.status_code == 200
    assert json.loads(response.content.splitlines()[-1]) == {"type": "done"}
    assert engine.calls[0][3] == language


def test_stream_route_falls_back_to_gemini_before_any_audio(client, engine, monkeypatch):
    from app.api.routes import speech as routes

    api, _ = client
    engine.fail = True
    monkeypatch.setattr(settings, "gemini_tts_enabled", True)

    async def cloud(text):
        yield b'{"type":"done"}\n'

    monkeypatch.setattr(routes, "audio_frames", cloud)
    response = api.post("/api/v1/speech/stream", json={"text": "مرحبا", "language": "ar"})
    assert response.status_code == 200
    # Gemini only speaks Arabic here; the phone supplies the other fallbacks.
    english = api.post("/api/v1/speech/stream", json={"text": "Hello", "language": "en"})
    assert english.status_code == 503
    assert "private runtime detail" not in english.text


def test_synthesis_route_forwards_the_fast_choice(client, monkeypatch):
    from app.api.routes import speech as routes

    api, _ = client
    seen = []
    monkeypatch.setattr(routes, "synthesize", lambda *args: seen.append(args) or b"RIFF")
    for provider in ("default", "fast"):
        body = {"text": "Hello", "language": "en", "provider": provider}
        assert api.post("/api/v1/speech/synthesis", json=body).status_code == 200
    assert [args[2] for args in seen] == [False, True]


def test_numbers_reach_the_voice_as_words(engine):
    speech.synthesize("Walk 250 m.", "en")
    assert engine.calls[0][0] == "Walk two hundred and fifty metres."


@pytest.mark.parametrize("configured,cores,expected", [(0, 20, 6), (0, 2, 2), (3, 20, 3)])
def test_threads_default_to_the_measured_fast_setting(monkeypatch, configured, cores, expected):
    monkeypatch.setattr(settings, "supertonic_threads", configured)
    monkeypatch.setattr(supertonic_speech.os, "cpu_count", lambda: cores)
    assert supertonic_speech.threads() == expected
