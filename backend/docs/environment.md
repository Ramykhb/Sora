# Backend environment reference

The authoritative Python settings are in `app/core/config.py`. `.env.example` lists every current setting except the unused legacy `API_KEY`, plus Docker's `POSTGRES_*` variables. Pydantic reads `backend/.env` even when Python starts elsewhere; actual process environment values override that file. For relative file paths, run native commands from `backend`. Missing fields use the Python defaults; unknown `.env` fields are ignored. `APP_ENV` currently has no behavioral effect.

## Audit of the existing .env (2026-10-27)

The existing file was read and left unchanged.

- `POSTGRES_DB=sora`, but native `DATABASE_URL` ends with `/visual_assistant`. Docker constructs its own URL ending in `/sora`, which explains why the container works while a native CLI could use another database. Update the native URL to the existing `sora` database using the same current credentials.
- `API_KEY=local-development-only` is obsolete and grants no authentication. Remove it from local configuration when convenient.
- Missing `AUTH_*` settings currently use defaults: 15-minute access tokens, 30-day refresh sessions, registration enabled, email verification not required. No signing secret is needed because tokens are opaque and stored as hashes.
- Missing SMTP settings default to unconfigured email. Registration/login work, but email send requests return 503. Configure host/from and other SMTP connection settings to enable recovery/verification.
- `CORS_ORIGINS` currently includes ports 8081 and 3000, but not the React dashboard's port 5173. Add `http://127.0.0.1:5173` and/or `http://localhost:5173` when connecting that dashboard. These are distinct origins. The current dashboard is still disconnected.
- `AUTH_PUBLIC_URL` defaults to `http://localhost:3000`. Set it to your future frontend origin when implementing email pages; the dashboard currently has no reset/verification pages.
- All other omitted Python settings use the defaults documented in `.env.example`. Their omission is not an error; the old example was simply incomplete.

## Native Python versus Docker

| Setting | Native Python / local scripts | API container override in Compose |
| --- | --- | --- |
| `DATABASE_URL` | Value in `.env`; host `localhost`, database `sora` for your setup | Constructed from `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`; host `postgres` |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | `http://object-storage:9000` |
| `OLLAMA_URL` | `http://localhost:11434` | `http://ollama:11434` |
| `YOLO_MODEL` | `models/yolo11n.pt` | `/app/models/yolo11n.pt` |
| `AUTO_MIGRATE` | `false` (run Alembic yourself) | Always `true` |

The rest of the API's `.env` fields are passed through `env_file`; Compose explicitly repeats some of them, including storage credentials, models, retention, CORS and ICE settings. The Compose PostgreSQL database-name fallback is `visual_assistant` when `POSTGRES_DB` is absent. Set it explicitly to avoid ambiguity. The Python database-URL fallback also uses `visual_assistant`; native Python does not construct that URL from `POSTGRES_*` automatically. The example includes an interpolated URL to keep its values aligned.

`POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` initialize a **new** PostgreSQL data volume. Changing them does not create/rename a database or rotate credentials in an existing volume. Preserve your working values. S3 credentials are shared by RustFS service configuration and the API client.

`HF_HOME=/app/models/huggingface` is fixed in the Dockerfile for the Hugging Face model cache. `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` are also image-level Python settings. RustFS `RUSTFS_*` variables are supplied by Compose. None needs to be copied into the backend `.env` for this setup. There are no paid-model API-key variables, frontend variables, or hidden script-only credentials to add. Smoke/evaluation CLI scripts prompt for account login credentials.

## Applying configuration

Native Python: restart the Python process after edits; settings are loaded at import time. Docker: from `backend`, recreate the API to load updated environment values:

```sh
docker compose --profile app up -d --no-deps --force-recreate api
```

No image rebuild is required for `.env` edits. `docker compose restart api` alone reuses the old container environment. If you change PostgreSQL/storage configuration, review the corresponding services and existing persistent volumes before recreating them.

Avoid printing a full rendered Compose configuration when sharing logs, because it includes database/storage/SMTP credentials. `docker compose --profile app config --quiet` validates syntax without printing values.

## Value formats and constraints

- CORS and ICE values must be JSON arrays. Booleans accept `true`/`false`.
- Retention: 1–168 hours; access lifetime: 1–60 minutes; refresh lifetime: 1–90 days.
- Uploads: 1–100 MB; maximum image side: 320–4096 px; audio: 1–120 seconds.
- Retrieval: 1–6 frames; live sessions: 1–32; sample interval: at least 0.25 seconds.
- `EMBEDDING_DIMENSIONS` is constrained to 1024 by the current code and database schema.
- SMTP security: `starttls`, `ssl`, or `none` (local mail sandbox). `MODEL_DEVICE` is passed to YOLO only; Whisper currently uses CPU.
- Database credentials containing URL-special characters must be percent-encoded in `DATABASE_URL`. Compose also currently interpolates credentials directly into its API database URL, so this requires a corresponding Compose adjustment; changing the raw password alone does not encode it.
