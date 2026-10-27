from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.core.config import settings
from app.db.base import Base

if settings.database_url.startswith("sqlite"):
    embedding_type = JSON()
else:
    from pgvector.sqlalchemy import Vector

    embedding_type = Vector(settings.embedding_dimensions)


def now():
    return datetime.now(timezone.utc)


class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    language: Mapped[str] = mapped_column(String(2), default="en")
    consent: Mapped[bool] = mapped_column(default=True)
    alerts_enabled: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Frame(Base):
    __tablename__ = "stored_frames"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True
    )
    source_filename: Mapped[str] = mapped_column(String(512))
    original_object_key: Mapped[str] = mapped_column(String(1024))
    processed_object_key: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(100), default="image/jpeg")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sharpness: Mapped[float] = mapped_column(Float)
    brightness: Mapped[float] = mapped_column(Float)
    perceptual_hash: Mapped[str] = mapped_column(String(16))
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0)
    detected_objects: Mapped[list] = mapped_column(JSON, default=list)
    caption: Mapped[str] = mapped_column(Text, default="")
    scene_flags: Mapped[list] = mapped_column(JSON, default=list)
    enhancements: Mapped[list] = mapped_column(JSON, default=list)
    search_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list | None] = mapped_column(embedding_type, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    processing_warnings: Mapped[list] = mapped_column(JSON, default=list)
    processing_ms: Mapped[float] = mapped_column(Float, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (
        Index("ix_stored_frames_session_time", "session_id", "captured_at"),
        Index(
            "ix_frame_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
    )


class QuestionAnswer(Base):
    __tablename__ = "question_answers"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    uncertain: Mapped[bool] = mapped_column(default=True)
    evidence_frame_ids: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(20), default="text")
    processing_warnings: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Alert(Base):
    __tablename__ = "frame_alerts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True
    )
    frame_id: Mapped[UUID] = mapped_column(
        ForeignKey("stored_frames.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Feedback(Base):
    __tablename__ = "answer_feedback"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_answers.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ObjectDeletion(Base):
    __tablename__ = "object_deletions"
    key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
