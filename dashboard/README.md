# Sora dashboard

React/Vite dashboard connected to the World Out Loud backend. Use the **same email and password as mobile**. Each device receives its own login tokens; both see the account’s shared capture sessions, images, questions and alerts.

## Run locally

Start the backend at `http://127.0.0.1:8000` using [its setup instructions](../backend/README.md). Restart it after the dashboard backend changes. From `dashboard`:

```sh
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/v1` (including WebSockets), `/health` and `/ready` to port 8000. No dashboard environment file is required for this setup. To change the backend, copy `.env.example` to `.env.local` and edit `BACKEND_PROXY_TARGET`. Both the dashboard and mobile must target the same backend instance and database.

1. Register once, then sign in on mobile and dashboard with that account.
2. On mobile, consent to processing, start a session, grant camera access and resume assistance.
3. The dashboard discovers that account’s live session within about four seconds and follows its stream automatically.
4. Use **Live session** to see the mobile camera, saved scene descriptions, OCR, detections, processing counters and alerts. Dashboard preview pause affects only the viewer. **End mobile capture** closes the shared session; retained memory remains until expiry.
5. Ask by text or record a voice question on either device. Both devices receive the shared answer and history through authenticated events. Conversations provides WAV playback, evidence images, uncertainty, warnings and feedback.

The dashboard is a viewer of the mobile producer. It does not take over the camera or start another producer. The server must run one worker, as required by its live stream architecture. Model preparation, Whisper and eSpeak installation are backend prerequisites. Automatic audio can be blocked by the browser; use **Play spoken answer** when prompted.

## Connected features

- Authentication: login, registration, tab refresh-token restoration, rotation, logout, verification and password recovery. Reset/verification tokens can be entered manually. For email links pointing here, set backend `AUTH_PUBLIC_URL=http://127.0.0.1:5173`; Vite handles `/reset-password?token=...` and `/verify-email?token=...`.
- Account workspace: automatic mobile-session discovery, manual retained-session selection, metrics, live events and producer statistics. `own_only=true` keeps session lists and metrics scoped to the signed-in account, including administrator accounts.
- Live frames save OCR/detections first. Cards indicate when AI descriptions are still processing; background events update the same frames. Details distinguish initial save time from later AI description time.
- Video: a receive-only WebRTC peer renders continuous mobile video in a muted, inline `<video>` element. Backend processing samples one image per second independently of playback. Authenticated offers, ICE gathering, connection refresh, reconnect, local pause and fullscreen are supported. Pausing the dashboard releases only its viewer peer and leaves phone capture running. The video path never polls JPEG previews. Detections still describe timestamped saved frames rather than being overlaid on newer video.
- Visual memory: authenticated images, enhanced/original detail views, OCR, objects, warnings, semantic search with optional time bounds, paginated timeline and deletion.
- Conversations: text/voice questions, current versus memory scope, language/time bounds, shared history, pagination, authenticated speech playback, evidence details and feedback with notes.
- Speech tools: standalone audio-file transcription and text synthesis. Browser recordings choose a supported WebM/MP4 format, stop automatically at 55 seconds, and release the microphone on navigation/backgrounding. Audio recordings are not retained by the backend.
- Preferences: server-persisted session language/alerts, browser spoken-answer preference, profile changes, password changes, login-device revocation, sign-out and account/session deletion. Retention is controlled by backend configuration and displayed through session expiry.
- Administrator controls: user activation/roles, expired-data cleanup, orphan reconciliation and dependency readiness. These explicit operations can affect other accounts; ordinary workspace views remain account-only.

The backend enforces resource ownership. Client account filtering is additional protection against displaying administrator-wide results; it does not replace API authorization. Access tokens stay in memory. Only the refresh token is kept in tab-scoped `sessionStorage`. Media uses authenticated fetch and short-lived blob URLs that are revoked on cleanup.

## Network and production configuration

The browser’s exact origin must appear in backend `CORS_ORIGINS`, including for WebSockets. The default configuration now includes `http://localhost:5173` and `http://127.0.0.1:5173`. An existing backend `.env` override takes precedence; merge these origins if needed. Do not use wildcard origins for authenticated sockets.

For production, set `VITE_API_URL=https://your-backend.example` **before building**, or provide an HTTP/WebSocket reverse proxy for `/api/v1` and `/ready` on the dashboard origin. `BACKEND_PROXY_TARGET` applies only to the Vite development server. `npm run preview` serves built assets; it does not provide the development API proxy. Configure production fallback routing for dashboard email-link paths. Use HTTPS/WSS; browser microphone recording requires HTTPS or localhost. No secrets belong in `VITE_*` variables.

```sh
npm test       # Auth rotation, ownership selection, binary MJPEG and socket contracts
npm run build # Production assets in dist/
```

Backend ownership regression test: `python -m pytest tests/test_auth.py -q` from a configured backend environment. Client tests use substitute transports; they do not verify real model accuracy, physical camera/microphone permissions or actual phone networking. Complete the two-device flow above to validate those in your environment.

Browser recording and streaming use the standard [MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder) and [ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/getReader) APIs.
