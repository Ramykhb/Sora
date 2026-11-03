# Sora mobile

Expo SDK 58 client for the World Out Loud FastAPI backend. Auth, camera capture, speech questions, conversations, visual memory, feedback, alerts and account settings use the backend API.

## Installable apps

The native app publishes continuous camera video using WebRTC on Android and iOS. Install a build containing the native WebRTC module; Expo Go cannot publish this stream.

iOS builds Expo modules from source to avoid an ABI mismatch between the bundled ExpoCamera and ExpoModulesCore frameworks. `npm install` also applies a small Swift compiler workaround in `scripts/patch-expo-swift.cjs`, removing an unnecessary cast in Expo's consuming result switch ([Swift issue #93625](https://github.com/swiftlang/swift/issues/93625)). Postinstall also applies the speech-recognition ducking adjustment described below. If dependencies are installed with scripts disabled, run `npm run postinstall` before building iOS.

For cloud builds without local Xcode or Android Studio, sign in to Expo and configure this project once:

```sh
cd mobile
npx eas-cli@latest login
npx eas-cli@latest build:configure
npx eas-cli@latest build --platform android --profile preview
# For iPhone (Apple Developer Program membership and device registration required):
npx eas-cli@latest device:create
npx eas-cli@latest build --platform ios --profile preview
```

The `preview` profile embeds the JavaScript bundle and runs without Metro. Download and install the resulting Android APK or the signed iOS build. Before signing in, use **Change server** to enter your backend origin, for example `http://192.168.0.100:8000`. The address is saved on the device. Changing it clears saved login credentials so one server's credentials never go to another. Sign out before changing servers.

To build an Android APK locally with Java and the Android SDK installed:

```sh
cd mobile
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease
```

The APK is at `mobile/android/app/build/outputs/apk/release/app-release.apk`. The generated local release build uses a debug signing key and is suitable for local testing, not store distribution.

To install on a connected iPhone locally, enable Developer Mode on the phone, add your Apple ID in Xcode Settings → Accounts, and run `npm run ios -- --device --configuration Release --no-bundler` from `mobile`. This embeds the bundle and installs the app without needing Metro. Xcode must have a valid signing certificate and provisioning profile.

For a same-Wi-Fi backend in Docker, set `TURN_PUBLIC_HOST` in `backend/.env` to the computer's current LAN IP, start the `webrtc` Compose profile, and recreate the API and TURN containers when that address changes. Allow camera, microphone, and local network access on the phone. Start a session and verify that **Received** keeps increasing; the dashboard should show continuous video while backend sampling remains independent.

From `mobile`:

```sh
npm install
cp .env.example .env.local
# Edit EXPO_PUBLIC_API_URL to your backend origin, then:
npm start
```

Run the backend using [its setup instructions](../backend/README.md), listening on `0.0.0.0:8000`. Use the computer's LAN IP for a physical phone on the same network; `localhost` on a phone points to the phone. The URL excludes `/api/v1`. If unset, the client uses Expo's development host on port 8000 (Android emulator fallback: `10.0.2.2`). Restart Metro after changing environment variables. Public Expo variables must never contain secrets.

Use an SDK 58 development build with camera, audio and SecureStore modules. Existing binaries need rebuilding after plugin changes (`npx expo run:android` / `npx expo run:ios`, or your EAS build). Permissions are configured through `app.json`. For deployment, use HTTPS/WSS. For local HTTP development, native transport policy is configured to permit cleartext in this project. Web camera/microphone require localhost or HTTPS. Add the exact web origin to backend `CORS_ORIGINS` for HTTP and socket access.

Register and sign in, consent to camera processing, then start a session. The phone publishes its back camera as a video-only WebRTC track (target 720p/15 fps). Signaling uses authenticated HTTP SDP offers with gathered ICE candidates. Once a TURN relay candidate is ready, the phone proceeds without waiting for unreachable cellular interfaces to finish gathering. The backend relays continuous video to dashboard WebRTC viewers and samples one frame per second for OCR/detection and deferred AI enrichment. It does not take still photographs or send JPEGs from the phone. Connection refreshes keep media authorization current; pausing, backgrounding, leaving the screen or signing out stops the camera and closes only that producer connection. Voice recording remains separate from the video stream.

On iPhone, rebuild and install the native app after adding WebRTC: connect/unlock the device, enable Developer Mode, then run `npm run ios -- --device` (Xcode and CocoaPods required). Expo Go and old development binaries cannot load the WebRTC module; the app displays a rebuild message instead. A prebuild-generated `ios/` directory is ignored by Git and must be regenerated with Expo after native configuration changes. The backend's TURN relay must be reachable from the phone; see [WebRTC networking](../backend/docs/environment.md#webrtc-networking).

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


## Hands-free voice

After signing in and finishing onboarding, SORA listens while the app is open.
Allow microphone and speech recognition permissions when prompted. Say
**“Hey Sora, start stream”** to open live assistance and start the camera stream.
This command consents to the same camera processing and session storage described
on the camera screen. The phone may show its camera permission dialog the first time.

With a stream running, say **“describe the scene”** or ask another question without
pressing a button. SORA waits for a completed utterance, sends it to the current
session, and speaks the answer. Live camera questions use the current view;
questions on an image result refer to that image; the workspace uses its selected
session and question scope. One hands-free question is processed at a time. If no
session is open, SORA explains how to start a stream by voice.

Every utterance beginning with **“Hey Sora”** is reserved for app commands.
Unsupported commands receive spoken feedback and are never submitted as questions.
Supported stream commands:

- **“Hey Sora, start stream”** starts live assistance.
- **“Hey Sora, pause stream”** releases the camera while keeping the session open.
- **“Hey Sora, resume stream”** reconnects the same session and returns to its camera view.
- **“Hey Sora, stop stream”** ends capture on the server and keeps saved moments.

Each command receives spoken confirmation. Voice listening remains available while
the stream is paused, so resume and stop work without touching the screen. Open
sessions remain controllable when you visit Preferences or another screen.

Preferences includes a **Hands-free voice** switch, listening status and a retry
button. The switch controls automatic questions and commands. Listening pauses in
the background and while recording a voice question, then resumes. During SORA
answer playback it remains active so speaking can interrupt the answer. The phone’s speech service may use the network. The listener
does not save audio recordings; recognized questions are submitted as text to the
session question endpoint and retained with the session conversation.

The `expo-speech-recognition` native module requires a **new development build**;
a Metro reload or OTA update cannot add it to an older binary. Generate native
configuration from `app.json` and rebuild using the existing Expo development-build
workflow. Expo Go and older builds show an explanation instead of loading the
missing module. Real recognition, camera permissions and microphone sharing need
verification on Android and iPhone before release. Background and lock-screen
listening are not implemented.


Answers and descriptions read aloud automatically by default, including on an
iPhone in silent mode. The first launch after this update enables automatic
reading for existing installs. You can mute future automatic descriptions using
**Read answers aloud** in Preferences or the camera's speaker button; that choice
is saved. Direct hands-free questions continue to receive spoken replies.


### Chatting without automatic questions

Say **“Hey Sora, stop listening”** to ignore ordinary speech while keeping app
commands available. Say **“Hey Sora, start listening”** (or **“resume listening”**)
to accept hands-free questions again. The preference is saved across launches and
can also be changed using **Hands-free questions** in Preferences.

Paused streams automatically ignore all speech without the Hey Sora prefix,
without submitting questions or reading an error aloud. Resume the stream to
restore questions, unless you explicitly turned question listening off. Starting
or resuming a stream does not override that choice. Responses to questions already
in progress stay silent after pausing or saying stop listening.

The microphone remains active for Hey Sora recognition while the app is open.
Stop listening disables automatic question handling; use the master Hands-free
voice switch to disable microphone listening completely.


## Accessible home screen

After onboarding and sign-in, the main home area is one large **Start live stream**
button. Tap anywhere in that area to begin live assistance directly, including
camera permissions when needed. VoiceOver/TalkBack users can focus the button and
double-tap to activate it. Voice guidance announces the shortcut when a screen
reader is not running. The button describes camera processing and storage in its
accessibility hint and visible text.

Navigation remains outside the start surface at the bottom. **More tools** opens
the previous dashboard, including Read Text, Describe Scene and recent activity.
The Hey Sora stream command continues to use the same startup flow.


## Interrupting spoken answers

With Hands-free voice enabled and the app open, start speaking while SORA reads an
answer. Playback stops on the first recognized user words, before the sentence is
finalized. The listener keeps the rest of that utterance so you can ask a follow-up
question or issue a Hey Sora command. This also pauses the optional server voice.

Recognition uses the shared play-and-record audio session and iOS voice processing
for speaker echo cancellation. Known words from SORA's playback are filtered out,
including a short tail of delayed recognition results, to reduce false interruptions and
Hey Sora commands picked up from the speaker. Normal conversation can stop playback in commands-only
mode, but it still cannot submit questions while question listening is off or the
stream is paused. Turning off Hands-free voice disables voice interruption too.

Verify interruption speed, speaker feedback, and headphone/Bluetooth routing on
a physical phone; these depend on the device's speech recognition service.


### Consistent volume at the beginning of answers

Speech waits for an active recognition audio session and its brief route-settling
period, then reuses that session instead of changing its category at the first word.
If recognition cannot become ready within two seconds, playback falls back to the
configured audio session so an unavailable listener cannot block an answer forever.
The server-voice player uses the same readiness check.

On iOS 17 and newer, `scripts/patch-speech-recognition.cjs` configures the native
voice-processing engine with fixed, minimum ducking. This reduces attenuation of
AVSpeechSynthesizer/AVPlayer while preserving microphone echo cancellation and voice
interruption. Apple documents this behavior in [Other audio ducking](https://developer.apple.com/videos/play/wwdc2023/10235/).
The patch is applied by `npm run postinstall`, checks its upstream anchor, and is
safe to reapply. It edits the installed dependency rather than generated iOS files.
It requires a new native build to take effect on a phone; app builds and installs
should only run when explicitly requested.
