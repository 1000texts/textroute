"""Canonical phone-number representation (E.164).

Phone numbers are identity keys for members and TextRoute lines.
All inbound lookups and persisted values should use this form.
"""

from __future__ import annotations

import re


class InvalidPhoneNumberError(ValueError):
    """Raised when a phone number cannot be normalized to E.164."""


def normalize_phone_number(
    raw: str,
    *,
    default_region: str = "US",
) -> str:
    """Normalize a phone number to E.164 (e.g. +13165551234).

    Accepts common US formats and already-E.164 values. Digits-only
    numbers with 10 digits are assumed to be ``default_region`` (US → +1).
    """
    if raw is None:
        raise InvalidPhoneNumberError("Phone number is required.")

    text = str(raw).strip()
    if not text:
        raise InvalidPhoneNumberError("Phone number is required.")

    digits = re.sub(r"\D", "", text)
    if not digits:
        raise InvalidPhoneNumberError(f"Invalid phone number: {raw!r}")

    if text.startswith("+"):
        if len(digits) < 8 or len(digits) > 15:
            raise InvalidPhoneNumberError(f"Invalid phone number: {raw!r}")
        return f"+{digits}"

    if default_region.upper() == "US":
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"

    if 8 <= len(digits) <= 15:
        return f"+{digits}"

    raise InvalidPhoneNumberError(f"Invalid phone number: {raw!r}")
