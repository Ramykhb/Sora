"""Download model weights explicitly before the live demo."""

import argparse
from pathlib import Path
import httpx
from app.core.config import settings
from app.services.frames.processing import detector
from app.services.ai.speech import whisper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ollama", action="store_true")
    args = parser.parse_args()
    Path(settings.yolo_model).parent.mkdir(parents=True, exist_ok=True)
    print("Downloading/loading YOLO weights...")
    detector()
    print("Downloading/loading multilingual Whisper weights...")
    whisper()
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
