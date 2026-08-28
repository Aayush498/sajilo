"""User-facing representations. Never expose password_hash."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole, UserStatus


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    phone_verified: bool
    email: EmailStr | None
    full_name: str | None
    avatar_url: str | None
    role: UserRole
    status: UserStatus
    locale: str
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Annotated[str | None, Field(default=None, min_length=2, max_length=120)]
    email: EmailStr | None = None
    locale: Annotated[str | None, Field(default=None, pattern="^(en|ne)$")]
