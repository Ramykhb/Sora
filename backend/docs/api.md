# Client contract

All HTTP data endpoints start with `/api/v1` and require `Authorization: Bearer <access_token>` from `POST /auth/login`. Register first at `POST /auth/register`. See [authentication.md](authentication.md) for the complete account, token refresh, logout, recovery and administrator API. Regular users only access their own capture sessions; administrators can inspect all. Cross-user resource requests return 404. HTTP response headers include request ID and duration. `/health` is public liveness; `/ready` requires an administrator. OpenAPI: `/docs` and `/openapi.json`.

## Sessions and images

- `POST /sessions`: JSON `{"consent":true,"language":"en","alerts_enabled":false}`. Returns persisted `id` and expiry.
- `GET /sessions`: paginated sessions; `GET/PATCH/DELETE /sessions/{id}` for details, language/alert preference changes and full deletion.
- `POST /sessions/{id}/close`: stop capture but keep retained memory until expiry.
- `POST /sessions/{id}/frames`: multipart `image`, optional `force` and timezone-aware `captured_at`. Returns `status=stored` plus frame, or `status=rejected` with `too_dark`, `too_blurry`, `duplicate`, or `uninformative`. Force is intended for controlled tests, not the live camera.
- `GET /sessions/{id}/frames`: newest-first timeline, optional `since`, `until`, `limit` (1–200), `offset`.
- `GET /sessions/{id}/frames/search?q=...`: semantic plus lexical memory search; optional time range and limit.
- `GET /sessions/{id}/frames/{frame_id}`: metadata. `/image` returns processed JPEG; `?original=true` returns sanitized pre-enhancement JPEG. Both require authentication.
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

## Live camera and events

`POST /sessions/{id}/stream/offer` takes `{"type":"offer","sdp":"..."}` and returns the server SDP answer. Client must include a sending video track and wait for ICE gathering to complete before POSTing (non-trickle ICE). Retrieve ICE configuration at `/stream/config`. Configure a reachable TURN server for clients separated by NAT or container networking.

`GET /sessions/{id}/stream/live.mjpeg` returns a multipart JPEG live preview (about 5 fps), independent of the lower-rate saved frames. Because ordinary HTML image elements cannot attach API headers, dashboard clients should fetch this stream with headers and render/decode the frames. `/stream/status` returns received/stored/rejected/dropped counts and processing errors. `DELETE /stream` disconnects the producer. The backend allows one producer per session and closes idle producers after 60 seconds.

For a simple camera integration, connect a WebSocket to `/api/v1/sessions/{id}/stream/frames`, send `{"access_token":"..."}` as the first text message within 5 seconds, wait for `type=ready`, then send binary JPEG frames at about 5 fps. Do not send a filename or a Base64 string. The server samples according to `SAMPLE_INTERVAL_SECONDS`; a queue of one keeps the newest frame when processing falls behind.

Connect another WebSocket to `/api/v1/sessions/{id}/events` and authenticate with the same first message. Events: ready, heartbeat, stream_started, stream_stopped, frame_stored, frame_rejected, processing_error, question_answered, alert, session_updated. `session_updated` carries the full session after a language/alert change or capture closure so connected devices can update their controls. Browser Origin must be in `CORS_ORIGINS`. Tokens never go in URLs. Authentication is rechecked during streaming; refresh and reconnect when tokens expire or rotate.

## Dashboard and operations

- `GET /dashboard`: owner-scoped session counts and live status (all for administrators).
- Timeline: frames endpoint above. History: questions endpoint above. Preview: MJPEG endpoint above.
- `GET /sessions/{id}/alerts`: stored warnings; speak a received warning using native TTS or `/speech/synthesis`.
- `GET /metrics`: owner-scoped retained frame/question totals, average timings, feedback counts, pending deletions and live connections.
- `POST /maintenance/cleanup`: administrator-only force expiry cleanup; also runs automatically every minute.
- `POST /maintenance/reconcile`: administrator-only removal of old unreferenced image objects after failed uploads; also runs hourly.

Most dependency failures use `{"error":{"code":"...","message":"..."}}` with 503. Invalid input is 422, byte/pixel/duration limits are 413, authentication is 401, missing/expired resources are 404, closed/conflicting sessions are 409 and capacity exhaustion is 429. Validation errors use a `detail` list with location, message and type; input values are omitted to avoid exposing secrets. Caption or embedding failures produce a stored frame with explicit warnings and OCR/object/lexical fallback; failed OCR or YOLO inference returns an error instead of an empty invented result. When the answer model is unavailable, the backend stores an uncertain response with a warning.

The dashboard requests `own_only=true` on `/sessions`, `/dashboard` and `/metrics` so even administrator accounts see only their own mobile sessions in this workspace. Omitting it preserves administrator-wide visibility. Maintenance and user-management controls remain explicitly administrator-only.
