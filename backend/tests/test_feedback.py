from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import select
from app.db.models import Feedback
from test_api import create, upload


def question(api):
    sid = create(api)
    upload(api, sid)
    answer = api.post(f'/api/v1/sessions/{sid}/questions', json={'question': 'What is visible?', 'scope': 'memory'}).json()
    return sid, answer['id']


def test_repeated_feedback_updates_the_same_rating_and_metrics(client):
    api, factory = client
    sid, qid = question(api)
    path = f'/api/v1/sessions/{sid}/questions/{qid}/feedback'
    first = api.post(path, json={'rating': 'correct', 'notes': 'Initial rating'}).json()
    for _ in range(3):
        assert api.post(path, json={'rating': 'correct'}).json()['id'] == first['id']
    changed = api.post(path, json={'rating': 'incorrect', 'notes': 'Corrected assessment'}).json()
    assert changed['id'] == first['id']
    assert api.get('/api/v1/metrics').json()['feedback'] == {'incorrect': 1}

    async def inspect():
        async with factory() as db:
            rows = (await db.scalars(select(Feedback).where(Feedback.question_id == UUID(qid)))).all()
            assert len(rows) == 1 and rows[0].notes == 'Corrected assessment'

    api.portal.call(inspect)


def test_concurrent_submissions_do_not_create_duplicate_ratings(client):
    api, _ = client
    sid, qid = question(api)
    path = f'/api/v1/sessions/{sid}/questions/{qid}/feedback'
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(lambda _: api.post(path, json={'rating': 'correct'}), range(8)))
    assert all(reply.status_code == 201 for reply in replies)
    assert len({reply.json()['id'] for reply in replies}) == 1
    assert api.get('/api/v1/metrics').json()['feedback'] == {'correct': 1}


def test_feedback_still_requires_session_ownership(client):
    from test_auth import account, headers
    api, _ = client
    sid, qid = question(api)
    other = headers(account(api, 'other-feedback@example.com'))
    assert api.post(f'/api/v1/sessions/{sid}/questions/{qid}/feedback', json={'rating': 'correct'}, headers=other).status_code == 404
    assert api.get('/api/v1/metrics').json()['feedback'] == {}


def test_migration_preserves_latest_rating_and_enforces_uniqueness(tmp_path):
    import importlib.util
    from pathlib import Path
    import pytest
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0010_unique_feedback.py'
    spec = importlib.util.spec_from_file_location('feedback_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///' + str(tmp_path / 'feedback.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE answer_feedback (id TEXT PRIMARY KEY, question_id TEXT, rating TEXT, notes TEXT, created_at TEXT)'))
        connection.execute(text("INSERT INTO answer_feedback VALUES ('old','one','correct','old note','2026-01-01'), ('new','one','incorrect','latest note','2026-01-02'), ('other','two','unsure','','2026-01-02')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.execute(text('SELECT id, rating, notes FROM answer_feedback ORDER BY id')).all()
        assert rows == [('new', 'incorrect', 'latest note'), ('other', 'unsure', '')]
        with pytest.raises(IntegrityError):
            connection.execute(text("INSERT INTO answer_feedback VALUES ('duplicate','one','correct','','2026-01-03')"))
        migration.downgrade()
    engine.dispose()
