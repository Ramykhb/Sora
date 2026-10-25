from functools import lru_cache
import logging
from pathlib import Path
from app.core.config import settings
from app.core.errors import BackendError

logger = logging.getLogger(__name__)


@lru_cache
def client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=15,
            retries={"max_attempts": 2},
        ),
    )


def local_path(key: str) -> Path:
    root = settings.local_storage_dir.resolve()
    path = (root / key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Invalid object key")
    return path


def storage_error(exc):
    logger.error("Object storage failed: %s", type(exc).__name__)
    return BackendError("Image storage unavailable", 503, "storage_unavailable")


def initialize_storage():
    if settings.storage_backend == "local":
        settings.local_storage_dir.mkdir(parents=True, exist_ok=True)
        return
    if settings.storage_backend != "s3":
        raise ValueError("STORAGE_BACKEND must be s3 or local")
    try:
        client().head_bucket(Bucket=settings.s3_bucket)
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code"))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise storage_error(exc) from exc
        try:
            client().create_bucket(Bucket=settings.s3_bucket)
        except Exception as race:
            if (
                getattr(race, "response", {}).get("Error", {}).get("Code")
                != "BucketAlreadyOwnedByYou"
            ):
                raise storage_error(race) from race


def put_image(key: str, content: bytes, content_type: str = "image/jpeg"):
    try:
        if settings.storage_backend == "local":
            path = local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
        else:
            client().put_object(
                Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type
            )
    except Exception as exc:
        raise storage_error(exc) from exc


def get_image(key: str) -> bytes:
    try:
        if settings.storage_backend == "local":
            return local_path(key).read_bytes()
        body = client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"]
        try:
            return body.read()
        finally:
            body.close()
    except Exception as exc:
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code"))
        if isinstance(exc, FileNotFoundError) or code in {"NoSuchKey", "404", "NotFound"}:
            raise BackendError("Stored image unavailable", 404, "image_unavailable") from exc
        raise storage_error(exc) from exc


def delete_image(key: str):
    try:
        if settings.storage_backend == "local":
            path = local_path(key)
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass
        else:
            client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except Exception as exc:
        raise storage_error(exc) from exc


def list_objects():
    """List only this application's image namespace for orphan reconciliation."""
    from datetime import datetime, timezone

    if settings.storage_backend == "local":
        root = settings.local_storage_dir.resolve()
        return [
            (
                str(path.relative_to(root)),
                datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
            )
            for path in (root / "images").rglob("*")
            if path.is_file()
        ]
    try:
        result = []
        paginator = client().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix="images/"):
            result.extend((item["Key"], item["LastModified"]) for item in page.get("Contents", []))
        return result
    except Exception as exc:
        raise storage_error(exc) from exc
