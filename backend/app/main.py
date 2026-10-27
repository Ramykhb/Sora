import asyncio
from contextlib import asynccontextmanager
import logging
import shutil
from time import perf_counter
from uuid import uuid4
import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import router
from app.api.routes.auth import router as auth_router
from app.api.routes.live import ws_router
from app.core.auth import require_admin
from app.core.config import settings
from app.core.errors import BackendError
from app.db.session import engine
from app.services.storage.object_store import client, initialize_storage
from app.services.streaming.session import streams
from app.workers.retention import retention_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    if settings.auto_migrate:
        from alembic import command
        from alembic.config import Config
        from app.core.config import BACKEND_ROOT

        await asyncio.to_thread(command.upgrade, Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    async with engine.connect() as connection:
        await connection.execute(text("SELECT owner_id FROM capture_sessions LIMIT 1"))
        await connection.execute(text("SELECT 1 FROM auth_sessions LIMIT 1"))
    for attempt in range(10):
        try:
            await asyncio.to_thread(initialize_storage)
            break
        except BackendError:
            if attempt == 9:
                raise
            await asyncio.sleep(2)
    tasks = [asyncio.create_task(retention_loop()), asyncio.create_task(streams.reap_idle())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await streams.close()
        await engine.dispose()


app = FastAPI(title="World Out Loud Backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(ws_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_metadata(request: Request, call_next):
    request_id = str(uuid4())
    start = perf_counter()
    length = request.headers.get("content-length", "0")
    if length.isdigit() and int(length) > (settings.max_upload_mb + 1) * 1024 * 1024:
        return JSONResponse(
            {"error": {"code": "upload_limit", "message": "Request too large"}}, 413
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(round((perf_counter() - start) * 1000, 2))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Do not reflect password/token values (or uploaded data) in validation errors.
    return JSONResponse(
        {
            "detail": [
                {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]
        },
        422,
    )


@app.exception_handler(BackendError)
async def backend_error(request, exc):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, exc.status_code)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("Database request failed: %s", type(exc).__name__)
    return JSONResponse(
        {"error": {"code": "database_unavailable", "message": "Database unavailable"}}, 503
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/ready", dependencies=[Depends(require_admin)])
async def ready():
    components = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1 FROM capture_sessions LIMIT 1"))
        components["database"] = "ready"
    except Exception:
        components["database"] = "unavailable"
    try:
        if settings.storage_backend == "s3":
            await asyncio.to_thread(client().head_bucket, Bucket=settings.s3_bucket)
        elif not settings.local_storage_dir.is_dir():
            raise OSError()
        components["storage"] = "ready"
    except Exception:
        components["storage"] = "unavailable"
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(settings.ollama_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            names = {model["name"] for model in response.json()["models"]}
        for name, model in [
            ("vision", settings.vision_model),
            ("embeddings", settings.embedding_model),
        ]:
            components[name] = "ready" if model in names else "model_missing"
    except Exception:
        components["vision"] = components["embeddings"] = "unavailable"
    import pytesseract

    try:
        langs = await asyncio.to_thread(pytesseract.get_languages)
        components["ocr"] = (
            "ready" if set(settings.ocr_languages.split("+")) <= set(langs) else "languages_missing"
        )
    except Exception:
        components["ocr"] = "unavailable"
    components["tts"] = "ready" if shutil.which(settings.espeak_binary) else "binary_missing"
    from pathlib import Path

    components["detector"] = "ready" if Path(settings.yolo_model).is_file() else "weights_missing"
    try:
        from faster_whisper.utils import download_model

        model_path = Path(settings.whisper_model)
        if not model_path.is_dir():
            model_path = Path(
                await asyncio.to_thread(
                    download_model, settings.whisper_model, local_files_only=True
                )
            )
        components["speech"] = (
            "ready" if (model_path / "model.bin").is_file() else "weights_missing"
        )
    except Exception:
        components["speech"] = "weights_or_runtime_missing"
    healthy = all(value == "ready" for value in components.values())
    return JSONResponse(
        {"status": "ready" if healthy else "degraded", "components": components},
        status_code=200 if healthy else 503,
    )
