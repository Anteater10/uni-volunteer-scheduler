"""F6: the email-transport boot guard in app.config.

Covers assert_email_config_valid, which exists because a missing
SENDGRID_API_KEY / EMAIL_FROM_ADDRESS used to produce a *successful-looking*
send that delivered nothing — the signup confirmation never arrived and the
signup stayed pending forever with no error anywhere.
"""
import pytest

from app.config import Settings, assert_email_config_valid


# --- sendgrid mode ---------------------------------------------------------


def test_sendgrid_missing_key_raises():
    with pytest.raises(RuntimeError, match="SENDGRID_API_KEY"):
        assert_email_config_valid(
            email_mode="sendgrid",
            sendgrid_api_key=None,
            email_from_address="from@x.com",
        )


def test_sendgrid_missing_from_address_raises():
    with pytest.raises(RuntimeError, match="EMAIL_FROM_ADDRESS"):
        assert_email_config_valid(
            email_mode="sendgrid",
            sendgrid_api_key="SG.key",
            email_from_address=None,
        )


def test_sendgrid_fully_configured_passes():
    assert_email_config_valid(
        email_mode="sendgrid",
        sendgrid_api_key="SG.key",
        email_from_address="from@x.com",
    )


# --- smtp mode -------------------------------------------------------------


def test_smtp_missing_from_address_raises():
    with pytest.raises(RuntimeError, match="EMAIL_FROM_ADDRESS"):
        assert_email_config_valid(
            email_mode="smtp",
            sendgrid_api_key=None,
            email_from_address=None,
        )


def test_smtp_needs_no_sendgrid_key():
    """The SMTP path must not be held hostage to a SendGrid credential."""
    assert_email_config_valid(
        email_mode="smtp",
        sendgrid_api_key=None,
        email_from_address="dev@localhost",
    )


# --- EMAIL_MODE is a Literal ----------------------------------------------


def test_unknown_email_mode_is_rejected_at_settings_construction(monkeypatch):
    """_send_email routes anything that isn't exactly "sendgrid" through SMTP,
    so a typo must fail at startup rather than silently pick a transport."""
    monkeypatch.setenv("EMAIL_MODE", "SendGird")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x")
    with pytest.raises(Exception, match="email_mode"):
        Settings(_env_file=None)


def test_default_email_mode_is_smtp(monkeypatch):
    monkeypatch.delenv("EMAIL_MODE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET", "x")
    assert Settings(_env_file=None).email_mode == "smtp"
