"""Editing your own profile.

The subtle case throughout is the difference between "I did not mention this
field" and "I am explicitly clearing it". Getting that wrong means a user can
set an email but never remove one.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import clear_otp_cooldown, login_with_otp

pytestmark = pytest.mark.anyio

CUSTOMER = "+9779841000100"
WORKER = "+9779841000001"


async def _sign_in(client: AsyncClient, phone: str, role: str) -> dict[str, str]:
    await clear_otp_cooldown(phone)
    session = await login_with_otp(client, phone, role)
    return {"Authorization": f"Bearer {session['access_token']}"}


async def test_a_new_account_starts_with_no_name(client: AsyncClient) -> None:
    """The UI relies on this to know when to ask for one."""
    headers = await _sign_in(client, CUSTOMER, "customer")
    me = (await client.get("/users/me", headers=headers)).json()
    assert me["full_name"] is None
    assert me["email"] is None


async def test_user_can_edit_name_email_and_language(client: AsyncClient) -> None:
    headers = await _sign_in(client, CUSTOMER, "customer")

    updated = await client.patch(
        "/users/me",
        headers=headers,
        json={"full_name": "Anjali Maharjan", "email": "anjali@example.com", "locale": "ne"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["full_name"] == "Anjali Maharjan"
    assert updated.json()["email"] == "anjali@example.com"
    assert updated.json()["locale"] == "ne"


async def test_email_can_be_cleared_but_name_cannot(client: AsyncClient) -> None:
    headers = await _sign_in(client, CUSTOMER, "customer")
    await client.patch(
        "/users/me", headers=headers, json={"full_name": "Anjali", "email": "a@example.com"}
    )

    # An explicit null clears the email.
    cleared = await client.patch("/users/me", headers=headers, json={"email": None})
    assert cleared.json()["email"] is None
    # ...and leaves everything else alone.
    assert cleared.json()["full_name"] == "Anjali"

    # Clearing a second time must not trip the "already in use" check against
    # other users who also have no email.
    again = await client.patch("/users/me", headers=headers, json={"email": None})
    assert again.status_code == 200, again.text

    # A null name is ignored rather than blanking the account.
    kept = await client.patch("/users/me", headers=headers, json={"full_name": None})
    assert kept.json()["full_name"] == "Anjali"


async def test_email_cannot_be_stolen_from_another_user(client: AsyncClient) -> None:
    first = await _sign_in(client, CUSTOMER, "customer")
    await client.patch("/users/me", headers=first, json={"email": "taken@example.com"})

    second = await _sign_in(client, "+9779841000200", "customer")
    clash = await client.patch("/users/me", headers=second, json={"email": "taken@example.com"})
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_worker_can_edit_bio_and_experience(client: AsyncClient) -> None:
    headers = await _sign_in(client, WORKER, "worker")

    saved = await client.patch(
        "/worker/profile",
        headers=headers,
        json={"bio": "Six years across Kathmandu.", "experience_years": 6},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["bio"] == "Six years across Kathmandu."
    assert saved.json()["experience_years"] == 6

    # A null bio clears it; experience is untouched because it was not sent.
    cleared = await client.patch("/worker/profile", headers=headers, json={"bio": None})
    assert cleared.json()["bio"] is None
    assert cleared.json()["experience_years"] == 6


async def test_experience_years_is_bounded(client: AsyncClient) -> None:
    headers = await _sign_in(client, WORKER, "worker")
    for bad in (-1, 61):
        rejected = await client.patch(
            "/worker/profile", headers=headers, json={"experience_years": bad}
        )
        assert rejected.status_code == 422, f"{bad} was accepted"


async def test_logout_everywhere_kills_the_current_session(client: AsyncClient) -> None:
    headers = await _sign_in(client, CUSTOMER, "customer")
    assert (await client.get("/users/me", headers=headers)).status_code == 200

    ended = await client.post("/auth/logout-all", headers=headers)
    assert ended.status_code == 204

    dead = await client.get("/users/me", headers=headers)
    assert dead.status_code == 401
    assert dead.json()["error"]["code"] == "SESSION_REVOKED"


async def test_customer_can_remove_a_saved_address(client: AsyncClient, db: AsyncSession) -> None:
    from app.services.catalog_seed import seed_catalog

    await seed_catalog(db)
    headers = await _sign_in(client, CUSTOMER, "customer")
    cities = (await client.get("/catalog/cities")).json()

    created = await client.post(
        "/addresses",
        headers=headers,
        json={"city_id": cities[0]["id"], "label": "Home", "area": "Baluwatar"},
    )
    address_id = created.json()["id"]
    assert len((await client.get("/addresses", headers=headers)).json()) == 1

    removed = await client.delete(f"/addresses/{address_id}", headers=headers)
    assert removed.status_code == 204
    assert (await client.get("/addresses", headers=headers)).json() == []
