"""Authentication: account lookup/creation, session issue, rotation, revocation."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.models.worker import WorkerProfile
from app.schemas.auth import AuthSession
from app.schemas.user import UserRead
from app.utils.phone import mask_phone

log = get_logger(__name__)


async def get_active_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    result = await db.execute(
        select(User).where(User.phone == phone, User.status != UserStatus.DELETED)
    )
    return result.scalar_one_or_none()


async def get_or_create_user(db: AsyncSession, *, phone: str, role: UserRole) -> tuple[User, bool]:
    """Return (user, is_new). OTP verification doubles as registration."""
    user = await get_active_user_by_phone(db, phone)
    if user is not None:
        if user.status == UserStatus.SUSPENDED:
            raise PermissionDeniedError(
                "This account is suspended. Contact Sajilo support.", code="ACCOUNT_SUSPENDED"
            )
        # A worker must not be able to sign in through the customer app or vice
        # versa; the role is fixed at registration and only an admin changes it.
        if user.role != role and user.role != UserRole.ADMIN:
            raise PermissionDeniedError(
                f"This number is registered as a {user.role.value}. "
                f"Please use the Sajilo {user.role.value} app.",
                code="ROLE_MISMATCH",
                details={"registered_role": user.role.value},
            )
        user.phone_verified = True
        return user, False

    user = User(phone=phone, role=role, phone_verified=True, status=UserStatus.ACTIVE)
    db.add(user)
    await db.flush()

    # A worker account is useless without its profile — it is what the
    # verification workflow and job assignment both hang off — so create it
    # here rather than leaving a window where the two can disagree.
    if role == UserRole.WORKER:
        db.add(WorkerProfile(user_id=user.id))
        await db.flush()

    log.info("user.registered", user_id=str(user.id), role=role.value, phone=mask_phone(phone))
    return user, True


async def authenticate_admin(db: AsyncSession, *, email: str, password: str) -> User:
    result = await db.execute(
        select(User).where(
            User.email == email,
            User.role == UserRole.ADMIN,
            User.status != UserStatus.DELETED,
        )
    )
    user = result.scalar_one_or_none()

    # Same error either way — do not reveal which admin emails exist.
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email or password.", code="INVALID_CREDENTIALS")
    if user.status == UserStatus.SUSPENDED:
        raise PermissionDeniedError("This account is suspended.", code="ACCOUNT_SUSPENDED")
    return user


async def issue_session(
    db: AsyncSession,
    user: User,
    *,
    device_label: str | None = None,
    ip_address: str | None = None,
    parent_id: uuid.UUID | None = None,
    is_new_user: bool = False,
) -> AuthSession:
    plaintext, digest = generate_refresh_token()
    session = RefreshToken(
        user_id=user.id,
        token_hash=digest,
        parent_id=parent_id,
        expires_at=refresh_token_expiry(user.role.value),
        device_label=device_label,
        ip_address=ip_address,
    )
    db.add(session)
    await db.flush()

    user.last_login_at = datetime.now(UTC)
    access = create_access_token(user_id=user.id, role=user.role.value, session_id=session.id)

    return AuthSession(
        access_token=access,
        refresh_token=plaintext,
        expires_in=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        user=UserRead.model_validate(user),
        is_new_user=is_new_user,
    )


async def rotate_session(
    db: AsyncSession, *, refresh_token: str, ip_address: str | None = None
) -> AuthSession:
    """Exchange a refresh token for a new pair, invalidating the old one."""
    digest = hash_refresh_token(refresh_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == digest))
    session = result.scalar_one_or_none()

    if session is None:
        raise AuthenticationError("Invalid refresh token.", code="REFRESH_INVALID")

    if session.revoked_at is not None:
        # This token was already exchanged. Either it leaked and an attacker is
        # replaying it, or the legitimate client is retrying. We cannot tell
        # them apart, so we assume the worst and kill every session for the
        # user; they log in again.
        await revoke_all_sessions(db, session.user_id)
        # Commit before raising: get_db rolls the transaction back on any
        # exception, which would silently undo the revocation and leave the
        # attacker's sibling tokens working.
        await db.commit()
        log.warning("auth.refresh_reuse_detected", user_id=str(session.user_id))
        raise AuthenticationError(
            "Session invalidated for security reasons. Please log in again.",
            code="REFRESH_REUSED",
        )

    if session.expires_at <= datetime.now(UTC):
        raise AuthenticationError("Session expired. Please log in again.", code="REFRESH_EXPIRED")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.", code="ACCOUNT_UNAVAILABLE")

    session.revoked_at = datetime.now(UTC)
    return await issue_session(
        db, user, device_label=session.device_label, ip_address=ip_address, parent_id=session.id
    )


async def revoke_session(db: AsyncSession, *, refresh_token: str) -> None:
    """Log out one device. Idempotent — an unknown token is not an error."""
    digest = hash_refresh_token(refresh_token)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == digest, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
