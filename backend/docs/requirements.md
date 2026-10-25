# Backend requirements mapping

| PDF requirement | Backend implementation |
| --- | --- |
| Phone streams live camera to server | WebRTC SDP offer/answer and aiortc video receiver; binary JPEG WebSocket for integration and testing |
| Select sharp, new, informative frames | Raw sharpness/brightness thresholds, perceptual hash deduplication, OCR/object/caption information check; sampling and latest-only queue |
| Improve dark or blurry images | Conditional CLAHE, denoising and mild unsharp mask; cannot reconstruct missing details |
| OCR signs and labels | Tesseract with English/French/Arabic language packs, text and confidence |
| Detect objects | YOLO11 nano, labels/confidences/boxes; generic person detection without identification |
| Store and search images, text, objects, time | PostgreSQL + pgvector, S3-compatible object storage or local files, timestamps, semantic/lexical/time search |
| Spoken question to answer | Multilingual Whisper transcription, evidence retrieval, Qwen vision answer, persisted history, eSpeak NG WAV synthesis |
| Answer from camera evidence and admit uncertainty | Images plus timestamps and OCR sent to VLM, validated evidence IDs, stale-view rejection, localized uncertainty and safety filter |
| At least two languages | English, French and Arabic request validation, OCR, STT, answer generation and TTS |
| Live dashboard status | Session overview, live status, frame timeline, question history, metrics and live events APIs |
| Display device live stream | Authenticated MJPEG preview and latest image responses |
| No face recognition | No face embeddings, face lookup, or identity API; VLM prompts forbid identification |
| Delete old frames, minimize collection | Frame/session/question expiry, DB deletion + retryable object-deletion outbox, no stored raw microphone audio/video |
| Consenting testers | Session creation requires explicit consent=true |
| Proactive warnings (bonus) | Opt-in, persisted, rate-limited alerts for large central objects and clearly visible central closed doors |
| Deliver speed/search/accuracy/feedback evidence | Processing/answer timing, evaluation CLI with retrieval/recognition metrics, manual answer feedback |

The accessible mobile UI and web dashboard UI belong to the other applications. Their backend contracts are implemented here.
