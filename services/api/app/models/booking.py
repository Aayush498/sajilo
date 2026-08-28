"""Bookings, their audit trail, payment, and review."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    BookingStatus,
    PaymentMethod,
    PaymentStatus,
    pg_enum,
)


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One job.

    Every price field is a snapshot taken at creation. If we later change what
    a 2 BHK clean costs, or adjust the commission rate, this row must still
    show what the customer agreed to and what the worker was promised.
    """

    __tablename__ = "bookings"

    # Human-readable reference used in SMS, invoices and support calls.
    reference: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("service_packages.id", ondelete="RESTRICT"), nullable=False
    )
    address_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_addresses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"), nullable=False, default=BookingStatus.PENDING
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- price snapshot -----------------------------------------------------
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    package_name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    worker_payout: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    warranty_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- lifecycle timestamps ----------------------------------------------
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[customer_id], lazy="joined"
    )
    worker: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[worker_id], lazy="joined"
    )
    address: Mapped["CustomerAddress"] = relationship("CustomerAddress", lazy="joined")  # noqa: F821

    # The worker's profile, reached through worker_id. There is no foreign key
    # between these tables (bookings point at users, not profiles), so the join
    # is spelled out and marked viewonly.
    worker_profile: Mapped["WorkerProfile | None"] = relationship(  # noqa: F821
        "WorkerProfile",
        primaryjoin="Booking.worker_id == foreign(WorkerProfile.user_id)",
        lazy="selectin",
        viewonly=True,
    )

    history: Mapped[list["BookingStatusHistory"]] = relationship(
        back_populates="booking",
        lazy="selectin",
        order_by="BookingStatusHistory.created_at",
        cascade="all, delete-orphan",
    )
    payment: Mapped["Payment | None"] = relationship(
        back_populates="booking", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )
    review: Mapped["Review | None"] = relationship(
        back_populates="booking", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_bookings_customer_id", "customer_id"),
        Index("ix_bookings_worker_id", "worker_id"),
        # Drives the admin dispatch board: "unassigned jobs, oldest first".
        Index("ix_bookings_status_scheduled", "status", "scheduled_at"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("total_amount >= 0", name="total_non_negative"),
    )


class BookingStatusHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only audit trail. Every dispute starts by reading this."""

    __tablename__ = "booking_status_history"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="history")

    __table_args__ = (Index("ix_booking_status_history_booking_id", "booking_id"),)


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One payment per booking. Cash only today; gateways slot in later."""

    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    method: Mapped[PaymentMethod] = mapped_column(
        pg_enum(PaymentMethod, "payment_method"), nullable=False, default=PaymentMethod.CASH
    )
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"), nullable=False, default=PaymentStatus.PENDING
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Gateway reference once online payments exist; null for cash.
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="payment")


class Review(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The customer's rating of a completed booking. One per booking."""

    __tablename__ = "reviews"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="review")

    __table_args__ = (
        Index("ix_reviews_worker_id", "worker_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )
