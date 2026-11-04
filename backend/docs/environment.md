# Backend environment reference

The authoritative Python settings are in `app/core/config.py`. `.env.example` lists the common local settings plus Docker's `POSTGRES_*` variables; omitted settings use the defaults in that class. Run `python3 backend/scripts/configure_local.py --host YOUR_LAN_IP` from the project root to generate secrets while preserving existing credentials and updating phone/TURN networking. Pydantic reads `backend/.env` even when Python starts elsewhere; actual process environment values override that file. For relative paths, run native commands from `backend`. Unknown `.env` fields are ignored. `APP_ENV` currently has no behavioral effect.

## Historical audit of the existing .env (2026-10-27)

These notes describe the configuration at that date, not the present UI or connectivity status. The phone and dashboard are now connected, and the dashboard has account recovery/verification screens.

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
- `VISION_IMAGE_MAX_SIDE` controls the separate image sent for AI captioning (default 448 px; range 224–2048). Smaller images may lose small visual details. OCR, object detection and stored images still use `MAX_IMAGE_SIDE` (default 1280), independently of this setting. Some vision runtimes enforce a minimum image-token count, so shrinking below this default may not improve latency further.
- Retrieval: 1–6 frames; live sessions: 1–32; sample interval: at least 0.25 seconds.
- `LIVE_DEFER_ENRICHMENT=true` saves memory frames without waiting for generative descriptions. `MAX_PENDING_ENRICHMENTS=2` bounds pending descriptions per session; older pending frames become `skipped` and retain searchable objects/OCR. In-progress inference finishes. HTTP uploads retain synchronous processing. Live alerts remain independent even when deferred memory enrichment is disabled.
- `DETECTION_INTERVAL_SECONDS=0.25` controls the independent latest-frame detector; `DETECTION_IMAGE_SIZE=320` bounds its inference resolution and `DETECTOR_THREADS=2` bounds PyTorch threads. `DETECTION_MAX_AGE_SECONDS=2` expires observations before notification. These settings are separate from one-second memory sampling.
- `MODEL_THREADS=2` requests bounded Ollama inference threading; Compose also enforces `cpus: 2.0` on Ollama. `MODEL_TIMEOUT_SECONDS=120` includes model queue waiting. User requests precede queued background inference; already-running inference finishes first. Current-view retrieval uses the newest frame without a query embedding; memory searches retain semantic ranking.
- `EMBEDDING_DIMENSIONS` is constrained to 1024 by the current code and database schema.
- SMTP security: `starttls`, `ssl`, or `none` (local mail sandbox). `MODEL_DEVICE` is passed to YOLO only; Whisper currently uses CPU.
- Database credentials containing URL-special characters must be percent-encoded in `DATABASE_URL`. Compose also currently interpolates credentials directly into its API database URL, so this requires a corresponding Compose adjustment; changing the raw password alone does not encode it.


## WebRTC networking

The API's Docker Compose service mounts `app/` and `migrations/` read-only for local development, so source fixes survive recreation. Dependencies still come from the API image. For a production image deployment, omit those development mounts.

`SAMPLE_INTERVAL_SECONDS=1` samples one image per second from incoming WebRTC video. It does not control video playback frame rate. Configure the optional authenticated TURN service for phone/browser connectivity through Docker:

```dotenv
TURN_PUBLIC_HOST=192.168.0.104
TURN_INTERNAL_HOST=turn
TURN_SHARED_SECRET=<a long randomly generated secret>
SAMPLE_INTERVAL_SECONDS=1
```

`TURN_PUBLIC_HOST` must be reachable from the phone and dashboard. Use the computer's actual LAN address for a same-Wi-Fi demo; update it if that address changes. Internet clients require a publicly reachable relay address and port forwarding/firewall configuration. `TURN_INTERNAL_HOST=turn` lets the API reach the relay through Docker DNS. The shared secret stays on the servers; authenticated `/stream/config` calls receive HMAC-based credentials valid for one hour, never the secret itself.

Start the relay with `docker compose --profile webrtc up -d turn`, then recreate the API after changing environment settings. Compose exposes TURN on UDP/TCP 3478 and relay UDP ports 48000–48099, below macOS's ephemeral port range to avoid conflicts with temporary UDP sockets. Allow or forward this relay range when configuring a firewall or router. After changing port mappings, run `docker compose --profile webrtc up -d turn` to recreate the container; `docker compose start` does not apply configuration changes. The local relay does not configure TURN-over-TLS; production networks needing TLS require that additional deployment configuration. Native capture needs a rebuilt WebRTC development app. Browser camera capture requires HTTPS or localhost; dashboard playback uses the browser's WebRTC support.

### Live video quality

The phone/browser publisher requests 1920×1080 at 20 fps (device support permitting), with a 4 Mbps encoding ceiling and balanced adaptation under load. The phone preview fits the whole camera image. Saved/OCR frames retain source detail up to `MAX_IMAGE_SIDE` independently of dashboard playback.

Dashboard viewers receive an unbuffered preview bounded by `STREAM_PREVIEW_MAX_SIDE=1280` (720p for 16:9 video) and `STREAM_PREVIEW_MAX_FPS=20`. Frames above the preview rate are skipped, not queued. This limits software re-encoding cost while keeping full-resolution camera sampling independent. `STREAM_VIDEO_MAX_BITRATE=3000000` caps dashboard encoding at 3 Mbps; encoders start at up to 1.5 Mbps and respond to congestion feedback. These are ceilings, not guaranteed frame rates or bandwidth.

These changes need no native rebuild. Reload the WebRTC development app and restart the stream to apply capture settings. Restart the API after changing preview/encoder settings; existing video connections will reconnect.

### Camera text recognition

`MAX_IMAGE_SIDE=1920` preserves full-HD detail in retained frames and sampled JPEGs; detector inference and VLM image sizes remain independently bounded. Existing installations with an explicit smaller value must update it to retain the additional detail from future captures.

OCR uses an enlarged grayscale copy of face-redacted pixels, compares sparse-text and page layouts, and can retry with long borders/rules removed. Stored images are not thresholded for OCR. `OCR_MIN_WORD_CONFIDENCE=60` filters unreliable words (isolated glyphs require higher confidence); `OCR_TIMEOUT_SECONDS=4` bounds all passes together. English, French and Arabic remain enabled through `OCR_LANGUAGES`. Confidence is an engine score, not a measured accuracy percentage. Small, defocused, skewed or glare-obscured text can still be unreadable. Text-reading requests without accepted OCR return a request for a clearer view rather than asking the VLM to reconstruct missing text from a small image.
