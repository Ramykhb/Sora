# Sora — a voice assistant with visual memory

Multimedia Database and Image Processing, Fall 2026/2027. An iPhone/Android camera streams live video to a server. The server detects supported objects, selects and enhances useful frames, reads text, stores searchable visual memory, and answers spoken questions from retained camera evidence. A web dashboard shares live video, timeline, search, conversations and feedback with the phone account.

This assistant describes observations and uncertainty. It does not establish that a walking route is clear or replace a white cane or guide dog. Detected faces are blurred in saved images; there is no face recognition. Start capture only with consenting participants; selected frames expire after 24 hours by default and can be deleted sooner. Raw camera video and uploaded voice recordings are not retained by the server.

## Run the whole application

Requirements: Docker Desktop, Node.js 22.12 or newer, Python 3 for local configuration, and an installed Expo SDK 58 development app containing WebRTC. Model preparation needs several GB of downloads and disk space. Keep the phone and computer on the same Wi-Fi.

From this repository, using the computer's current LAN address:

```sh
python3 backend/scripts/configure_local.py --host 192.168.0.102
docker compose -f backend/docker-compose.yml --profile app --profile webrtc up -d --build
docker compose -f backend/docker-compose.yml exec api python -m scripts.prepare_models
```

The configuration helper generates local secrets, preserves existing credentials, and updates networking. Replace the example IP with your own. `backend/.env` and `mobile/.env.local` are private local files. If the address changes, run the helper again and recreate API/TURN with `docker compose -f backend/docker-compose.yml --profile app --profile webrtc up -d api turn`.

In another terminal:

```sh
cd dashboard
npm ci
npm run dev
```

Open [the dashboard](http://localhost:5173). Register an account. Then, in another terminal:

```sh
cd mobile
npm ci
npm start -- --dev-client --host lan
```

Open the installed development app and connect to this Metro server. Sign in with the same account as the dashboard. Before signing in, **Change server** to `http://YOUR_LAN_IP:8000`; a saved phone setting overrides the build's environment default. Allow local-network, camera and microphone permissions. Enable spoken answers and optional obstacle alerts, consent, then start a session. The dashboard automatically follows your live session. Turn off iPhone silent mode for native text-to-speech.

No new native module was added by the live-alert changes. Existing SDK 58 development clients with WebRTC can load the updated JavaScript from Metro. An app with an embedded bundle needs a fresh build/update to receive JavaScript changes; see [mobile setup](mobile/README.md). Expo Go cannot run this project's native WebRTC publisher.

Check [backend health](http://localhost:8000/health). The [API explorer](http://localhost:8000/docs) documents authenticated requests. Database, images and model weights use named volumes. Stop with `docker compose -f backend/docker-compose.yml --profile app --profile webrtc stop`; do not remove volumes to troubleshoot startup.

## How the implementation matches the project

| Requirement | Implementation |
| --- | --- |
| Phone camera streams to server and web dashboard | WebRTC publisher, aiortc unbuffered relay and receive-only browser viewer |
| Sharp, new, informative frames | Sharpness/brightness checks, perceptual-hash deduplication and sampled memory frames |
| Image processing and OCR | CLAHE, denoising, sharpening, Tesseract English/French/Arabic |
| Objects, text and time in a multimedia database | YOLO boxes/labels, OCR, captions, timestamps, PostgreSQL/pgvector and RustFS image objects |
| Time and meaning search | Time filters plus semantic and lexical retrieval; objects/OCR remain available when captions are deferred |
| Voice question and grounded spoken answer | Whisper → evidence retrieval → Qwen VLM → native speech or eSpeak WAV |
| At least two languages | English, French and Arabic paths; English and French form the primary speech demo |
| Accessible phone and web UI | Labeled controls, screen-reader states, voice input/output, explicit errors and interruptible alerts |
| Status, timeline and past conversations | Shared authenticated dashboard, live events, image library and answer feedback |
| Privacy and uncertainty | Explicit consent, ownership, expiry/deletion, no face recognition, grounded evidence IDs and stale-view checks |
| Bonus unsolicited warnings | Independent live detection and opt-in central-object alerts; no generative model on the live alert path |

Object alerts and visual memory run independently. The live detector uses a newest-only queue, bounded inference resolution and fresh-observation deadlines. OCR or object-storage delays do not hold up live notifications. Memory is sampled separately. Each session admits at most two pending expensive descriptions plus an in-progress description; superseded frames keep their objects/OCR and remain searchable. User inference requests precede queued background work. Ollama is capped at two CPU cores; the detector also uses two inference threads.

Explicit text-reading questions use retained OCR as grounded model input, avoiding another image-encoding pass. Questions about appearance or position still include actual images. Multiple retrieved views share a bounded, numbered contact sheet with frame IDs and full-resolution OCR in the context. A current-view question saves a fresh received snapshot when streaming, so duplicate filtering cannot indefinitely leave only an old view. Current-view retrieval selects the latest retained frame and avoids query embeddings; old evidence is rejected before and after inference.

Simple current-view questions such as “What is in front of me?” use a qualified overview of supported detector labels directly, without OCR or generative inference. The matching source image is retained as evidence through a separate object-only save that does not wait for memory OCR. English, French and Arabic overviews admit that other objects may be missed; no detections never establishes a clear route. Detailed current-view questions have an eight-second processing budget, including snapshot work and the model queue; a timeout returns uncertainty instead of waiting for stale evidence. Memory questions retain the full model path.

Walking questions such as “Is it safe to walk?” also use the immediate detector path. They describe supported objects and their left/center/right positions in the camera image, prioritize objects in the center, and explicitly state that route conditions cannot be confirmed. They always require current evidence (two-second default), even if Memory is selected. A missing detection never means the path is clear; steps, drop-offs, transparent obstacles and hazards outside the image are not reliably covered by this detector.

The prepared 80-class detector does not include doors or stairs. Closed-door interpretation is a best-effort VLM memory feature and is not promised as an immediate warning. Detection confidence/box area are not distance estimates. Full generative descriptions can remain slow under the CPU cap; the live objects panel and alerts do not wait for them.

## Verification and demo

See [verification results and limits](backend/docs/validation.md), [the presentation](docs/presentation.html), [the original audit](backend/docs/requirements-performance-audit.md), [API contracts](backend/docs/api.md), and [network/environment configuration](backend/docs/environment.md).

```sh
cd mobile
npm test
npm run typecheck
npm run lint
# In dashboard: npm test && npm run build
# In backend with requirements-dev.txt installed: python -m pytest -q
```

The real-service acceptance flow creates its own temporary account, generates two signs without people, verifies WebRTC publishing/viewing, OCR, inference, semantic retrieval, English/French answers, WAV speech, speech recognition, history, feedback and deletion. It deletes its own test account/session and reports failures explicitly:

```sh
docker compose -f backend/docker-compose.yml exec api python -m scripts.acceptance --output /tmp/acceptance-report.json
docker cp backend-api-1:/tmp/acceptance-report.json backend/docs/acceptance-report.json
```

Synthetic acceptance checks do not establish real-world answer accuracy or obstacle recall. Use [the dataset evaluation tool](backend/scripts/README.md) with consented scenes and human feedback. [The demo checklist](docs/demo.md) includes physical-phone accessibility and speech-latency checks.
