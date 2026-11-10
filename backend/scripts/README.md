Run modules from backend with the virtual environment active:
- `python -m scripts.prepare_models`: download YOLO, Whisper and Ollama weights.
- `python -m scripts.prepare_ocr`: download the lightweight PP-OCRv5 detector plus English, Latin/French and Arabic recognizers into `models/paddleocr`, with a SHA-256 manifest.
- `python -m scripts.check_ocr`: verify those models with generated local text images; use an environment installed from `requirements-ocr.txt`. This is an optional PaddleOCR setup and does not change the API's current Tesseract engine.
- `python -m scripts.process_image /path/to/image.jpg`: process and persist a test image.
- `python -m scripts.process_video /path/to/video.mp4`: sample a local video through the same pipeline.
- `python -m scripts.cleanup`: expire old records and retry object deletion.
- `python -m scripts.evaluate /path/to/dataset.json`: create a reproducible evaluation report.

- `python -m scripts.smoke /path/to/image.jpg --webrtc`: real-service image, speech, storage and transport smoke check.
- `python -m scripts.benchmark_stream --relay-only --image tests/fixtures/astronaut.jpg`: measure 720p/60 publishing and viewing through the running API/TURN with a temporary account; print real fps and clean up the generated session/account.
- `python -m scripts.configure_local --host YOUR_LAN_IP`: generate local configuration and preserve existing credentials (also runnable from the repository root as `python3 backend/scripts/configure_local.py`).
- `python -m scripts.acceptance --output acceptance-report.json`: full real-service workflow with generated person-free signs and a temporary account; cleans up its own account/session and writes partial results on failure. This checks functionality, not human accuracy or physical iPhone accessibility.

Account administration: `python -m scripts.manage_users create-admin EMAIL`, `promote EMAIL`, or `claim-session EMAIL UUID`. Passwords are prompted. Smoke/evaluation scripts now prompt for registered account credentials; optional `--email EMAIL` preselects the account.
