from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["en", "fr", "ar"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SessionCreate(BaseModel):
    language: Language = "en"
    consent: Literal[True]
    alerts_enabled: bool = False


class SessionOut(ORMModel):
    id: UUID
    owner_id: UUID | None
    language: Language
    consent: bool
    alerts_enabled: bool
    status: str
    created_at: datetime
    expires_at: datetime


class SessionPatch(BaseModel):
    language: Language | None = None
    alerts_enabled: bool | None = None


class FrameOut(ORMModel):
    id: UUID
    session_id: UUID
    width: int
    height: int
    sharpness: float
    brightness: float
    ocr_text: str
    ocr_confidence: float
    detected_objects: list[dict]
    caption: str
    scene_flags: list[str]
    enhancements: list[str]
    processing_warnings: list[str]
    processing_ms: float
    enrichment_status: Literal["pending", "complete", "failed"]
    enrichment_ms: float | None
    captured_at: datetime
    expires_at: datetime


class IngestResult(BaseModel):
    status: Literal["stored", "rejected"]
    reason: str | None = None
    frame: FrameOut | None = None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    language: Language | None = None
    scope: Literal["auto", "recent", "memory"] = "auto"
    since: datetime | None = None
    until: datetime | None = None

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Question must contain text")
        return value.strip()

    @field_validator("since", "until")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value


class AnswerOut(ORMModel):
    id: UUID
    session_id: UUID
    question: str
    answer: str
    language: Language
    uncertain: bool
    evidence_frame_ids: list[str]
    source: str
    processing_warnings: list[str]
    latency_ms: float
    created_at: datetime


class FeedbackRequest(BaseModel):
    rating: Literal["correct", "incorrect", "unsure"]
    notes: str = Field(default="", max_length=2000)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: Language = "en"


class Offer(BaseModel):
    sdp: str = Field(min_length=1, max_length=100_000)
    type: Literal["offer"] = "offer"
