from httpx import AsyncClient

from tests.conftest import login_with_otp


async def test_protected_route_requires_a_token(client: AsyncClient) -> None:
    response = await client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/users/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


async def test_customer_cannot_reach_an_admin_route(client: AsyncClient) -> None:
    session = await login_with_otp(client, "9841234567")
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    response = await client.get("/users/admin/ping", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["details"]["required_roles"] == ["admin"]


async def test_worker_cannot_reach_an_admin_route(client: AsyncClient) -> None:
    session = await login_with_otp(client, "9851234567", role="worker")
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    assert (await client.get("/users/admin/ping", headers=headers)).status_code == 403


async def test_admin_can_reach_an_admin_route(client: AsyncClient, admin_user) -> None:
    login = await client.post(
        "/auth/admin/login", json={"email": "admin@sajilo-test.com", "password": "AdminPass123!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get("/users/admin/ping", headers=headers)

    assert response.status_code == 200
    assert response.json()["scope"] == "admin"


async def test_user_can_update_their_own_profile(client: AsyncClient) -> None:
    session = await login_with_otp(client, "9841234567")
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    response = await client.patch(
        "/users/me", headers=headers, json={"full_name": "Aayush Jha", "locale": "ne"}
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Aayush Jha"
    assert response.json()["locale"] == "ne"


async def test_profile_response_never_includes_the_password_hash(
    client: AsyncClient, admin_user
) -> None:
    login = await client.post(
        "/auth/admin/login", json={"email": "admin@sajilo-test.com", "password": "AdminPass123!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    body = (await client.get("/users/me", headers=headers)).json()

    assert "password_hash" not in body
