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

Register and sign in, consent to camera processing, then start a session. The phone publishes its back camera as a video-only WebRTC track (target 720p/60 fps). Signaling uses authenticated HTTP SDP offers with gathered ICE candidates. Once a TURN relay candidate is ready, the phone proceeds without waiting for unreachable cellular interfaces to finish gathering. The backend relays continuous video to dashboard WebRTC viewers and samples one frame per second for OCR/detection and deferred AI enrichment. It does not take still photographs or send JPEGs from the phone. Connection refreshes keep media authorization current; pausing, backgrounding, leaving the screen or signing out stops the camera and closes only that producer connection. Voice recording remains separate from the video stream.

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

### Repeat and stop spoken answers

- **“Repeat that”**, **“say that again”**, or **“Hey Sora, repeat the last answer”** replays the most recent answer in its original language.
- **“Repeat the directions”** or **“Hey Sora, repeat my route”** replays the last walking route, including its steps and distances, even after an unrelated camera answer.
- **“Stop speaking”**, **“stop talking”**, or **“Hey Sora, stop audio”** stops playback and suppresses a pending hands-free spoken reply. It does not mute future answers, pause the camera, or disable listening.

These are exact command phrases, optionally followed by “please.” They do not send a question or fetch another route. They also work while ordinary questions or the stream are paused, provided foreground voice commands are enabled. Muted playback stays muted; unmute with “Hey Sora, unmute” before replaying. If there is no answer or route to repeat, Sora explains what to ask first. App confirmations, errors, and obstacle alerts do not replace the remembered answer. Answers from the voice assistant, typed questions, scene/text results, and manually selected answer playback can be remembered.

Replay history is held only in the current app process, clears on sign-out/account/server changes and provider teardown, and is not restored from backend history after an app restart. This is separate from the backend's persistent destination memory. A repeated answer describes the original evidence; replay does not analyze a new frame or recalculate a route. Reload the app's JavaScript to receive these controls; no native rebuild is required.

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

## Muting Sora by voice

Say **Hey Sora, mute** to stop current speech and mute subsequent answers, guidance and alerts. Speech recognition and questions stay active. Say **Hey Sora, unmute** to restore voice and hear a brief confirmation. These commands update the same saved voice preference as the screen's speaker button. The mute setting also stops server-voice playback and prevents it from starting while muted.

## Shared dashboard appearance

Mobile uses the dashboard’s charcoal surfaces, purple actions, green live status and pink voice accents. New installs start in dark mode; saved Light and System choices, high contrast, larger text, voice settings and haptics still apply. The main home area remains a single accessible Start live stream button and scrolls on smaller screens.

Editable logo, hero, app icon and Android themed-icon sources live in `../brand`. The mobile and dashboard share the same Buddy robot logo. Launch artwork is configured in `app.json`; regenerate native resources and rebuild when ready to show the new home-screen icon and splash. Existing installed apps continue to use their bundled launch artwork until rebuilt.

## Native iOS navigation

iOS uses Expo Router native tabs for Home, Assist, History and Settings. UIKit supplies Liquid Glass on iOS 26+ and the standard system bar on earlier iOS versions. Tabs stay expanded for predictable accessibility and hide during onboarding, sign-in and full-screen camera capture. Web and Android retain the existing accessible bottom navigation. Public URLs (`/camera`, `/tools`, `/assistant`, `/explore`, `/settings`) and voice-command routes are unchanged.

Walking trip questions such as `start a trip to the nearest McDonald's`, `route to Starbucks`, and `give me directions to the hospital` attach current GPS with high accuracy requested. Nearby lookups keep their existing location behavior and straight-line distances. The backend uses Google Routes walking directions to return the walking distance and ordered turns with meters; existing answer playback reads these instructions. Initial directions use compass/street wording because the phone's facing direction is not collected. Trip answers are route overviews, with no continuous tracking or live rerouting. Reload the app's JavaScript to receive the new trip phrase handling; no native rebuild is required for this change.

Sign-in uses one Buddy hero and a compact form that fits common phone sizes without scrolling. Scrolling remains available when the keyboard, larger accessibility text or expanded account/connection options need more space.

Destination follow-ups work within the same session: ask `What is the nearest restaurant?`, then `route to there` or `take me there`. Each follow-up requests fresh GPS and the backend reuses the exact previously returned place. A new session has separate destination memory; missing context asks you to identify a place. Reload mobile JavaScript for short follow-up phrases.

## Saved destinations

While signed in, open **Settings → Saved destinations**. Add multiple places using your own nicknames, such as `home`, `university`, or `favorite restaurant`. Enter decimal latitude/longitude manually, or tap **Use my current location** while at that place to fill them in, then tap **Save destination**. Each entry has edit and delete controls. Coordinates support negative values and zero; latitude must be between −90 and 90 and longitude between −180 and 180. Nicknames are 1–80 characters, unique per account after normalization; follow-up words such as “there” are reserved.

Say `route home`, `navigate university`, or `route to favorite restaurant`. The phone supplies fresh, high-accuracy origin GPS; the backend resolves the nickname to the saved destination and requests Google walking directions directly, without a Places search. Nickname lookup ignores case, repeated spacing, and punctuation; `route to my home` can address an entry named `home`. Use `route to saved NICKNAME` to explicitly require a saved entry. Missing shorthand nicknames ask you to add them in Settings. Named/proximity searches with an explicit `to`, such as `route to the nearest McDonald's`, still use Places when no saved nickname matches.

Saved destinations belong to your signed-in account and persist across app/backend restarts and capture sessions. They remain until you delete them or the account; previous route answers retain their usual conversation lifetime. The Settings form is keyed by account/server and guards against account changes while GPS or requests are pending. Location permission is needed only when using current GPS or requesting a route, not for entering destination coordinates manually. Apply backend migration `0007_saved_destinations` and reload mobile JavaScript; no native rebuild is required.

## Find an object

While live assistance is running, ask **“Help me find my backpack,” “Where is my phone?”**, or **“Can you see my keys?”** without the “Hey Sora” prefix. The current frame is analyzed for the requested object, and Sora speaks/displays its position relative to the camera image: left/center/right and top/middle/bottom. Use **“repeat that”** to replay the answer. Each question analyzes a fresh snapshot; it does not start continuous object tracking.

Gemini, when enabled on the backend, checks visual matches and requested attributes. The local detector provides a fallback for supported object classes; unsupported classes or attributes, poor visibility, weak matches, and multiple possible matches remain uncertain. A matching object is not proof that it belongs to the user. Not finding a target in one image does not establish that it is absent from the surroundings. No distance or walking/reaching instructions are inferred. Missing/stale camera evidence requests a new view. Ask explicitly historical questions, such as “Where was my backpack earlier?”, to search retained memory. This feature uses existing question and speech interfaces and requires the updated backend rather than a native app rebuild.
