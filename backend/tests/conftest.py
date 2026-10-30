import os

# Tests use no live services or credentials. File-backed engines are allocated per API test.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["STORAGE_BACKEND"] = "local"

os.environ["API_KEY"] = "test-only-key"
os.environ["APP_ENV"] = "test"

import asyncio
import sys
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.services.ai.models import ModelAnswer, Scene, models
from app.services.frames.processing import Analysis


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.main as main
    import app.services.frames.ingestion as ingestion
    from sqlalchemy import event

    engine = create_async_engine(
        "sqlite+aiosqlite:///" + str(tmp_path / "test.db"), poolclass=NullPool
    )

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(initialize())
    monkeypatch.setattr(settings, "auto_migrate", False)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "local_storage_dir", tmp_path / "objects")
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("app.") and hasattr(module, "SessionFactory"):
            monkeypatch.setattr(module, "SessionFactory", factory)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "warmup_detector", lambda: None)
    # Background enrichment is driven explicitly in its integration tests.
    async def idle_enrichment():
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "enrichment_loop", idle_enrichment)
    monkeypatch.setattr(
        ingestion,
        "analyze_image",
        lambda *args: Analysis(
            "EXIT", 95, [{"label": "chair", "confidence": 0.9, "box": [20, 20, 80, 95]}]
        ),
    )

    async def describe(_):
        return Scene(caption="A chair beside an EXIT sign", uncertain=False)

    async def embed(*args, **kwargs):
        return [1.0] + [0.0] * (settings.embedding_dimensions - 1)

    async def chat(messages, schema):
        import json

        context = json.loads(messages[-1]["content"])["camera_observations"]
        return ModelAnswer(
            answer="A chair is visible.",
            uncertain=False,
            evidence_frame_ids=[context[0]["frame_id"]],
        )

    monkeypatch.setattr(models, "describe", describe)
    monkeypatch.setattr(models, "embed", embed)
    monkeypatch.setattr(models, "chat", chat)
    monkeypatch.setattr(settings, "auth_require_verified_email", False)
    monkeypatch.setattr(settings, "auth_registration_enabled", True)
    monkeypatch.setattr(settings, "smtp_host", "")
    with TestClient(app) as api:
        response = api.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@example.com",
                "password": "a-valid-admin-password",
                "display_name": "Test admin",
            },
        )
        assert response.status_code == 201, response.text

        async def promote():
            from app.db.auth_models import User
            from sqlalchemy import select

            async with factory() as db:
                user = await db.scalar(select(User).where(User.email == "admin@example.com"))
                user.role = "admin"
                await db.commit()

        asyncio.run(promote())
        login = api.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "a-valid-admin-password"},
        )
        assert login.status_code == 200, login.text
        api.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        yield api, factory
    asyncio.run(engine.dispose())
