Run modules from backend with the virtual environment active:
- `python -m scripts.prepare_models`: download YOLO, Whisper and Ollama weights.
- `python -m scripts.process_image /path/to/image.jpg`: process and persist a test image.
- `python -m scripts.process_video /path/to/video.mp4`: sample a local video through the same pipeline.
- `python -m scripts.cleanup`: expire old records and retry object deletion.
- `python -m scripts.evaluate /path/to/dataset.json`: create a reproducible evaluation report.

- `python -m scripts.smoke /path/to/image.jpg --webrtc`: real-service image, speech, storage and transport smoke check.
- `python -m scripts.configure_local --host YOUR_LAN_IP`: generate local configuration and preserve existing credentials (also runnable from the repository root as `python3 backend/scripts/configure_local.py`).
- `python -m scripts.acceptance --output acceptance-report.json`: full real-service workflow with generated person-free signs and a temporary account; cleans up its own account/session and writes partial results on failure. This checks functionality, not human accuracy or physical iPhone accessibility.

Account administration: `python -m scripts.manage_users create-admin EMAIL`, `promote EMAIL`, or `claim-session EMAIL UUID`. Passwords are prompted. Smoke/evaluation scripts now prompt for registered account credentials; optional `--email EMAIL` preselects the account.
