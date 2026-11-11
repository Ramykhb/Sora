from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.frame import now


class SavedDestination(Base):
    __tablename__ = "saved_destinations"
    __table_args__ = (
        UniqueConstraint("owner_id", "nickname_key", name="uq_saved_destination_owner_nickname"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_destination_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_destination_longitude"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    nickname: Mapped[str] = mapped_column(String(80))
    nickname_key: Mapped[str] = mapped_column(String(240))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
