Run modules from backend with the virtual environment active:
- `python -m scripts.prepare_models`: download YOLO, Whisper and Ollama weights.
- `python -m scripts.process_image /path/to/image.jpg`: process and persist a test image.
- `python -m scripts.process_video /path/to/video.mp4`: sample a local video through the same pipeline.
- `python -m scripts.cleanup`: expire old records and retry object deletion.
- `python -m scripts.evaluate /path/to/dataset.json`: create a reproducible evaluation report.

- `python -m scripts.smoke /path/to/image.jpg --webrtc`: real-service image, speech, storage and transport smoke check.
