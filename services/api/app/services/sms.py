"""SMS delivery.

Only the console provider exists today: it logs the message instead of sending
it, which is what local development needs and costs nothing. When a paid Nepali
gateway (Sparrow, Aakash) is wired up, add a branch here and a value to
Settings.SMS_PROVIDER — nothing upstream of `send_sms` changes.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.phone import mask_phone

log = get_logger(__name__)


async def send_sms(*, to: str, message: str) -> None:
    if settings.SMS_PROVIDER == "console":
        log.info("sms.console", to=mask_phone(to), message=message)
        return
    raise RuntimeError(f"Unsupported SMS provider: {settings.SMS_PROVIDER}")


async def send_otp_sms(*, to: str, code: str, locale: str = "en") -> None:
    minutes = settings.OTP_TTL_SECONDS // 60
    if locale == "ne":
        body = f"तपाईंको Sajilo OTP कोड {code} हो। यो {minutes} मिनेटमा समाप्त हुन्छ। कसैलाई नबताउनुहोस्।"
    else:
        body = (
            f"{code} is your Sajilo verification code. "
            f"It expires in {minutes} minutes. Do not share it."
        )
    await send_sms(to=to, message=body)
