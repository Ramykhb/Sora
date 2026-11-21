from functools import partial
from uuid import UUID
from sqlalchemy import delete
from app.core.errors import BackendError
from app.db.models import Frame
from app.services.ai.models import Scene, models
from app.services.frames.ingestion import ingest_bytes
from app.services.frames.processing import Analysis
from app.workers.enrichment import enrich_frame
from test_api import create, image_bytes
import pytest


def save_fast(api, sid):
    return api.portal.call(partial(ingest_bytes, image_bytes(), UUID(sid), defer_enrichment=True))


@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize("language,text", [
    ("en", "It is safe to cross now."),
    ("en", "The hallway is completely clear. You should proceed."),
    ("fr", "Le couloir est dégagé."),
    ("ar", "الطريق آمن ويمكنك العبور بأمان."),
])
def test_captions_are_guarded_before_storage_search_and_speech(client, monkeypatch, deferred, language, text):
    from app.services.ai.safety import UNKNOWN

    api, factory = client
    sid = create(api)
    api.patch(f"/api/v1/sessions/{sid}", json={"language": language})

    async def unsafe(*_):
        return Scene(caption=text, uncertain=False, central_closed_door=True)

    monkeypatch.setattr(models, "describe", unsafe)
    saved = api.portal.call(partial(ingest_bytes, image_bytes(), UUID(sid), defer_enrichment=deferred))
    if deferred:
        api.portal.call(enrich_frame, saved.frame.id)
    frame = api.get(f"/api/v1/sessions/{sid}/frames/{saved.frame.id}").json()
    assert frame["caption"] == UNKNOWN[language]
    assert "caption_safety_filtered" in frame["processing_warnings"]
    assert "scene_uncertain" in frame["processing_warnings"]
    assert "central_closed_door" not in frame["scene_flags"]

    async def inspect():
        async with factory() as db:
            row = await db.get(Frame, saved.frame.id)
            assert text not in row.search_text

    api.portal.call(inspect)


def test_fast_capture_persists_without_waiting_for_any_model(client, monkeypatch):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = create(api)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Fast capture must not wait for captioning or embeddings")

    monkeypatch.setattr(models, "describe", forbidden)
    monkeypatch.setattr(models, "embed", forbidden)
    # A clear frame with no OCR/detections can still become useful after captioning.
    monkeypatch.setattr(ingestion, "analyze_image", lambda *args: Analysis("", 0, []))
    result = save_fast(api, sid)
    assert result.status == "stored"
    frame = api.get(f"/api/v1/sessions/{sid}/frames").json()[0]
    assert frame["enrichment_status"] == "pending"
    assert frame["enrichment_ms"] is None
    assert frame["caption"] == ""
    assert api.get(f"/api/v1/sessions/{sid}/frames/{frame['id']}/image").status_code == 200


def test_enrichment_reads_durable_work_and_updates_the_same_saved_frame(client):
    api, factory = client
    sid = create(api)
    result = save_fast(api, sid)
    saved_ms = result.frame.processing_ms
    with api.websocket_connect(f"/api/v1/sessions/{sid}/events") as socket:
        socket.send_json({"access_token": api.headers["Authorization"].split(" ", 1)[1]})
        assert socket.receive_json()["type"] == "ready"
        api.portal.call(enrich_frame, result.frame.id)
        update = socket.receive_json()
        assert update["type"] == "frame_updated"
        assert update["frame"]["id"] == str(result.frame.id)
        assert update["frame"]["enrichment_status"] == "complete"
        assert update["frame"]["caption"] == "A chair beside an EXIT sign"
        assert update["frame"]["processing_ms"] == saved_ms
        assert update["frame"]["enrichment_ms"] is not None

    async def check_vector():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            assert row.embedding is not None
            assert "EXIT" in row.search_text

    api.portal.call(check_vector)
    assert len(api.get(f"/api/v1/sessions/{sid}/frames").json()) == 1


def test_enrichment_uses_processed_image_without_reprocessing(client, monkeypatch):
    import app.services.frames.processing as processing
    import app.workers.enrichment as enrichment
    from app.services.storage.object_store import get_image
    from PIL import Image
    from io import BytesIO

    api, _ = client
    result = save_fast(api, create(api))
    keys = []
    original_get = get_image

    def read(key):
        keys.append(key)
        return original_get(key)

    def forbidden(*_args):
        raise AssertionError("Enrichment must not repeat image preparation")

    async def describe(content):
        image = Image.open(BytesIO(content))
        assert max(image.size) <= 448
        return Scene(caption="A chair", uncertain=False)

    monkeypatch.setattr(enrichment, "get_image", read)
    monkeypatch.setattr(processing, "prepare_image", forbidden)
    monkeypatch.setattr(models, "describe", describe)
    api.portal.call(enrich_frame, result.frame.id)
    assert len(keys) == 1 and keys[0].endswith("/processed.jpg")
    updated = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()[0]
    assert updated["caption"] == "A chair"
    assert updated["ocr_text"] == result.frame.ocr_text
    assert updated["detected_objects"] == result.frame.detected_objects


def test_enrichment_fails_closed_without_privacy_marker_or_processed_object(client, monkeypatch):
    from app.services.storage.object_store import get_image
    import app.workers.enrichment as enrichment

    api, factory = client
    result = save_fast(api, create(api))

    async def remove_marker():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            row.enhancements = []
            await db.commit()

    api.portal.call(remove_marker)
    monkeypatch.setattr(enrichment, "get_image", lambda *_: (_ for _ in ()).throw(AssertionError("no read")))
    api.portal.call(enrich_frame, result.frame.id)
    frame = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()[0]
    assert frame["enrichment_status"] == "failed"
    assert "face_privacy_unavailable" in frame["processing_warnings"]

    second = api.portal.call(partial(ingest_bytes, image_bytes(), result.frame.session_id,
                                     defer_enrichment=True, force=True))

    async def missing_image():
        async with factory() as db:
            row = await db.get(Frame, second.frame.id)
            row.processed_object_key = "missing/processed.jpg"
            await db.commit()

    api.portal.call(missing_image)
    monkeypatch.setattr(enrichment, "get_image", get_image)
    api.portal.call(enrich_frame, second.frame.id)
    frames = api.get(f"/api/v1/sessions/{result.frame.session_id}/frames").json()
    failed = next(frame for frame in frames if frame["id"] == str(second.frame.id))
    assert failed["enrichment_status"] == "failed"
    assert "processed_image_unavailable" in failed["processing_warnings"]


def test_enrichment_failure_keeps_saved_ocr_and_reports_the_failure(client, monkeypatch):
    api, _ = client
    sid = create(api)
    result = save_fast(api, sid)

    async def unavailable(*args):
        raise BackendError("Offline", 503, "vision_unavailable")

    monkeypatch.setattr(models, "describe", unavailable)
    api.portal.call(enrich_frame, result.frame.id)
    frame = api.get(f"/api/v1/sessions/{sid}/frames").json()[0]
    assert frame["ocr_text"] == "EXIT"
    assert frame["enrichment_status"] == "failed"
    assert "vision_unavailable" in frame["processing_warnings"]


def test_deletion_during_enrichment_cannot_resurrect_an_image(client, monkeypatch):
    api, factory = client
    sid = create(api)
    result = save_fast(api, sid)

    async def deleted_during_inference(*args):
        async with factory() as db:
            await db.execute(delete(Frame).where(Frame.id == result.frame.id))
            await db.commit()
        return Scene(caption="A door", uncertain=False, central_closed_door=True)

    monkeypatch.setattr(models, "describe", deleted_during_inference)
    api.portal.call(enrich_frame, result.frame.id)
    assert api.get(f"/api/v1/sessions/{sid}/frames").json() == []


def test_delayed_caption_preserves_updated_ocr_in_search(client, monkeypatch):
    api, factory = client
    result = save_fast(api, create(api))
    async def describe(_):
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            row.ocr_text = "PLATFORM 7"
            await db.commit()
        return Scene(caption="A sign", uncertain=False)
    monkeypatch.setattr(models, "describe", describe)
    api.portal.call(enrich_frame, result.frame.id)
    async def verify():
        async with factory() as db:
            row = await db.get(Frame, result.frame.id)
            assert row.ocr_text == "PLATFORM 7"
            assert "PLATFORM 7" in row.search_text and "EXIT" not in row.search_text
            assert row.embedding is None
    api.portal.call(verify)


def test_superseded_frames_are_backfilled_after_pending_work(client):
    from app.core.config import settings
    from app.workers.enrichment import claim_enrichment

    api, factory = client
    sid = create(api)
    for _ in range(settings.max_pending_enrichments + 2):
        api.portal.call(partial(ingest_bytes, image_bytes(), UUID(sid), force=True, defer_enrichment=True))
    claimed = []
    for _ in range(settings.max_pending_enrichments + 2):
        frame_id = api.portal.call(claim_enrichment)
        assert frame_id is not None
        claimed.append(frame_id)
        api.portal.call(enrich_frame, frame_id)
    assert len(set(claimed)) == settings.max_pending_enrichments + 2
    assert api.portal.call(claim_enrichment) is None
    frames = api.get(f"/api/v1/sessions/{sid}/frames").json()
    assert all(frame["enrichment_status"] == "complete" for frame in frames)

    async def check():
        async with factory() as db:
            for frame_id in claimed:
                row = await db.get(Frame, frame_id)
                assert row.embedding is not None and row.enrichment_attempts == 1

    api.portal.call(check)


def test_failures_retry_after_backoff_and_stop_at_the_attempt_limit(client, monkeypatch):
    from datetime import timedelta
    from app.core.config import settings
    from app.db.models.frame import now
    from app.workers.enrichment import claim_enrichment

    api, factory = client
    saved = save_fast(api, create(api))

    async def unavailable(*_args):
        raise BackendError("Offline", code="vision_unavailable")

    monkeypatch.setattr(models, "describe", unavailable)
    for attempt in range(1, settings.enrichment_max_attempts + 1):
        assert api.portal.call(claim_enrichment) == saved.frame.id
        api.portal.call(enrich_frame, saved.frame.id)
        assert api.portal.call(claim_enrichment) is None

        async def due():
            async with factory() as db:
                row = await db.get(Frame, saved.frame.id)
                assert row.enrichment_attempts == attempt
                if attempt < settings.enrichment_max_attempts:
                    assert row.enrichment_retry_at is not None
                    row.enrichment_retry_at = now() - timedelta(seconds=1)
                    await db.commit()
                else:
                    assert row.enrichment_retry_at is None

        api.portal.call(due)
    assert api.portal.call(claim_enrichment) is None


def test_failed_enrichment_recovers_without_stale_failure_warnings(client, monkeypatch):
    from datetime import timedelta
    from app.db.models.frame import now
    from app.workers.enrichment import claim_enrichment

    api, factory = client
    saved = save_fast(api, create(api))
    describe = models.describe

    async def unavailable(*_args):
        raise BackendError("Offline", code="vision_unavailable")

    monkeypatch.setattr(models, "describe", unavailable)
    api.portal.call(claim_enrichment)
    api.portal.call(enrich_frame, saved.frame.id)

    async def due():
        async with factory() as db:
            row = await db.get(Frame, saved.frame.id)
            row.enrichment_retry_at = now() - timedelta(seconds=1)
            await db.commit()

    api.portal.call(due)
    monkeypatch.setattr(models, "describe", describe)
    assert api.portal.call(claim_enrichment) == saved.frame.id
    api.portal.call(enrich_frame, saved.frame.id)
    frame = api.get(f"/api/v1/sessions/{saved.frame.session_id}/frames").json()[0]
    assert frame["enrichment_status"] == "complete"
    assert "vision_unavailable" not in frame["processing_warnings"]


def test_uninformative_provisional_frames_are_deleted_with_their_objects(client, monkeypatch):
    import pytest
    import app.services.frames.ingestion as ingestion
    from app.services.storage.object_store import get_image

    api, factory = client
    monkeypatch.setattr(ingestion, "analyze_image", lambda *_: Analysis("", 0, []))
    saved = save_fast(api, create(api))
    assert "information_check_pending" in saved.frame.processing_warnings

    async def key():
        async with factory() as db:
            frame = await db.get(Frame, saved.frame.id)
            return frame.original_object_key, frame.processed_object_key

    keys = api.portal.call(key)

    async def empty(*_args):
        return Scene(caption="Only texture.", informative=False, uncertain=False)

    monkeypatch.setattr(models, "describe", empty)
    api.portal.call(enrich_frame, saved.frame.id)
    assert api.get(f"/api/v1/sessions/{saved.frame.session_id}/frames").json() == []
    for key in keys:
        with pytest.raises(BackendError, match="unavailable"):
            get_image(key)


def test_uninformative_assessment_preserves_explicit_capture_and_ocr(client, monkeypatch):
    import app.services.frames.ingestion as ingestion

    api, _ = client
    sid = UUID(create(api))

    async def empty(*_args):
        return Scene(caption="Only texture.", informative=False, uncertain=False)

    monkeypatch.setattr(models, "describe", empty)
    # A detector or OCR observation overrides an uninformative scene assessment.
    saved = save_fast(api, str(sid))
    api.portal.call(enrich_frame, saved.frame.id)
    assert api.get(f"/api/v1/sessions/{sid}/frames/{saved.frame.id}").status_code == 200
    monkeypatch.setattr(ingestion, "analyze_image", lambda *_: Analysis("", 0, []))
    forced = api.portal.call(partial(ingest_bytes, image_bytes(), sid, force=True, defer_enrichment=True))
    api.portal.call(enrich_frame, forced.frame.id)
    assert api.get(f"/api/v1/sessions/{sid}/frames/{forced.frame.id}").status_code == 200
    other_sid = UUID(create(api))
    rejected = api.portal.call(partial(ingest_bytes, image_bytes(), other_sid))
    assert rejected.status == "rejected" and rejected.reason == "uninformative"


def test_retry_migration_preserves_rows_and_only_backfills_superseded_frames(tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    path = Path(__file__).resolve().parents[1] / "migrations/versions/0009_enrichment_retry.py"
    spec = importlib.util.spec_from_file_location("retry_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///" + str(tmp_path / "retry.db"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE stored_frames (id INTEGER PRIMARY KEY, enrichment_status TEXT, processing_warnings TEXT)"))
        connection.execute(text("INSERT INTO stored_frames VALUES (1, 'skipped', :warnings), (2, 'skipped', '[]')"), {"warnings": '["enrichment_superseded"]'})
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.execute(text("SELECT enrichment_attempts, enrichment_retry_at FROM stored_frames ORDER BY id")).all()
        assert rows[0][0] == rows[1][0] == 0
        assert rows[0][1] is not None and rows[1][1] is None
        migration.downgrade()
        assert {column["name"] for column in inspect(connection).get_columns("stored_frames")} == {"id", "enrichment_status", "processing_warnings"}
    engine.dispose()


def test_uninformative_assessment_keeps_images_already_used_as_answer_evidence(client, monkeypatch):
    import app.services.frames.ingestion as ingestion
    from app.db.models import QuestionAnswer
    from app.db.models.frame import now
    from datetime import timedelta

    api, factory = client
    monkeypatch.setattr(ingestion, "analyze_image", lambda *_: Analysis("", 0, []))
    saved = save_fast(api, create(api))

    async def cite():
        async with factory() as db:
            db.add(QuestionAnswer(session_id=saved.frame.session_id, question="What did I see?",
                                  answer="No recognizable content.", language="en", uncertain=True,
                                  evidence_frame_ids=[str(saved.frame.id)], expires_at=now() + timedelta(hours=1)))
            await db.commit()

    async def empty(*_args):
        return Scene(caption="Only texture.", informative=False, uncertain=False)

    api.portal.call(cite)
    monkeypatch.setattr(models, "describe", empty)
    api.portal.call(enrich_frame, saved.frame.id)
    assert api.get(f"/api/v1/sessions/{saved.frame.session_id}/frames/{saved.frame.id}").status_code == 200


def test_existing_unsafe_caption_is_filtered_when_served(client):
    from app.services.ai.safety import UNKNOWN
    api, factory = client
    saved = save_fast(api, create(api))

    async def unsafe_legacy_caption():
        async with factory() as db:
            frame = await db.get(Frame, saved.frame.id)
            frame.caption = 'It is safe to cross now.'
            await db.commit()

    api.portal.call(unsafe_legacy_caption)
    frame = api.get(f'/api/v1/sessions/{saved.frame.session_id}/frames/{saved.frame.id}').json()
    assert frame['caption'] == UNKNOWN['en']
    assert 'caption_safety_filtered' in frame['processing_warnings']
