"""Booking lifecycle: pricing, creation, and guarded status transitions."""

import secrets
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, noload, selectinload

from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.booking import Booking, BookingStatusHistory, Payment, Review
from app.models.catalog import Service, ServicePackage
from app.models.customer import CustomerAddress
from app.models.enums import (
    BOOKING_TRANSITIONS,
    BookingStatus,
    PaymentMethod,
    PaymentStatus,
    UserRole,
    WorkerVerificationStatus,
)
from app.models.user import User
from app.models.worker import WorkerProfile, WorkerService
from app.schemas.address import AddressRead
from app.schemas.booking import BookingRead, PersonRead

log = get_logger(__name__)

TWO_DP = Decimal("0.01")


class InvalidTransitionError(AppError):
    status_code = 409
    code = "INVALID_TRANSITION"
    message = "That action is not allowed for this booking right now."


class WorkerNotAssignableError(AppError):
    status_code = 409
    code = "WORKER_NOT_ASSIGNABLE"
    message = "That worker cannot take this job."


# --- pricing ----------------------------------------------------------------


def quote(package: ServicePackage, service: Service, quantity: int) -> dict[str, Decimal | int]:
    """Work out the money for a booking.

    Rounded to paisa with ROUND_HALF_UP (banker's rounding would surprise
    people reading an invoice). Payout is derived by subtraction so commission
    plus payout always equals the total exactly, with no rounding drift.
    """
    unit_price = Decimal(package.price)
    total = (unit_price * quantity).quantize(TWO_DP, rounding=ROUND_HALF_UP)
    rate = Decimal(service.commission_rate)
    commission = (total * rate).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    return {
        "unit_price": unit_price,
        "quantity": quantity,
        "total_amount": total,
        "commission_rate": rate,
        "commission_amount": commission,
        "worker_payout": total - commission,
        "duration_minutes": package.duration_minutes * quantity,
    }


def _generate_reference() -> str:
    """SJ-260806-K4T2 — short enough to read over the phone."""
    stamp = datetime.now(UTC).strftime("%y%m%d")
    suffix = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
    return f"SJ-{stamp}-{suffix}"


# --- creation ---------------------------------------------------------------


async def create_booking(
    db: AsyncSession,
    *,
    customer: User,
    package_id: uuid.UUID,
    address_id: uuid.UUID,
    scheduled_at: datetime,
    quantity: int = 1,
    notes: str | None = None,
) -> Booking:
    package = await db.get(ServicePackage, package_id)
    if package is None or not package.is_active:
        raise NotFoundError("That service option is not available.", code="PACKAGE_NOT_FOUND")

    service = await db.get(Service, package.service_id)
    if service is None or not service.is_active:
        raise NotFoundError("That service is not available.", code="SERVICE_NOT_FOUND")

    address = await db.get(CustomerAddress, address_id)
    if address is None or address.is_deleted or address.user_id != customer.id:
        raise NotFoundError("Address not found.", code="ADDRESS_NOT_FOUND")

    if scheduled_at <= datetime.now(UTC):
        raise AppError("Pick a time in the future.", code="SCHEDULE_IN_PAST")

    priced = quote(package, service, quantity)

    booking = Booking(
        reference=_generate_reference(),
        customer_id=customer.id,
        service_id=service.id,
        package_id=package.id,
        address_id=address.id,
        status=BookingStatus.PENDING,
        scheduled_at=scheduled_at,
        notes=notes,
        service_name=service.name,
        package_name=package.name,
        warranty_days=service.warranty_days,
        **priced,
    )
    db.add(booking)
    await db.flush()

    # Cash on completion is the default; online payment lands in a later module.
    db.add(
        Payment(
            booking_id=booking.id,
            method=PaymentMethod.CASH,
            status=PaymentStatus.PENDING,
            amount=booking.total_amount,
        )
    )
    _record(db, booking, None, BookingStatus.PENDING, "create", customer)
    await db.flush()

    log.info(
        "booking.created",
        booking_id=str(booking.id),
        reference=booking.reference,
        service=service.name,
        total=str(booking.total_amount),
    )
    return booking


# --- transitions ------------------------------------------------------------


def _record(
    db: AsyncSession,
    booking: Booking,
    from_status: BookingStatus | None,
    to_status: BookingStatus,
    action: str,
    actor: User | None,
    note: str | None = None,
) -> None:
    """Append to the audit trail.

    Adds the row straight to the session rather than through
    `booking.history.append()`. Touching that collection on a flushed booking
    triggers a lazy load, which is illegal on an async session.
    """
    db.add(
        BookingStatusHistory(
            booking_id=booking.id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            action=action,
            actor_id=actor.id if actor else None,
            actor_role=actor.role.value if actor else None,
            note=note,
        )
    )


async def transition(
    db: AsyncSession,
    booking: Booking,
    action: str,
    *,
    actor: User,
    note: str | None = None,
) -> Booking:
    """Move a booking along its lifecycle.

    The legal moves live in BOOKING_TRANSITIONS, so an illegal jump is rejected
    here rather than depending on every caller remembering the rules.
    """
    allowed_from, to_status = BOOKING_TRANSITIONS[action]

    if booking.status not in allowed_from:
        raise InvalidTransitionError(
            f"Cannot {action.replace('_', ' ')} a booking that is {booking.status.value}.",
            details={"current_status": booking.status.value, "action": action},
        )

    from_status = booking.status
    booking.status = to_status
    now = datetime.now(UTC)

    if action == "assign":
        booking.assigned_at = now
    elif action == "claim":
        booking.assigned_at = now
        booking.accepted_at = now
    elif action == "accept":
        booking.accepted_at = now
    elif action == "reject":
        # Back into the pool, and the worker is detached so they are not
        # offered the same job again by the dispatch board.
        booking.worker_id = None
        booking.assigned_at = None
    elif action == "start_work":
        booking.started_at = now
    elif action == "complete":
        booking.completed_at = now
    elif action == "close":
        booking.closed_at = now
    elif action == "cancel":
        booking.cancelled_at = now
        booking.cancellation_reason = note

    _record(db, booking, from_status, to_status, action, actor, note)
    await db.flush()

    log.info(
        "booking.transition",
        booking_id=str(booking.id),
        reference=booking.reference,
        action=action,
        **{"from": from_status.value, "to": to_status.value},
    )
    return booking


async def assign_worker(
    db: AsyncSession, booking: Booking, worker_user_id: uuid.UUID, *, actor: User
) -> Booking:
    """Attach a worker and move the booking to ASSIGNED."""
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == worker_user_id))
    if profile is None:
        raise NotFoundError("Worker not found.", code="WORKER_NOT_FOUND")

    if not profile.is_assignable:
        raise WorkerNotAssignableError(
            "This worker is not verified or is currently unavailable.",
            details={
                "verification_status": profile.verification_status.value,
                "is_available": profile.is_available,
            },
        )

    # A plumber must never be dispatched to an AC job.
    cleared = await db.scalar(
        select(WorkerService.id).where(
            WorkerService.worker_profile_id == profile.id,
            WorkerService.service_id == booking.service_id,
        )
    )
    if cleared is None:
        raise WorkerNotAssignableError(
            f"This worker is not cleared for {booking.service_name}.",
            code="SERVICE_NOT_CLEARED",
        )

    booking.worker_id = worker_user_id
    return await transition(db, booking, "assign", actor=actor)


async def eligible_worker_profile(db: AsyncSession, worker_user_id: uuid.UUID) -> WorkerProfile:
    """The worker's profile, refusing anyone who may not take work."""
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == worker_user_id))
    if profile is None:
        raise NotFoundError("Worker profile not found.", code="PROFILE_NOT_FOUND")
    if profile.verification_status != WorkerVerificationStatus.VERIFIED:
        raise WorkerNotAssignableError(
            "Your account is still being verified. You will be able to take jobs once "
            "Sajilo has approved it.",
            code="NOT_VERIFIED",
            details={"verification_status": profile.verification_status.value},
        )
    if not profile.is_available:
        raise WorkerNotAssignableError(
            "You are marked unavailable. Turn availability on to take jobs.",
            code="NOT_AVAILABLE",
        )
    return profile


async def open_jobs_for_worker(db: AsyncSession, profile: WorkerProfile) -> list[Booking]:
    """Unclaimed bookings this worker is cleared to do.

    The pool is deliberately narrow: only PENDING jobs with no worker attached,
    and only for services this worker has been cleared for. A worker never sees
    a job they could not legally take.
    """
    service_ids = select(WorkerService.service_id).where(
        WorkerService.worker_profile_id == profile.id
    )
    stmt = (
        with_relations(select(Booking))
        .where(
            Booking.status == BookingStatus.PENDING,
            Booking.worker_id.is_(None),
            Booking.service_id.in_(service_ids),
        )
        .order_by(Booking.scheduled_at)
    )
    return list((await db.scalars(stmt)).unique().all())


async def claim_booking(db: AsyncSession, booking_id: uuid.UUID, *, worker: User) -> Booking:
    """A worker takes an open job for themselves.

    Two workers hitting "Accept" on the same job at the same moment is the
    normal case, not the rare one, so the row is locked before its status is
    read. The loser gets a clean 409 instead of silently overwriting the
    winner's claim.
    """
    profile = await eligible_worker_profile(db, worker.id)

    # noload("*") strips the model's default joined eager loads: Postgres
    # refuses FOR UPDATE on the nullable side of an outer join, and the lock is
    # the whole point here. serialize() gets its relationships from reload().
    booking = await db.scalar(
        select(Booking).where(Booking.id == booking_id).options(noload("*")).with_for_update()
    )
    if booking is None:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")

    if booking.status != BookingStatus.PENDING or booking.worker_id is not None:
        raise ConflictError("Another professional already took this job.", code="JOB_ALREADY_TAKEN")

    cleared = await db.scalar(
        select(WorkerService.id).where(
            WorkerService.worker_profile_id == profile.id,
            WorkerService.service_id == booking.service_id,
        )
    )
    if cleared is None:
        raise WorkerNotAssignableError(
            f"You are not cleared for {booking.service_name}.", code="SERVICE_NOT_CLEARED"
        )

    booking.worker_id = worker.id
    return await transition(db, booking, "claim", actor=worker)


async def complete_booking(
    db: AsyncSession, booking: Booking, *, actor: User, cash_collected: bool
) -> Booking:
    """Worker marks the job done and confirms whether cash was taken.

    Finished work that has been paid for closes here and now. Waiting for the
    customer's rating to close it made the rating load-bearing: a customer who
    never opened the app left the job sitting in `completed` forever, which
    kept it on the dispatch board, out of the earnings total, and looking
    unfinished to everyone involved. A rating is feedback, not settlement.

    Unpaid work is the one case that stays open — the money has not changed
    hands, so the job genuinely is not done with.
    """
    await transition(db, booking, "complete", actor=actor)

    payment = booking.payment
    if payment is not None and cash_collected:
        payment.status = PaymentStatus.PAID
        payment.paid_at = datetime.now(UTC)

    if booking.worker_id:
        profile = await db.scalar(
            select(WorkerProfile).where(WorkerProfile.user_id == booking.worker_id)
        )
        if profile is not None:
            profile.jobs_completed += 1

    if is_settled(booking):
        await transition(db, booking, "close", actor=actor, note="Work finished and paid")

    await db.flush()
    return booking


def is_settled(booking: Booking) -> bool:
    """Has the money for this booking actually been taken?

    A booking with no payment row is treated as settled rather than stuck:
    every booking gets one at creation, so a missing row is a data fault, and
    blocking the lifecycle on it would strand the job with no way forward.
    """
    return booking.payment is None or booking.payment.status == PaymentStatus.PAID


REVIEWABLE_STATUSES = (BookingStatus.COMPLETED, BookingStatus.CLOSED)


async def submit_review(
    db: AsyncSession, booking: Booking, *, customer: User, rating: int, comment: str | None
) -> Booking:
    """Rate a finished booking.

    Rating no longer drives the lifecycle — a paid job has already closed
    itself — so this is pure feedback and can arrive whenever the customer
    gets round to it. The one case where it still closes the booking is
    unpaid work the customer rates anyway: the transition table refuses the
    jump from any other status, but that path is worth keeping.

    Because closing is no longer what guards this, the status check has to be
    explicit. Without it a booking still in progress could be rated.
    """
    if booking.status not in REVIEWABLE_STATUSES:
        raise ConflictError("This job is not finished yet.", code="NOT_REVIEWABLE")
    if booking.review is not None:
        raise ConflictError("This booking has already been rated.", code="ALREADY_REVIEWED")
    if booking.worker_id is None:
        raise AppError("This booking has no worker to rate.", code="NO_WORKER")

    db.add(
        Review(
            booking_id=booking.id,
            customer_id=customer.id,
            worker_id=booking.worker_id,
            rating=rating,
            comment=comment,
        )
    )
    await db.flush()

    # Recompute from the reviews table rather than nudging a running average,
    # so a corrected or deleted review cannot leave the aggregate wrong.
    profile = await db.scalar(
        select(WorkerProfile).where(WorkerProfile.user_id == booking.worker_id)
    )
    if profile is not None:
        stats = (
            await db.execute(
                select(func.avg(Review.rating), func.count(Review.id)).where(
                    Review.worker_id == booking.worker_id
                )
            )
        ).one()
        profile.rating_avg = Decimal(stats[0] or 0).quantize(TWO_DP)
        profile.rating_count = stats[1]

    # Already closed in the normal (paid) case; this only fires for unpaid work
    # the customer chose to rate.
    if booking.status == BookingStatus.COMPLETED:
        await transition(db, booking, "close", actor=customer, note=f"Rated {rating}/5")

    return booking


# --- access control ---------------------------------------------------------


def assert_can_view(booking: Booking, user: User) -> None:
    """Customers see their own bookings, workers see theirs, admins see all."""
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.CUSTOMER and booking.customer_id == user.id:
        return
    if user.role == UserRole.WORKER and booking.worker_id == user.id:
        return
    # 404 rather than 403: confirming a booking exists is itself a leak.
    raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")


def assert_is_assigned_worker(booking: Booking, user: User) -> None:
    if booking.worker_id != user.id:
        raise PermissionDeniedError("This job is not assigned to you.", code="NOT_YOUR_JOB")


# --- loading ----------------------------------------------------------------

# serialize() is synchronous, so every relationship it touches must already be
# loaded — a lazy load there raises MissingGreenlet. These options make that
# explicit instead of relying on the models' default strategies, which do not
# survive a refresh() of an object built during this request.
_LOAD_OPTIONS = (
    joinedload(Booking.customer),
    joinedload(Booking.worker),
    joinedload(Booking.address),
    selectinload(Booking.worker_profile),
    selectinload(Booking.payment),
    selectinload(Booking.review),
    selectinload(Booking.history),
)


def with_relations(stmt: Select) -> Select:
    """Apply the eager loads serialize() needs to a bookings query."""
    return stmt.options(*_LOAD_OPTIONS)


async def reload(db: AsyncSession, booking_id: uuid.UUID) -> Booking:
    """Re-read a booking with everything serialize() will touch.

    populate_existing is essential: the session keeps objects alive after
    commit (expire_on_commit=False), so without it SQLAlchemy hands back the
    identity-mapped booking with its *stale* relationships — an assign would
    respond with worker=null, a review with review=null.
    """
    booking = await db.scalar(
        with_relations(select(Booking))
        .where(Booking.id == booking_id)
        .execution_options(populate_existing=True)
    )
    if booking is None:
        raise NotFoundError("Booking not found.", code="BOOKING_NOT_FOUND")
    return booking


# --- serialisation ----------------------------------------------------------

# Phone numbers are exchanged only while a job is actually live. Before
# assignment there is nobody to call; after closing, the reason to call is
# gone and support should handle it instead.
_CONTACT_VISIBLE_STATUSES = (
    BookingStatus.ASSIGNED,
    BookingStatus.ACCEPTED,
    BookingStatus.EN_ROUTE,
    BookingStatus.IN_PROGRESS,
    BookingStatus.COMPLETED,
)


def serialize(booking: Booking, viewer: User) -> BookingRead:
    """Build the response for one booking, filtered to what `viewer` may see."""
    is_admin = viewer.role == UserRole.ADMIN
    share_contacts = is_admin or booking.status in _CONTACT_VISIBLE_STATUSES

    data = BookingRead.model_validate(booking)
    data.address = AddressRead.model_validate(booking.address)

    data.customer = PersonRead(
        id=booking.customer.id,
        full_name=booking.customer.full_name,
        phone=booking.customer.phone if share_contacts else None,
        avatar_url=booking.customer.avatar_url,
    )

    if booking.worker is not None:
        profile = booking.worker_profile
        data.worker = PersonRead(
            id=booking.worker.id,
            full_name=booking.worker.full_name,
            phone=booking.worker.phone if share_contacts else None,
            avatar_url=booking.worker.avatar_url,
            rating_avg=profile.rating_avg if profile else None,
            jobs_completed=profile.jobs_completed if profile else None,
        )

    # Customers are quoted one number: the price. What Sajilo takes out of it
    # is between us and the worker.
    if viewer.role == UserRole.CUSTOMER:
        data.commission_amount = None
        data.worker_payout = None

    return data
