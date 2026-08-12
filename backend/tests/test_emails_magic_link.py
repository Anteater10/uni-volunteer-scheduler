"""Plan 02-02: Magic-link email template tests."""
import logging
from types import SimpleNamespace

import pytest

from app.emails import _humanise_minutes, build_magic_link_email


def test_magic_link_email_html_contains_url():
    result = build_magic_link_email(
        "user@example.com",
        "abc123def456",
        SimpleNamespace(title="Test Event"),
        "https://example.com",
    )
    assert result["to"] == "user@example.com"
    assert "Test Event" in result["subject"]
    assert "https://example.com/auth/magic/abc123def456" in result["html"]
    assert "font-size:16px" in result["html"]
    assert "#0b5ed7" in result["html"]
    assert 'role="presentation"' in result["html"]


def test_magic_link_email_text_contains_url():
    result = build_magic_link_email(
        "user@example.com",
        "abc123def456",
        SimpleNamespace(title="Test Event"),
        "https://example.com",
    )
    assert "https://example.com/auth/magic/abc123def456" in result["text"]
    # K20: this used to assert "15 minutes" — the settings default, not the
    # lifetime a signup-confirm token is ever issued with. The sentence now
    # tracks the real TTL.
    assert "14 days" in result["text"]


def test_magic_link_email_states_the_ttl_it_was_given():
    result = build_magic_link_email(
        "user@example.com",
        "tok",
        SimpleNamespace(title="Test Event"),
        "https://example.com",
        ttl_minutes=4320,
    )
    assert "3 days" in result["text"]
    assert "3 days" in result["html"]
    assert "15 minutes" not in result["text"]


@pytest.mark.parametrize(
    "minutes,expected",
    [
        (20160, "14 days"),
        (1440, "1 day"),
        (120, "2 hours"),
        (60, "1 hour"),
        (15, "15 minutes"),
        (1, "1 minute"),
    ],
)
def test_humanise_minutes(minutes, expected):
    assert _humanise_minutes(minutes) == expected


def test_magic_link_email_is_branded_scitrek():
    result = build_magic_link_email(
        "user@example.com",
        "tok",
        SimpleNamespace(title="Test Event"),
        "https://example.com",
    )
    # K20: nothing in this email said who it was from.
    assert "SciTrek" in result["subject"]
    assert "UCSB SciTrek" in result["html"]
    assert "UCSB SciTrek" in result["text"]


def test_magic_link_email_log_redacted(caplog):
    with caplog.at_level(logging.INFO, logger="app.emails"):
        build_magic_link_email(
            "user@example.com",
            "abc123def456",
            SimpleNamespace(title="Test Event"),
            "https://example.com",
        )
    log_output = caplog.text
    # The 6-char prefix should appear
    assert "abc123" in log_output
    # The full token must NOT appear in any log line
    assert "abc123def456" not in log_output


def test_magic_link_strips_trailing_slash_from_base_url():
    result = build_magic_link_email(
        "user@example.com",
        "tok123",
        SimpleNamespace(title="Evt"),
        "https://example.com/",
    )
    assert "https://example.com/auth/magic/tok123" in result["html"]
    assert "https://example.com//auth" not in result["html"]


def test_magic_link_uses_title_attribute():
    """Event model uses .title, not .name."""
    result = build_magic_link_email(
        "u@x.com",
        "t",
        SimpleNamespace(title="My Event Title"),
        "http://localhost",
    )
    assert "My Event Title" in result["subject"]
    assert "My Event Title" in result["html"]
