"""Worker portal: profile, availability, and the jobs assigned to them."""

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentWorker, DbSession
from app.core.errors import AppError, NotFoundError
from app.models.booking import Booking
from app.models.catalog import Service
from app.models.enums import TERMINAL_BOOKING_STATUSES, BookingStatus
from app.models.worker import WorkerProfile, WorkerService
from app.schemas.booking import BookingRead, CancelRequest, CompleteRequest
from app.schemas.worker import WorkerProfileRead, WorkerProfileUpdate, WorkerServicesUpdate
from app.services import booking as booking_service

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
async def read_profile(worker: CurrentWorker, db: DbSession) -> WorkerProfile:
    return await _profile(db, worker.id)


@router.patch("/profile", response_model=WorkerProfileRead, summary="Update bio / availability")
async def update_profile(
    body: WorkerProfileUpdate, worker: CurrentWorker, db: DbSession
) -> WorkerProfile:
    profile = await _profile(db, worker.id)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put(
    "/services",
    response_model=WorkerProfileRead,
    summary="Choose which trades I work in",
)
async def set_services(
    body: WorkerServicesUpdate, worker: CurrentWorker, db: DbSession
) -> WorkerProfile:
    """Replace the worker's trade list.

    Picking a trade is a claim, not a credential: `skill_verified` stays false
    until an admin says otherwise, and verification is what actually unlocks
    work.
    """
    profile = await _profile(db, worker.id)

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
    return await _profile(db, worker.id, fresh=True)


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
