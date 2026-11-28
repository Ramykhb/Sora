import asyncio
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BackendError
from app.db.models import CaptureSession, DetectionWatch
from app.db.models.frame import now
from app.services import detection_memory
from app.services.ai import cloud_view, gemini
from app.services.events import events
from app.services.streaming.session import LiveState, Streams
from test_api import create
from test_auth import account, headers


@pytest.mark.parametrize('question,target', [
    ('alert me when you detect a stop sign', 'a stop sign'),
    ('Please alert me when you see a car!', 'a car'),
    ('Hey so alert me when you detect a laptop', 'a laptop'),
    ('Alert me on detected a laptop', 'a laptop'),
    ('Hey Sora, alert me when you detect a laptop', 'a laptop'),
    ('HeySora alert me when you detect a laptop', 'a laptop'),
    ('Hey Sora. Alert me when you detect a laptop', 'a laptop'),
    ('Hey sorta, notify me if you see a red car', 'a red car'),
    ('He saw the alert me when you detect a laptop', 'a laptop'),
    ('alert me upon detecting a car', 'a car'),
    ('alert me on detection of a stop sign', 'a stop sign'),
    ('What does "alert me when you detect a laptop" mean?', None),
    ('Do not alert me when you detect a laptop', None),
    ('Did she say alert me when you detect a laptop?', None),
    ('notify me if you spot a red car please', 'a red car'),
    ('let me know when you notice a traffic light', 'a traffic light'),
    ('alert me when a car is detected', 'a car'),
    ('Préviens-moi quand tu vois un panneau stop', 'un panneau stop'),
    ('نبهني عندما ترى سيارة', 'سيارة'),
    ('أخبرني إذا تكتشف علامة توقف', 'علامة توقف'),
    ('What is a stop sign?', None),
    ('Did you detect a car?', None),
])
def test_request_parsing(question, target):
    assert detection_memory.request_target(question) == target


@pytest.fixture
def memory(client, monkeypatch):
    api, factory = client
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('watch-key'))
    sid = UUID(create(api))

    async def owner():
        async with factory() as db:
            return (await db.get(CaptureSession, sid)).owner_id

    return api, factory, sid, api.portal.call(owner)


def ask(api, sid, question, **extra):
    result = api.post(f'/api/v1/sessions/{sid}/questions', json={'question': question, **extra})
    assert result.status_code == 200, result.text
    return result.json()


def test_registration_is_persistent_deduplicated_and_needs_no_frame_or_question_model(memory, monkeypatch):
    api, _, sid, owner = memory

    async def forbidden(*args, **kwargs):
        raise AssertionError('Remembering a request must not run image inference')

    monkeypatch.setattr(gemini, 'ask_image', forbidden)
    result = ask(api, sid, 'alert me when you detect a stop sign')
    assert result['answer'] == "Okay, I'll alert you when I detect a stop sign."
    assert not result['uncertain'] and not result['evidence_frame_ids']
    ask(api, sid, 'alert me when you detect a car')
    ask(api, sid, 'alert me when you detect THE CAR')
    pending = api.portal.call(detection_memory.pending, owner)
    assert {row['target'] for row in pending} == {'a stop sign', 'a car'}
    # A new DB session and a new camera session see the same durable account memory.
    new_sid = UUID(create(api))
    assert new_sid != sid
    assert len(api.portal.call(detection_memory.pending, owner)) == 2
    assert len(api.get(f'/api/v1/sessions/{sid}/questions').json()) == 3
    assert api.get(f'/api/v1/sessions/{sid}/frames').json() == []


def test_audio_requests_use_the_same_memory_path(memory, monkeypatch):
    from app.api.routes import questions
    api, _, sid, owner = memory
    monkeypatch.setattr(questions, 'transcribe', lambda *args: ('alert me when you detect a car', 'en'))
    result = api.post(f'/api/v1/sessions/{sid}/questions/audio', files={
        'audio': ('question.wav', b'fake-audio', 'audio/wav'),
    })
    assert result.status_code == 200, result.text
    assert result.json()['source'] == 'audio'
    assert api.portal.call(detection_memory.pending, owner)[0]['target'] == 'a car'


@pytest.mark.parametrize('target', ['', 'x' * 201])
def test_invalid_targets_are_not_saved(memory, target):
    api, _, sid, owner = memory
    result = ask(api, sid, 'alert me when you detect ' + target)
    assert result['uncertain']
    assert api.portal.call(detection_memory.pending, owner) == []


def test_no_secondary_key_does_not_falsely_promise_an_alert(memory, monkeypatch):
    api, _, sid, owner = memory
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr(''))
    result = ask(api, sid, 'alert me when you detect a car')
    assert 'gemini_not_configured' in result['processing_warnings']
    assert api.portal.call(detection_memory.pending, owner) == []


def test_pending_limit_and_duplicates_at_the_limit(memory):
    api, factory, sid, owner = memory

    async def seed():
        async with factory() as db:
            db.add_all([DetectionWatch(owner_id=owner, target=f'object {i}',
                                       target_key=detection_memory.target_key(f'object {i}')) for i in range(20)])
            await db.commit()

    api.portal.call(seed)
    result = ask(api, sid, 'alert me when you detect another target')
    assert 'alert_memory_full' in result['processing_warnings']
    duplicate = ask(api, sid, 'alert me when you detect object 0')
    assert not duplicate['uncertain']
    assert len(api.portal.call(detection_memory.pending, owner)) == 20


def test_other_accounts_and_admins_cannot_write_someone_elses_memory(memory):
    api, _, sid, owner = memory
    other = account(api, 'watcher@example.com')
    other_sid = api.post('/api/v1/sessions', headers=headers(other), json={'consent': True}).json()['id']
    result = api.post(f'/api/v1/sessions/{other_sid}/questions', json={
        'question': 'alert me when you detect a car',
    })  # The fixture account is an admin, but must not install watches for another user.
    assert result.status_code == 403
    result = api.post(f'/api/v1/sessions/{sid}/questions', headers=headers(other), json={
        'question': 'alert me when you detect a car',
    })
    assert result.status_code in (403, 404)
    assert api.portal.call(detection_memory.pending, owner) == []


def configure_scene(memory, monkeypatch):
    api, _, sid, _ = memory
    manager = Streams()
    state = LiveState(source='test', latest=b'raw', latest_at=now())
    manager.states[sid] = state
    monkeypatch.setattr(cloud_view, 'cloud_image', lambda content, privacy: b'redacted')
    return manager, state


def test_clear_matches_alert_once_remove_only_matches_and_share_one_gemini_request(memory, monkeypatch):
    api, _, sid, owner = memory
    for target in ['a stop sign', 'a car', 'a dog']:
        ask(api, sid, 'alert me when you detect ' + target)
    manager, state = configure_scene(memory, monkeypatch)
    calls = []

    async def analyze(image, language, *, watches):
        assert image == b'redacted'
        calls.append(watches)
        return gemini.GeminiAnswer(
            answer='A car blocks the passage.', uncertain=False, visible_path='blocked',
            visible_path_distance='unknown',
            matched_alert_ids=[watch['id'] for watch in watches if watch['target'] != 'a dog'],
        )

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def exercise():
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            alert = queue.get_nowait()
            assert alert['label'] == 'remembered_detection'
            assert 'a stop sign' in alert['message'] and 'a car' in alert['message']
            assert 'blocks the passage' in alert['message']
            assert queue.empty() and state.history_queue.empty()  # Already persisted atomically.
            await manager.check_obstacles(sid, state)
            assert queue.empty()
            return alert

    alert = api.portal.call(exercise)
    assert len(calls) == 2 and len(calls[0]) == 3 and len(calls[1]) == 1
    assert api.portal.call(detection_memory.pending, owner)[0]['target'] == 'a dog'
    stored = api.get(f'/api/v1/sessions/{sid}/alerts').json()
    assert len(stored) == 1 and stored[0]['id'] == alert['id']


@pytest.mark.parametrize('failure', ['no-match', 'stale', 'stopped', 'provider-error'])
def test_non_matches_and_failed_or_late_results_keep_memory_and_stay_silent(memory, monkeypatch, failure):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a stop sign')
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(image, language, *, watches):
        if failure == 'stopped':
            manager.states.pop(sid)
        if failure == 'provider-error':
            raise BackendError('Unavailable', code='gemini_unavailable')
        if failure == 'stale':
            import app.services.streaming.session as streaming
            monkeypatch.setattr(streaming, 'now', lambda: state.latest_at + timedelta(seconds=20))
        return gemini.GeminiAnswer(answer='Not sure from this view.', uncertain=True,
                                   visible_path='unknown', visible_path_distance='unknown',
                                   matched_alert_ids=[] if failure == 'no-match' else [watches[0]['id']])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def exercise():
        async with events.subscribe(sid) as queue:
            if failure in {'provider-error', 'stale'}:
                with pytest.raises(BackendError):
                    await manager.check_obstacles(sid, state)
            else:
                await manager.check_obstacles(sid, state)
            assert queue.empty() and state.history_queue.empty()

    api.portal.call(exercise)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    assert api.get(f'/api/v1/sessions/{sid}/alerts').json() == []


def test_detection_switch_pauses_all_requests_and_preserves_watches_until_reenabled(memory, monkeypatch):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a stop sign')
    api.patch(f'/api/v1/sessions/{sid}', json={'alerts_enabled': False})
    manager, state = configure_scene(memory, monkeypatch)
    calls = []

    async def analyze(image, language, *, watches):
        calls.append(watches)
        return gemini.GeminiAnswer(answer='The forward path cannot be assessed.', uncertain=True,
                                   visible_path='unknown', visible_path_distance='unknown',
                                   matched_alert_ids=[watches[0]['id']])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def paused():
        async with events.subscribe(sid) as queue:
            for _ in range(3):
                await manager.check_obstacles(sid, state)
            assert queue.empty()

    api.portal.call(paused)
    assert calls == []
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    api.patch(f'/api/v1/sessions/{sid}', json={'alerts_enabled': True})

    async def resumed():
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            assert queue.get_nowait()['label'] == 'remembered_detection'

    api.portal.call(resumed)
    assert len(calls) == 1
    assert api.portal.call(detection_memory.pending, owner) == []
    assert 'a stop sign' in api.get(f'/api/v1/sessions/{sid}/alerts').json()[0]['message']


def test_alert_persistence_failure_rolls_back_memory_deletion(memory, monkeypatch):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a car')
    matches = [watch['id'] for watch in api.portal.call(detection_memory.pending, owner)]

    async def failed_commit(*args, **kwargs):
        raise RuntimeError('DB failure')

    async def exercise():
        with monkeypatch.context() as patch:
            patch.setattr(AsyncSession, 'commit', failed_commit)
            with pytest.raises(RuntimeError):
                await detection_memory.fulfill(owner, sid, matches, now(), now() + timedelta(seconds=6), lambda: True)

    api.portal.call(exercise)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    assert api.get(f'/api/v1/sessions/{sid}/alerts').json() == []


def test_two_streams_cannot_consume_the_same_request_twice(memory):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a car')
    matches = [watch['id'] for watch in api.portal.call(detection_memory.pending, owner)]
    other_sid = UUID(create(api))

    async def exercise():
        return await asyncio.gather(*[
            detection_memory.fulfill(owner, session_id, matches, now(), now() + timedelta(seconds=6), lambda: True)
            for session_id in [sid, other_sid]
        ])

    results = api.portal.call(exercise)
    assert sum(value is not None for value in results) == 1
    assert api.portal.call(detection_memory.pending, owner) == []


def test_memory_protocol_prepends_targets_and_uses_only_key_two(monkeypatch):
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('watch-key'))
    watches = [{'id': str(uuid4()), 'target': 'a stop sign'}, {'id': str(uuid4()), 'target': 'a red car'}]

    def handler(request):
        assert request.headers['x-goog-api-key'] == 'watch-key'
        payload = json.loads(request.content)
        parts = payload['contents'][0]['parts']
        assert json.loads(parts[0]['text']) == {'pending_alerts': watches}
        assert 'question' in json.loads(parts[1]['text'])
        assert parts[2]['inlineData']['mimeType'] == 'image/jpeg'
        schema = payload['generationConfig']['responseJsonSchema']
        assert 'matched_alert_ids' in schema['required']
        assert set(schema['properties']['matched_alert_ids']['items']['enum']) == {watch['id'] for watch in watches}
        result = {'answer': 'A stop sign is on the left.', 'uncertain': True, 'visible_path': 'unknown',
                  'visible_path_distance': 'unknown', 'matched_alert_ids': [watches[0]['id']]}
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(result)}]}}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(gemini.ask_obstacles(b'redacted', 'en', watches=watches))
    assert result.matched_alert_ids == [watches[0]['id']]


@pytest.mark.parametrize('matches', [None, [str(uuid4())]])
def test_missing_or_invented_ids_reject_the_provider_response(monkeypatch, matches):
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('watch-key'))
    result = {'answer': 'No obstacle.', 'uncertain': True, 'visible_path': 'unknown', 'visible_path_distance': 'unknown'}
    if matches is not None:
        result['matched_alert_ids'] = matches
    original = httpx.AsyncClient
    monkeypatch.setattr(gemini.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(result)}]}}]}),
    ), **kwargs))
    with pytest.raises(BackendError):
        asyncio.run(gemini.ask_obstacles(b'redacted', 'en', watches=[{'id': str(uuid4()), 'target': 'a car'}]))


def test_migration_creates_unique_account_memory_and_downgrades(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0008_detection_watches.py'
    spec = importlib.util.spec_from_file_location('watch_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        schema = inspect(connection)
        assert schema.get_unique_constraints('detection_watches')[0]['column_names'] == ['owner_id', 'target_key']
        assert schema.get_foreign_keys('detection_watches')[0]['options']['ondelete'] == 'CASCADE'
        migration.downgrade()
        assert 'detection_watches' not in inspect(connection).get_table_names()
    engine.dispose()


def test_new_target_added_during_inference_is_not_consumed_by_that_old_request(memory, monkeypatch):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a car')
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(image, language, *, watches):
        await detection_memory.remember(sid, 'a dog', 'en')
        all_pending = await detection_memory.pending(owner)
        return gemini.GeminiAnswer(answer='Objects are visible.', uncertain=True,
                                   visible_path='unknown', visible_path_distance='unknown',
                                   matched_alert_ids=[watch['id'] for watch in all_pending])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def receive():
        async with events.subscribe(sid):
            await manager.check_obstacles(sid, state)

    api.portal.call(receive)
    remaining = api.portal.call(detection_memory.pending, owner)
    assert [watch['target'] for watch in remaining] == ['a dog']
    message = api.get(f'/api/v1/sessions/{sid}/alerts').json()[0]['message']
    assert 'a car' in message and 'a dog' not in message


def test_other_accounts_pending_targets_are_never_sent_or_consumed(memory, monkeypatch):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a car')
    other = account(api, 'other-watches@example.com')
    other_sid = api.post('/api/v1/sessions', headers=headers(other), json={'consent': True}).json()['id']
    result = api.post(f'/api/v1/sessions/{other_sid}/questions', headers=headers(other), json={
        'question': 'alert me when you detect a stop sign',
    })
    assert result.status_code == 200, result.text
    other_owner = UUID(other['user']['id'])
    foreign_watches = api.portal.call(detection_memory.pending, other_owner)
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(image, language, *, watches):
        assert [watch['target'] for watch in watches] == ['a car']
        return gemini.GeminiAnswer(answer='Not sure.', uncertain=True,
                                   visible_path='unknown', visible_path_distance='unknown',
                                   matched_alert_ids=[foreign_watches[0]['id']])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)
    api.portal.call(manager.check_obstacles, sid, state)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    assert api.portal.call(detection_memory.pending, other_owner) == foreign_watches
    assert api.get(f'/api/v1/sessions/{sid}/alerts').json() == []


def test_missing_alert_receiver_preserves_request_until_a_connected_client_can_be_alerted(memory, monkeypatch):
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a laptop')
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(image, language, *, watches):
        return gemini.GeminiAnswer(answer='A laptop is visible.', uncertain=False,
                                   visible_path='unobstructed', visible_path_distance='unknown',
                                   matched_alert_ids=[watches[0]['id']])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def exercise():
        await manager.check_obstacles(sid, state)
        assert len(await detection_memory.pending(owner)) == 1
        assert not events.has_subscribers(sid)
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            assert queue.get_nowait()['message'] == 'Detected: a laptop.'
            assert await detection_memory.pending(owner) == []
        assert not events.has_subscribers(sid)

    api.portal.call(exercise)
    assert len(api.get(f'/api/v1/sessions/{sid}/alerts').json()) == 1


def test_registration_while_detection_is_off_saves_the_target_and_explains_it_is_paused(memory):
    api, _, sid, owner = memory
    api.patch(f'/api/v1/sessions/{sid}', json={'alerts_enabled': False})
    answer = ask(api, sid, 'alert me when you detect a laptop')
    assert 'Detection is off' in answer['answer']
    assert len(api.portal.call(detection_memory.pending, owner)) == 1


def test_switching_off_during_inference_discards_result_without_consuming_memory(memory, monkeypatch):
    api, factory, sid, owner = memory
    ask(api, sid, 'alert me when you detect a laptop')
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(image, language, *, watches):
        async with factory() as db:
            session = await db.get(CaptureSession, sid)
            session.alerts_enabled = False
            await db.commit()
        return gemini.GeminiAnswer(answer='A laptop is visible.', uncertain=False,
                                   visible_path='blocked', visible_path_distance='unknown',
                                   matched_alert_ids=[watches[0]['id']])

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def receive():
        async with events.subscribe(sid) as queue:
            await manager.check_obstacles(sid, state)
            assert queue.empty()

    api.portal.call(receive)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    assert api.get(f'/api/v1/sessions/{sid}/alerts').json() == []


def test_switching_off_during_redaction_prevents_the_cloud_upload(memory, monkeypatch):
    import threading
    api, factory, sid, owner = memory
    ask(api, sid, 'alert me when you detect a laptop')
    manager, state = configure_scene(memory, monkeypatch)

    async def analyze(*args, **kwargs):
        raise AssertionError('Turning detection off must prevent an upload after redaction')

    monkeypatch.setattr(gemini, 'ask_obstacles', analyze)

    async def exercise():
        entered = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def redact(*args):
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(2)
            return b'redacted'

        monkeypatch.setattr(cloud_view, 'cloud_image', redact)
        pending = asyncio.create_task(manager.check_obstacles(sid, state))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            async with factory() as db:
                session = await db.get(CaptureSession, sid)
                session.alerts_enabled = False
                await db.commit()
        finally:
            release.set()
            await pending

    api.portal.call(exercise)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1


@pytest.mark.parametrize('question', [
    'Hey so alert me when you detect a laptop',
    'Alert me on detected a laptop',
    'Hey Sora, alert me when you detect a laptop',
])
def test_phone_transcript_variations_create_a_watch_instead_of_an_image_answer(memory, monkeypatch, question):
    api, _, sid, owner = memory
    monkeypatch.setattr(settings, 'gemini_enabled', True)
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('question-key'))

    async def forbidden(*args, **kwargs):
        raise AssertionError('An alert request must never be answered as a current-view image question')

    monkeypatch.setattr(gemini, 'ask_image', forbidden)
    result = ask(api, sid, question)
    assert result['answer'] == "Okay, I'll alert you when I detect a laptop."
    assert [watch['target'] for watch in api.portal.call(detection_memory.pending, owner)] == ['a laptop']


def test_watch_management_edits_cancel_and_clear_are_account_scoped(memory):
    from test_auth import account, headers
    api, _, sid, owner = memory
    ask(api, sid, 'alert me when you detect a car')
    ask(api, sid, 'alert me when you detect a dog')
    rows = api.get('/api/v1/detection-watches').json()
    assert len(rows) == 2 and all(row['expires_at'] for row in rows)
    watch = rows[0]
    other = headers(account(api, 'other-watch-owner@example.com'))
    assert api.get('/api/v1/detection-watches', headers=other).json() == []
    assert api.put('/api/v1/detection-watches/' + watch['id'], json={'target': 'a bus'}, headers=other).status_code == 404
    assert api.delete('/api/v1/detection-watches/' + watch['id'], headers=other).status_code == 404
    assert api.delete('/api/v1/detection-watches', headers=other).status_code == 204
    assert len(api.portal.call(detection_memory.pending, owner)) == 2
    assert api.put('/api/v1/detection-watches/' + watch['id'], json={'target': '   '}).status_code == 422
    assert api.put('/api/v1/detection-watches/' + watch['id'], json={'target': 'a bus'}).status_code == 204
    edited = next(row for row in api.get('/api/v1/detection-watches').json() if row['target'] == 'a bus')
    assert edited['id'] != watch['id']
    assert edited['expires_at'] == watch['expires_at']
    assert api.delete('/api/v1/detection-watches/' + edited['id']).status_code == 204
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    assert api.delete('/api/v1/detection-watches').status_code == 204
    assert api.portal.call(detection_memory.pending, owner) == []


def test_expired_watches_do_not_block_registration(memory):
    from app.core.config import settings
    from app.workers.retention import cleanup_once
    api, factory, sid, owner = memory

    async def expire():
        async with factory() as db:
            db.add_all([DetectionWatch(owner_id=owner, target=f'expired {i}', target_key=f'expired-{i}',
                        created_at=now() - timedelta(days=settings.detection_watch_retention_days + 1)) for i in range(20)])
            await db.commit()

    api.portal.call(expire)
    assert api.portal.call(detection_memory.pending, owner) == []
    assert api.get('/api/v1/detection-watches').json() == []
    result = ask(api, sid, 'alert me when you detect a car')
    assert 'alert_memory_full' not in result['processing_warnings']
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
    api.portal.call(cleanup_once)
    assert len(api.portal.call(detection_memory.pending, owner)) == 1
