"""Domain enums.

Stored as native Postgres enums. `values_callable` makes SQLAlchemy persist the
lowercase *values* ("customer") rather than the Python member names
("CUSTOMER"), which keeps raw SQL and admin queries readable.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    WORKER = "worker"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    # Set by an admin: the user keeps their data but cannot obtain a token.
    SUSPENDED = "suspended"
    # Soft-deleted on user request; phone is released for re-registration.
    DELETED = "deleted"


class BookingStatus(StrEnum):
    PENDING = "pending"  # created, waiting for a worker to be assigned
    ASSIGNED = "assigned"  # a worker has been chosen, awaiting their acceptance
    ACCEPTED = "accepted"  # worker took the job
    EN_ROUTE = "en_route"  # worker travelling to the customer
    IN_PROGRESS = "in_progress"  # work started
    COMPLETED = "completed"  # work finished, awaiting the customer's rating
    CLOSED = "closed"  # terminal: rated and settled
    CANCELLED = "cancelled"  # terminal


# Which statuses each transition may start from, and where it lands. The whole
# lifecycle lives here so an illegal jump is impossible rather than merely
# unlikely — see app/services/booking.py.
BOOKING_TRANSITIONS: dict[str, tuple[tuple[BookingStatus, ...], BookingStatus]] = {
    "assign": ((BookingStatus.PENDING,), BookingStatus.ASSIGNED),
    # A verified worker taking an open job themselves. Skips ASSIGNED: nobody
    # dispatched it, so there is no offer left to accept.
    "claim": ((BookingStatus.PENDING,), BookingStatus.ACCEPTED),
    "accept": ((BookingStatus.ASSIGNED,), BookingStatus.ACCEPTED),
    "reject": ((BookingStatus.ASSIGNED,), BookingStatus.PENDING),
    "start_travel": ((BookingStatus.ACCEPTED,), BookingStatus.EN_ROUTE),
    "start_work": ((BookingStatus.ACCEPTED, BookingStatus.EN_ROUTE), BookingStatus.IN_PROGRESS),
    "complete": ((BookingStatus.IN_PROGRESS,), BookingStatus.COMPLETED),
    "close": ((BookingStatus.COMPLETED,), BookingStatus.CLOSED),
    "cancel": (
        (
            BookingStatus.PENDING,
            BookingStatus.ASSIGNED,
            BookingStatus.ACCEPTED,
            BookingStatus.EN_ROUTE,
        ),
        BookingStatus.CANCELLED,
    ),
}

TERMINAL_BOOKING_STATUSES = (BookingStatus.CLOSED, BookingStatus.CANCELLED)


class ServiceRequestStatus(StrEnum):
    """A verified worker asking to be cleared for another trade."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # The worker changed their mind before support got to it.
    WITHDRAWN = "withdrawn"


class PaymentMethod(StrEnum):
    CASH = "cash"
    ESEWA = "esewa"
    KHALTI = "khalti"
    FONEPAY = "fonepay"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class WorkerVerificationStatus(StrEnum):
    PENDING = "pending"  # registered, nothing submitted
    UNDER_REVIEW = "under_review"  # documents submitted, admin reviewing
    VERIFIED = "verified"  # may receive bookings
    REJECTED = "rejected"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        native_enum=True,
    )
