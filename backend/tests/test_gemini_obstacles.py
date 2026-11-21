import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.errors import BackendError
from app.db.models.frame import now
from app.services.ai import cloud_view, gemini
from app.services.events import events
from app.services.streaming import session as streaming
from app.services.streaming.session import LiveState, Streams


def test_obstacle_settings_preserve_one_second_storage_and_accept_lowercase_keys(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY_2', raising=False)
    monkeypatch.setenv('gemini_api_key_2', 'second-test-key')
    monkeypatch.setenv('gemini_api_key_12', 'twelfth-test-key')
    config = Settings(_env_file=None)
    assert config.gemini_api_key_2.get_secret_value() == 'second-test-key'
    assert config.gemini_api_key_12.get_secret_value() == 'twelfth-test-key'
    assert config.sample_interval_seconds == 1
    assert config.gemini_obstacle_interval_seconds == 1


def test_questions_and_automatic_obstacles_select_from_same_key_pool(monkeypatch):
    monkeypatch.setattr(settings, 'gemini_enabled', True)
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('question-key'))
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('obstacle-key'))
    keys = []
    selections = iter(['obstacle-key', 'question-key'])

    def select(candidates):
        assert candidates == ('question-key', 'obstacle-key')
        return next(selections)

    monkeypatch.setattr(gemini.secrets, 'choice', select)

    def handle(request):
        keys.append(request.headers['x-goog-api-key'])
        assert 'key' not in str(request.url)
        body = json.loads(request.content)
        automatic = 'visible_path' in body['generationConfig']['responseJsonSchema']['required']
        if automatic:
            assert 'visible_path' in body['generationConfig']['responseJsonSchema']['required']
        answer = {'answer': 'A chair blocks the passage.', 'uncertain': False}
        if automatic:
            answer.update(visible_path='blocked', visible_path_distance='unknown')
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps(answer)}],
        }}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(handle), **kwargs,
    ))

    async def exercise():
        await gemini.ask_image(b'jpeg', 'Describe the scene', 'en')
        # Automatic checks work independently of the question feature's switch.
        monkeypatch.setattr(settings, 'gemini_enabled', False)
        await gemini.ask_obstacles(b'jpeg', 'en')
        monkeypatch.setattr(settings, 'gemini_api_key', SecretStr(''))
        monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr(''))
        with pytest.raises(BackendError, match='not configured'):
            await gemini.ask_obstacles(b'jpeg', 'en')

    asyncio.run(exercise())
    assert keys == ['obstacle-key', 'question-key']


def test_all_twelve_keys_are_eligible_for_each_request_type(monkeypatch):
    monkeypatch.setattr(settings, 'gemini_enabled', True)
    expected = tuple(f'slot-{index}' for index in range(1, 13))
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr(expected[0]))
    for index in range(2, 13):
        monkeypatch.setattr(settings, f'gemini_api_key_{index}', SecretStr(expected[index - 1]))
    selected, sent = [], []

    def select(candidates):
        assert candidates == expected
        key = candidates[len(selected) % len(candidates)]
        selected.append(key)
        return key

    def handle(request):
        sent.append(request.headers['x-goog-api-key'])
        automatic = 'visible_path' in json.loads(request.content)['generationConfig']['responseJsonSchema']['required']
        answer = {'answer': 'A chair is visible.', 'uncertain': False}
        if automatic:
            answer.update(visible_path='blocked', visible_path_distance='unknown')
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps(answer)}],
        }}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.secrets, 'choice', select)
    monkeypatch.setattr(gemini.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(handle), **kwargs,
    ))

    async def exercise():
        for _ in expected:
            await gemini.ask_image(b'jpeg', 'Describe the scene', 'en')
        for _ in expected:
            await gemini.ask_obstacles(b'jpeg', 'en')

    asyncio.run(exercise())
    assert selected == list(expected) * 2
    assert sent == selected


@pytest.fixture
def obstacle_scene(monkeypatch):
    from app.services import sessions
    manager = Streams()
    sid = uuid4()
    state = LiveState(source='test', latest=b'raw-jpeg', latest_at=now())
    manager.states[sid] = state
    session = SimpleNamespace(alerts_enabled=True, language='en')

    async def get_session(*args, **kwargs):
        return session

    def redact(content, privacy_checked):
        assert content == b'raw-jpeg'
        assert privacy_checked is False
        return b'redacted-jpeg'

    monkeypatch.setattr(sessions, 'get_session', get_session)
    monkeypatch.setattr(cloud_view, 'cloud_image', redact)
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('obstacle-key'))
    return manager, sid, state, session


@pytest.mark.parametrize('assessment', ['unobstructed', 'unknown', None])
def test_no_obstacle_means_no_event_speech_or_history(obstacle_scene, monkeypatch, assessment):
    manager, sid, state, _ = obstacle_scene

    async def ask(image, language):
        assert image == b'redacted-jpeg'
        return gemini.GeminiAnswer(answer='No obstacle detected.', uncertain=True,
                                   visible_path=assessment, visible_path_distance='unknown')

    monkeypatch.setattr(gemini, 'ask_obstacles', ask)

    async def exercise():
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            assert queue.empty()
            assert state.history_queue.empty()

    asyncio.run(exercise())


def test_obstacle_emits_alert_and_history_with_cooldown(obstacle_scene, monkeypatch):
    manager, sid, state, _ = obstacle_scene
    result = gemini.GeminiAnswer(answer='A chair blocks the passage.', uncertain=False,
                                 visible_path='blocked', visible_path_distance='unknown')

    async def ask(*args):
        return result

    monkeypatch.setattr(gemini, 'ask_obstacles', ask)

    async def exercise():
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            alert = queue.get_nowait()
            assert alert['message'] == result.answer
            assert alert['label'] == 'gemini_obstacle'
            assert alert['frame_id'] is None
            assert state.history_queue.get_nowait() == alert
            await manager.check_obstacles(sid, state)
            assert queue.empty()
            result.visible_path = 'unobstructed'
            await manager.check_obstacles(sid, state)
            assert queue.empty()
            result.visible_path = 'blocked'
            await manager.check_obstacles(sid, state)
            assert queue.get_nowait()['type'] == 'alert'

    asyncio.run(exercise())


@pytest.mark.parametrize('change', ['disabled', 'stopped', 'stale'])
def test_late_results_are_discarded(obstacle_scene, monkeypatch, change):
    manager, sid, state, session = obstacle_scene

    async def ask(*args):
        if change == 'disabled':
            session.alerts_enabled = False
        elif change == 'stopped':
            manager.states.pop(sid)
        else:
            monkeypatch.setattr(streaming, 'now', lambda: state.latest_at + timedelta(seconds=20))
        return gemini.GeminiAnswer(answer='A chair blocks the passage.', uncertain=False,
                                   visible_path='blocked', visible_path_distance='unknown')

    monkeypatch.setattr(gemini, 'ask_obstacles', ask)

    async def exercise():
        async with events.subscribe(sid) as queue:
            if change == 'stale':
                with pytest.raises(BackendError, match='expired'):
                    await manager.check_obstacles(sid, state)
            else:
                await manager.check_obstacles(sid, state)
            assert queue.empty()
            assert state.history_queue.empty()

    asyncio.run(exercise())


@pytest.mark.parametrize('reason', ['disabled', 'stale', 'missing'])
def test_disabled_or_missing_fresh_camera_does_not_upload(obstacle_scene, monkeypatch, reason):
    manager, sid, state, session = obstacle_scene
    if reason == 'disabled':
        session.alerts_enabled = False
    elif reason == 'stale':
        state.latest_at = now() - timedelta(seconds=20)
    else:
        state.latest = None

    async def forbidden(*args):
        raise AssertionError('No cloud request expected')

    monkeypatch.setattr(gemini, 'ask_obstacles', forbidden)
    asyncio.run(manager.check_obstacles(sid, state))


def test_worker_checks_every_second_and_survives_failure(obstacle_scene, monkeypatch):
    manager, sid, state, _ = obstacle_scene
    clock = [0.0]
    checks, sleeps = [], []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
        if len(sleeps) == 4:
            raise asyncio.CancelledError

    async def check(*args):
        checks.append(clock[0])
        clock[0] += .4  # Inference time counts toward the one-second interval.
        if len(checks) == 1:
            raise BackendError('Provider unavailable', code='gemini_unavailable')

    monkeypatch.setattr(streaming, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(streaming.asyncio, 'sleep', sleep)
    monkeypatch.setattr(manager, 'check_obstacles', check)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(manager.detect_obstacles(sid, state))
    assert checks == pytest.approx([1, 2, 3])
    assert sleeps == pytest.approx([1, .6, .6, .6])
    assert state.obstacle_error == 'gemini_unavailable'


def test_slow_cloud_request_does_not_block_frame_storage_or_stop(client, monkeypatch):
    from test_api import create
    from uuid import UUID
    from app.services.frames import ingestion
    api, _ = client
    sid = UUID(create(api))
    manager = Streams()
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('obstacle-key'))
    monkeypatch.setattr(settings, 'gemini_obstacle_interval_seconds', .01)

    async def exercise():
        entered, stored = asyncio.Event(), asyncio.Event()

        async def stall(*args):
            entered.set()
            await asyncio.Event().wait()

        async def ingest(*args, **kwargs):
            stored.set()
            return SimpleNamespace(status='stored')

        monkeypatch.setattr(manager, 'check_obstacles', stall)
        monkeypatch.setattr(ingestion, 'ingest_bytes', ingest)
        state = manager.start(sid, 'test')
        try:
            await asyncio.wait_for(entered.wait(), 1)
            manager.enqueue_sample(state, b'jpeg', now())
            await asyncio.wait_for(stored.wait(), 1)
            assert not state.obstacle_worker.done()
        finally:
            await asyncio.wait_for(manager.stop(sid), 1)
        assert state.obstacle_worker.cancelled()
        assert sid not in manager.states

    api.portal.call(exercise)


def test_automatic_provider_error_does_not_retry_with_another_key(monkeypatch):
    monkeypatch.setattr(settings, 'gemini_enabled', True)
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('question-key'))
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('obstacle-key'))
    monkeypatch.setattr(gemini.secrets, 'choice', lambda keys: keys[1])
    keys = []

    def handle(request):
        keys.append(request.headers['x-goog-api-key'])
        return httpx.Response(429, json={'error': 'quota exceeded'})

    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    with pytest.raises(BackendError) as error:
        asyncio.run(gemini.ask_obstacles(b'jpeg', 'en'))
    assert error.value.code == 'gemini_unavailable'
    assert keys == ['obstacle-key']


def test_cloud_mode_keeps_local_observations_without_duplicate_local_alerts(client, monkeypatch):
    from test_api import create
    from uuid import UUID
    api, _ = client
    sid = UUID(create(api))
    manager = Streams()
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('obstacle-key'))

    async def exercise():
        async with events.subscribe(sid) as queue:
            state = manager.start(sid, 'test')
            try:
                manager.enqueue_detection(state, b'jpeg', now())
                await asyncio.wait_for(state.detection_queue.join(), 1)
                messages = []
                while not queue.empty():
                    messages.append(queue.get_nowait())
                assert any(item['type'] == 'observation' for item in messages)
                assert not any(item['type'] == 'alert' for item in messages)
                assert state.history_queue.empty()
            finally:
                await manager.stop(sid)

    api.portal.call(exercise)


@pytest.mark.parametrize('failure', ['provider', 'timeout'])
def test_cloud_failure_enables_local_alerts_and_recovery_stops_fallback(obstacle_scene, monkeypatch, failure):
    from app.services.frames import processing

    manager, sid, state, _ = obstacle_scene
    monkeypatch.setattr(settings, 'gemini_obstacle_interval_seconds', .01)
    monkeypatch.setattr(processing, 'detect_live', lambda _: (
        100, 100, [{'label': 'chair', 'confidence': .9, 'box': [20, 20, 80, 95]}],
    ))
    healthy = False

    async def ask(*args):
        if not healthy:
            if failure == 'timeout':
                raise TimeoutError()
            raise BackendError('Provider failed', code='gemini_unavailable')
        return gemini.GeminiAnswer(answer='The image is ambiguous.', uncertain=True, visible_path='unknown')

    monkeypatch.setattr(gemini, 'ask_obstacles', ask)

    async def exercise():
        nonlocal healthy
        async with events.subscribe(sid) as queue:
            tasks = [asyncio.create_task(manager.detect_obstacles(sid, state)),
                     asyncio.create_task(manager.detect(sid, state))]
            try:
                while (await asyncio.wait_for(queue.get(), 1))['type'] != 'obstacle_error':
                    pass
                manager.enqueue_detection(state, b'jpeg', now())
                await asyncio.wait_for(state.detection_queue.join(), 1)
                messages = []
                while not queue.empty():
                    messages.append(queue.get_nowait())
                assert any(item['type'] == 'alert' and item['label'] == 'chair' for item in messages)
                assert state.obstacle_error
                healthy = True
                while (await asyncio.wait_for(queue.get(), 1))['type'] != 'obstacle_status':
                    pass
                assert state.obstacle_error is None
                manager.enqueue_detection(state, b'jpeg', now())
                await asyncio.wait_for(state.detection_queue.join(), 1)
                while not queue.empty():
                    assert queue.get_nowait()['type'] != 'alert'
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(exercise())
