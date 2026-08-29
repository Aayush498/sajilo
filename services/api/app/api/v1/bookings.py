"""Customer-facing booking endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.models.booking import Booking
from app.models.catalog import Service, ServicePackage
from app.models.enums import UserRole
from app.schemas.booking import (
    BookingCreate,
    BookingRead,
    CancelRequest,
    QuoteRequest,
    QuoteResponse,
    ReviewCreate,
)
from app.services import booking as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])

# "Book now" still needs a slot a worker can realistically reach.
INSTANT_LEAD_TIME = timedelta(minutes=30)


async def _load(db: DbSession, booking_id: uuid.UUID, user: CurrentUser) -> Booking:
    booking = await booking_service.reload(db, booking_id)
    booking_service.assert_can_view(booking, user)
    return booking


@router.post("/quote", response_model=QuoteResponse, summary="Price a booking before committing")
async def get_quote(body: QuoteRequest, db: DbSession) -> QuoteResponse:
    package = await db.get(ServicePackage, body.package_id)
    if package is None or not package.is_active:
        raise NotFoundError("That option is not available.", code="PACKAGE_NOT_FOUND")
    service = await db.get(Service, package.service_id)
    if service is None:
        raise NotFoundError("Service not found.", code="SERVICE_NOT_FOUND")

    priced = booking_service.quote(package, service, body.quantity)
    return QuoteResponse(
        service_name=service.name,
        package_name=package.name,
        warranty_days=service.warranty_days,
        **priced,
    )


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a booking",
)
async def create_booking(body: BookingCreate, user: CurrentUser, db: DbSession) -> BookingRead:
    scheduled_at = body.scheduled_at or (datetime.now(UTC) + INSTANT_LEAD_TIME)

    booking = await booking_service.create_booking(
        db,
        customer=user,
        package_id=body.package_id,
        address_id=body.address_id,
        scheduled_at=scheduled_at,
        quantity=body.quantity,
        notes=body.notes,
    )
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, user)


@router.get("", response_model=list[BookingRead], summary="My bookings")
async def list_my_bookings(user: CurrentUser, db: DbSession) -> list[BookingRead]:
    # Workers get their jobs from /worker/jobs; this is the customer's list.
    column = Booking.worker_id if user.role == UserRole.WORKER else Booking.customer_id
    stmt = (
        booking_service.with_relations(select(Booking))
        .where(column == user.id)
        .order_by(Booking.created_at.desc())
    )
    bookings = (await db.scalars(stmt)).unique().all()
    return [booking_service.serialize(b, user) for b in bookings]


@router.get("/{booking_id}", response_model=BookingRead, summary="One booking")
async def get_booking(booking_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BookingRead:
    booking = await _load(db, booking_id, user)
    return booking_service.serialize(booking, user)


@router.post("/{booking_id}/cancel", response_model=BookingRead, summary="Cancel a booking")
async def cancel_booking(
    booking_id: uuid.UUID, body: CancelRequest, user: CurrentUser, db: DbSession
) -> BookingRead:
    booking = await _load(db, booking_id, user)
    if user.role == UserRole.WORKER:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    await booking_service.transition(db, booking, "cancel", actor=user, note=body.reason)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, user)


@router.post(
    "/{booking_id}/review",
    response_model=BookingRead,
    summary="Rate a finished booking",
)
async def review_booking(
    booking_id: uuid.UUID, body: ReviewCreate, user: CurrentUser, db: DbSession
) -> BookingRead:
    booking = await _load(db, booking_id, user)
    if booking.customer_id != user.id:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    await booking_service.submit_review(
        db, booking, customer=user, rating=body.rating, comment=body.comment
    )
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, user)
