"""Authentication endpoints.

Customers and workers: phone -> OTP -> session.
Admins: email + password -> session.
"""

from fastapi import APIRouter, status

from app.api.deps import ClientIP, CurrentUser, DbSession
from app.core.logging import get_logger
from app.core.redis import enforce_rate_limit
from app.schemas.auth import (
    AdminLogin,
    AuthSession,
    OTPRequest,
    OTPRequestResponse,
    OTPVerify,
    RefreshRequest,
)
from app.services import auth as auth_service
from app.services import otp as otp_service
from app.utils.phone import mask_phone

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/request-otp",
    response_model=OTPRequestResponse,
    summary="Send a login code to a phone number",
)
async def request_otp(body: OTPRequest, db: DbSession, ip: ClientIP) -> OTPRequestResponse:
    # Two limits: per-phone (stops targeting one victim) and per-IP (stops one
    # script from enumerating many numbers). The per-phone daily cap lives in
    # the OTP service alongside the cooldown.
    await enforce_rate_limit(f"otp:phone:{body.phone}", limit=5, window_seconds=900)
    if ip:
        await enforce_rate_limit(f"otp:ip:{ip}", limit=20, window_seconds=900)

    # Send in the user's saved language if we already know them.
    existing = await auth_service.get_active_user_by_phone(db, body.phone)
    locale = existing.locale if existing else "en"

    issued = await otp_service.issue_otp(body.phone, locale=locale)
    log.info("otp.requested", phone=mask_phone(body.phone), role=body.role.value)

    return OTPRequestResponse(
        message="Verification code sent.",
        expires_in_seconds=issued.expires_in_seconds,
        resend_after_seconds=issued.resend_after_seconds,
        debug_code=issued.debug_code,
    )


@router.post(
    "/verify-otp",
    response_model=AuthSession,
    summary="Verify the code and start a session (registers the user if new)",
)
async def verify_otp(body: OTPVerify, db: DbSession, ip: ClientIP) -> AuthSession:
    await enforce_rate_limit(f"otp:verify:{body.phone}", limit=10, window_seconds=900)

    await otp_service.verify_otp(body.phone, body.code)
    user, is_new = await auth_service.get_or_create_user(db, phone=body.phone, role=body.role)
    session = await auth_service.issue_session(
        db, user, device_label=body.device_label, ip_address=ip, is_new_user=is_new
    )
    await db.commit()

    log.info("auth.login", user_id=str(user.id), role=user.role.value, is_new_user=is_new)
    return session


@router.post("/admin/login", response_model=AuthSession, summary="Admin email + password login")
async def admin_login(body: AdminLogin, db: DbSession, ip: ClientIP) -> AuthSession:
    await enforce_rate_limit(f"login:email:{body.email}", limit=5, window_seconds=900)
    if ip:
        await enforce_rate_limit(f"login:ip:{ip}", limit=20, window_seconds=900)

    user = await auth_service.authenticate_admin(db, email=body.email, password=body.password)
    session = await auth_service.issue_session(
        db, user, device_label=body.device_label, ip_address=ip
    )
    await db.commit()

    log.info("auth.admin_login", user_id=str(user.id))
    return session


@router.post("/refresh", response_model=AuthSession, summary="Exchange a refresh token")
async def refresh(body: RefreshRequest, db: DbSession, ip: ClientIP) -> AuthSession:
    session = await auth_service.rotate_session(db, refresh_token=body.refresh_token, ip_address=ip)
    await db.commit()
    return session


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out this device",
)
async def logout(body: RefreshRequest, db: DbSession) -> None:
    # Deliberately unauthenticated: an expired access token must not stop a
    # client from logging out. Knowing the refresh token is proof enough, and
    # revoking a token you already hold grants no advantage.
    await auth_service.revoke_session(db, refresh_token=body.refresh_token)
    await db.commit()


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out every device for the current user",
)
async def logout_all(user: CurrentUser, db: DbSession) -> None:
    await auth_service.revoke_all_sessions(db, user.id)
    await db.commit()
    log.info("auth.logout_all", user_id=str(user.id))
