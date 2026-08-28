"""Nepali phone number normalisation.

Every phone entering the system is normalised to E.164 (+9779XXXXXXXX) before
it is stored or looked up. Users type "9841234567", "098-4123-4567" and
"+977 9841234567" interchangeably; without this they would create three
separate accounts.
"""

import phonenumbers
from phonenumbers import NumberParseException

from app.core.errors import AppError

NEPAL_REGION = "NP"


class InvalidPhoneError(AppError):
    code = "INVALID_PHONE"
    message = "Enter a valid Nepali mobile number."


def normalize_phone(raw: str) -> str:
    """Return the E.164 form, or raise InvalidPhoneError."""
    candidate = raw.strip().replace(" ", "").replace("-", "")
    if not candidate:
        raise InvalidPhoneError()

    try:
        parsed = phonenumbers.parse(candidate, NEPAL_REGION)
    except NumberParseException:
        raise InvalidPhoneError() from None

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneError()

    number_type = phonenumbers.number_type(parsed)
    if number_type not in (
        phonenumbers.PhoneNumberType.MOBILE,
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
    ):
        raise InvalidPhoneError("Only mobile numbers can receive an OTP.")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(e164: str) -> str:
    """+9779841234567 -> +977••••••4567. For logs and support screens."""
    return f"{e164[:4]}{'•' * max(len(e164) - 8, 0)}{e164[-4:]}" if len(e164) > 8 else "••••"
