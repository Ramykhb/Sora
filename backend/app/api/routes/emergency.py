from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from app.auth_schemas import Credentials
from app.core.auth import current_user
from app.db.auth_models import User
from app.db.session import SessionFactory
from app.schemas import QuestionLocation
from app.services.authentication import throttle
from app.services.emergency import send_location_email

router = APIRouter()


class EmergencyContact(BaseModel):
    email: str = Field(default="", max_length=254)

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        return Credentials.normalize_email(value) if value.strip() else ""


class SOSLocation(QuestionLocation):
    captured_at: datetime
    accuracy_meters: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    request_id: UUID = Field(default_factory=uuid4)

    @field_validator("captured_at")
    @classmethod
    def fresh_location(cls, value):
        if value.tzinfo is None:
            raise ValueError("Location timestamp must include a timezone")
        age = (datetime.now(timezone.utc) - value).total_seconds()
        if age > 120 or age < -30:
            raise ValueError("Get a fresh location before sending SOS")
        return value


@router.get("/contact", response_model=EmergencyContact)
async def contact(user: User = Depends(current_user)):
    return EmergencyContact(email=user.emergency_contact_email)


@router.put("/contact", response_model=EmergencyContact)
async def save_contact(body: EmergencyContact, user: User = Depends(current_user)):
    async with SessionFactory() as db:
        row = await db.get(User, user.id)
        row.emergency_contact_email = body.email
        await db.commit()
    return body


@router.post("/location")
async def share_location(body: SOSLocation, request: Request, user: User = Depends(current_user)):
    if not user.emergency_contact_email:
        raise HTTPException(409, "Add your SOS contact email in Settings first")
    await throttle(request, "sos-email", user.email, limit=5)
    await send_location_email(user, body)
    return {"status": "submitted", "message": "Your location email was submitted to your SOS contact."}
