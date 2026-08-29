"""End-to-end booking lifecycle: order placed, worker takes it, job closed.

These exercise the API the apps actually call, not the service layer directly,
so a broken route or a wrong permission shows up here rather than in staging.
"""

import asyncio

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
PLUMBER = "+9779841000004"


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _sign_in(client: AsyncClient, phone: str, role: str) -> dict[str, str]:
    await clear_otp_cooldown(phone)
    return auth(await login_with_otp(client, phone, role))


async def _verify_worker(db: AsyncSession, phone: str, service_slugs: list[str]) -> None:
    """Approve a worker and clear them for the given trades, as an admin would."""
    from app.models.catalog import Service
    from app.models.user import User
    from app.models.worker import WorkerService

    user = await db.scalar(select(User).where(User.phone == phone))
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    profile.verification_status = WorkerVerificationStatus.VERIFIED
    profile.is_available = True

    for slug in service_slugs:
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
        json={
            "city_id": cities[0]["id"],
            "label": "Home",
            "area": "Baluwatar",
            "contact_name": "Test Customer",
            "contact_phone": CUSTOMER,
        },
    )
    assert address.status_code == 201, address.text

    created = await client.post(
        "/bookings",
        headers=headers,
        json={
            "package_id": service["packages"][0]["id"],
            "address_id": address.json()["id"],
            "notes": "Test order",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.fixture
async def catalog(db: AsyncSession) -> None:
    await seed_catalog(db)


async def test_worker_claims_a_job_and_runs_it_to_close(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")
    assert booking["status"] == "pending"
    assert booking["worker"] is None
    # Customers are quoted the price, never our cut of it.
    assert booking["commission_amount"] is None

    worker = await _sign_in(client, CLEANER, "worker")
    await _verify_worker(db, CLEANER, ["house-cleaning"])

    pool = await client.get("/worker/available-jobs", headers=worker)
    assert [b["id"] for b in pool.json()] == [booking["id"]]

    claimed = await client.post(f"/worker/available-jobs/{booking['id']}/claim", headers=worker)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "accepted"
    # The worker is told their payout; the customer is not.
    assert claimed.json()["worker_payout"] is not None

    # Claimed jobs leave the pool.
    assert (await client.get("/worker/available-jobs", headers=worker)).json() == []

    for step, expected in (("start-travel", "en_route"), ("start", "in_progress")):
        moved = await client.post(f"/worker/jobs/{booking['id']}/{step}", headers=worker)
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == expected

    done = await client.post(
        f"/worker/jobs/{booking['id']}/complete", headers=worker, json={"cash_collected": True}
    )
    # Finished and paid closes the job then and there. It does not wait for a
    # rating the customer may never give.
    assert done.json()["status"] == "closed"
    assert done.json()["payment"]["status"] == "paid"
    assert done.json()["closed_at"] is not None

    rated = await client.post(
        f"/bookings/{booking['id']}/review", headers=customer, json={"rating": 5}
    )
    assert rated.status_code == 200, rated.text
    assert rated.json()["status"] == "closed"
    assert rated.json()["review"]["rating"] == 5

    earnings = (await client.get("/worker/earnings", headers=worker)).json()
    assert earnings["jobs_completed"] == 1
    assert float(earnings["gross_amount"]) == float(booking["total_amount"])
    # Commission plus payout must reconcile to the total exactly.
    assert float(earnings["net_earnings"]) + float(earnings["commission_deducted"]) == float(
        earnings["gross_amount"]
    )


async def test_worker_cannot_see_or_claim_another_trade(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")

    plumber = await _sign_in(client, PLUMBER, "worker")
    await _verify_worker(db, PLUMBER, ["plumber"])

    assert (await client.get("/worker/available-jobs", headers=plumber)).json() == []

    refused = await client.post(f"/worker/available-jobs/{booking['id']}/claim", headers=plumber)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "SERVICE_NOT_CLEARED"


async def test_unverified_worker_is_locked_out_of_the_pool(
    client: AsyncClient, catalog: None
) -> None:
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")

    worker = await _sign_in(client, CLEANER, "worker")  # signs up as PENDING

    assert (await client.get("/worker/available-jobs", headers=worker)).json() == []
    refused = await client.post(f"/worker/available-jobs/{booking['id']}/claim", headers=worker)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "NOT_VERIFIED"


async def test_only_one_worker_wins_a_contested_job(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    """Two workers hitting Accept together is the normal case, not the rare one."""
    customer = await _sign_in(client, CUSTOMER, "customer")
    booking = await _place_order(client, customer, "house-cleaning")

    first = await _sign_in(client, CLEANER, "worker")
    await _verify_worker(db, CLEANER, ["house-cleaning"])
    second = await _sign_in(client, "+9779841000002", "worker")
    await _verify_worker(db, "+9779841000002", ["house-cleaning"])

    path = f"/worker/available-jobs/{booking['id']}/claim"
    responses = await asyncio.gather(
        client.post(path, headers=first),
        client.post(path, headers=second),
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409]

    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"]["code"] == "JOB_ALREADY_TAKEN"


async def test_worker_picks_their_own_trades(client: AsyncClient, catalog: None) -> None:
    worker = await _sign_in(client, CLEANER, "worker")
    services = (await client.get("/catalog/services")).json()
    chosen = [services[0]["id"], services[1]["id"]]

    updated = await client.put("/worker/services", headers=worker, json={"service_ids": chosen})
    assert updated.status_code == 200, updated.text
    assert sorted(s["service_id"] for s in updated.json()["services"]) == sorted(chosen)

    # Replacing the list drops what is no longer selected.
    trimmed = await client.put(
        "/worker/services", headers=worker, json={"service_ids": [services[1]["id"]]}
    )
    assert [s["service_id"] for s in trimmed.json()["services"]] == [services[1]["id"]]


async def test_customer_cannot_reach_the_worker_or_admin_surface(
    client: AsyncClient, catalog: None
) -> None:
    customer = await _sign_in(client, CUSTOMER, "customer")

    for path in ("/worker/available-jobs", "/worker/jobs", "/worker/earnings", "/admin/bookings"):
        blocked = await client.get(path, headers=customer)
        assert blocked.status_code == 403, f"{path} was not blocked"
