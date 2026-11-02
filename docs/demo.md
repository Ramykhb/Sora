# End-to-end demo and evaluation

## Demonstration

1. Confirm phone/server address and same Wi-Fi; open `/health` in phone Safari. Sign into phone and dashboard with the same account.
2. Turn on native speech, consent to selected-frame retention and start capture. Confirm continuous dashboard video and increasing received-frame counts.
3. Show a well-lit EXIT sign. Check fast objects separately from saved OCR/AI descriptions. Keep full caption latency visible rather than presenting it as live detection latency.
4. Enable obstacle alerts and place a supported object, such as a chair, centrally in the camera view. Check alert speech onset while an earlier answer is playing. Repeat after moving the object out of view and back in. No detected object must never be announced as a clear route.
5. Ask an English voice question about a sign; listen to the answer and inspect its cited evidence. Move to another sign, then ask about the earlier one using Memory. Repeat a question in French.
6. Search retained images by meaning and time; inspect original/enhanced views, OCR, objects and history. Submit honest correct/incorrect/unsure feedback.
7. Pause capture, background the phone and leave its screen. Confirm camera/media peers stop and expired observations are not spoken. Resume; expire/logout/revoke a login and confirm data/media access ends.
8. Delete an image or session; verify it disappears from both clients. The automated retention suite checks database and object deletion, including retries.

## Measurements to collect on the physical phone

For each supported obstacle class and lighting condition, record at least the class, scene, detector confidence, false positives, missed objects and camera-to-first-audible-word time. Separate p50/p95 alert latency, OCR time, storage time, caption time, question time, STT time and speech onset. Server observation timing excludes upstream capture/network and phone playback delay.

Use consented testers and representative scenes in at least two languages. Human reviewers should assess factual grounding, correct sign reading, useful uncertainty, missing evidence and speech intelligibility. Record sample size and hardware/CPU settings. Do not turn term overlap into a claimed human accuracy rate.

VoiceOver checks: locate/start/pause capture, change language, enable/disable alerts, record/send a question, hear/stop speech, navigate history and delete data without relying on visual feedback. Confirm font scaling, touch targets, error announcements and focus behavior on the actual device. Native camera, microphone, permissions and audible latency cannot be certified by a JavaScript export alone.

## Presentation outline

1. User problem, scoped observations and consent.
2. Phone → WebRTC relay → independent object alerts and multimedia memory.
3. Frame quality selection and image enhancement; OCR/detection examples.
4. PostgreSQL schema, image-object keys, time/vector/lexical search and retention.
5. Speech → retrieval → grounded vision answer → spoken response, with two-language examples.
6. Measured results, CPU budget, representative failures and unsupported classes.
7. Live phone/dashboard demonstration and lessons learned.

Team attribution is intentionally omitted at the user's request.
