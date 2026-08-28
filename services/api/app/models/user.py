"""The user account — one row per person, whatever their role."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole, UserStatus, pg_enum


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    # E.164, always. See app.utils.phone.normalize_phone.
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Optional for customers and workers; admins are expected to have one.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Only ever set for admins — customers and workers log in with an OTP.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.CUSTOMER
    )
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), nullable=False, default=UserStatus.ACTIVE
    )

    # "en" or "ne" — drives SMS language now, app copy in Module 3.
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Partial unique index: a deleted account frees its number for
        # re-registration while its history stays intact for accounting.
        Index(
            "uq_users_phone_active",
            "phone",
            unique=True,
            postgresql_where=text("status <> 'deleted'"),
        ),
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL AND status <> 'deleted'"),
        ),
        Index("ix_users_role_status", "role", "status"),
    )

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<User {self.id} {self.role}>"
