"""The current user's own profile.

Role-specific profiles (customer addresses, worker KYC) arrive in Module 3.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.errors import ConflictError
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="Current user's profile")
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead, summary="Update the current user's profile")
async def update_me(body: UserUpdate, user: CurrentUser, db: DbSession) -> User:
    updates = body.model_dump(exclude_unset=True, exclude_none=True)

    if "email" in updates and updates["email"] != user.email:
        taken = await db.scalar(
            select(User.id).where(User.email == updates["email"], User.id != user.id)
        )
        if taken:
            raise ConflictError("That email is already in use.", code="EMAIL_TAKEN")

    for field, value in updates.items():
        setattr(user, field, value)

    try:
        await db.commit()
    except IntegrityError:
        # The partial unique index is the real guard; the check above just
        # produces a nicer message when there is no race.
        await db.rollback()
        raise ConflictError("That email is already in use.", code="EMAIL_TAKEN") from None

    await db.refresh(user)
    return user


@router.get(
    "/admin/ping",
    summary="Admin-only probe (verifies RBAC wiring end to end)",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
async def admin_ping() -> dict[str, str]:
    return {"status": "ok", "scope": "admin"}
