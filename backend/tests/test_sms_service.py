"""Phase 27 — sms_service unit tests.

No live AWS calls. The SNS publish path is patched at every branch — we
never import boto3 at module scope and we reset the lazy client cache
between tests that flip the flag.

Covers:
- Feature-flag-off short-circuits.
- E.164 validation.
- STOP footer guaranteed.
- Body length < 160 chars for pre_2h + no_show templates.
- Idempotency via _dedup_insert.
- No-show window math.
- should_send_sms combines flag + opt-in + phone + quiet hours.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app import models
from app.services import reminder_service, sms_service
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user


PT = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sms_flag_on(monkeypatch):
    """Enable sms feature flag for the duration of a test."""
    from app.services import sms_service as svc
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", True)
    svc._reset_client_cache()
    yield
    svc._reset_client_cache()


@pytest.fixture
def sms_flag_off(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sms_enabled", False)
    yield


def _seed_signup(
    db_session,
    *,
    tag="t",
    start_time=None,
    status=models.SignupStatus.confirmed,
):
    owner = make_user(db_session, email=f"owner_sms_{tag}@example.com")
    _bind_factories(db_session)
    vol = VolunteerFactory(
        email=f"vol_sms_{tag}@example.com",
        first_name="Ada",
        last_name="Sms",
    )
    event, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    if start_time is not None:
        slot.start_time = start_time
        slot.end_time = start_time + timedelta(hours=1)
    event.title = "CRISPR Module"
    event.location = "Lot 22"
    db_session.flush()
    signup = SignupFactory(volunteer=vol, slot=slot, status=status)
    db_session.flush()
    return signup, slot, event


# ---------------------------------------------------------------------------
# Validation + formatters
# ---------------------------------------------------------------------------


def test_is_valid_e164_accepts_valid_us():
    assert sms_service.is_valid_e164("+18055551234") is True


def test_is_valid_e164_rejects_bad_shapes():
    assert sms_service.is_valid_e164("") is False
    assert sms_service.is_valid_e164(None) is False
    assert sms_service.is_valid_e164("18055551234") is False  # missing +
    assert sms_service.is_valid_e164("+1") is False  # too short
    assert sms_service.is_valid_e164("+0123") is False  # leading 0 after +


def test_format_pre_2h_body_under_160_chars():
    start = datetime(2030, 6, 4, 14, 30, tzinfo=timezone.utc)
    body = sms_service.format_pre_2h_body(
        event_title="CRISPR Module for Ada Lovelace",
        venue="UCSB Broida Hall Room 1234",
        start_time=start,
    )
    assert len(body) < 160, f"body too long: {len(body)}"
    assert sms_service.STOP_FOOTER in body


def test_format_no_show_body_under_160_chars():
    start = datetime(2030, 6, 4, 14, 0, tzinfo=timezone.utc)
    body = sms_service.format_no_show_body(
        first_name="Ada",
        event_title="CRISPR Module",
        start_time=start,
    )
    assert len(body) < 160
    assert sms_service.STOP_FOOTER in body


def test_ensure_footer_appends_when_missing():
    assert sms_service._ensure_footer("Hello there").endswith(
        sms_service.STOP_FOOTER
    )
    # No duplicate append when already present.
    already = f"Hi. {sms_service.STOP_FOOTER}"
    assert sms_service._ensure_footer(already).count(sms_service.STOP_FOOTER) == 1


# ---------------------------------------------------------------------------
# send_sms — flag gating + transport
# ---------------------------------------------------------------------------


def test_send_sms_flag_off_returns_skipped(sms_flag_off):
    result = sms_service.send_sms("+18055551234", "Hi")
    assert result == {"status": "skipped_flag_off"}


def test_send_sms_invalid_phone_returns_invalid(sms_flag_on):
    fake = MagicMock()
    with patch.object(sms_service, "_get_sns_client", return_value=fake):
        result = sms_service.send_sms("not-a-phone", "Hi")
    assert result["status"] == "invalid_phone"
    fake.publish.assert_not_called()


def test_send_sms_calls_sns_publish_on_success(sms_flag_on):
    fake_client = MagicMock()
    fake_client.publish.return_value = {"MessageId": "abc-123"}
    with patch.object(sms_service, "_get_sns_client", return_value=fake_client):
        result = sms_service.send_sms("+18055551234", "Hi there")
    assert result["status"] == "sent"
    assert result["message_id"] == "abc-123"
    # STOP footer auto-appended
    call_kwargs = fake_client.publish.call_args.kwargs
    assert call_kwargs["PhoneNumber"] == "+18055551234"
    assert sms_service.STOP_FOOTER in call_kwargs["Message"]


def test_send_sms_publish_failure_returns_failed(sms_flag_on):
    fake_client = MagicMock()
    fake_client.publish.side_effect = RuntimeError("SNS down")
    with patch.object(sms_service, "_get_sns_client", return_value=fake_client):
        result = sms_service.send_sms("+18055551234", "Hi")
    assert result["status"] == "failed"
    assert "SNS down" in result["error"]


# ---------------------------------------------------------------------------
# should_send_sms — compound eligibility
# ---------------------------------------------------------------------------


def test_should_send_sms_flag_off(db_session, sms_flag_off):
    signup, _, _ = _seed_signup(db_session, tag="flagoff")
    ok, reason = sms_service.should_send_sms(db_session, signup)
    assert ok is False
    assert reason == "flag_off"


def test_should_send_sms_requires_opt_in(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="optin")
    # Default prefs row has sms_opt_in=False
    ok, reason = sms_service.should_send_sms(db_session, signup)
    assert ok is False
    assert reason == "opted_out"


def test_should_send_sms_requires_phone(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="nophone")
    reminder_service.update_preferences(
        db_session, signup.volunteer.email, sms_opt_in=True, phone_e164=None
    )
    signup.volunteer.phone_e164 = None
    db_session.flush()
    ok, reason = sms_service.should_send_sms(db_session, signup)
    assert ok is False
    assert reason == "no_phone"


def test_should_send_sms_blocked_by_quiet_hours(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="quiet")
    reminder_service.update_preferences(
        db_session,
        signup.volunteer.email,
        sms_opt_in=True,
        phone_e164="+18055551234",
    )
    # 22:00 PT is quiet hours.
    quiet = datetime(2030, 1, 6, 22, 0, tzinfo=PT).astimezone(timezone.utc)
    ok, reason = sms_service.should_send_sms(db_session, signup, now=quiet)
    assert ok is False
    assert reason == "quiet_hours"


def test_should_send_sms_happy_path(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="happy")
    reminder_service.update_preferences(
        db_session,
        signup.volunteer.email,
        sms_opt_in=True,
        phone_e164="+18055551234",
    )
    mid_day = datetime(2030, 1, 6, 14, 0, tzinfo=PT).astimezone(timezone.utc)
    ok, reason = sms_service.should_send_sms(db_session, signup, now=mid_day)
    assert ok is True
    assert reason == ""


# ---------------------------------------------------------------------------
# Window math
# ---------------------------------------------------------------------------


def test_pre_2h_window_in_range(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    _, slot, _ = _seed_signup(db_session, tag="pre2hin", start_time=start)
    # Exactly 2h before is the target; 2h05m is still within ±15 min.
    now = start - timedelta(hours=2, minutes=5)
    assert sms_service.is_in_pre_2h_window(slot, now) is True


def test_pre_2h_window_outside(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    _, slot, _ = _seed_signup(db_session, tag="pre2hout", start_time=start)
    now = start - timedelta(hours=3)
    assert sms_service.is_in_pre_2h_window(slot, now) is False


def test_no_show_window_in_range(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    _, slot, _ = _seed_signup(db_session, tag="nowin", start_time=start)
    now = start + timedelta(minutes=35)  # 5 min off from target 30m → within ±15m
    assert sms_service.is_in_no_show_window(slot, now) is True


def test_no_show_window_before_start(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    _, slot, _ = _seed_signup(db_session, tag="nowbefore", start_time=start)
    assert sms_service.is_in_no_show_window(slot, start - timedelta(minutes=5)) is False


# ---------------------------------------------------------------------------
# send_and_record — idempotency + failure audit
# ---------------------------------------------------------------------------


def test_send_and_record_dedup_idempotent(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="dedup")
    reminder_service.update_preferences(
        db_session,
        signup.volunteer.email,
        sms_opt_in=True,
        phone_e164="+18055551234",
    )
    fake = MagicMock()
    fake.publish.return_value = {"MessageId": "m1"}
    with patch.object(sms_service, "_get_sns_client", return_value=fake):
        r1 = sms_service.send_and_record(
            db_session, signup=signup, kind="sms_pre_2h", body="Hi"
        )
        r2 = sms_service.send_and_record(
            db_session, signup=signup, kind="sms_pre_2h", body="Hi"
        )

    assert r1["status"] == "sent"
    assert r2["status"] == "skipped_duplicate"
    # Only one publish call despite two dispatches.
    assert fake.publish.call_count == 1


def test_send_and_record_failure_writes_audit(db_session, sms_flag_on):
    signup, _, _ = _seed_signup(db_session, tag="fail")
    reminder_service.update_preferences(
        db_session,
        signup.volunteer.email,
        sms_opt_in=True,
        phone_e164="+18055551234",
    )
    fake = MagicMock()
    fake.publish.side_effect = RuntimeError("boom")
    before = db_session.query(models.AuditLog).filter(
        models.AuditLog.action == "sms_send_failed"
    ).count()
    with patch.object(sms_service, "_get_sns_client", return_value=fake):
        r = sms_service.send_and_record(
            db_session, signup=signup, kind="sms_pre_2h", body="Hi"
        )
    assert r["status"] == "failed"
    after = db_session.query(models.AuditLog).filter(
        models.AuditLog.action == "sms_send_failed"
    ).count()
    assert after == before + 1


# ---------------------------------------------------------------------------
# Admin preview
# ---------------------------------------------------------------------------


def test_list_upcoming_sms_includes_both_kinds(db_session):
    # Slot starts 1h from now → pre_2h already passed but no_show is upcoming
    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=1)
    _seed_signup(db_session, tag="preview", start_time=start)
    rows = sms_service.list_upcoming_sms(db_session, days=2)
    kinds = {r["kind"] for r in rows}
    # At minimum the no_show target (start+30m) is in the future horizon.
    assert "sms_no_show" in kinds
