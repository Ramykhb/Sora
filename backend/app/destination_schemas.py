import re
import unicodedata
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from app.schemas import ORMModel, QuestionLocation


def destination_key(nickname):
    value = unicodedata.normalize("NFKC", nickname).casefold().replace("’", "").replace("'", "")
    return " ".join(re.findall(r"[^\W_]+", value))


class DestinationWrite(QuestionLocation):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=1, max_length=80)

    @field_validator("nickname", mode="before")
    @classmethod
    def normalize_nickname(cls, value):
        if not isinstance(value, str):
            raise ValueError("Nickname must be text")
        value = " ".join(unicodedata.normalize("NFKC", value).split())
        key = destination_key(value)
        if not key:
            raise ValueError("Nickname must contain letters or numbers")
        if key in {"there", "it", "that", "that place", "that restaurant", "that one", "this place", "the place", "the restaurant", "هناك", "ذلك المكان"}:
            raise ValueError("Choose a specific nickname rather than a follow-up word such as 'there'")
        return value


class DestinationOut(ORMModel):
    id: UUID
    nickname: str
    latitude: float
    longitude: float
    created_at: datetime
    updated_at: datetime
