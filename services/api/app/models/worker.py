"""Worker profile and the services they are cleared to perform."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WorkerVerificationStatus, pg_enum


class WorkerProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Extends a user with role=worker.

    Verification is an explicit state machine, not a boolean, because "trust"
    is the product. An admin must move a worker to VERIFIED before they can be
    assigned any job.
    """

    __tablename__ = "worker_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    city_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cities.id", ondelete="RESTRICT"), nullable=True
    )

    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_years: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    citizenship_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_status: Mapped[WorkerVerificationStatus] = mapped_column(
        pg_enum(WorkerVerificationStatus, "worker_verification_status"),
        nullable=False,
        default=WorkerVerificationStatus.PENDING,
    )
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    police_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Worker's own on/off switch, separate from admin verification. Both must
    # be true for the worker to appear in the assignable pool.
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Denormalised from reviews so listing workers does not aggregate on read.
    # Recomputed in app/services/booking.py when a review lands.
    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("0.00")
    )
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    services: Mapped[list["WorkerService"]] = relationship(
        back_populates="worker", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_worker_profiles_verification", "verification_status"),)

    @property
    def is_assignable(self) -> bool:
        return self.verification_status == WorkerVerificationStatus.VERIFIED and self.is_available


class WorkerService(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which services a worker is cleared for. A plumber must not get an AC job."""

    __tablename__ = "worker_services"

    worker_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("worker_profiles.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    skill_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    worker: Mapped[WorkerProfile] = relationship(back_populates="services")

    __table_args__ = (
        UniqueConstraint("worker_profile_id", "service_id", name="uq_worker_services_pair"),
        Index("ix_worker_services_service_id", "service_id"),
    )
