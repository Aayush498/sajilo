"""Request and response bodies for /auth."""

from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.user import UserRead
from app.utils.phone import normalize_phone


class _PhoneBody(BaseModel):
    phone: Annotated[str, Field(examples=["9841234567", "+9779841234567"])]

    @field_validator("phone")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_phone(v)


class OTPRequest(_PhoneBody):
    # Which app is asking. Decides the role a brand-new account is created with,
    # and blocks a customer from signing in through the worker app.
    role: Literal[UserRole.CUSTOMER, UserRole.WORKER] = UserRole.CUSTOMER


class OTPRequestResponse(BaseModel):
    message: str
    expires_in_seconds: int
    resend_after_seconds: int
    # Populated only outside production, so the dev/QA client can autofill.
    debug_code: str | None = None


class OTPVerify(_PhoneBody):
    code: Annotated[str, Field(min_length=4, max_length=8, examples=["123456"])]
    role: Literal[UserRole.CUSTOMER, UserRole.WORKER] = UserRole.CUSTOMER
    device_label: Annotated[str | None, Field(max_length=120, examples=["Pixel 7"])] = None


class AdminLogin(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    device_label: Annotated[str | None, Field(max_length=120)] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access-token lifetime, seconds


class AuthSession(TokenPair):
    user: UserRead
    is_new_user: bool = False
