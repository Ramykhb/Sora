# Requirements and live-response audit — 2 November 2026

## Scope and conclusion

Reviewed the supplied three-page project PDF and traced the mobile camera, WebRTC server receiver, frame selection, OCR, YOLO detection, image persistence, caption/embedding worker, retrieval, question answering, alert generation, mobile speech, dashboard live view, retention, evaluation scripts and relevant tests. This is a functional and performance audit, not an exhaustive security or accessibility certification.

The project has implementations for most required features. Its current architecture does not meet the user's additional requirement for immediate obstacle warnings. The roughly 30-second description delay is real, but object detection and generative descriptions are different operations. The live pipeline already defers captions; the remaining problem is that alerts still depend on the selected-frame persistence pipeline, and doors depend on generative inference.

## What the PDF requires

The PDF requires live phone video, useful-frame selection, OCR and objects, a searchable multimedia database with time and meaning, spoken questions and grounded spoken answers, at least two languages, an accessible mobile app, and a dashboard with live device video, status, timeline and question history. It prohibits face recognition and assurances of walking safety, requires uncertainty and consenting testers, and calls for data minimization and deletion. Deliverables include code/README, presentation, speed/search/accuracy/feedback results and team responsibilities.

Unsolicited warnings such as a closed door are a bonus. The PDF specifies no numerical latency, detection frame rate, distance accuracy or immediate obstacle-warning guarantee. Immediate warnings are an additional product goal stated by the user, not a quoted grading requirement.

| Requirement | Current implementation | Assessment |
| --- | --- | --- |
| Live phone video and dashboard playback | Native WebRTC camera, aiortc relay, browser receive-only peer | Present in code; this audit did not exercise the physical phone |
| Useful-frame selection | Brightness/sharpness thresholds and perceptual-hash deduplication | Present; fast deferred path saves even frames without OCR or objects, pending later interpretation |
| Image preprocessing | CLAHE, denoising and unsharp mask | Present; enhancement cannot recover missing visual information |
| OCR and objects | Tesseract with three language packs; YOLO labels, confidence and boxes | Present; OCR runs before detection and can prevent detection on error |
| Multimedia memory and search | PostgreSQL/pgvector, object storage, timestamps, semantic and lexical retrieval | Present; semantic indexing waits for enrichment |
| Spoken questions/answers | Whisper, grounded VLM answer, native speech and server WAV | Present; inference latency and stale-evidence checks conflict for current-view questions |
| At least two languages | English, French and Arabic contracts and processing paths | Present; real recognition/answer quality needs a multilingual evaluation |
| Dashboard status/timeline/history | Authenticated shared session and live events | Present |
| Uncertainty and no safety assurances | Prompt restrictions, evidence IDs, localized answer filters, freshness checks | Present; automated guards do not establish factual reliability |
| Consent and deletion | Required consent flag, session/frame expiry, deletion outbox and cleanup | Present; tester consent is also an operational responsibility |
| Accessible mobile application | Voice I/O and labeled controls in parts of the UI | Partial evidence; needs VoiceOver testing and clearer urgent-alert behavior |
| Proactive obstacle warnings (bonus) | Large central-object heuristic; VLM closed-door flag | Present as a limited feature; unsuitable for immediate generalized obstacle warnings |
| Evaluation deliverables | Evaluation CLI, example manifest, feedback API, historical validation notes | Infrastructure exists; no complete current consented-dataset report or presentation/team-responsibility artifact was found in the searched project files |

## Measurements from the running deployment

Read-only database snapshot before applying the CPU limit:

| Metric | Observed |
| --- | --- |
| Retained frames | 10 |
| Pending enrichment | 6 |
| Initial processing mean / p95 | 557.2 ms / 862.3 ms |
| Completed enrichment mean / maximum | 29,130.9 ms / 34,079.9 ms |
| Retained alerts / questions | 0 / 0 |
| Live sample interval | 1 second |
| Fresh-evidence window | 15 seconds |
| Vision / embedding runtime | Both reported 100% CPU by `ollama ps` |

Initial `processing_ms` starts after acquiring the session lock and is assigned before database commit and alert publication. It excludes network transport, queue/lock waiting and phone speech onset. `enrichment_ms` includes the enrichment operation, including model-gate waiting, but excludes the frame's earlier wait in the pending database queue. Neither is complete camera-to-alert latency.

A separate API-container process read one existing 360×640 image without changing stored data. Three OCR runs took 564.2 / 339.6 / 378.1 ms. YOLO took 7,787.4 ms on its first run and 670.7 / 776.1 ms on the next two. The API itself already warms its detector at startup; the separate process's first-run number is not the normal warmed API latency. This tiny sample is diagnostic, not a general performance benchmark. All ten snapshot frames had zero detected objects; this alone does not establish a detector fault or scene-level accuracy.

The loaded detector exposes 80 classes and no `door` or `stairs` class. No new model downloads or external image transfers were used for the audit.

## Findings in priority order

1. **Alerts wait for memory work.** `app/services/frames/ingestion.py` rejects/deduplicates the image, runs OCR then detection, uploads two images, commits the frame and only then invokes `generate_alert`. Duplicate frames never reach alert detection. An OCR error or storage failure prevents an alert even when an object could be detected. `streams.consume` shares this ingestion path. A separate live detector must run independently of memory selection, OCR and storage availability.

2. **Closed-door warnings cannot keep up with observed inference.** `app/workers/enrichment.py` derives the closed-door flag from `models.describe`, then waits for embedding and frame update before considering an alert. It permits that alert only within the 15-second evidence window. A roughly 29-second enrichment therefore suppresses the warning for that frame. The freshness protection is appropriate; widening it would allow old observations to be announced as current. Door state needs a suitable fast detector/classifier if it remains a promised live warning.

3. **The durable caption backlog has no admission bound besides expiry.** The live input queue holds one waiting sample and replaces old waiting samples, but every accepted deferred frame becomes pending database work. The enrichment loop processes the oldest pending frame across sessions, one at a time. At one retained frame per second versus one enrichment per roughly 29 seconds, sustained admission exceeds service capacity by about 29×. Deduplication can reduce admission, but movement introduces novelty. Six pending frames were observed. Cap expensive enrichment admission, choose representative keyframes and prioritize current/on-demand work; preserve the required useful visual memory separately.

4. **Interactive questions compete with background descriptions.** `app/services/ai/models.py` uses one semaphore for both captioning and answers. A user can wait for the background call before their own inference starts; the HTTP model timeout starts after acquiring the semaphore. Query embeddings add another step. The recent-answer path in `app/services/ai/assistant.py` rechecks evidence against 15 seconds after inference. Slow answers can thus be correctly discarded as stale. There were no stored questions in the snapshot, so this is a code-path finding, not an observed question benchmark.

5. **Current obstacle logic is a limited image heuristic.** `app/services/alerts.py` accepts only ten object labels, a horizontal center between 30% and 70%, and at least 15% image area. It cannot infer physical distance, free space, route geometry or all obstacle types. The 30-second per-label cooldown can suppress a different object of the same class. It publishes at most one alert per stored frame. Use explicit class coverage, tracked observations, freshness and repeat policies instead of treating large boxes as a complete obstacle system.

6. **Sampling adds latency before processing begins.** Live analysis samples every second even though the phone requests 15 video fps. An object appearing just after sampling can wait nearly a second before analysis. Raising the rate on the existing OCR/storage path would add load without fixing its dependencies. A separate latest-frame detector should use a measured rate that the hardware can sustain.

7. **The phone does not prioritize urgent speech.** In `mobile/src/app/index.tsx`, an alert calls `Speech.speak` without stopping an existing answer; answer playback does call `Speech.stop`. Alert events have no capture timestamp or validity deadline for the client to check. Add speech priority, expiry checks and deduplication, and verify actual speech onset on the iPhone. The main scene card displays captions/OCR but not the already available object labels, making a saved detection look unfinished until its slow caption arrives.

8. **Current tests do not establish real-time performance.** Backend fixtures substitute OCR/detection and VLM results, disable automatic enrichment, and drive it explicitly. Existing tests are useful functional checks, but do not measure alert latency during slow OCR, storage outages, duplicate views, caption backlogs or speech already playing. The evaluation CLI uploads frames synchronously and measures memory questions; it does not measure live camera-to-alert speech onset.

## Architecture to implement

Keep the existing WebRTC video relay and split processing into independent consumers:

```text
Live camera
  ├─ Latest-frame detector → fresh object observations → priority phone alert
  └─ Useful memory frames → OCR + storage → bounded caption/embedding work
                                               └─ retrieved evidence → spoken Q&A
```

The live path must avoid generative inference, OCR, object uploads and database commits before notification. Persist alert history asynchronously, with bounded retry handling. Use a separate latest-only queue, session authorization/consent checks and cancellation on pause/disconnect. Expire observations before speaking them; distinguish observations from unsupported statements about route safety.

Treat below-one-second p95 camera-to-speech onset as a proposed initial acceptance target for the agreed supported classes, not an achieved guarantee. The current measurements do not establish this target. If a stricter target is needed or network independence is essential, prototype and benchmark local phone inference before committing to it. Native model integration would require compatibility checks and an updated development binary. Door and stairs coverage requires separately validated models/data; changing a label list cannot add model capabilities.

Prioritize: independent live detector; freshness/priority speech; bounded enrichment admission; interactive model scheduling; object-label UI; then model/runtime speed tuning and multilingual quality evaluation. Do not increase the stale-evidence window or run several expensive caption workers merely to hide the backlog.

## CPU mitigation applied during the audit

At the user's request, `docker-compose.yml` now limits the Ollama container to two CPU cores using `cpus: 2.0`. This limits aggregate container CPU time; Docker's percentage display can fluctuate around 200%. It does not cap the API container's YOLO/OCR/Whisper work or guarantee temperature. Recreating Ollama can interrupt an active model call; descriptions can become slower under the cap. The measurements above predate the cap and must not be reused as post-cap performance results.

## Verification and limits

- Mobile client tests: 15 passed. Dashboard client tests: 13 passed.
- Mobile lint and typecheck passed earlier in this diagnostic session.
- The attempted local backend test run could not load its test configuration because the available environment lacks FastAPI. No backend-suite pass is claimed for this audit.
- No physical iPhone obstacle/speech timing, recall, false-positive rate, multilingual answer-quality or temperature measurement was performed.
- No application inference or alert behavior was changed as part of this review. The CPU resource limit is the performance-related runtime change; earlier network fixes remain separate.
