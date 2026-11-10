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

For an isolated Wi-Fi demo, `ngrok tcp 3478` can forward the phone's TURN control and media connection to the local relay. Set `TURN_PUBLIC_URLS=["turn:YOUR_TCP_HOST:YOUR_TCP_PORT?transport=tcp"]` in `backend/.env`, using the endpoint ngrok prints, and recreate the API. This overrides only phone/browser TURN URLs; the API keeps using `TURN_INTERNAL_HOST` on port 3478. Keep the tunnel running and update this setting if its endpoint changes. This setup requires the API to reach the local TURN relay's allocated UDP addresses; it does not publish that relay's UDP port range for arbitrary internet peers. Set `TURN_PUBLIC_URLS=[]` to restore the standard LAN configuration.

### Live video quality

The phone/browser publisher requests 1280×720 at 60 fps (device support permitting), with a 6 Mbps encoding ceiling and the negotiated adaptation policy. The phone preview fits the whole camera image. Saved/OCR frames retain source detail up to `MAX_IMAGE_SIDE` independently of dashboard playback.

Dashboard viewers receive a preview bounded by `STREAM_PREVIEW_MAX_SIDE=1280` (720p for 16:9 video) and `STREAM_PREVIEW_MAX_FPS=60`. A three-frame buffer absorbs short decode bursts and drops the oldest frame when full. Rate limiting uses media timestamps so arrival jitter does not discard valid camera frames. The sampler keeps only the latest frame; each consumer has independent pixel storage for safe concurrent PyAV conversions. H.264 is preferred for mobile hardware encoding, with VP8 fallback. `STREAM_VIDEO_MAX_BITRATE=6000000` caps dashboard encoding at 6 Mbps; encoders start at up to 3 Mbps and respond to congestion feedback. These are ceilings, not guaranteed frame rates or bandwidth.

The dashboard displays actual playback resolution and fps. `/stream/status` also reports `received_fps`, `video_width` and `video_height`, independently of OCR/detection sampling. From the backend environment, run `python -m scripts.benchmark_stream --relay-only --image tests/fixtures/astronaut.jpg` to measure a moving 720p source through the running API and TURN, including the viewer leg. It creates and removes its own temporary account/session, warms up for two seconds of frames, then checks three five-second windows for at least 90% of the target fps (`--fps 60` by default; `--fps 30` for comparison). It requires registration without email verification; it does not measure the physical phone's camera, Wi-Fi or browser rendering.

For a development client, reload from Metro and restart the stream to apply capture settings. A standalone installed app embeds its JavaScript: rebuild and reinstall it (`npm run ios -- --configuration Release --device` from `mobile`) to receive these changes. Starting Metro alone does not update that app. Restart/recreate the API after changing preview/encoder settings; existing video connections will reconnect.

### Camera text recognition

`MAX_IMAGE_SIDE=1920` preserves full-HD detail in retained frames and sampled JPEGs; detector inference and VLM image sizes remain independently bounded. Existing installations with an explicit smaller value must update it to retain the additional detail from future captures.

`OCR_ENGINE=paddleocr` selects local PP-OCRv5 by default. A mobile detector finds text regions, perspective-corrected crops are recognized by the requested language models, and credible regions are returned in reading order. English-only requests use the English recognizer; English/French combinations share the Latin model; Arabic uses the Arabic recognizer. `OCR_MIN_WORD_CONFIDENCE=60` filters uncertain regions. Confidence is an engine score, not a measured accuracy percentage. Small, defocused or glare-obscured text can still be unreadable.

Prepare the models and isolated runtime before starting the API:

```sh
python -m scripts.prepare_ocr --install-runtime
```

The standard `scripts.prepare_models` command also performs this preparation when PaddleOCR is selected. Models and the `.venv` runtime live under `PADDLE_OCR_MODEL_DIR` (default `models/paddleocr`); Docker keeps them in its persistent model volume. `requirements-ocr.txt` pins PaddleOCR 3.7.0 and a platform-compatible PaddlePaddle runtime; Linux ARM64 uses PaddlePaddle 3.2.2. The four models total about 28 MiB. A SHA-256 manifest records their sources and file hashes. No model is downloaded during inference.

The API warms one persistent local worker on startup, using the model directory's `.venv/bin/python` or `PADDLE_OCR_PYTHON` when explicitly configured. The worker keeps models loaded, processes only already face-redacted images, and has no network listener. `OCR_THREADS=2` bounds CPU use and `OCR_MAX_REGIONS=64` bounds text-region work. `OCR_TIMEOUT_SECONDS=4` includes waiting for the worker and inference; a stuck inference is terminated and the next request can recover with a fresh worker. Initial and replacement-worker startup (including representative detector/recognizer warmup) has a separate 45-second budget and is not charged to a frame's inference deadline. Dense frames are processed in small batches, with larger regions first. When the budget is reached, recognized text is retained with `ocr_partial` rather than discarded. `/ready` checks the active PaddleOCR worker rather than Tesseract language packs.

`python -m scripts.check_ocr` checks individual model loading on generated text. For the current Docker installation, run `docker exec -w /app backend-api-1 /app/models/paddleocr/.venv/bin/python -m scripts.check_ocr --directory /app/models/paddleocr`. Results are saved in `verification.json`. Set `OCR_ENGINE=tesseract` only to explicitly select the legacy engine. Restart the API after changing OCR configuration or preparing a fresh runtime. Existing stored OCR text is retained; newly processed frames use the selected engine.

## Nearby places

`GOOGLE_PLACE_API_KEY` enables GPS-based place search using Google Places API (New). Enable that API and billing on its Google Cloud project. Credentials stay on the backend. `GROQ_API_KEY` enables query extraction through `GROQ_MODEL=openai/gpt-oss-20b`; if Groq fails, the question is used as the search query. Generic restaurant requests use Nearby Search; named businesses and filtered requests use Text Search. Named business requests also require the returned display name to match the requested business; similarly named restaurants are rejected. Explicit McDonald’s mentions stay pinned to that brand even when Groq is unavailable. Both are ranked by distance, and results outside `PLACES_RADIUS_METERS` (default 5000) are discarded. Provider deadlines are `GROQ_TIMEOUT_SECONDS=4` and `PLACES_TIMEOUT_SECONDS=8`.

Clients request foreground GPS only for proximity questions. Coordinates are sent to Google, but not Groq, and are not persisted with question history. Spoken answers give the business/category and approximate distance in one short sentence. Distances are straight-line estimates, not walking routes. If a named business has no verified match within the configured radius, the answer says so instead of substituting another business. Location permission failures produce a location-required answer. Restart the backend after changing `.env`. The mobile app adds `expo-location` and requires a new development build for native location support.
