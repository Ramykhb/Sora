from fastapi import UploadFile
from app.core.config import settings
from app.core.errors import BackendError


async def read_upload(file: UploadFile) -> bytes:
    try:
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if not data or len(data) > settings.max_upload_mb * 1024 * 1024:
            raise BackendError("File is empty or exceeds upload limit", 413, "upload_limit")
        return data
    finally:
        await file.close()
