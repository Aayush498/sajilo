from httpx import AsyncClient

from tests.conftest import clear_otp_cooldown, login_with_otp

PHONE = "9841234567"
E164 = "+9779841234567"


async def test_first_otp_login_registers_the_user(client: AsyncClient) -> None:
    session = await login_with_otp(client, PHONE)

    assert session["is_new_user"] is True
    assert session["user"]["phone"] == E164
    assert session["user"]["role"] == "customer"
    assert session["user"]["phone_verified"] is True
    assert session["access_token"] and session["refresh_token"]


async def test_second_login_reuses_the_same_account(client: AsyncClient) -> None:
    first = await login_with_otp(client, PHONE)
    await clear_otp_cooldown(E164)
    second = await login_with_otp(client, "+977 9841234567")  # same number, typed differently

    assert second["is_new_user"] is False
    assert second["user"]["id"] == first["user"]["id"]


async def test_wrong_code_is_rejected_and_reports_attempts_left(client: AsyncClient) -> None:
    await client.post("/auth/request-otp", json={"phone": PHONE})

    response = await client.post("/auth/verify-otp", json={"phone": PHONE, "code": "000000"})

    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "OTP_INVALID"
    assert body["details"]["attempts_left"] == 4


async def test_code_cannot_be_replayed(client: AsyncClient) -> None:
    requested = await client.post("/auth/request-otp", json={"phone": PHONE})
    code = requested.json()["debug_code"]

    first = await client.post("/auth/verify-otp", json={"phone": PHONE, "code": code})
    replay = await client.post("/auth/verify-otp", json={"phone": PHONE, "code": code})

    assert first.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "OTP_EXPIRED"


async def test_resend_is_rate_limited_by_cooldown(client: AsyncClient) -> None:
    first = await client.post("/auth/request-otp", json={"phone": PHONE})
    second = await client.post("/auth/request-otp", json={"phone": PHONE})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "OTP_COOLDOWN"


async def test_worker_number_cannot_sign_in_through_the_customer_app(client: AsyncClient) -> None:
    await login_with_otp(client, PHONE, role="worker")

    await clear_otp_cooldown(E164)
    requested = await client.post("/auth/request-otp", json={"phone": PHONE, "role": "customer"})
    code = requested.json()["debug_code"]

    response = await client.post(
        "/auth/verify-otp", json={"phone": PHONE, "code": code, "role": "customer"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_MISMATCH"


async def test_invalid_phone_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.post("/auth/request-otp", json={"phone": "12345"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PHONE"


# --- refresh rotation -------------------------------------------------------


async def test_refresh_returns_a_new_pair_and_retires_the_old_token(client: AsyncClient) -> None:
    session = await login_with_otp(client, PHONE)

    refreshed = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != session["refresh_token"]


async def test_reusing_a_rotated_token_kills_every_session(client: AsyncClient) -> None:
    session = await login_with_otp(client, PHONE)
    rotated = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})
    new_refresh = rotated.json()["refresh_token"]

    # An attacker replays the token the real client already exchanged.
    replay = await client.post("/auth/refresh", json={"refresh_token": session["refresh_token"]})

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REFRESH_REUSED"

    # ...and the legitimate client's newer token is dead too. Both parties must
    # log in again, which is the safe outcome when we cannot tell them apart.
    after = await client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert after.status_code == 401


async def test_logout_revokes_the_session_and_its_access_token(client: AsyncClient) -> None:
    session = await login_with_otp(client, PHONE)
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    assert (await client.get("/users/me", headers=headers)).status_code == 200

    logout = await client.post("/auth/logout", json={"refresh_token": session["refresh_token"]})
    assert logout.status_code == 204

    # The access token has not expired, but its session is gone.
    after = await client.get("/users/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "SESSION_REVOKED"


# --- admin login ------------------------------------------------------------


async def test_admin_logs_in_with_email_and_password(client: AsyncClient, admin_user) -> None:
    response = await client.post(
        "/auth/admin/login", json={"email": "admin@sajilo-test.com", "password": "AdminPass123!"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


async def test_wrong_admin_password_is_rejected(client: AsyncClient, admin_user) -> None:
    response = await client.post(
        "/auth/admin/login", json={"email": "admin@sajilo-test.com", "password": "WrongPassword1!"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_unknown_admin_email_gives_the_same_error(client: AsyncClient) -> None:
    # Identical response to a wrong password, so the endpoint cannot be used to
    # discover which admin accounts exist.
    response = await client.post(
        "/auth/admin/login", json={"email": "nobody@sajilo-test.com", "password": "WrongPassword1!"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
