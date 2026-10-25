"""Sample a local video through the same live-frame selection and storage pipeline."""

import argparse
import asyncio
from pathlib import Path
import cv2
from app.core.config import settings
from app.db.session import engine
from app.services.frames.ingestion import ingest_bytes
from app.services.frames.processing import jpeg
from app.services.sessions import create_session
from app.services.storage.object_store import initialize_storage


async def run(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    await asyncio.to_thread(initialize_storage)
    session = await create_session()
    print("session_id:", session.id)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("Could not open video")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    every = max(1, round(fps * settings.sample_interval_seconds))
    index = 0
    try:
        while True:
            ok, image = capture.read()
            if not ok:
                break
            if index % every == 0:
                result = await ingest_bytes(jpeg(image), session.id)
                print(result.model_dump_json())
            index += 1
    finally:
        capture.release()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path", type=Path)
    asyncio.run(run(parser.parse_args().video_path.expanduser()))
