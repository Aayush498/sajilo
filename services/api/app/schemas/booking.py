"""Booking request and response bodies."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BookingStatus, PaymentMethod, PaymentStatus
from app.schemas.address import AddressRead


class QuoteRequest(BaseModel):
    package_id: uuid.UUID
    quantity: Annotated[int, Field(default=1, ge=1, le=10)]


class QuoteResponse(BaseModel):
    service_name: str
    package_name: str
    unit_price: Decimal
    quantity: int
    total_amount: Decimal
    duration_minutes: int
    warranty_days: int
    # What Sajilo keeps. Shown to admins and workers, not to customers.
    commission_amount: Decimal
    worker_payout: Decimal


class BookingCreate(BaseModel):
    package_id: uuid.UUID
    address_id: uuid.UUID
    # Omit for "book now" — the API schedules it 30 minutes out.
    scheduled_at: datetime | None = None
    quantity: Annotated[int, Field(default=1, ge=1, le=10)]
    notes: Annotated[str | None, Field(default=None, max_length=1000)]


class StatusEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    action: str
    actor_role: str | None
    note: str | None
    created_at: datetime


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    method: PaymentMethod
    status: PaymentStatus
    amount: Decimal
    paid_at: datetime | None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: int
    comment: str | None
    created_at: datetime


class PersonRead(BaseModel):
    """A counterparty on a booking. Phone is only exposed once the job is live."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    phone: str | None = None
    avatar_url: str | None = None
    rating_avg: Decimal | None = None
    jobs_completed: int | None = None


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    status: BookingStatus
    # The names are snapshots and never change; the ids point at the live
    # catalogue, so "book this again" can land on the right package instead of
    # matching on a name that may since have been edited.
    service_id: uuid.UUID
    package_id: uuid.UUID
    service_name: str
    package_name: str
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    duration_minutes: int
    warranty_days: int
    scheduled_at: datetime
    notes: str | None
    created_at: datetime

    assigned_at: datetime | None
    accepted_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None

    address: AddressRead | None = None
    customer: PersonRead | None = None
    worker: PersonRead | None = None
    payment: PaymentRead | None = None
    review: ReviewRead | None = None
    history: list[StatusEvent] = []

    # Commission figures — populated for worker and admin views only.
    commission_amount: Decimal | None = None
    worker_payout: Decimal | None = None


class CancelRequest(BaseModel):
    reason: Annotated[str | None, Field(default=None, max_length=500)]


class CompleteRequest(BaseModel):
    cash_collected: bool = True
    note: Annotated[str | None, Field(default=None, max_length=500)]


class ReviewCreate(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    comment: Annotated[str | None, Field(default=None, max_length=1000)]


class AssignRequest(BaseModel):
    worker_id: uuid.UUID
