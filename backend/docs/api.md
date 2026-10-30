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

`GET /sessions/{id}/stream/config` returns ICE servers (including temporary TURN credentials), transport policy and the sampling interval. Native mobile and web publishers attach a sending video track, wait for ICE gathering to finish, then POST their `{"type":"offer","sdp":"..."}` to `/stream/offer` with bearer authorization. The answer includes `sdp`, `type` and `connection_id`. There is one producer per capture session.

Dashboard clients create a `recvonly` video transceiver, gather ICE and POST their offer to `/stream/viewer/offer`. The backend subscribes them to the producer's video through `MediaRelay` with unbuffered live tracks. They receive continuous RTP video, independently of sampled/saved frames. At most `MAX_STREAM_VIEWERS` viewers (default 8) may join each producer.

Clients POST `/stream/connections/{connection_id}/refresh` every 20 seconds to renew media authorization using the current access token, and DELETE that URL to release their own peer. These endpoints enforce session ownership. Connections are revalidated every second; expiry/revocation, session closure and producer termination close affected media peers. Cleanup uses connection IDs so an old screen cannot close its replacement producer. `DELETE /stream` closes the producer and all viewers.

The backend decodes received video and extracts a JPEG once per `SAMPLE_INTERVAL_SECONDS` (default **1 second**). `frames_received` counts video frames, `frames_sampled` counts extracted images, and saved/rejected/dropped counters describe the analysis queue. Video continues while OCR/AI processing runs. A queue of one keeps the newest sampled image if processing falls behind.

Legacy integrations may still send binary JPEGs to `/stream/frames` or consume `/stream/preview.jpg` / `/stream/live.mjpeg`. The mobile publisher and dashboard playback use WebRTC rather than these compatibility endpoints. Configure a reachable TURN relay for Docker or NAT; exposing the HTTP API alone does not expose WebRTC media.

By default, live frames are saved after OCR and detection, without waiting for captioning or embeddings. `frame_stored` includes `enrichment_status=pending`; `frame_updated` carries the same frame after background AI work completes or fails. `processing_ms` measures initial processing/storage work; `enrichment_ms` records later AI time. Clients must merge updates by frame ID and retain capture-time ordering. Pending work survives restarts; deleted or expired frames are never recreated. Clear frames without OCR/detections can be saved for later visual description. Uploads retain their synchronous behavior. The detector warms up at startup when its prepared weights exist, avoiding model loading on the first capture.

Connect another WebSocket to `/api/v1/sessions/{id}/events` and authenticate with the same first message. Events: ready, heartbeat, stream_started, stream_stopped, frame_stored, frame_updated, frame_rejected, processing_error, question_answered, alert, session_updated. `session_updated` carries the full session after a language/alert change or capture closure so connected devices can update their controls. WebSocket Origin must match the API's own HTTP(S) origin (as sent by native mobile clients) or be in `CORS_ORIGINS` for cross-origin browser clients. Tokens never go in URLs. Authentication is rechecked during streaming; refresh and reconnect when tokens expire or rotate.

## Dashboard and operations

- `GET /dashboard`: owner-scoped session counts and live status (all for administrators).
- Timeline: frames endpoint above. History: questions endpoint above. Preview: MJPEG endpoint above.
- `GET /sessions/{id}/alerts`: stored warnings; speak a received warning using native TTS or `/speech/synthesis`.
- `GET /dashboard/statistics` (also available as `/metrics`): owner-scoped retained frame/question totals, average timings, feedback counts, pending deletions and live connections.
- `POST /maintenance/cleanup`: administrator-only force expiry cleanup; also runs automatically every minute.
- `POST /maintenance/reconcile`: administrator-only removal of old unreferenced image objects after failed uploads; also runs hourly.

Most dependency failures use `{"error":{"code":"...","message":"..."}}` with 503. Invalid input is 422, byte/pixel/duration limits are 413, authentication is 401, missing/expired resources are 404, closed/conflicting sessions are 409 and capacity exhaustion is 429. Validation errors use a `detail` list with location, message and type; input values are omitted to avoid exposing secrets. Caption or embedding failures produce a stored frame with explicit warnings and OCR/object/lexical fallback; failed OCR or YOLO inference returns an error instead of an empty invented result. When the answer model is unavailable, the backend stores an uncertain response with a warning.

The dashboard requests `own_only=true` on `/sessions`, `/dashboard` and `/dashboard/statistics` so even administrator accounts see only their own mobile sessions in this workspace. Omitting it preserves administrator-wide visibility. Maintenance and user-management controls remain explicitly administrator-only.
