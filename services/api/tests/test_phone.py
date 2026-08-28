import pytest

from app.utils.phone import InvalidPhoneError, mask_phone, normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "9841234567",
        "+9779841234567",
        "977 9841234567",
        "984-123-4567",
        "+977 98-4123-4567",
    ],
)
def test_all_common_formats_collapse_to_one_identity(raw: str) -> None:
    # This is the whole point: one person, one account, however they type it.
    assert normalize_phone(raw) == "+9779841234567"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "12345",
        "abcdefghij",
        "+9779841234567890",
        "014412345",  # Kathmandu landline — cannot receive an OTP
    ],
)
def test_invalid_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_mask_phone_keeps_only_the_last_four_digits() -> None:
    masked = mask_phone("+9779841234567")
    assert masked.endswith("4567")
    assert "984123" not in masked
