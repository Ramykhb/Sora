# Implementation validation — 2026-10-25

The local server-logic suite passes 35 tests. Ruff lint, Python syntax checks and Docker Compose configuration validation also pass.

The suite covers image validation, contrast enhancement, resizing, perceptual deduplication, actual system Tesseract recognition of a generated EXIT sign, model protocol/schema validation, English/French/Arabic safety filters, persisted sessions/frames/history, semantic retrieval orchestration, stale-evidence rejection before and after inference, voice-question and TTS contracts, authenticated live JPEG WebSockets and event delivery, central closed-door alerts, feedback, cross-session ID checks, storage-failure compensation, durable deletion retries, expiry cleanup and orphan reconciliation.

API tests use SQLite and local image files with deterministic model substitutes. Test dependencies were available from local caches in a temporary test environment. This validates backend behavior, not real model quality or a PostgreSQL/vector deployment.

The full dependency installation in backend/.venv was attempted but failed because the sandbox could not resolve PyPI. Docker socket access is also denied in this environment. Consequently the container build, PostgreSQL migrations, RustFS integration, model weight downloads, real YOLO/Whisper/Qwen inference, eSpeak output, and real WebRTC ICE networking have not been run here. No end-to-end latency or answer-accuracy figures are claimed.

After setup on the host, run:

```sh
python -m scripts.smoke /path/to/test-image.jpg --webrtc
python -m scripts.evaluate /path/to/consented-dataset.json --output evaluation-report.json
```

The smoke script runs image storage/retrieval, text answers, TTS, an audio question, history and optional actual WebRTC video. It deletes its test session afterward. The evaluation script produces per-example data and timings for review. Human ratings remain necessary to establish factual answer accuracy and accessibility usefulness.

## Authentication layer — 2026-10-26

- All 47 tests passed in the available `/tmp/visual-backend-tests` environment (real SQLite, local objects, real Argon2 password hashing; model inference and SMTP sending substituted).
- Ruff checks, Python compilation, CLI argument/help checks and Git whitespace checks passed.
- Authentication coverage includes cross-user REST/WebSocket denial, scoped dashboard/metrics, refresh rotation and simultaneous reuse, expiry/logout, live-stream logout, password recovery/change, single-use/purpose/expiry checks, verification, role management, account deletion and rate limits.
- New Alembic migration `0002_authentication` is implemented but was not applied to a running PostgreSQL deployment here. The local `.venv` has not been populated; installation failed because PyPI DNS resolution is unavailable. Run `uv pip install -r requirements-dev.txt`, then `alembic upgrade head` in the configured environment.
- Real SMTP delivery has not been tested; configure SMTP and exercise verification/reset with your mailbox or a local mail sandbox.
- Frontend authentication remains outside this change; the web dashboard still uses sample data.
