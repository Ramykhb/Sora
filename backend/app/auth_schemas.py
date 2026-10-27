from datetime import datetime
from typing import Literal
from uuid import UUID
import re
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(
            r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value
        ):
            raise ValueError("Enter a valid email address")
        return value


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError("Display name cannot be blank")
        return value.strip()


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    _email = field_validator("email")(Credentials.normalize_email.__func__)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=512)


class ResetRequest(TokenRequest):
    new_password: SecretStr = Field(min_length=12, max_length=128)


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=12, max_length=128)


class ProfilePatch(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    _name = field_validator("display_name")(Registration.name.__func__)


class DeleteAccount(BaseModel):
    password: SecretStr = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_expires_at: datetime
    user: UserOut


class AdminUserPatch(BaseModel):
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None
