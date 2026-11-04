# Client contract

All HTTP data endpoints start with `/api/v1` and require `Authorization: Bearer <access_token>` from `POST /auth/login`. Register first at `POST /auth/register`. See [authentication.md](authentication.md) for the complete account, token refresh, logout, recovery and administrator API. Regular users only access their own capture sessions; administrators can inspect all. Cross-user resource requests return 404. HTTP response headers include request ID and duration. `/health` is public liveness; `/ready` requires an administrator. OpenAPI: `/docs` and `/openapi.json`.

## Sessions and images

- `POST /sessions`: JSON `{"consent":true,"language":"en","alerts_enabled":false}`. Returns persisted `id` and expiry.
- `GET /sessions`: paginated sessions; `GET/PATCH/DELETE /sessions/{id}` for details, language/alert preference changes and full deletion.
- `POST /sessions/{id}/close`: stop capture but keep retained memory until expiry.
- `POST /sessions/{id}/frames`: multipart `image`, optional `force` and timezone-aware `captured_at`. Returns `status=stored` plus frame, or `status=rejected` with `too_dark`, `too_blurry`, `duplicate`, or `uninformative`. Force is intended for controlled tests, not the live camera.
- `GET /sessions/{id}/frames`: newest-first timeline, optional `since`, `until`, `limit` (1–200), `offset`.
- `GET /sessions/{id}/frames/search?q=...`: semantic plus lexical memory search; optional time range and limit.
- `GET /sessions/{id}/frames/{frame_id}`: metadata. `/image` returns processed JPEG; `?original=true` returns sanitized pre-enhancement JPEG. Both variants have detected faces blurred before storage and require authentication.
- `DELETE /sessions/{id}/frames/{frame_id}`: metadata deletion and object deletion with retry on storage outage.

Do not form public S3 URLs. Images are served through the authenticated API. Input EXIF metadata is removed and originals are resized to the configured limit. Expired records are immediately excluded from reads, even before cleanup runs.

## Questions and speech

- `POST /sessions/{id}/questions`: JSON `question`, optional `language` (en/fr/ar), `scope` (auto/recent/memory), and timezone-aware `since`/`until`. Returns persisted question/answer, uncertainty, evidence IDs, warnings and latency.
- Auto selects recent evidence for current questions and memory for recognized past-tense phrases. Clients should send explicit scope/time bounds for precise historical requests. Recent evidence is at most `RECENT_EVIDENCE_SECONDS` old; memory must never be used as a current view.
- `POST /sessions/{id}/questions/audio`: multipart `audio`, optional `language`, `scope`. Returns the same answer schema and saves the recognized transcript. The uploaded audio is not retained.
- `GET /sessions/{id}/questions`: paginated history. `GET /sessions/{id}/questions/{question_id}`: one record.
- `GET /sessions/{id}/questions/{question_id}/audio`: WAV of that answer.
- `POST /sessions/{id}/questions/{question_id}/feedback`: JSON `rating` (correct/incorrect/unsure), optional notes.
- `POST /speech/transcriptions`: multipart audio and optional language; transcript and detected language.
- `POST /speech/synthesis`: JSON `text`, `language`; WAV response. The mobile client can also use its native TTS.

Current-view questions select the newest retained frame without a semantic embedding request. While streaming, a question can save a fresh received snapshot even when ordinary sampling rejects stationary duplicates. The original timestamps of old frames are never changed. Evidence must still be fresh after inference. Explicit text-reading questions use retained OCR as model context; visual appearance/location questions use actual camera images. Multiple views are combined into one bounded, numbered contact sheet, with panel-to-frame mapping and full-resolution OCR in the context.

Simple current-view object overviews (“What is in front of me?”, including French/Arabic equivalents) use detector labels directly. A matched source image is retained with `enrichment_status=skipped`, objects and no OCR/caption/embedding, independently of the regular memory-processing lock. Answers are explicitly uncertain about detector coverage and cite that image. `CURRENT_ANSWER_TIMEOUT_SECONDS` defaults to 8 and bounds current-view processing, including preprocessing and model-queue waits. Timeout returns an uncertain answer with `current_view_timeout`; evidence freshness checks remain enabled. Memory-scope questions still use generative inference.

Walking/route questions, including “Is it safe to walk?”, “Can I walk forward?” and “Is the path clear?”, also bypass generative inference. They return supported object names and camera-relative left/center/right locations with explicit route uncertainty. These questions force current scope and require evidence within `DETECTION_MAX_AGE_SECONDS` (default two seconds), both before answering and at final evidence validation. Selecting Memory cannot turn an old frame into a current route observation. No response establishes walking/crossing permission or unsupported distance.

## Live camera and events

`GET /sessions/{id}/stream/config` returns ICE servers (including temporary TURN credentials), transport policy and the sampling interval. Native mobile and web publishers attach a sending video track, wait for ICE candidates (the mobile app can proceed once a TURN relay candidate is available), then POST their `{"type":"offer","sdp":"..."}` to `/stream/offer` with bearer authorization. The answer includes `sdp`, `type` and `connection_id`. There is one producer per capture session.

Dashboard clients create a `recvonly` video transceiver, gather ICE and POST their offer to `/stream/viewer/offer`. The backend subscribes them to the producer's video through `MediaRelay` with unbuffered live tracks. They receive continuous RTP video, independently of sampled/saved frames. At most `MAX_STREAM_VIEWERS` viewers (default 8) may join each producer.

Clients POST `/stream/connections/{connection_id}/refresh` every 20 seconds to renew media authorization using the current access token, and DELETE that URL to release their own peer. These endpoints enforce session ownership. Connections are revalidated every second; expiry/revocation, session closure and producer termination close affected media peers. Cleanup uses connection IDs so an old screen cannot close its replacement producer. `DELETE /stream` closes the producer and all viewers.

The backend decodes received video and extracts a JPEG at `DETECTION_INTERVAL_SECONDS` (default **0.25 seconds**). An independent newest-only queue runs bounded-resolution object detection, without OCR, deduplication, storage or generative AI. `observation` events carry `id`, `captured_at`, `expires_at`, `width`, `height`, `detected_objects` and `latency_ms`. These are short-lived observations, not retained frames. Expired results are discarded on the server and client. Detection timings start at server receipt; they exclude capture, upstream transport and speech onset.

Memory is sampled from detected frames at `SAMPLE_INTERVAL_SECONDS` (default **1 second**), reusing the same image's boxes before running OCR/storage independently. `frames_received` counts video frames; `frames_sampled` counts memory samples, and saved/rejected/dropped counters describe the memory queue. `detection_frames_dropped` describes the live queue. Video and live detection continue while memory processing runs. `/stream/status` includes a fresh `observation` or null, `detection_error` and both queue counters.

Legacy integrations may still send binary JPEGs to `/stream/frames` or consume `/stream/preview.jpg` / `/stream/live.mjpeg`. The mobile publisher and dashboard playback use WebRTC rather than these compatibility endpoints. Configure a reachable TURN relay for Docker or NAT; exposing the HTTP API alone does not expose WebRTC media.

By default, live frames are saved after OCR and detection, without waiting for captioning or embeddings. `frame_stored` includes `enrichment_status=pending`; `frame_updated` carries the same frame after background AI work completes or fails. States are `pending`, `processing`, `complete`, `failed`, and `skipped`. Only `MAX_PENDING_ENRICHMENTS` pending descriptions per session are admitted; superseded frames keep their OCR/objects/images with status `skipped`. In-progress inference is allowed to finish. `processing_ms` measures initial processing/storage work; `enrichment_ms` records later AI time, excluding the pending database wait. Clients merge updates by frame ID and retain capture-time ordering. Pending work survives restarts; deleted or expired frames are never recreated. Uploads retain their synchronous behavior. The detector warms up at startup when its prepared weights exist.

Connect another WebSocket to `/api/v1/sessions/{id}/events` and authenticate with the same first message. Events include ready, heartbeat, stream_started, stream_stopped, observation, detection_error, frame_stored, frame_updated, frame_rejected, processing_error, question_answered, alert, alert_history_error, session_updated. Live `alert` events include `id`, `label`, `message`, `language`, `captured_at`, `expires_at`, `latency_ms` and `frame_id=null`; they do not require a stored frame. History persistence runs in a separate bounded queue. Clients must reject expired alerts and interrupt lower-priority speech before speaking a fresh one. Historical alerts must not be replayed as current warnings. `session_updated` carries changed session controls. WebSocket Origin must match the API's own HTTP(S) origin or be in `CORS_ORIGINS`. Tokens never go in URLs. Authentication is rechecked during streaming; refresh and reconnect when tokens expire or rotate.

## Dashboard and operations

- `GET /dashboard`: owner-scoped session counts and live status (all for administrators).
- Timeline: frames endpoint above. History: questions endpoint above. Preview: MJPEG endpoint above.
- `GET /sessions/{id}/alerts`: stored warnings; speak a received warning using native TTS or `/speech/synthesis`.
- `GET /dashboard/statistics` (also available as `/metrics`): owner-scoped retained frame/question totals, average timings, feedback counts, pending deletions and live connections.
- `POST /maintenance/cleanup`: administrator-only force expiry cleanup; also runs automatically every minute.
- `POST /maintenance/reconcile`: administrator-only removal of old unreferenced image objects after failed uploads; also runs hourly.

Most dependency failures use `{"error":{"code":"...","message":"..."}}` with 503. Invalid input is 422, byte/pixel/duration limits are 413, authentication is 401, missing/expired resources are 404, closed/conflicting sessions are 409 and capacity exhaustion is 429. Validation errors use a `detail` list with location, message and type; input values are omitted to avoid exposing secrets. Caption or embedding failures produce a stored frame with explicit warnings and OCR/object/lexical fallback; failed OCR or YOLO inference returns an error instead of an empty invented result. When the answer model is unavailable, the backend stores an uncertain response with a warning.

The dashboard requests `own_only=true` on `/sessions`, `/dashboard` and `/dashboard/statistics` so even administrator accounts see only their own mobile sessions in this workspace. Omitting it preserves administrator-wide visibility. Maintenance and user-management controls remain explicitly administrator-only.
