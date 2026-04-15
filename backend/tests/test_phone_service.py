"""Unit tests for phone_service.normalize_us_phone.

Tests cover E.164 normalization and error cases per Phase 09 Task 3 spec.
"""
import pytest

from app.services.phone_service import normalize_us_phone, InvalidPhoneError


class TestNormalizeUsPhone:
    def test_dashes(self):
        assert normalize_us_phone("805-555-1234") == "+18055551234"

    def test_parentheses_and_space(self):
        assert normalize_us_phone("(805) 555-1234") == "+18055551234"

    def test_e164_with_spaces(self):
        assert normalize_us_phone("+1 805 555 1234") == "+18055551234"

    def test_bare_10_digits(self):
        assert normalize_us_phone("8055551234") == "+18055551234"

    def test_not_a_phone_raises(self):
        with pytest.raises(InvalidPhoneError):
            normalize_us_phone("not-a-phone")

    def test_empty_raises(self):
        with pytest.raises(InvalidPhoneError):
            normalize_us_phone("")

    def test_no_area_code_raises(self):
        """7-digit local number without area code — invalid US number."""
        with pytest.raises(InvalidPhoneError):
            normalize_us_phone("555-1234")

    def test_non_us_number_raises(self):
        """UK number — country_code != 1, must be rejected."""
        with pytest.raises(InvalidPhoneError):
            normalize_us_phone("+44 20 7946 0958")
