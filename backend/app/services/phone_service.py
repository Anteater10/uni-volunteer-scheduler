"""Phone number normalization service.

Normalizes US phone numbers to E.164 format (+1XXXXXXXXXX).
Raises InvalidPhoneError for non-US or unparseable inputs.

# noqa: log-scrub — never log raw phone input; caller must not log request bodies.
"""
import phonenumbers
from phonenumbers import NumberParseException


class InvalidPhoneError(ValueError):
    """Raised when a phone string cannot be parsed to a valid US E.164 number."""


def normalize_us_phone(raw: str) -> str:
    """Normalize a US phone number string to E.164 format.

    Args:
        raw: Raw phone string (e.g., '805-555-1234', '(805) 555-1234', '+18055551234')

    Returns:
        E.164 formatted string (e.g., '+18055551234')

    Raises:
        InvalidPhoneError: If the input cannot be parsed or is not a valid US number.
    """
    if not raw or not raw.strip():
        raise InvalidPhoneError("phone number is empty")
    try:
        parsed = phonenumbers.parse(raw, "US")
    except NumberParseException as exc:
        raise InvalidPhoneError(f"cannot parse phone number: {exc}") from exc
    if parsed.country_code != 1:
        raise InvalidPhoneError("only US (+1) phone numbers are accepted")
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneError("phone number is not a valid US number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
