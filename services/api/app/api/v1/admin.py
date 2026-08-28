"""Admin dispatch and operations."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentAdmin, DbSession
from app.core.errors import ConflictError, NotFoundError
from app.models.booking import Booking
from app.models.catalog import Service
from app.models.enums import (
    BookingStatus,
    ServiceRequestStatus,
    UserRole,
    WorkerVerificationStatus,
)
from app.models.user import User
from app.models.worker import WorkerProfile, WorkerService, WorkerServiceRequest
from app.schemas.booking import AssignRequest, BookingRead, CancelRequest
from app.schemas.worker import ServiceRequestDecision, ServiceRequestRead, WorkerSummary
from app.services import booking as booking_service

router = APIRouter(prefix="/admin", tags=["admin"])


async def _worker_rows(db: DbSession, profiles: list[WorkerProfile]) -> list[WorkerSummary]:
    """Attach user details and cleared service names to each profile."""
    if not profiles:
        return []

    user_ids = [p.user_id for p in profiles]
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()}

    # One query for every profile's services rather than one per profile.
    pairs = (
        await db.execute(
            select(WorkerService.worker_profile_id, Service.name)
            .join(Service, Service.id == WorkerService.service_id)
            .where(WorkerService.worker_profile_id.in_([p.id for p in profiles]))
        )
    ).all()
    by_profile: dict[uuid.UUID, list[str]] = {}
    for profile_id, service_name in pairs:
        by_profile.setdefault(profile_id, []).append(service_name)

    rows = []
    for p in profiles:
        user = users.get(p.user_id)
        if user is None:
            continue
        rows.append(
            WorkerSummary(
                user_id=p.user_id,
                full_name=user.full_name,
                phone=user.phone,
                verification_status=p.verification_status,
                is_available=p.is_available,
                rating_avg=p.rating_avg,
                rating_count=p.rating_count,
                jobs_completed=p.jobs_completed,
                service_names=sorted(by_profile.get(p.id, [])),
            )
        )
    return rows


@router.get("/bookings", response_model=list[BookingRead], summary="All bookings")
async def list_bookings(
    admin: CurrentAdmin,
    db: DbSession,
    status: Annotated[BookingStatus | None, Query()] = None,
) -> list[BookingRead]:
    stmt = booking_service.with_relations(select(Booking)).order_by(Booking.created_at.desc())
    if status:
        stmt = stmt.where(Booking.status == status)
    bookings = (await db.scalars(stmt)).unique().all()
    return [booking_service.serialize(b, admin) for b in bookings]


@router.get("/workers", response_model=list[WorkerSummary], summary="All workers")
async def list_workers(
    admin: CurrentAdmin,
    db: DbSession,
    verification_status: Annotated[WorkerVerificationStatus | None, Query()] = None,
) -> list[WorkerSummary]:
    stmt = select(WorkerProfile)
    if verification_status:
        stmt = stmt.where(WorkerProfile.verification_status == verification_status)
    profiles = list((await db.scalars(stmt)).unique().all())
    return await _worker_rows(db, profiles)


@router.get(
    "/bookings/{booking_id}/candidates",
    response_model=list[WorkerSummary],
    summary="Workers eligible for this job",
)
async def assignment_candidates(
    booking_id: uuid.UUID, admin: CurrentAdmin, db: DbSession
) -> list[WorkerSummary]:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    # Verified, available, and cleared for this specific service. Ordered by
    # rating so the dispatcher's first choice is the best-rated worker.
    stmt = (
        select(WorkerProfile)
        .join(WorkerService, WorkerService.worker_profile_id == WorkerProfile.id)
        .where(
            WorkerService.service_id == booking.service_id,
            WorkerProfile.verification_status == WorkerVerificationStatus.VERIFIED,
            WorkerProfile.is_available.is_(True),
        )
        .order_by(WorkerProfile.rating_avg.desc(), WorkerProfile.jobs_completed.desc())
    )
    return await _worker_rows(db, list((await db.scalars(stmt)).unique().all()))


@router.post(
    "/bookings/{booking_id}/assign",
    response_model=BookingRead,
    summary="Dispatch a worker to a booking",
)
async def assign(
    booking_id: uuid.UUID, body: AssignRequest, admin: CurrentAdmin, db: DbSession
) -> BookingRead:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    await booking_service.assign_worker(db, booking, body.worker_id, actor=admin)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, admin)


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=BookingRead,
    summary="Cancel on the customer's behalf",
)
async def admin_cancel(
    booking_id: uuid.UUID, body: CancelRequest, admin: CurrentAdmin, db: DbSession
) -> BookingRead:
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    await booking_service.transition(db, booking, "cancel", actor=admin, note=body.reason)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, admin)


@router.post(
    "/workers/{user_id}/verify", response_model=WorkerSummary, summary="Approve or reject a worker"
)
async def verify_worker(
    user_id: uuid.UUID,
    admin: CurrentAdmin,
    db: DbSession,
    decision: Annotated[WorkerVerificationStatus, Query()],
    note: str | None = None,
) -> WorkerSummary:
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user_id))
    if profile is None:
        raise NotFoundError("Worker not found.", code="WORKER_NOT_FOUND")

    profile.verification_status = decision
    profile.verification_note = note
    await db.commit()
    await db.refresh(profile)

    rows = await _worker_rows(db, [profile])
    return rows[0]


@router.get(
    "/service-requests",
    response_model=list[ServiceRequestRead],
    summary="Workers asking to be cleared for another trade",
)
async def list_service_requests(
    admin: CurrentAdmin,
    db: DbSession,
    request_status: Annotated[ServiceRequestStatus | None, Query()] = ServiceRequestStatus.PENDING,
) -> list[ServiceRequestRead]:
    stmt = select(WorkerServiceRequest).order_by(WorkerServiceRequest.created_at)
    if request_status:
        stmt = stmt.where(WorkerServiceRequest.status == request_status)
    requests = list((await db.scalars(stmt)).unique().all())
    if not requests:
        return []

    # One query for the people, rather than one per request.
    user_ids = [r.worker.user_id for r in requests if r.worker]
    users = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()}

    rows = []
    for r in requests:
        data = ServiceRequestRead.model_validate(r)
        data.service_name = r.service.name if r.service else None
        user = users.get(r.worker.user_id) if r.worker else None
        if user:
            data.worker_user_id = user.id
            data.worker_name = user.full_name
            data.worker_phone = user.phone
        rows.append(data)
    return rows


@router.post(
    "/service-requests/{request_id}/decide",
    response_model=ServiceRequestRead,
    summary="Approve or reject a trade request",
)
async def decide_service_request(
    request_id: uuid.UUID, body: ServiceRequestDecision, admin: CurrentAdmin, db: DbSession
) -> ServiceRequestRead:
    """Approving clears the worker for that trade straight away.

    The clearance is written in the same transaction as the decision, so the
    worker's job pool widens the moment support says yes — there is no second
    step for anyone to forget.
    """
    req = await db.get(WorkerServiceRequest, request_id)
    if req is None:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    if req.status != ServiceRequestStatus.PENDING:
        raise ConflictError("That request has already been decided.", code="REQUEST_DECIDED")

    req.status = ServiceRequestStatus.APPROVED if body.approve else ServiceRequestStatus.REJECTED
    req.decision_note = body.note
    req.decided_by_id = admin.id
    req.decided_at = datetime.now(UTC)

    if body.approve:
        # Guard the unique pair: a worker could have been cleared by another
        # route between the request and this decision.
        existing = await db.scalar(
            select(WorkerService.id).where(
                WorkerService.worker_profile_id == req.worker_profile_id,
                WorkerService.service_id == req.service_id,
            )
        )
        if existing is None:
            db.add(
                WorkerService(
                    worker_profile_id=req.worker_profile_id,
                    service_id=req.service_id,
                    skill_verified=True,
                )
            )

    await db.commit()
    await db.refresh(req)

    data = ServiceRequestRead.model_validate(req)
    data.service_name = req.service.name if req.service else None
    return data


@router.get("/stats", summary="Dashboard headline numbers")
async def stats(admin: CurrentAdmin, db: DbSession) -> dict[str, object]:
    by_status = dict(
        (
            await db.execute(
                select(Booking.status, func.count(Booking.id)).group_by(Booking.status)
            )
        ).all()
    )

    revenue = await db.scalar(
        select(func.coalesce(func.sum(Booking.commission_amount), 0)).where(
            Booking.status.in_((BookingStatus.COMPLETED, BookingStatus.CLOSED))
        )
    )
    gross = await db.scalar(
        select(func.coalesce(func.sum(Booking.total_amount), 0)).where(
            Booking.status.in_((BookingStatus.COMPLETED, BookingStatus.CLOSED))
        )
    )
    customers = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.CUSTOMER))
    pending_verification = await db.scalar(
        select(func.count(WorkerProfile.id)).where(
            WorkerProfile.verification_status != WorkerVerificationStatus.VERIFIED
        )
    )

    pending_service_requests = await db.scalar(
        select(func.count(WorkerServiceRequest.id)).where(
            WorkerServiceRequest.status == ServiceRequestStatus.PENDING
        )
    )

    return {
        "bookings_by_status": {s.value: c for s, c in by_status.items()},
        "total_bookings": sum(by_status.values()),
        "gross_booking_value": str(gross),
        "commission_revenue": str(revenue),
        "customers": customers,
        "workers_pending_verification": pending_verification,
        "pending_service_requests": pending_service_requests,
        "currency": "NPR",
    }
