"""OTP issue and verify, backed by Redis.

Redis rather than Postgres: the code is short-lived and disposable, TTL expiry
is free, and INCR gives an atomic attempt counter. Losing Redis costs a user one
"resend" tap, nothing more.

Keys per phone:
    otp:code:<phone>      the code            (TTL = OTP_TTL_SECONDS)
    otp:attempts:<phone>  wrong tries so far  (TTL = OTP_TTL_SECONDS)
    otp:cooldown:<phone>  resend lock         (TTL = OTP_RESEND_COOLDOWN_SECONDS)
    otp:daily:<phone>     codes sent today    (TTL = 24h)
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import generate_otp
from app.services.sms import send_otp_sms
from app.utils.phone import mask_phone

log = get_logger(__name__)


class OTPCooldownError(AppError):
    status_code = 429
    code = "OTP_COOLDOWN"
    message = "Please wait before requesting another code."


class OTPDailyLimitError(AppError):
    status_code = 429
    code = "OTP_DAILY_LIMIT"
    message = "Too many codes requested today. Try again tomorrow or contact support."


class OTPInvalidError(AppError):
    status_code = 400
    code = "OTP_INVALID"
    message = "That code is incorrect or has expired."


@dataclass(frozen=True)
class IssuedOTP:
    expires_in_seconds: int
    resend_after_seconds: int
    debug_code: str | None


def _k(kind: str, phone: str) -> str:
    return f"otp:{kind}:{phone}"


async def issue_otp(phone: str, *, locale: str = "en") -> IssuedOTP:
    redis = get_redis()

    if await redis.exists(_k("cooldown", phone)):
        ttl = await redis.ttl(_k("cooldown", phone))
        raise OTPCooldownError(
            f"Please wait {max(ttl, 1)}s before requesting another code.",
            details={"retry_after_seconds": max(ttl, 1)},
        )

    sent_today = await redis.incr(_k("daily", phone))
    if sent_today == 1:
        await redis.expire(_k("daily", phone), 86_400)
    if sent_today > settings.OTP_MAX_PER_PHONE_PER_DAY:
        raise OTPDailyLimitError()

    # Fixed codes let QA and app-store reviewers in without a real SMS.
    # settings.otp_test_numbers is always empty in production.
    test_code = settings.otp_test_numbers.get(phone)
    code = test_code or generate_otp(settings.OTP_LENGTH)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(_k("code", phone), code, ex=settings.OTP_TTL_SECONDS)
        pipe.delete(_k("attempts", phone))
        pipe.set(_k("cooldown", phone), "1", ex=settings.OTP_RESEND_COOLDOWN_SECONDS)
        await pipe.execute()

    if test_code is None:
        await send_otp_sms(to=phone, code=code, locale=locale)
    else:
        log.info("otp.test_number_used", phone=mask_phone(phone))

    return IssuedOTP(
        expires_in_seconds=settings.OTP_TTL_SECONDS,
        resend_after_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        debug_code=None if settings.is_production else code,
    )


async def verify_otp(phone: str, code: str) -> None:
    """Consume the code. Raises OTPInvalidError on any failure."""
    redis = get_redis()
    stored = await redis.get(_k("code", phone))

    if stored is None:
        raise OTPInvalidError("That code has expired. Request a new one.", code="OTP_EXPIRED")

    attempts = await redis.incr(_k("attempts", phone))
    if attempts == 1:
        await redis.expire(_k("attempts", phone), settings.OTP_TTL_SECONDS)

    if attempts > settings.OTP_MAX_ATTEMPTS:
        # Burn the code so an attacker cannot keep guessing this one.
        await redis.delete(_k("code", phone), _k("attempts", phone))
        log.warning("otp.too_many_attempts", phone=mask_phone(phone))
        raise OTPInvalidError(
            "Too many incorrect attempts. Request a new code.", code="OTP_ATTEMPTS_EXCEEDED"
        )

    if not _constant_time_equals(stored, code):
        raise OTPInvalidError(details={"attempts_left": settings.OTP_MAX_ATTEMPTS - attempts})

    # Single-use: delete on success so the same code cannot be replayed.
    await redis.delete(_k("code", phone), _k("attempts", phone))


def _constant_time_equals(a: str, b: str) -> bool:
    from hmac import compare_digest

    return compare_digest(a, b)
