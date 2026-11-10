# Current validation — 2026-11-02

The implementation was checked against the three-page Fall 2026/2027 project brief. Team attribution is omitted at the user's request. See the root README for the requirement mapping and `docs/presentation.html` for the presentation.

- **131 backend tests pass**, with Ruff checks. Coverage includes live alerts while OCR/storage are blocked, bounded queues, fresh/stale snapshots, current-view retrieval without embeddings, English/French/Arabic OCR-question routing, numbered visual evidence, model priority/cancellation, ownership, speech contracts and retention/deletion. Server tests use SQLite/local objects and deterministic model substitutes, with actual Tesseract sign checks and aiortc transport tests.
- **18 mobile tests pass**, plus typecheck, lint and an iOS Hermes JavaScript export. **15 dashboard tests pass**, plus the production build. These are distinct from native installation and physical-phone accessibility checks.
- Docker Compose configuration validates; the running PostgreSQL database is at `0004_live_alerts`. Ollama's container limit is `2,000,000,000` NanoCPUs (two cores), verified at runtime. During inference it used approximately 199% CPU rather than the previously reported 1050%. The detector uses two PyTorch threads and 320-pixel inference resolution.

## Real-service acceptance run

### Current-view latency correction

A physical-phone report of `evidence_expired_during_inference` exposed the practical failure of putting a general object-overview question through the VLM: Ollama logs showed approximately 50 seconds for one image, exceeding the 15-second freshness limit. The freshness guard was working, but the answer path was too slow.

Simple current-view object questions now use translated detector labels with explicit uncertainty, retaining the exact detected source image as evidence. This path bypasses OCR, memory-processing locks and Ollama. Detailed current-view requests now have an eight-second processing budget, including snapshot work and model-queue waits; timeout produces an explicit uncertain response. Memory questions retain full generative inference. The CPU cap and evidence freshness checks remain enabled.

A follow-up report exposed overly narrow wording matching: the actual text requests `what object is in front of me` and `what us in front of me?` still entered the VLM path. The overview matcher now accepts natural generic-object wording, polite wrappers and this common `is`/`us` typo while excluding text-reading and visual-attribute questions. Regression tests exercise both exact user requests with the OCR lock and model gate held busy.

Both exact requests also passed against the running WebRTC/API stack, returning in **57.3 ms** and **60.7 ms**, respectively, with retained evidence and no warnings. See the [wording regression report](live-overview-wording-report.json). As in the other targeted test, the generated sign has no supported objects; this verifies routing and latency, not obstacle recall or iPhone speech onset.

Walking questions originally still reached generative inference and timed out. They now use the detector path directly, prioritize central detections and describe left/center/right locations in the camera image, followed by explicit route uncertainty. They require evidence within two seconds by default, even when Memory is selected. The exact question `is it safe to walk` passed the [real-service walking check](live-walking-report.json) in **58.1 ms**, with retained evidence and no warnings. The person-free synthetic sign has no supported objects, so the response correctly reported no detections without declaring a clear route. Regression tests verify chair/left/center/right output, English/French/Arabic wording, no model/OCR wait, and rejection of a five-second-old frame for a walking request. These checks do not validate real-world navigation or obstacle recall.

The [targeted real-service report](live-overview-report.json) passed: a continuous WebRTC viewer received 92 frames over approximately three seconds, then “What is in front of me?” returned in **88.2 ms** with retained evidence and no warnings. An earlier targeted run took 30 ms. This uses a generated sign with no supported objects and does not measure obstacle recall or phone-to-speech latency. The regression test separately supplies a chair detection and holds both the OCR session lock and generative-model gate busy, verifying that the qualified answer still completes and cites its image. Multilingual label/intent tests, no-detection uncertainty and detailed-request timeout/cancellation tests also pass.

### Full workflow before the latency correction

The checked-in [acceptance report](acceptance-report.json), started at 10:54 UTC on November 2, passed using the running API, PostgreSQL/pgvector, RustFS, YOLO, Tesseract, Whisper, Ollama and eSpeak. The script created its own temporary account, generated person-free signs and deleted its account/session afterward.

| Check | Observed result |
| --- | --- |
| Live publisher → server → viewer | 92 viewer frames in 3.04 seconds; no detection/processing error |
| Server receipt → object observation | Nine sampled observations: 43–140 ms, median 65.1 ms |
| Current-view text question during stationary live video | `EXIT 123`, fresh retained evidence, no warnings, 3.85 seconds |
| OCR | Both generated signs correctly read: `EXIT 123`, `ROOM 215` |
| Semantic memory search | Expected sign present in top three for both queries |
| English/French memory answers | Both returned `215`, cited evidence, no warnings; answer times 7.79 / 7.75 seconds |
| Speech output | Valid English and French WAV files generated |
| Voice input | Whisper transcription and a grounded-answer request completed; see accuracy limitation below |
| History, feedback and deletion | Four questions, automated `unsure` feedback, session deletion and temporary-account deletion passed |

These are small synthetic functional checks, not representative accuracy percentages. The latest voice transcription was imperfect (`What's up but what's written after room?`) and its answer was incorrect (`The word 'up' is written after 'room'.`). The preceding run answered the same synthesized utterance correctly. This is a real remaining model-quality limitation: successful transport and valid evidence IDs do not prove that an answer is factually grounded. Human feedback is explicitly recorded as `unsure`, not invented tester approval. English/French text-question term matches were 2/2 in this run; that is not a general answer-accuracy score.

The final run's forced synchronous image uploads took 51.47 and 2.05 seconds including full VLM enrichment. The first includes contention with background inference after the live question. General visual answers using a contact sheet took approximately 61–63 seconds in an earlier successful run at the same CPU cap. Explicit OCR-reading questions avoid that image encoding work. Real live memory saving defers VLM enrichment; immediate labels/alerts do not wait for captions, OCR or storage.

An earlier real run exposed unreadable bordered signs; an OCR-only line-removal fallback fixed both generated signs. Another run exposed a multi-image VLM timeout; a bounded numbered contact sheet resolved the timeout. The report and tests retain the distinction between live detection, saved memory, and slow full visual interpretation.

## Practical limits

- Server observation timing excludes phone capture, network delay and audible speech onset. Synthetic signs contain no supported obstacle, so these timings do not measure obstacle recall. The 80-class detector does not include doors/stairs; closed-door VLM interpretation is best effort and can arrive too late for a fresh alert.
- Camera freshness is based on server receipt timestamps. Current-view questions can save a newly received snapshot even when the scene was deduplicated; old stored timestamps are never refreshed. Evidence that ages beyond the configured window during inference produces uncertainty.
- Xcode's signed Release build succeeded and the update was installed over `com.ramykhachab.mobile` on the connected physical iPhone 16. The embedded Hermes bundle contains the new Live objects panel and current LAN API address. The app launched, restored the existing sign-in and displayed its retained session; Metro was then stopped and the app relaunched. Native camera/microphone, VoiceOver, audio interruption and camera-to-speech latency still require device interaction and representative consented scenes. Human correctness/usefulness ratings remain necessary; use `docs/demo.md` and `scripts.evaluate`.
- Real SMTP delivery is not exercised by the synthetic acceptance flow.

## Historical validation — 2026-10-29

- 75 backend tests pass in Docker, including real local aiortc producer/viewer peers, continuous video delivery, one-second sampling, connection cleanup, account isolation, temporary TURN credentials and durable background enrichment. SQLite/local storage and model substitutes are used for server-logic tests.
- A separate smoke test used actual TURN-only ICE candidates through the running Docker/LAN relay: the viewer received **68 video frames in 2.2 seconds**, while the backend sampled **2 images**. Test media was not stored. This validates the relay path independently of JPEG previews.
- Three real warmed fast saves using OCR, YOLO, PostgreSQL and object storage measured 479/396/405 ms (427 ms average) on one retained sample. Full AI descriptions remain slower and finish afterward; a real background run successfully populated both caption and embedding. These measurements do not establish general model quality or a latency guarantee for every scene.
- Dashboard: 13 client tests and production build pass. Mobile: 8 client tests, lint, typecheck, Expo iOS prebuild and iOS JavaScript bundle export pass. Physical iPhone compilation/installation and camera testing still require native dependencies and an available development device.

The notes below describe earlier validation runs and their limitations at the time.

## Implementation validation — 2026-10-25

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

### Gemini current-view path — 2026-11-04

- 173 backend tests passed with cloud credentials mocked and explicitly disabled outside the cloud tests. Tests cover a redacted retained image, key-free error responses, structured output, provider failure/deadline fallback, identity-request exclusion, local memory queries, and walking-answer guards. Lint passed.
- With the configured private key, one generated `EXIT 123` image request to Gemini 3.5 Flash-Lite returned the correct text in 3.18 seconds. The first complete pipeline probe hit its former four-second cloud allocation and returned local detection in 4.04 seconds. The allocation now reserves 0.5 seconds of the five-second analysis deadline for fallback. A warmed complete pipeline probe then returned the correct text with one retained evidence ID in 1.59 seconds. Temporary probe sessions, questions, and images were deleted.
- These are individual synthetic checks, not real-world accuracy, hazard recall or a latency guarantee. Actual network/provider load, image preparation, frame age, database work and phone speech timing vary. Walking evidence still expires after two seconds; a slow cloud walking response must fall back or report unavailable recent evidence.

### 720p live playback — 2026-11-10

- A moving 1280×720 photograph passed through the running Docker API and TURN with both media legs restricted to relay candidates. After 60 warm-up frames, three five-second windows measured **29.98, 30.02 and 30.09 fps** at the decoded viewer. The API reported **30.0 received fps** throughout. Real background detection/storage/enrichment remained enabled. The temporary benchmark account and sessions were removed.
- Reproduce with `python -m scripts.benchmark_stream --url http://localhost:8000 --relay-only --image tests/fixtures/astronaut.jpg`. This test measures two aiortc clients, API and relay; physical phone capture/Wi-Fi and browser rendering still require a device check. The dashboard now exposes actual playback fps/resolution for that check.
- Regression coverage verifies media-clock limiting under arrival jitter, bounded burst buffering, independent frame storage, subscriber shutdown, H.264 negotiation and 720p continuous playback. The integration tests also preserve 1080p source detail while producing a 720p preview.
- **177 backend tests, 79 mobile tests and 18 dashboard tests passed**. Backend Ruff, mobile lint/type checking, dashboard production build and Git whitespace checks passed. Backend tests ran in the Docker test environment with `YOLO_MODEL=/app/models/yolo11n.pt`; cloud responses were mocked in the test suite.

### Physical iPhone verification — 2026-11-10

- The first physical-phone check still received 1080×1920 at roughly 1–3 fps. The standalone installed app had not loaded the modified JavaScript; running Metro did not update its embedded bundle. A new Release build was compiled and installed on the paired iPhone 16.
- The updated app's `720p30-v2` telemetry confirmed a 1280×720 camera source at 30 fps, VideoToolbox H.264 encoding, and portrait output of 720×1280 at 30 fps. The backend measured approximately 29–30 fps, with no reported RTP packet loss, and the user confirmed **720×1280 at about 30 fps on the dashboard**.
- WebRTC initially reduced resolution while its bandwidth estimate ramped from roughly 0.3 Mbps; resolution can still adapt during motion or congestion. This is a confirmed live device run, not a guarantee for every network/thermal condition.
- Added filtered publisher diagnostics for camera fps, encoded fps/resolution, encoder implementation, quality-limitation reason and bandwidth estimate, plus periodic backend receive/viewer transport metrics. Network addresses and credentials are excluded from publisher diagnostics. Mobile lint, type checking and all **80 mobile tests** passed; **23 focused backend API/relay/preview tests** passed.

### PaddleOCR model preparation — 2026-11-10

- Downloaded official PP-OCRv5 mobile detection, English recognition, Latin/French recognition and Arabic recognition models (27.9 MiB total). Files and SHA-256 manifest are retained in the project model directory and the Docker model volume.
- Installed PaddleOCR 3.7.0 with PaddlePaddle 3.2.2 in an isolated Python environment inside the Linux ARM64 API container. The environment occupies approximately 743 MiB and does not replace the API's dependencies or active Tesseract engine.
- A local CPU smoke check detected the generated text and correctly recognized `EXIT 123`, `Entrée principale` and `مخرج 123`. Warm recognition measurements were 37.0, 37.1 and 36.8 ms respectively; detector inference was 12.0 ms, using two CPU threads. These are clean generated single-line examples, not camera-image accuracy or full-frame end-to-end latency measurements.

### Active PaddleOCR pipeline — 2026-11-10

- Switched the default/live API OCR engine to PaddleOCR. The API preloads a persistent local CPU worker, sends only prepared face-redacted pixels, detects/crops text, recognizes requested languages, and returns confidence-filtered regions in reading order. The isolated runtime keeps Paddle's dependencies separate from the API/video stack. Inference and queue waits have a shared deadline; a stuck worker is terminated and recreated on the next request. Tesseract requires explicit selection with `OCR_ENGINE=tesseract`.
- Through the running API's authenticated JPEG stream → detection/privacy preparation → OCR → storage → frame retrieval path, generated English `EXIT 123`, French `Entrée principale` and Arabic `مخرج 123` were correctly stored. Frame processing measured 288, 187 and 304 ms respectively; polling observed the stored frames after approximately 444, 444 and 650 ms. The temporary account, sessions and test images were deleted. These are generated sample checks, not real-world accuracy benchmarks.
- All **188 backend tests** and Ruff/whitespace checks passed, including worker reuse/shutdown, timeout/recovery, language selection, reading order, confidence filtering, image preservation and existing privacy/authorization behavior.

### OCR timeout recovery and dense frames — 2026-11-10

- Reproduced a restart loop on saved camera frames: model initialization took about 3.7 seconds and was incorrectly charged to each replacement worker's four-second frame deadline. Replacement startup now has the same separate 45-second allowance as initial warmup, including representative detector and recognizer inference before READY.
- A dense frame contained 36 regions; recognizing all regions in both script models took more than four seconds. Recognition now prioritizes larger regions, uses batches of two and estimates remaining batch time. Completed text is retained with `ocr_partial` when the frame budget is exhausted. An empty partial result remains an explicit failure to check text and does not discard the loaded models. True stuck inference still terminates the worker.
- Replayed eight formerly timed-out saved frames locally without a hard timeout. Warm processing ranged from approximately 429 to 3536 ms; an intentionally killed worker recovered in 4461 ms including model reload. Three dense frames preserved partial text. A generated 78-line image also passed through the running authenticated stream/storage API with recognized text and `ocr_partial`; the temporary account and images were deleted. The user confirmed newly saved live frames no longer time out.
- The 193-test backend suite, all 12 focused PaddleOCR regression tests (including an additional recovery case), 19 dashboard tests, production dashboard build and Ruff/whitespace checks passed. Dashboard details now distinguish timeout/busy/unavailable results from successful no-text results and explain partial OCR. Existing failed frame records are not rewritten.
