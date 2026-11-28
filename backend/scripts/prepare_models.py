"""Download model weights explicitly before the live demo."""

import argparse
from pathlib import Path
import httpx
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument(
        "--speech-only", action="store_true", help="Prepare only local Supertonic TTS weights"
    )
    args = parser.parse_args()
    if args.speech_only:
        from app.services.ai.supertonic_speech import prepare

        print("Downloading/loading Supertonic speech weights (about 400 MB)...", flush=True)
        prepare()
        print("Speech model prepared.")
        return
    from app.services.frames.processing import detector
    from app.services.ai.speech import whisper

    Path(settings.yolo_model).parent.mkdir(parents=True, exist_ok=True)
    print("Downloading/loading YOLO weights...")
    detector()
    print("Downloading/loading multilingual Whisper weights...")
    whisper()
    if settings.supertonic_enabled:
        from app.services.ai.supertonic_speech import prepare as prepare_speech

        print("Downloading/loading Supertonic speech weights (about 400 MB)...", flush=True)
        prepare_speech()
    if settings.ocr_engine == "paddleocr":
        from scripts.prepare_ocr import prepare, install_runtime

        print("Preparing PaddleOCR models and isolated CPU runtime...", flush=True)
        prepare(settings.paddle_ocr_model_dir)
        install_runtime(settings.paddle_ocr_model_dir)
    if not args.skip_ollama:
        with httpx.Client(timeout=3600) as client:
            for model in (settings.vision_model, settings.embedding_model):
                print("Pulling", model)
                response = client.post(
                    settings.ollama_url.rstrip("/") + "/api/pull",
                    json={"model": model, "stream": False},
                )
                response.raise_for_status()
                if response.json().get("error"):
                    raise RuntimeError(response.json()["error"])
    print("Models prepared.")


if __name__ == "__main__":
    main()
