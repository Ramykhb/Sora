import secrets
from fastapi import Header, HTTPException
from app.core.config import settings


def valid_key(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and secrets.compare_digest(
            value.encode("utf-8"), settings.api_key.get_secret_value().encode("utf-8")
        )
    )


async def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if not valid_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
