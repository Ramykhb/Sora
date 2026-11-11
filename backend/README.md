# World Out Loud backend

A backend for the university multimedia database and image processing project. It receives live camera frames, selects useful images, enhances them, reads text, detects objects, stores visual memory, retrieves evidence, answers spoken questions and produces spoken replies in English, French and Arabic. The mobile app and dashboard consume the API; they are not part of this directory.

See [the complete environment reference](docs/environment.md) for native/Docker settings, defaults and configuration precedence.

## Stack

- FastAPI / SQLAlchemy / Alembic; PostgreSQL 16 with pgvector.
- RustFS S3-compatible storage, with a local-file option for development.
- OpenCV and Pillow for enhancement, image validation and quality/novelty checks.
- Local PaddleOCR PP-OCRv5 for text detection/recognition in English, French and Arabic; YOLO11 nano for object labels, confidence and bounding boxes.
- Ollama running Qwen2.5-VL 3B for scene descriptions and grounded answers; Qwen3 Embedding 0.6B for multilingual semantic retrieval over captions/OCR/objects.
- faster-whisper base for multilingual speech recognition; eSpeak NG for WAV output.
- aiortc WebRTC ingest and live viewer relay, one-second image sampling, optional TURN relay, legacy JPEG ingress/preview and authenticated event WebSockets.

The vision model and embedding model are separate tasks. This system uses text embeddings of scene descriptions, OCR and object labels rather than CLIP image embeddings. Changing the embedding dimensions requires a DB migration; the initial schema is 1024 dimensions. Models run locally with no paid API key, but download several GB of weights. CPU inference works and can be slow on a MacBook Air. Accuracy and latency need measurement on your scenes and hardware. eSpeak Arabic pronunciation relies on diacritics; English and French are the primary speech demo languages.

## Run Python natively on macOS

This is the recommended development setup for WebRTC on a Mac. Start Docker Desktop first. From `backend`:

```sh
uv venv --python 3.13
source .venv/bin/activate
uv pip install -r requirements-dev.txt
cp .env.example .env
brew install espeak-ng ffmpeg
# Starts PostgreSQL + pgvector, RustFS, and Ollama. No data volumes are reset.
docker compose up -d
alembic upgrade head
python -m scripts.prepare_models
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --limit-concurrency 32 --ws-max-size 15728640
```

If `.venv` already exists, keep it and run the install command. If `.env` exists, merge new settings instead of overwriting secrets. The API packages are confined to `.venv`; PaddleOCR uses a separate persistent runtime under `models/paddleocr/.venv`. eSpeak/FFmpeg are system binaries. To use the optional legacy engine, install `tesseract` and `tesseract-lang` with Homebrew and set `OCR_ENGINE=tesseract`. The existing plain Postgres 16 Docker service is upgraded to a pgvector-enabled Postgres 16 image using the same volume. Old scaffold `frames` tables, if present, are preserved; the new schema uses `stored_frames` and `capture_sessions`.

Register at `POST /api/v1/auth/register`, then log in at `POST /api/v1/auth/login`. Send `Authorization: Bearer <access_token>` on data requests. The shared API key no longer grants access. Create a trusted administrator with `python -m scripts.manage_users create-admin admin@example.com` (password prompted). See [authentication setup and endpoint reference](docs/authentication.md) for refresh tokens, recovery, SMTP, ownership, roles and upgrading existing data. Swagger docs: `http://localhost:8000/docs`. RustFS console: `http://localhost:9001`, using your configured S3 credentials.

If Ollama is already installed on the host, stop the compose `ollama` service and use the host instance on port 11434. The same model preparation command works. macOS native Ollama can use Apple hardware acceleration; Docker Ollama uses CPU in this setup.

To avoid object-storage setup during development, set `STORAGE_BACKEND=local`. Files then live under `data/objects`; the same authenticated API and retention logic apply. PostgreSQL is still required for the application.

## Run the entire backend in containers

```sh
docker compose --profile app up --build -d
# Prepare YOLO/Whisper/PaddleOCR and pull the Ollama models before the demo:
docker compose exec api python -m scripts.prepare_models
docker compose restart api
```

The API container applies migrations automatically. PaddleOCR models and its isolated CPU runtime are prepared explicitly in the persistent model volume. Its image also includes eSpeak and legacy Tesseract language packs. Weights and database/image data use named volumes. On Docker Desktop, WebSocket/HTTP frame ingestion works through the published port; WebRTC needs reachable ICE candidates or a configured TURN relay. For Docker WebRTC, configure and start the optional TURN service as described in [WebRTC networking](docs/environment.md#webrtc-networking). This is a single-process server: run exactly one API worker because live peer connections, bounded queues and event subscriptions are held in memory. Stored sessions, images, history and the deletion outbox survive API restarts. A restart disconnects live clients; they reconnect and renegotiate.

## Process one test image

```sh
source .venv/bin/activate
python scripts/process_image.py "/absolute/path/to/test.jpg" --output /tmp/enhanced.jpg
# Reuse a session to test memory/deduplication; force only for poor-image experiments:
python scripts/process_image.py "/absolute/path/to/next.jpg" --session-id SESSION_UUID
```

The trusted local command creates an unowned, consenting test session if no session ID is supplied. It is visible only to administrators through the API until explicitly claimed with `scripts.manage_users claim-session`. It prints the full ingestion result, including session/frame ID, OCR text, object boxes, caption and timing. Faces detected by the bundled YuNet model are strongly blurred in both saved variants before storage or AI/OCR analysis. A face-detector error rejects the save, including forced snapshots. This is detection, not identity recognition; small, obscured or difficult faces can still be missed. The pre-enhancement image is normalized to JPEG, resized and stripped of EXIF; both it and the enhanced image are stored. PostgreSQL holds metadata and an embedding. Low quality, duplicate and uninformative frames are rejected; `--force` overrides selection for controlled tests. `--language eng` can restrict OCR; default is eng+fra+ara. `--init-db` applies migrations on a fresh database.

To exercise the same selection pipeline with a local video: `python -m scripts.process_video /path/to/video.mp4`. For actual live camera ingestion use the WebRTC or JPEG WebSocket contracts in [docs/api.md](docs/api.md).

## Basic HTTP flow

```sh
# Log in first; copy access_token from the login response:
export SORA_ACCESS_TOKEN="your-access-token"
curl -H "Authorization: Bearer $SORA_ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"consent":true,"language":"en","alerts_enabled":true}' \
  http://localhost:8000/api/v1/sessions
# Copy the returned id into SESSION_UUID:
curl -H "Authorization: Bearer $SORA_ACCESS_TOKEN" -F image=@/path/to/image.jpg \
  http://localhost:8000/api/v1/sessions/SESSION_UUID/frames
curl -H "Authorization: Bearer $SORA_ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"What did that sign say?","scope":"memory","language":"en"}' \
  http://localhost:8000/api/v1/sessions/SESSION_UUID/questions
```

Current-view questions use fresh frames only; memory questions use retained images. The response includes `evidence_frame_ids`, `uncertain` and any dependency warnings. Use the returned question ID with `/questions/{id}/audio` to play the answer, or native mobile TTS. Full endpoints, media and event protocols are in [docs/api.md](docs/api.md).

## Retention and uncertainty

The default retention is 24 hours. Session/frame/question reads immediately hide expired data. The background worker deletes expired metadata and queues image deletion in a durable outbox, retrying object-store failures. Explicit session/frame deletion follows the same path. An hourly reconciliation pass also removes unreferenced image objects older than ten minutes after failed uploads. Microphone uploads and continuous video are not stored. Run cleanup manually with `python -m scripts.cleanup` or the administrator-only maintenance endpoint.

Do not identify people. Do not certify that walking is safe. Answers use retrieved images and validated evidence IDs, with language-specific uncertainty and a filter for safety assurances and movement instructions. A model can still make perceptual mistakes: this is the course's assistive demo and needs human evaluation. Opt-in alerts describe central obstacles and do not estimate distance or give route instructions.

## Tests and evaluation

```sh
python -m pytest -q
ruff check app scripts tests migrations
```

Tests cover image limits/enhancement/deduplication, model protocol validation, localized safeguards and API persistence, memory, stale evidence, feedback, session isolation and deletion. API tests use SQLite and local object files with deterministic substitute models. Authentication tests also cover password hashing, ownership, revocation, token rotation/replay, recovery and account management. They exercise server logic, not model accuracy or actual WebRTC networking. Real PostgreSQL/pgvector, RustFS, Ollama, YOLO, Whisper and WebRTC require a configured integration run. After setup, run `python -m scripts.smoke /path/to/test.jpg --webrtc` for the real image/speech/history/transport flow; smoke/evaluation scripts prompt for account credentials. [docs/validation.md](docs/validation.md) records what has actually been verified in this environment.

Prepare consented fixture images and copy [docs/evaluation.example.json](docs/evaluation.example.json) to your dataset folder. Fill in paths and ground truth, then run:

```sh
python -m scripts.evaluate /path/to/dataset.json --output evaluation-report.json
```

It reports OCR/object recall, retrieval recall@k, answer-term recall, timing and raw answers for review. Term overlap is not factual accuracy; record human correctness ratings through the feedback endpoint. Evaluation sessions are deleted by default; `--keep-session` preserves them until normal expiry. Test only with consenting participants.

[docs/requirements.md](docs/requirements.md) maps every PDF requirement to its backend implementation.

## Upstream documentation

- [Ollama chat](https://docs.ollama.com/api/chat), [embeddings](https://docs.ollama.com/api/embed), [Qwen2.5-VL](https://ollama.com/library/qwen2.5vl), [Qwen3 Embedding](https://ollama.com/library/qwen3-embedding).
- [YOLO predictions](https://docs.ultralytics.com/modes/predict/), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [aiortc](https://aiortc.readthedocs.io/en/latest/api.html).
- [RustFS containers](https://docs.rustfs.com/en/installation/container).

### Blur faces in existing saved frames

New uploads, sampled stream frames and forced current-view snapshots all apply face privacy before writing either object. Live WebRTC video is unchanged. To process previously stored original and enhanced images in place, run:

```sh
docker compose -f backend/docker-compose.yml exec api python -m scripts.blur_saved_faces
```

The command reports checked/blurred frames and skips frames already processed by the current privacy policy. It can resume after interruption. The bundled MIT-licensed YuNet detector scans all four image orientations, with padded blur regions. Detection is automated and cannot guarantee that every face is found.

### Optional Gemini current-view analysis

Get a key from [Google AI Studio](https://aistudio.google.com/apikey), then set the following **only in private `backend/.env`**:

```dotenv
GEMINI_ENABLED=true
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Apply changed environment values with:

```sh
docker compose -f backend/docker-compose.yml --profile app --profile webrtc up -d --no-build --force-recreate api
```

When enabled with a key, walking, detailed current-view and text-reading questions send one face-redacted JPEG to Google's Gemini API. A forced evidence save uses the shared privacy path, skipping OCR, detector inference and the local generative-model queue. Retained images are compressed to `GEMINI_IMAGE_MAX_SIDE=1024` for upload. The server assigns the real evidence ID and validates it after inference. Historical-memory questions, background captions/embeddings and basic object overviews remain local. No cloud calls occur with the flag off or the key empty. The key is sent only in an HTTPS request header and is never returned to phone/dashboard clients.

`GEMINI_DEADLINE_SECONDS=5` bounds the current-view analysis stage, including evidence preparation and fallback. Half a second is reserved for local detection; the provider HTTP timeout is `GEMINI_HTTP_TIMEOUT_SECONDS=4`. Gemini uses `GEMINI_THINKING_LEVEL=MINIMAL` and at most 256 output tokens. There are no slow retries or local-VLM fallback on this path. Database authentication/persistence, speech recognition and speech playback add overhead outside the analysis budget; this is a latency target, not a five-second guarantee for every spoken interaction. Model, key, quota and network errors fall back to local object observations, with explicit warning codes. Without recent evidence the answer reports that limitation.

Walking questions request a structured assessment of the visible path: `unobstructed`, `blocked`, or `unknown`, followed by a short visual reason. An unobstructed assessment describes only the visible section and never certifies walking safety or gives permission to move. Assessments check both ground hazards and obstructions directly ahead at body/head height. A visible closed door, wall across the passage, or other forward blocker produces `blocked` even when the floor is out of view. Missing ground or an unclear forward passage produces `unknown` when no blocker can be established; `unobstructed` requires both areas to be visible. Crossing/traffic decisions are also unknown. Weak image quality downgrades the assessment to unknown. Model uncertainty prevents an unobstructed verdict; a reported blocker remains visible in the answer with uncertainty retained in metadata. Local detection fallback explicitly says the walking path is uncertain, then describes detected objects; it never treats missing detections as an unobstructed path. Walking questions require input no older than `DETECTION_MAX_AGE_SECONDS` (two seconds by default). Cloud results have a separate total snapshot age limit, `GEMINI_WALKING_MAX_AGE_SECONDS=6`, to allow inference to finish; that same limit is checked again before saving the answer. The limit describes the age of the assessed snapshot, not a guarantee about the scene at playback time. Local fallback retains the two-second limit. Over-age cloud responses fall back to a fresh local observation. Identity questions never send images to Gemini. Automated face detection can miss small or obscured faces. Google receives the redacted camera image and question when cloud analysis is used; configure the flag deliberately. Refer to Google's API account terms and quotas for your project.

### Nearby lookups and walking trip directions

`What is the nearest McDonald's?` keeps the existing nearest matching Places result and approximate straight-line distance. `Start a trip to the nearest McDonald's`, `route to Starbucks`, `give me directions to the hospital`, and `navigate me to the nearest restaurant` also request a walking route to that result. The destination is selected by straight-line proximity, preserving named-brand filtering; it is not a comparison of walking routes to every branch.

Enable [Google Routes API](https://developers.google.com/maps/documentation/routes/compute_route_directions) for the project and allow it in the API key's restrictions. Routes uses the server's existing `GOOGLE_PLACE_API_KEY`, or an optional separate `GOOGLE_ROUTES_API_KEY`. `ROUTES_TIMEOUT_SECONDS=8` bounds that additional request; the overall trip budget includes query interpretation, Places search, and route calculation. Keys stay on the server. The phone sends its current GPS coordinates, with high accuracy requested for trips, and Google receives the origin and destination to calculate the route.

The Routes request always uses `travelMode=WALK` and metric units. Results include walking distance and the complete ordered provider instructions with each segment's meters, in the requested English, French, or Arabic. Place IDs are used for destinations when available. Distances and turns come directly from Google, without LLM-generated navigation. The first instruction uses Google's compass/street wording: the app does not collect a reliable facing direction and cannot assume the user is facing the route. This is a spoken route overview, with no background tracking, live turn announcements, or rerouting. Google warnings and the required note about potentially missing sidewalks/pedestrian paths are included in the answer. A routing failure reports an explicit limitation; any retained place distance is labeled straight-line and no replacement turns are invented.

Reload the mobile JavaScript after updating it so trip phrases without `nearest`/`nearby` also request GPS. Existing nearby questions continue to work as before. No new native dependencies are needed; the destination-memory feature below adds a database migration.

### Destination memory for follow-up directions

After `What is the nearest restaurant?`, say `route to there`, `route there`, `take me there`, or `how do I get there?` in the same session. The backend retains the exact returned place's name, ID, and coordinates as private structured metadata on the answer. Follow-ups route to that same place from newly requested GPS, without re-running the nearby search or sending conversation history to an LLM. Other camera questions do not change the destination. A new place search replaces the destination; an unsuccessful new search clears the reference rather than silently routing to an older place.

Memory is scoped to the authenticated session and its retained answers, survives backend restarts, and expires/deletes with that data. It does not carry between sessions or accounts. A missing or expired destination asks the user to name a place or run a nearby search first. Answers created before this feature do not contain destination metadata, so ask for the place again once after updating. This implements place follow-ups, not unrestricted conversation memory.

Apply the nullable metadata column with `docker compose -f backend/docker-compose.yml exec -T api alembic upgrade head`, then restart the API. Reload mobile JavaScript for short phrases such as `take me there` to request fresh GPS. No native rebuild is needed.

### Account-owned saved destinations

Mobile **Settings → Saved destinations** manages multiple nicknames and coordinates through authenticated `/api/v1/destinations` CRUD endpoints. The account owns these entries independently of capture sessions: they survive sign-out/restarts, are not subject to frame-retention expiry, and are removed on explicit deletion or account deletion. Nicknames are normalized for case/spacing/punctuation, unique per account, and editable along with latitude/longitude. The API never accepts a client-supplied owner, and even administrator CRUD requests remain scoped to the signed-in account.

Explicit navigation requests first try an exact saved nickname. `route home`, `navigate university`, and `route to saved favorite cafe` require a saved destination; a missing entry returns `saved_destination_not_found` and points to Settings. `route to my home` also matches a saved `home`. Ordinary destination searches with `to` retain their existing Places fallback when no nickname matches. Saved routes bypass Places, Groq, and camera analysis, send the current origin and saved destination coordinates to Google Routes in walking mode, and also populate session destination memory for a subsequent `route to there`. They work from visual-memory screens as explicit navigation requests. Account nicknames are never resolved from another owner's capture session, including administrative capture access.

Migration `0007_saved_destinations` adds the table. Run `alembic upgrade head` before restarting an existing backend; Docker startup also applies it automatically. Saved-coordinate routing requires a valid `GOOGLE_ROUTES_API_KEY` or the existing Places key with Routes enabled; it can work without a Places search key when a separate Routes key is configured. Deleting an entry does not erase previously retained route answers or their context; normal conversation expiry/deletion applies to those records.
