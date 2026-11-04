"""Apply the current face privacy policy to existing retained frame variants."""
import asyncio
import json

import cv2
import numpy as np
from sqlalchemy import select

from app.core.errors import BackendError
from app.db.models import Frame
from app.db.session import SessionFactory
from app.services.frames.privacy import PRIVACY_VERSION, blur_regions, face_regions
from app.services.frames.processing import jpeg
from app.services.storage.object_store import get_image, put_image


def redact_variants(keys):
    images = [cv2.imdecode(np.frombuffer(get_image(key), np.uint8), cv2.IMREAD_COLOR) for key in keys]
    if any(image is None for image in images):
        raise ValueError("Cannot decode stored frame")
    if images[0].shape != images[1].shape:
        raise ValueError("Stored frame variants have different dimensions")
    # Union detections from both variants, so an enhanced-only detection also
    # protects the original. Finish both reads/detections before overwriting.
    regions = [region for image in images for region in face_regions(image)]
    if regions:
        for key, image in zip(keys, images):
            put_image(key, jpeg(blur_regions(image, regions)))
    return bool(regions)


async def main():
    counts = {"checked": 0, "blurred": 0, "already_processed": 0, "unavailable": 0}
    # Bound database memory; an interrupted run can safely resume. Stamp a row
    # only after both objects were successfully processed.
    after = None
    while True:
        async with SessionFactory() as db:
            query = select(Frame).order_by(Frame.id).limit(100)
            if after is not None:
                query = query.where(Frame.id > after)
            rows = list((await db.scalars(query)).all())
            if not rows:
                break
            for row in rows:
                if PRIVACY_VERSION in row.enhancements:
                    counts["already_processed"] += 1
                    continue
                try:
                    blurred = await asyncio.to_thread(redact_variants, [
                        row.original_object_key, row.processed_object_key,
                    ])
                except BackendError as exc:
                    if exc.code != "image_unavailable":
                        raise
                    counts["unavailable"] += 1
                    continue
                row.enhancements = [*row.enhancements, PRIVACY_VERSION, *(["face_blur"] if blurred else [])]
                await db.commit()
                counts["checked"] += 1
                counts["blurred"] += int(blurred)
            after = rows[-1].id
    print(json.dumps(counts))


if __name__ == "__main__":
    asyncio.run(main())
