"""Shared FastAPI dependencies: current user, role guards, client IP."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.db.session import get_db
from app.models.auth import RefreshToken
from app.models.enums import UserRole
from app.models.user import User

# auto_error=False so a missing header raises our envelope, not FastAPI's.
_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/verify-otp")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    from app.core.security import decode_access_token

    if credentials is None:
        raise AuthenticationError("Missing Authorization header.")

    payload = decode_access_token(credentials.credentials)
    user = await db.get(User, uuid.UUID(payload["sub"]))

    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.", code="ACCOUNT_UNAVAILABLE")

    # The access token is stateless, but its session can be revoked mid-life by
    # a logout, a suspension, or refresh-reuse detection. Checking the session
    # here caps the damage window at the 15-minute access TTL instead of
    # letting a revoked session keep working.
    session = await db.scalar(
        select(RefreshToken).where(RefreshToken.id == uuid.UUID(payload["sid"]))
    )
    if session is None or session.revoked_at is not None:
        raise AuthenticationError("Session has been revoked.", code="SESSION_REVOKED")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    """Route guard: `Depends(require_roles(UserRole.ADMIN))`."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "This action is not available for your account type.",
                details={"required_roles": [r.value for r in roles]},
            )
        return user

    return _guard


CurrentCustomer = Annotated[User, Depends(require_roles(UserRole.CUSTOMER))]
CurrentWorker = Annotated[User, Depends(require_roles(UserRole.WORKER))]
CurrentAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


def get_client_ip(request: Request) -> str | None:
    """Real client IP behind a reverse proxy.

    Trusts X-Forwarded-For, which is only safe because nothing but our own
    load balancer is allowed to reach the container. It is used for rate-limit
    keys and session records, never for authorisation.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


ClientIP = Annotated[str | None, Depends(get_client_ip)]
