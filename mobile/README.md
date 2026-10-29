# Sora mobile

Expo SDK 58 client for the World Out Loud FastAPI backend. Auth, camera capture, speech questions, conversations, visual memory, feedback, alerts and account settings use the backend API.

From `mobile`:

```sh
npm install
cp .env.example .env.local
# Edit EXPO_PUBLIC_API_URL to your backend origin, then:
npm start
```

Run the backend using [its setup instructions](../backend/README.md), listening on `0.0.0.0:8000`. Use the computer's LAN IP for a physical phone on the same network; `localhost` on a phone points to the phone. The URL excludes `/api/v1`. If unset, the client uses Expo's development host on port 8000 (Android emulator fallback: `10.0.2.2`). Restart Metro after changing environment variables. Public Expo variables must never contain secrets.

Use an SDK 58 development build with camera, audio and SecureStore modules. Existing binaries need rebuilding after plugin changes (`npx expo run:android` / `npx expo run:ios`, or your EAS build). Permissions are configured through `app.json`. For deployment, use HTTPS/WSS. For local HTTP development, native transport policy is configured to permit cleartext in this project. Web camera/microphone require localhost or HTTPS. Add the exact web origin to backend `CORS_ORIGINS` for HTTP and socket access.

Register and sign in, consent to camera processing, then start a session. Capture uses the backend's supported binary JPEG WebSocket protocol: authenticate in the first message, wait for `ready`, send JPEG bytes with bounded buffering. There is one producer per session. The camera takes sequential stills with a 250 ms minimum delay; actual frame rate depends on the device. The server independently samples useful frames. Events carry scene descriptions, frame rejections, answers and opt-in alerts. Backgrounding or leaving the assistance screen stops capture and recording. Temporary camera and voice files are deleted after use.

Use Current view for fresh evidence, Memory for retained frames, or Auto for backend scope selection. Record a voice question and tap again to send it; recordings automatically stop at 55 seconds (backend default maximum: 60). Backend Whisper handles recognition. Answers use native TTS automatically, with authenticated server WAV playback available per answer. English, French and Arabic preferences are saved per capture session. Models and speech binaries must be prepared on the backend; their errors and uncertainty are displayed.

Moments shows retained sessions, enhanced/original images, OCR, object detections, semantic search, optional time bounds, conversations and feedback. Images and sessions can be deleted. Settings supports profile changes, password changes, device revocation, sign-out and account deletion. Password resets and verification accept the token from the backend email link; delivery requires backend SMTP configuration. This mobile client exposes user workflows; administrator operations remain in the dashboard/API.

Refresh tokens use SecureStore on native platforms and tab-scoped sessionStorage on web. Access tokens stay in memory. Requests refresh once on 401, concurrent refreshes share one rotation, and sockets reconnect as tokens expire. Backend logout must succeed before local credentials are cleared so failures remain visible. A session's memory survives closing capture until expiry; expired sessions require a new consented session.

```sh
npm run typecheck
npm run lint
npm test
```

Automated tests validate the API client and live protocol with fake transports. Physical camera/microphone, real model inference, native permissions, and device networking require a device smoke test: register → start capture → verify a stored scene → ask by text and voice → play a server answer → search Moments → delete data → sign out and restore/revoke sign-in.

Implementation follows the [Expo SDK 58 reference](https://docs.expo.dev/versions/v58.0.0/), including its [camera](https://docs.expo.dev/versions/v58.0.0/sdk/camera/), [audio](https://docs.expo.dev/versions/v58.0.0/sdk/audio/) and [SecureStore](https://docs.expo.dev/versions/v58.0.0/sdk/securestore/) APIs.
