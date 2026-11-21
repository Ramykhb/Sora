from datetime import timedelta
from uuid import UUID

import pytest
from app.core.errors import BackendError
from app.db.models import Frame
from app.db.models.frame import now
from app.services.ai.models import models
from test_api import create, upload


@pytest.mark.parametrize('label,query,newer_text', [
    ('ÉCOLE', 'école', 'chair'),
    ('ÉCOLE', 'ecole', 'chair'),
    ('Entrée', 'entree', 'chair'),
    ('مَدْرَسَة', 'مدرسة', 'chair'),
    ('bus', 'bus', 'business'),
    ('room_1', 'room_1', 'rooma1'),
])
def test_lexical_search_finds_old_normalized_matches_beyond_recent_pool(client, monkeypatch, label, query, newer_text):
    api, factory = client
    sid = create(api)
    frame = upload(api, sid)

    async def populate():
        async with factory() as db:
            original = await db.get(Frame, UUID(frame['id']))
            original.search_text = label
            original.caption = label
            original.embedding = None
            original.captured_at = now() - timedelta(minutes=10)
            for _ in range(101):
                db.add(Frame(session_id=UUID(sid), source_filename='test.jpg', original_object_key=original.original_object_key,
                             processed_object_key=original.processed_object_key, width=100, height=100,
                             sharpness=100, brightness=100, perceptual_hash='0000000000000000',
                             search_text=newer_text, captured_at=now(), expires_at=now() + timedelta(hours=1)))
            await db.commit()

    async def offline(*_args, **_kwargs):
        raise BackendError('Offline', code='embedding_unavailable')

    api.portal.call(populate)
    monkeypatch.setattr(models, 'embed', offline)
    result = api.get(f'/api/v1/sessions/{sid}/frames/search', params={'q': query}).json()
    assert [row['id'] for row in result['frames']] == [frame['id']]
    assert 'no_relevant_evidence' not in result['warnings']


def test_search_terms_follow_enrichment_updates(client):
    from app.workers.enrichment import update_frame

    api, factory = client
    frame = upload(api, create(api))

    async def change():
        async with factory() as db:
            row = await db.get(Frame, UUID(frame['id']))
            row.enrichment_status = 'pending'
            await db.commit()
        await update_frame(UUID(frame['id']), caption='Une ÉCOLE', search_text='ignored old input', enrichment_status='complete')
        async with factory() as db:
            row = await db.get(Frame, UUID(frame['id']))
            assert ' ecole ' in row.normalized_search_text
            assert ' ignored ' not in row.normalized_search_text

    api.portal.call(change)


def test_migration_backfills_existing_unicode_rows_in_batches(tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text
    from app.core.search_text import normalized_search_text

    path = Path(__file__).resolve().parents[1] / 'migrations/versions/0011_normalized_frame_search.py'
    spec = importlib.util.spec_from_file_location('normalized_search_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///' + str(tmp_path / 'search.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE stored_frames (id INTEGER PRIMARY KEY, search_text TEXT)'))
        connection.execute(text('INSERT INTO stored_frames VALUES (:id, :source)'), [{'id': i, 'source': 'ÉCOLE مَدْرَسَة buses'} for i in range(1001)])
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        values = connection.execute(text('SELECT normalized_search_text FROM stored_frames')).scalars().all()
        assert len(values) == 1001 and set(values) == {normalized_search_text('ÉCOLE مَدْرَسَة buses')}
        migration.downgrade()
        assert 'normalized_search_text' not in {column['name'] for column in inspect(connection).get_columns('stored_frames')}
    engine.dispose()
