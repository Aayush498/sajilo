"""Worker portal: profile, availability, and the jobs assigned to them."""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentWorker, DbSession
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.booking import Booking
from app.models.catalog import Service
from app.models.enums import (
    TERMINAL_BOOKING_STATUSES,
    BookingStatus,
    ServiceRequestStatus,
)
from app.models.worker import WorkerProfile, WorkerService, WorkerServiceRequest
from app.schemas.booking import BookingRead, CancelRequest, CompleteRequest
from app.schemas.worker import (
    ServiceRequestCreate,
    ServiceRequestRead,
    WorkerProfileRead,
    WorkerProfileUpdate,
    WorkerServicesUpdate,
)
from app.services import booking as booking_service

log = get_logger(__name__)
router = APIRouter(prefix="/worker", tags=["worker"])


async def _profile(db: DbSession, user_id: uuid.UUID, *, fresh: bool = False) -> WorkerProfile:
    """The signed-in worker's profile.

    `fresh` re-reads the services collection from the database. The session
    keeps objects past commit (expire_on_commit=False), so after editing the
    trade list the cached profile still carries the old one — and the response
    would show the change as having done nothing.
    """
    stmt = select(WorkerProfile).where(WorkerProfile.user_id == user_id)
    if fresh:
        stmt = stmt.execution_options(populate_existing=True)
    profile = await db.scalar(stmt)
    if profile is None:
        raise NotFoundError("Worker profile not found.", code="PROFILE_NOT_FOUND")
    return profile


async def _job(db: DbSession, booking_id: uuid.UUID, worker: CurrentWorker) -> Booking:
    booking = await booking_service.reload(db, booking_id)
    booking_service.assert_is_assigned_worker(booking, worker)
    return booking


@router.get("/profile", response_model=WorkerProfileRead, summary="My worker profile")
async def read_profile(worker: CurrentWorker, db: DbSession) -> WorkerProfileRead:
    return _serialize_profile(await _profile(db, worker.id))


@router.patch("/profile", response_model=WorkerProfileRead, summary="Update bio / availability")
async def update_profile(
    body: WorkerProfileUpdate, worker: CurrentWorker, db: DbSession
) -> WorkerProfileRead:
    profile = await _profile(db, worker.id)
    # As in users.py: an omitted field is left alone, but an explicit null
    # clears the bio. experience_years and is_available are not nullable.
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if value is None and field != "bio":
            continue
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return _serialize_profile(profile)


def _serialize_profile(profile: WorkerProfile) -> WorkerProfileRead:
    data = WorkerProfileRead.model_validate(profile)
    data.services_locked = _is_locked(profile)
    return data


def _is_locked(profile: WorkerProfile) -> bool:
    """Trades freeze the moment the worker declares them, not at verification.

    What an admin reviews is a specific person offering a specific set of
    trades. Locking only at approval left a window where the thing being
    reviewed could still change underneath the reviewer: a worker could submit
    as a cleaner, sit in the queue, and switch to electrician before anyone
    looked — and support would approve a list they never actually read.

    So the declaration is the commitment. Widening it afterwards goes through
    support as a request, which is the same route a verified worker takes, and
    approval writes the clearance in the same transaction as the decision.

    An empty list means onboarding is simply not finished yet.
    """
    return len(profile.services) > 0


@router.put(
    "/services",
    response_model=WorkerProfileRead,
    summary="Declare which trades I work in (onboarding, once)",
)
async def set_services(
    body: WorkerServicesUpdate, worker: CurrentWorker, db: DbSession
) -> WorkerProfileRead:
    """Set the worker's trade list. This is the last step of onboarding.

    Picking a trade is a claim, not a credential: `skill_verified` stays false
    until an admin says otherwise, and verification is what actually unlocks
    work. The list itself is frozen as soon as it is submitted — see
    `_is_locked` — so this succeeds exactly once per worker.
    """
    profile = await _profile(db, worker.id)

    if _is_locked(profile):
        raise ConflictError(
            "Your trades are locked. Ask support to add another one and they will review it.",
            code="SERVICES_LOCKED",
        )

    wanted = set(body.service_ids)
    if wanted:
        found = set(
            (
                await db.scalars(
                    select(Service.id).where(Service.id.in_(wanted), Service.is_active.is_(True))
                )
            ).all()
        )
        if found != wanted:
            raise AppError("One of those services does not exist.", code="UNKNOWN_SERVICE")

    existing = {link.service_id: link for link in profile.services}

    for service_id in wanted - existing.keys():
        db.add(WorkerService(worker_profile_id=profile.id, service_id=service_id))
    for service_id in existing.keys() - wanted:
        await db.delete(existing[service_id])

    await db.commit()
    return _serialize_profile(await _profile(db, worker.id, fresh=True))


def _request_row(req: WorkerServiceRequest) -> ServiceRequestRead:
    data = ServiceRequestRead.model_validate(req)
    data.service_name = req.service.name if req.service else None
    return data


@router.get(
    "/service-requests",
    response_model=list[ServiceRequestRead],
    summary="My requests to add a trade",
)
async def my_service_requests(worker: CurrentWorker, db: DbSession) -> list[ServiceRequestRead]:
    profile = await _profile(db, worker.id)
    rows = (
        (
            await db.scalars(
                select(WorkerServiceRequest)
                .where(WorkerServiceRequest.worker_profile_id == profile.id)
                .order_by(WorkerServiceRequest.created_at.desc())
            )
        )
        .unique()
        .all()
    )
    return [_request_row(r) for r in rows]


@router.post(
    "/service-requests",
    response_model=ServiceRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Ask support to clear me for another trade",
)
async def request_service(
    body: ServiceRequestCreate, worker: CurrentWorker, db: DbSession
) -> ServiceRequestRead:
    profile = await _profile(db, worker.id)

    service = await db.get(Service, body.service_id)
    if service is None or not service.is_active:
        raise NotFoundError("That service is not available.", code="SERVICE_NOT_FOUND")

    already = await db.scalar(
        select(WorkerService.id).where(
            WorkerService.worker_profile_id == profile.id,
            WorkerService.service_id == service.id,
        )
    )
    if already is not None:
        raise ConflictError(f"You are already cleared for {service.name}.", code="ALREADY_CLEARED")

    pending = await db.scalar(
        select(WorkerServiceRequest.id).where(
            WorkerServiceRequest.worker_profile_id == profile.id,
            WorkerServiceRequest.service_id == service.id,
            WorkerServiceRequest.status == ServiceRequestStatus.PENDING,
        )
    )
    if pending is not None:
        raise ConflictError(
            f"You already have a request for {service.name} waiting for review.",
            code="REQUEST_PENDING",
        )

    req = WorkerServiceRequest(worker_profile_id=profile.id, service_id=service.id, note=body.note)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    log.info(
        "worker.service_requested",
        worker_id=str(worker.id),
        service=service.name,
    )
    return _request_row(req)


@router.post(
    "/service-requests/{request_id}/withdraw",
    response_model=ServiceRequestRead,
    summary="Withdraw a request I no longer need",
)
async def withdraw_service_request(
    request_id: uuid.UUID, worker: CurrentWorker, db: DbSession
) -> ServiceRequestRead:
    profile = await _profile(db, worker.id)
    req = await db.get(WorkerServiceRequest, request_id)
    # 404 rather than 403 — whose request this is, is not the caller's business.
    if req is None or req.worker_profile_id != profile.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    if req.status != ServiceRequestStatus.PENDING:
        raise ConflictError("That request has already been decided.", code="REQUEST_DECIDED")

    req.status = ServiceRequestStatus.WITHDRAWN
    await db.commit()
    await db.refresh(req)
    return _request_row(req)


@router.get(
    "/available-jobs",
    response_model=list[BookingRead],
    summary="Open jobs I can take",
)
async def available_jobs(worker: CurrentWorker, db: DbSession) -> list[BookingRead]:
    """The claimable pool. Empty (not an error) when the worker cannot work."""
    try:
        profile = await booking_service.eligible_worker_profile(db, worker.id)
    except booking_service.WorkerNotAssignableError:
        return []

    jobs = await booking_service.open_jobs_for_worker(db, profile)
    return [booking_service.serialize(j, worker) for j in jobs]


@router.post(
    "/available-jobs/{booking_id}/claim",
    response_model=BookingRead,
    summary="Take an open job",
)
async def claim_job(booking_id: uuid.UUID, worker: CurrentWorker, db: DbSession) -> BookingRead:
    booking = await booking_service.claim_booking(db, booking_id, worker=worker)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, worker)


@router.get("/jobs", response_model=list[BookingRead], summary="Jobs assigned to me")
async def list_jobs(
    worker: CurrentWorker, db: DbSession, active_only: bool = False
) -> list[BookingRead]:
    stmt = booking_service.with_relations(select(Booking)).where(Booking.worker_id == worker.id)
    if active_only:
        stmt = stmt.where(Booking.status.notin_(TERMINAL_BOOKING_STATUSES))
    stmt = stmt.order_by(Booking.scheduled_at)

    jobs = (await db.scalars(stmt)).unique().all()
    return [booking_service.serialize(j, worker) for j in jobs]


async def _act(
    db: DbSession,
    booking_id: uuid.UUID,
    worker: CurrentWorker,
    action: str,
    note: str | None = None,
) -> BookingRead:
    booking = await _job(db, booking_id, worker)
    await booking_service.transition(db, booking, action, actor=worker, note=note)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, worker)


@router.post("/jobs/{booking_id}/accept", response_model=BookingRead, summary="Accept a job")
async def accept_job(booking_id: uuid.UUID, worker: CurrentWorker, db: DbSession) -> BookingRead:
    return await _act(db, booking_id, worker, "accept")


@router.post("/jobs/{booking_id}/reject", response_model=BookingRead, summary="Decline a job")
async def reject_job(
    booking_id: uuid.UUID, body: CancelRequest, worker: CurrentWorker, db: DbSession
) -> BookingRead:
    booking = await _job(db, booking_id, worker)
    # transition() detaches the worker, so serialise against the pre-move view
    # of who the actor was rather than re-reading booking.worker.
    await booking_service.transition(db, booking, "reject", actor=worker, note=body.reason)
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, worker)


@router.post("/jobs/{booking_id}/start-travel", response_model=BookingRead, summary="On my way")
async def start_travel(booking_id: uuid.UUID, worker: CurrentWorker, db: DbSession) -> BookingRead:
    return await _act(db, booking_id, worker, "start_travel")


@router.post("/jobs/{booking_id}/start", response_model=BookingRead, summary="Start the work")
async def start_work(booking_id: uuid.UUID, worker: CurrentWorker, db: DbSession) -> BookingRead:
    return await _act(db, booking_id, worker, "start_work")


@router.post(
    "/jobs/{booking_id}/complete",
    response_model=BookingRead,
    summary="Finish the job and confirm payment",
)
async def complete_job(
    booking_id: uuid.UUID, body: CompleteRequest, worker: CurrentWorker, db: DbSession
) -> BookingRead:
    booking = await _job(db, booking_id, worker)
    await booking_service.complete_booking(
        db, booking, actor=worker, cash_collected=body.cash_collected
    )
    await db.commit()
    booking = await booking_service.reload(db, booking.id)
    return booking_service.serialize(booking, worker)


@router.get("/earnings", summary="Earnings summary")
async def earnings(worker: CurrentWorker, db: DbSession) -> dict[str, object]:
    """Payout totals. Only counts jobs that actually finished."""
    stmt = select(Booking).where(
        Booking.worker_id == worker.id,
        Booking.status.in_((BookingStatus.COMPLETED, BookingStatus.CLOSED)),
    )
    jobs = (await db.scalars(stmt)).unique().all()

    return {
        "jobs_completed": len(jobs),
        "gross_amount": str(sum((j.total_amount for j in jobs), start=0)),
        "commission_deducted": str(sum((j.commission_amount for j in jobs), start=0)),
        "net_earnings": str(sum((j.worker_payout for j in jobs), start=0)),
        "currency": "NPR",
    }
