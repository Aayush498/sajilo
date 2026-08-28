"""Password hashing, JWT access tokens, and opaque refresh tokens."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher()


# --- Passwords --------------------------------------------------------------
# Only admins have passwords; customers and workers authenticate by phone OTP.


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# --- Access tokens ----------------------------------------------------------


def create_access_token(*, user_id: uuid.UUID, role: str, session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
        "iss": "sajilo",
        "typ": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="sajilo",
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Session expired.", code="TOKEN_EXPIRED") from None
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token.", code="TOKEN_INVALID") from None

    if payload.get("typ") != "access":
        raise AuthenticationError("Invalid token.", code="TOKEN_INVALID")
    return payload


# --- Refresh tokens ---------------------------------------------------------
# Opaque random strings. Only the SHA-256 digest is stored, so a database leak
# does not hand an attacker usable sessions. SHA-256 (not Argon2) because these
# are already 256 bits of entropy — there is nothing to brute-force — and
# refresh happens on a hot path.


def generate_refresh_token() -> tuple[str, str]:
    """Return (plaintext, digest). Only the plaintext ever leaves the server."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expiry(role: str) -> datetime:
    """Admin sessions are deliberately short — they can do the most damage."""
    if role == "admin":
        delta = timedelta(hours=settings.ADMIN_REFRESH_TOKEN_TTL_HOURS)
    else:
        delta = timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)
    return datetime.now(UTC) + delta


def generate_otp(length: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))
