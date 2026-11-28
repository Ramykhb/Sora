import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services import sessions
from app.services.alerts import stop_sign_message
from app.services.events import events
from app.services.frames import processing
from app.services.streaming import session as streaming
from app.services.streaming.session import LiveState, Streams


@pytest.mark.parametrize('text', ['STOP', 'stop', 'Stop!', 'road\nSTOP\nahead', 'ＳＴＯＰ'])
def test_matches_a_complete_stop_word(text):
    assert stop_sign_message(text, 95, 'en') == 'A stop sign is visible.'


@pytest.mark.parametrize('text,confidence', [
    ('nonstop', 99), ('stopping', 99), ('stopped', 99), ('stopwatch', 99),
    ('', 99), ('STOP', 10), ('STOP', float('nan')),
])
def test_substrings_and_unreliable_ocr_do_not_alert(text, confidence):
    assert stop_sign_message(text, confidence, 'en') is None


@pytest.fixture
def scene(monkeypatch):
    manager, sid = Streams(), uuid4()
    state = LiveState(source='test', latest=b'raw-jpeg', latest_at=now())
    manager.states[sid] = state
    session = SimpleNamespace(alerts_enabled=False, language='en')
    prepared = object()
    calls = []

    async def get_session(session_id, active=False):
        assert session_id == sid and active
        return session

    def prepare(content):
        assert content == b'raw-jpeg'
        calls.append('redact')
        return prepared

    def read(image):
        assert image is prepared  # OCR receives only prepared, face-redacted pixels.
        calls.append('ocr')
        return 'STOP', 95

    monkeypatch.setattr(sessions, 'get_session', get_session)
    monkeypatch.setattr(processing, 'prepare_image', prepare)
    monkeypatch.setattr(processing, 'read_text', read)
    return manager, sid, state, session, calls


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('language,message', [
    ('en', 'A stop sign is visible.'), ('fr', 'Un panneau stop est visible.'),
    ('ar', 'توجد علامة توقف.'),
])
def test_stop_alerts_work_with_obstacles_on_or_off_and_use_session_language(scene, enabled, language, message):
    manager, sid, state, session, calls = scene
    session.alerts_enabled, session.language = enabled, language

    async def exercise():
        async with events.subscribe(sid) as queue:
            await manager.check_stop_sign(sid, state)
            alert = queue.get_nowait()
            assert alert['label'] == 'ocr_stop_sign'
            assert alert['message'] == message and alert['language'] == language
            assert alert['captured_at'] == state.latest_at.isoformat()
            assert alert['expires_at'] > now().isoformat()
            assert state.history_queue.get_nowait() == alert
            assert state.queue.empty()  # No storage, deduplication or caption dependency.

    asyncio.run(exercise())
    assert calls == ['redact', 'ocr']


def test_continuously_visible_stop_text_respects_cooldown_then_alerts_again(scene, monkeypatch):
    manager, sid, state, _, _ = scene
    clock = [100.0]
    monkeypatch.setattr(streaming, 'monotonic', lambda: clock[0])

    async def exercise():
        async with events.subscribe(sid) as queue:
            await manager.check_stop_sign(sid, state)
            queue.get_nowait()
            await manager.check_stop_sign(sid, state)
            assert queue.empty()
            clock[0] += settings.alert_cooldown_seconds
            await manager.check_stop_sign(sid, state)
            assert queue.get_nowait()['label'] == 'ocr_stop_sign'

    asyncio.run(exercise())


@pytest.mark.parametrize('condition', ['no_frame', 'old_input', 'late_ocr', 'replaced', 'closed'])
def test_missing_stale_or_disconnected_views_do_not_alert(scene, monkeypatch, condition):
    manager, sid, state, _, _ = scene
    if condition == 'no_frame':
        state.latest = None
    elif condition == 'old_input':
        state.latest_at = now() - timedelta(seconds=20)
    else:
        def read(_):
            if condition == 'late_ocr':
                state.latest_at = now() - timedelta(seconds=20)
            elif condition == 'replaced':
                manager.states[sid] = LiveState(source='replacement')
            return 'STOP', 95

        monkeypatch.setattr(processing, 'read_text', read)
        if condition == 'late_ocr':
            # Simulate OCR completing after this captured frame's deadline.
            captured_at = state.latest_at
            monkeypatch.setattr(streaming, 'now', lambda: captured_at + timedelta(seconds=10))
            monkeypatch.setattr(manager, 'fresh_snapshot', lambda _: (state.latest, captured_at))
        if condition == 'closed':
            calls = [0]

            async def get_session(*args, **kwargs):
                calls[0] += 1
                if calls[0] > 1:
                    raise BackendError('Session closed', 409, 'session_closed')
                return SimpleNamespace(language='en')

            monkeypatch.setattr(sessions, 'get_session', get_session)

    async def exercise():
        async with events.subscribe(sid) as queue:
            if condition == 'closed':
                with pytest.raises(BackendError):
                    await manager.check_stop_sign(sid, state)
            else:
                await manager.check_stop_sign(sid, state)
            assert queue.empty() and state.history_queue.empty()

    asyncio.run(exercise())


def test_worker_retries_after_ocr_failure_without_overlapping_checks(scene, monkeypatch):
    manager, sid, state, _, _ = scene
    checks, sleeps = [], []
    clock = [0.0]

    async def check(*args):
        checks.append(clock[0])
        clock[0] += .5
        if len(checks) == 1:
            raise BackendError('OCR unavailable', code='ocr_unavailable')

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(manager, 'check_stop_sign', check)
    monkeypatch.setattr(streaming, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(streaming.asyncio, 'sleep', sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(manager.detect_stop_signs(sid, state))
    assert checks == [0, 2, 4]
    assert sleeps == [1.5, 1.5, 1.5]
    assert state.stop_sign_error is None


def test_stream_stop_cancels_stop_sign_worker(scene, monkeypatch):
    manager, sid, _, _, _ = scene
    manager.states.pop(sid)

    async def idle(*args):
        await asyncio.Event().wait()

    for name in ['consume', 'detect', 'persist_alerts', 'detect_obstacles', 'check_stop_sign']:
        monkeypatch.setattr(manager, name, idle)

    async def exercise():
        state = manager.start(sid, 'test')
        await asyncio.sleep(0)
        assert state.stop_sign_worker and not state.stop_sign_worker.done()
        await manager.stop(sid)
        assert state.stop_sign_worker.cancelled()

    asyncio.run(exercise())
