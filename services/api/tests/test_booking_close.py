"""Closing a booking, and where the rating sits relative to it.

Rating used to be the only way a job ever reached `closed`. That made a piece
of optional feedback load-bearing: a customer who never opened the app left
the job stuck in `completed` forever — still on the dispatch board, still
looking unfinished to the worker. Settlement and feedback are now separate,
and these tests pin down the seam between them.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkerVerificationStatus
from app.models.worker import WorkerProfile
from app.services.catalog_seed import seed_catalog
from tests.conftest import clear_otp_cooldown, login_with_otp

pytestmark = pytest.mark.anyio

CUSTOMER = "+9779841000100"
CLEANER = "+9779841000001"


async def _sign_in(client: AsyncClient, phone: str, role: str) -> dict[str, str]:
    await clear_otp_cooldown(phone)
    session = await login_with_otp(client, phone, role)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _verify_worker(db: AsyncSession, phone: str, slugs: list[str]) -> None:
    from app.models.catalog import Service
    from app.models.user import User
    from app.models.worker import WorkerService

    user = await db.scalar(select(User).where(User.phone == phone))
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    profile.verification_status = WorkerVerificationStatus.VERIFIED
    profile.is_available = True
    for slug in slugs:
        service = await db.scalar(select(Service).where(Service.slug == slug))
        db.add(WorkerService(worker_profile_id=profile.id, service_id=service.id))
    await db.commit()


async def _place_order(client: AsyncClient, headers: dict[str, str], slug: str) -> dict:
    services = (await client.get("/catalog/services")).json()
    service = next(s for s in services if s["slug"] == slug)
    cities = (await client.get("/catalog/cities")).json()
    address = await client.post(
        "/addresses",
        headers=headers,
        json={"city_id": cities[0]["id"], "label": "Home", "area": "Baluwatar"},
    )
    created = await client.post(
        "/bookings",
        headers=headers,
        json={"package_id": service["packages"][0]["id"], "address_id": address.json()["id"]},
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _run_to_completion(
    client: AsyncClient, db: AsyncSession, *, cash_collected: bool
) -> tuple[dict, dict[str, str], dict[str, str]]:
    """Place an order and drive it to the point the worker finishes."""
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")

    worker = await _sign_in(client, CLEANER, "worker")
    await _verify_worker(db, CLEANER, ["house-cleaning"])

    await client.post(f"/worker/available-jobs/{booking['id']}/claim", headers=worker)
    await client.post(f"/worker/jobs/{booking['id']}/start", headers=worker)
    done = await client.post(
        f"/worker/jobs/{booking['id']}/complete",
        headers=worker,
        json={"cash_collected": cash_collected},
    )
    assert done.status_code == 200, done.text
    return done.json(), customer, worker


@pytest.fixture
async def catalog(db: AsyncSession) -> None:
    await seed_catalog(db)


async def test_paid_work_closes_without_waiting_for_a_rating(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    done, customer, _ = await _run_to_completion(client, db, cash_collected=True)

    assert done["status"] == "closed"
    assert done["closed_at"] is not None
    assert done["review"] is None  # closed, and nobody has rated it

    # The audit trail records who closed it and why, not a silent jump.
    moves = [(e["action"], e["to_status"]) for e in done["history"]]
    assert ("complete", "completed") in moves
    assert ("close", "closed") in moves

    # And it really is closed when read back fresh, not just in this response.
    again = await client.get(f"/bookings/{done['id']}", headers=customer)
    assert again.json()["status"] == "closed"


async def test_unpaid_work_stays_open(client: AsyncClient, db: AsyncSession, catalog: None) -> None:
    """The one thing that still holds a job open is money not changing hands."""
    done, _, _ = await _run_to_completion(client, db, cash_collected=False)

    assert done["status"] == "completed"
    assert done["payment"]["status"] == "pending"
    assert done["closed_at"] is None


async def test_rating_unpaid_work_still_closes_it(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    done, customer, _ = await _run_to_completion(client, db, cash_collected=False)
    assert done["status"] == "completed"

    rated = await client.post(
        f"/bookings/{done['id']}/review", headers=customer, json={"rating": 4}
    )
    assert rated.status_code == 200, rated.text
    assert rated.json()["status"] == "closed"
    assert rated.json()["review"]["rating"] == 4


async def test_a_closed_booking_can_still_be_rated(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    """The whole point: the rating arrives after the job is already settled."""
    done, customer, worker = await _run_to_completion(client, db, cash_collected=True)
    assert done["status"] == "closed"

    rated = await client.post(
        f"/bookings/{done['id']}/review",
        headers=customer,
        json={"rating": 5, "comment": "On time and tidy."},
    )
    assert rated.status_code == 200, rated.text
    assert rated.json()["status"] == "closed"
    assert rated.json()["review"]["rating"] == 5
    assert rated.json()["review"]["comment"] == "On time and tidy."

    # The worker's public rating reflects it.
    profile = (await client.get("/worker/profile", headers=worker)).json()
    assert float(profile["rating_avg"]) == 5.0
    assert profile["rating_count"] == 1


async def test_a_booking_cannot_be_rated_twice(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    done, customer, _ = await _run_to_completion(client, db, cash_collected=True)
    first = await client.post(
        f"/bookings/{done['id']}/review", headers=customer, json={"rating": 5}
    )
    assert first.status_code == 200

    second = await client.post(
        f"/bookings/{done['id']}/review", headers=customer, json={"rating": 1}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_REVIEWED"


async def test_unfinished_work_cannot_be_rated(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    """Closing used to be the thing that guarded this, so it is now explicit."""
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")

    # Still pending — no worker has even taken it.
    too_early = await client.post(
        f"/bookings/{booking['id']}/review", headers=customer, json={"rating": 5}
    )
    assert too_early.status_code == 409
    assert too_early.json()["error"]["code"] == "NOT_REVIEWABLE"

    worker = await _sign_in(client, CLEANER, "worker")
    await _verify_worker(db, CLEANER, ["house-cleaning"])
    await client.post(f"/worker/available-jobs/{booking['id']}/claim", headers=worker)
    await client.post(f"/worker/jobs/{booking['id']}/start", headers=worker)

    # Mid-job is no better.
    mid_job = await client.post(
        f"/bookings/{booking['id']}/review", headers=customer, json={"rating": 5}
    )
    assert mid_job.status_code == 409
    assert mid_job.json()["error"]["code"] == "NOT_REVIEWABLE"


async def test_closed_jobs_count_towards_earnings(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    """Auto-closing must not drop the job out of the worker's payout total."""
    done, _, worker = await _run_to_completion(client, db, cash_collected=True)

    earnings = (await client.get("/worker/earnings", headers=worker)).json()
    assert earnings["jobs_completed"] == 1
    assert float(earnings["gross_amount"]) == float(done["total_amount"])
