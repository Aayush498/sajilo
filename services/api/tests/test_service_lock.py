"""Trades are declared once during onboarding, and frozen from that moment.

The point of the lock: what an admin reviews is a specific person offering a
specific set of trades. If the list stayed editable, a worker could submit as a
cleaner, sit in the review queue, and quietly become an electrician before
anyone looked — support would approve a list they never actually read, and
somebody would be doing electrical work in a stranger's home on the strength of
it.

Widening the list goes through support instead, which is a review of the
addition rather than a silent swap.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkerVerificationStatus
from app.models.user import User
from app.models.worker import WorkerProfile
from app.services.catalog_seed import seed_catalog
from tests.conftest import clear_otp_cooldown, login_with_otp

pytestmark = pytest.mark.anyio

WORKER = "+9779841000001"
CUSTOMER = "+9779841000100"
ADMIN_EMAIL = "admin@sajilo-test.com"


async def _sign_in(client: AsyncClient, phone: str, role: str) -> dict[str, str]:
    await clear_otp_cooldown(phone)
    session = await login_with_otp(client, phone, role)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def _admin(client: AsyncClient, admin_user: User) -> dict[str, str]:
    res = await client.post(
        "/auth/admin/login", json={"email": admin_user.email, "password": "AdminPass123!"}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def _service_id(client: AsyncClient, slug: str) -> str:
    services = (await client.get("/catalog/services")).json()
    return next(s["id"] for s in services if s["slug"] == slug)


async def _verify(db: AsyncSession, phone: str) -> None:
    user = await db.scalar(select(User).where(User.phone == phone))
    profile = await db.scalar(select(WorkerProfile).where(WorkerProfile.user_id == user.id))
    profile.verification_status = WorkerVerificationStatus.VERIFIED
    await db.commit()


@pytest.fixture
async def catalog(db: AsyncSession) -> None:
    await seed_catalog(db)


async def test_a_new_worker_starts_with_nothing_declared(
    client: AsyncClient, catalog: None
) -> None:
    """An empty, unlocked list is how the client knows onboarding is unfinished."""
    worker = await _sign_in(client, WORKER, "worker")

    profile = (await client.get("/worker/profile", headers=worker)).json()
    assert profile["services"] == []
    assert profile["services_locked"] is False
    assert profile["verification_status"] == "pending"


async def test_declaring_trades_locks_them_immediately(client: AsyncClient, catalog: None) -> None:
    """Locked on submission, not on approval.

    Locking only at approval left a window where the thing under review could
    change underneath the reviewer.
    """
    worker = await _sign_in(client, WORKER, "worker")
    cleaning = await _service_id(client, "house-cleaning")
    electrician = await _service_id(client, "electrician")

    saved = await client.put("/worker/services", headers=worker, json={"service_ids": [cleaning]})
    assert saved.status_code == 200, saved.text
    assert len(saved.json()["services"]) == 1
    # Locked straight away, while still unverified.
    assert saved.json()["services_locked"] is True
    assert saved.json()["verification_status"] == "pending"

    # Cannot widen it...
    widened = await client.put(
        "/worker/services", headers=worker, json={"service_ids": [cleaning, electrician]}
    )
    assert widened.status_code == 409
    assert widened.json()["error"]["code"] == "SERVICES_LOCKED"

    # ...and cannot swap it for something else either.
    swapped = await client.put(
        "/worker/services", headers=worker, json={"service_ids": [electrician]}
    )
    assert swapped.status_code == 409

    # The list really is unchanged, not merely reported as such.
    after = (await client.get("/worker/profile", headers=worker)).json()
    assert [s["service_id"] for s in after["services"]] == [cleaning]


async def test_an_empty_declaration_is_refused(client: AsyncClient, catalog: None) -> None:
    """Nothing to offer is not an answer to "what do you do?"."""
    worker = await _sign_in(client, WORKER, "worker")

    empty = await client.put("/worker/services", headers=worker, json={"service_ids": []})
    assert empty.status_code == 422

    # And it did not half-apply: onboarding is still open.
    profile = (await client.get("/worker/profile", headers=worker)).json()
    assert profile["services"] == []
    assert profile["services_locked"] is False


async def test_the_lock_survives_verification(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    worker = await _sign_in(client, WORKER, "worker")
    cleaning = await _service_id(client, "house-cleaning")
    electrician = await _service_id(client, "electrician")
    await client.put("/worker/services", headers=worker, json={"service_ids": [cleaning]})

    await _verify(db, WORKER)

    assert (await client.get("/worker/profile", headers=worker)).json()["services_locked"] is True
    widened = await client.put(
        "/worker/services", headers=worker, json={"service_ids": [cleaning, electrician]}
    )
    assert widened.status_code == 409
    assert widened.json()["error"]["code"] == "SERVICES_LOCKED"


async def test_approved_request_clears_the_trade_immediately(
    client: AsyncClient, db: AsyncSession, admin_user: User, catalog: None
) -> None:
    worker = await _sign_in(client, WORKER, "worker")
    cleaning = await _service_id(client, "house-cleaning")
    electrician = await _service_id(client, "electrician")
    await client.put("/worker/services", headers=worker, json={"service_ids": [cleaning]})
    await _verify(db, WORKER)

    asked = await client.post(
        "/worker/service-requests",
        headers=worker,
        json={"service_id": electrician, "note": "Three years of wiring work."},
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["status"] == "pending"
    request_id = asked.json()["id"]

    admin = await _admin(client, admin_user)
    queue = await client.get("/admin/service-requests", headers=admin)
    assert [r["id"] for r in queue.json()] == [request_id]
    assert queue.json()[0]["service_name"] == "Electrician"
    assert queue.json()[0]["worker_phone"] == WORKER

    decided = await client.post(
        f"/admin/service-requests/{request_id}/decide",
        headers=admin,
        json={"approve": True, "note": "Certificate seen."},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"

    # Immediately, with no second step for anyone to forget.
    profile = (await client.get("/worker/profile", headers=worker)).json()
    assert len(profile["services"]) == 2
    assert profile["services_locked"] is True


async def test_rejected_request_changes_nothing_but_can_be_retried(
    client: AsyncClient, db: AsyncSession, admin_user: User, catalog: None
) -> None:
    worker = await _sign_in(client, WORKER, "worker")
    cleaning = await _service_id(client, "house-cleaning")
    electrician = await _service_id(client, "electrician")
    await client.put("/worker/services", headers=worker, json={"service_ids": [cleaning]})
    await _verify(db, WORKER)

    request_id = (
        await client.post(
            "/worker/service-requests", headers=worker, json={"service_id": electrician}
        )
    ).json()["id"]

    admin = await _admin(client, admin_user)
    refused = await client.post(
        f"/admin/service-requests/{request_id}/decide",
        headers=admin,
        json={"approve": False, "note": "Send your certificate."},
    )
    assert refused.json()["status"] == "rejected"
    # The worker is told why.
    assert refused.json()["decision_note"] == "Send your certificate."
    assert len((await client.get("/worker/profile", headers=worker)).json()["services"]) == 1

    # A rejection is not a life sentence — the partial unique index covers
    # pending rows only, so re-applying works.
    again = await client.post(
        "/worker/service-requests", headers=worker, json={"service_id": electrician}
    )
    assert again.status_code == 201, again.text


async def test_duplicate_and_pointless_requests_are_refused(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    worker = await _sign_in(client, WORKER, "worker")
    cleaning = await _service_id(client, "house-cleaning")
    electrician = await _service_id(client, "electrician")
    await client.put("/worker/services", headers=worker, json={"service_ids": [cleaning]})
    await _verify(db, WORKER)

    first = await client.post(
        "/worker/service-requests", headers=worker, json={"service_id": electrician}
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/worker/service-requests", headers=worker, json={"service_id": electrician}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "REQUEST_PENDING"

    already = await client.post(
        "/worker/service-requests", headers=worker, json={"service_id": cleaning}
    )
    assert already.status_code == 409
    assert already.json()["error"]["code"] == "ALREADY_CLEARED"


async def test_a_request_cannot_be_decided_twice(
    client: AsyncClient, db: AsyncSession, admin_user: User, catalog: None
) -> None:
    worker = await _sign_in(client, WORKER, "worker")
    electrician = await _service_id(client, "electrician")
    await _verify(db, WORKER)
    request_id = (
        await client.post(
            "/worker/service-requests", headers=worker, json={"service_id": electrician}
        )
    ).json()["id"]

    admin = await _admin(client, admin_user)
    body = {"approve": True}
    assert (
        await client.post(f"/admin/service-requests/{request_id}/decide", headers=admin, json=body)
    ).status_code == 200
    second = await client.post(
        f"/admin/service-requests/{request_id}/decide", headers=admin, json=body
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REQUEST_DECIDED"


async def test_a_worker_cannot_touch_someone_elses_request(
    client: AsyncClient, db: AsyncSession, catalog: None
) -> None:
    owner = await _sign_in(client, WORKER, "worker")
    electrician = await _service_id(client, "electrician")
    await _verify(db, WORKER)
    request_id = (
        await client.post(
            "/worker/service-requests", headers=owner, json={"service_id": electrician}
        )
    ).json()["id"]

    other = await _sign_in(client, "+9779841000002", "worker")
    # 404, not 403 — whose request this is, is not the caller's business.
    blocked = await client.post(f"/worker/service-requests/{request_id}/withdraw", headers=other)
    assert blocked.status_code == 404


async def test_customers_cannot_reach_the_request_endpoints(
    client: AsyncClient, catalog: None
) -> None:
    customer = await _sign_in(client, CUSTOMER, "customer")
    assert (await client.get("/worker/service-requests", headers=customer)).status_code == 403
    assert (await client.get("/admin/service-requests", headers=customer)).status_code == 403
