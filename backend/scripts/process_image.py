import argparse
import asyncio
from pathlib import Path
import sys
from uuid import UUID

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import BACKEND_ROOT
from app.db.session import engine
from app.services.frames.ingestion import ingest_image
from app.services.storage.object_store import initialize_storage, get_image


async def run(args):
    try:
        if args.init_db:
            from alembic import command
            from alembic.config import Config

            await asyncio.to_thread(
                command.upgrade, Config(str(BACKEND_ROOT / "alembic.ini")), "head"
            )
        await asyncio.to_thread(initialize_storage)
        result = await ingest_image(
            args.image_path,
            session_id=args.session_id,
            force=args.force,
            ocr_language=args.language,
        )
        print(result.model_dump_json(indent=2))
        if args.output and result.frame:
            from app.db.models import Frame
            from app.db.session import SessionFactory

            async with SessionFactory() as db:
                frame = await db.get(Frame, result.frame.id)
                data = await asyncio.to_thread(get_image, frame.processed_object_key)
                args.output.write_bytes(data)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Analyze an image and store its visual memory")
    parser.add_argument("image_path", type=Path)
    parser.add_argument("--session-id", type=UUID)
    parser.add_argument("--language", help="Tesseract language code(s); default from OCR_LANGUAGES")
    parser.add_argument(
        "--force", action="store_true", help="Store even a blurry or duplicate test image"
    )
    parser.add_argument("--init-db", action="store_true", help="Apply database migrations first")
    parser.add_argument("--output", type=Path, help="Also write the enhanced image to this path")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        parser.exit(1, f"Image processing failed: {exc}\n")


if __name__ == "__main__":
    main()
