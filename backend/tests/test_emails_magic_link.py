"""Plan 02-02: Magic-link email template tests."""
import logging
from types import SimpleNamespace

from app.emails import send_magic_link


def test_magic_link_email_html_contains_url():
    result = send_magic_link(
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
    result = send_magic_link(
        "user@example.com",
        "abc123def456",
        SimpleNamespace(title="Test Event"),
        "https://example.com",
    )
    assert "https://example.com/auth/magic/abc123def456" in result["text"]
    assert "15 minutes" in result["text"]


def test_magic_link_email_log_redacted():
    """Attach a handler directly to the app.emails logger.

    caplog goes via the root logger and is fragile to anything else in
    the test session that mutates global logging state (Celery's
    worker_hijack_root_logger, sentence-transformers' logging.basicConfig
    on first model load, etc). A direct handler bypasses all of that.
    """
    import io

    target = logging.getLogger("app.emails")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    prev_level = target.level
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    try:
        send_magic_link(
            "user@example.com",
            "abc123def456",
            SimpleNamespace(title="Test Event"),
            "https://example.com",
        )
    finally:
        target.removeHandler(handler)
        target.setLevel(prev_level)

    log_output = buf.getvalue()
    # The 6-char prefix should appear
    assert "abc123" in log_output
    # The full token must NOT appear in any log line
    assert "abc123def456" not in log_output


def test_magic_link_strips_trailing_slash_from_base_url():
    result = send_magic_link(
        "user@example.com",
        "tok123",
        SimpleNamespace(title="Evt"),
        "https://example.com/",
    )
    assert "https://example.com/auth/magic/tok123" in result["html"]
    assert "https://example.com//auth" not in result["html"]


def test_magic_link_uses_title_attribute():
    """Event model uses .title, not .name."""
    result = send_magic_link(
        "u@x.com",
        "t",
        SimpleNamespace(title="My Event Title"),
        "http://localhost",
    )
    assert "My Event Title" in result["subject"]
    assert "My Event Title" in result["html"]
