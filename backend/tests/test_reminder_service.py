"""Phase 24 — reminder_service unit tests.

Covers:
- Window math for kickoff / pre_24h / pre_2h (too early, in window, too late).
- Idempotency: second send_reminder in the same window returns already_sent.
- Opt-out honored.
- Quiet hours block sends (and force=True bypasses).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from app import models
from app.services import reminder_service
from app import celery_app as celery_mod
from app.celery_app import send_email_notification
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user


PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    class _Proxy:
        def __init__(self, session):
            self._s = session

        def __getattr__(self, name):
            return getattr(self._s, name)

        def close(self):
            pass

    def _factory():
        return _Proxy(db_session)

    monkeypatch.setattr(celery_mod, "SessionLocal", _factory)
    return _factory


@pytest.fixture
def capture_delay(monkeypatch):
    calls = []

    def fake_delay(*args, **kwargs):
        calls.append((args, kwargs))

        class _R:
            id = "fake"

        return _R()

    monkeypatch.setattr(send_email_notification, "delay", fake_delay)
    return calls


def _seed(db_session, *, start_time, email_tag="", status=models.SignupStatus.confirmed):
    owner = make_user(db_session, email=f"owner_r{email_tag}@example.com")
    _bind_factories(db_session)
    v = VolunteerFactory(
        email=f"vol_r{email_tag}@example.com",
        first_name="Vee",
        last_name=f"Rem{email_tag or 'x'}",
    )
    event, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    slot.start_time = start_time
    slot.end_time = start_time + timedelta(hours=1)
    db_session.flush()
    s = SignupFactory(volunteer=v, slot=slot, status=status)
    db_session.flush()
    return s


# ---------------------------------------------------------------
# is_quiet_hours
# ---------------------------------------------------------------


def test_is_quiet_hours_evening_pt():
    # 22:00 PT is quiet
    pt = datetime(2030, 1, 6, 22, 0, tzinfo=PT)
    assert reminder_service.is_quiet_hours(pt.astimezone(timezone.utc)) is True


def test_is_quiet_hours_early_morning_pt():
    # 06:30 PT is quiet
    pt = datetime(2030, 1, 6, 6, 30, tzinfo=PT)
    assert reminder_service.is_quiet_hours(pt.astimezone(timezone.utc)) is True


def test_is_quiet_hours_mid_day_pt():
    # 14:00 PT is allowed
    pt = datetime(2030, 1, 6, 14, 0, tzinfo=PT)
    assert reminder_service.is_quiet_hours(pt.astimezone(timezone.utc)) is False


def test_is_quiet_hours_seven_am_pt_allowed():
    # 07:00 PT is exactly the edge — allowed (kickoff instant)
    pt = datetime(2030, 1, 6, 7, 0, tzinfo=PT)
    assert reminder_service.is_quiet_hours(pt.astimezone(timezone.utc)) is False


# ---------------------------------------------------------------
# compute_reminder_window
# ---------------------------------------------------------------


def test_window_pre_24h_in_window(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)  # Tuesday 18:00 UTC
    s = _seed(db_session, start_time=start, email_tag="24hin")
    now = start - timedelta(hours=24)
    assert reminder_service.compute_reminder_window(s.slot, "pre_24h", now) is True


def test_window_pre_24h_outside(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="24hout")
    now = start - timedelta(hours=23)  # too late (23h out, we want 24h ±15m)
    assert reminder_service.compute_reminder_window(s.slot, "pre_24h", now) is False


def test_window_pre_2h_in_window(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="2hin")
    now = start - timedelta(hours=2, minutes=10)
    assert reminder_service.compute_reminder_window(s.slot, "pre_2h", now) is True


def test_window_pre_2h_outside(db_session):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="2hout")
    now = start - timedelta(hours=3)
    assert reminder_service.compute_reminder_window(s.slot, "pre_2h", now) is False


def test_window_kickoff_monday_0700_pt(db_session):
    # Event Wednesday 2030-06-05 10:00 PT -> ISO week starts Mon 2030-06-03
    # Kickoff instant = Mon 2030-06-03 07:00 PT (14:00 UTC during PDT)
    start_pt = datetime(2030, 6, 5, 10, 0, tzinfo=PT)
    s = _seed(
        db_session,
        start_time=start_pt.astimezone(timezone.utc),
        email_tag="kickoff",
    )
    kickoff_pt = datetime(2030, 6, 3, 7, 0, tzinfo=PT)
    now = kickoff_pt.astimezone(timezone.utc)
    assert reminder_service.compute_reminder_window(s.slot, "kickoff", now) is True


def test_window_kickoff_wrong_day(db_session):
    start_pt = datetime(2030, 6, 5, 10, 0, tzinfo=PT)
    s = _seed(db_session, start_time=start_pt.astimezone(timezone.utc), email_tag="kickow")
    # Tuesday 07:00 PT — not the kickoff instant.
    wrong = datetime(2030, 6, 4, 7, 0, tzinfo=PT).astimezone(timezone.utc)
    assert reminder_service.compute_reminder_window(s.slot, "kickoff", wrong) is False


# ---------------------------------------------------------------
# send_reminder — idempotency / opt-out / quiet hours
# ---------------------------------------------------------------


def test_send_reminder_happy_path_dedup(
    db_session, patch_session_local, capture_delay
):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="dedup")
    now = datetime(2030, 6, 4, 16, 0, tzinfo=timezone.utc)  # 2h before, mid-day PT

    r1 = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now)
    r2 = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now)

    assert r1.sent is True, r1
    assert r2.sent is False and r2.reason == "already_sent", r2
    assert len(capture_delay) == 1


def test_send_reminder_respects_opt_out(
    db_session, patch_session_local, capture_delay
):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="optout")
    # Volunteer opts out
    reminder_service.update_preferences(
        db_session, s.volunteer.email, email_reminders_enabled=False
    )
    now = datetime(2030, 6, 4, 16, 0, tzinfo=timezone.utc)

    r = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now)
    assert r.sent is False and r.reason == "opted_out"
    assert capture_delay == []


def test_send_reminder_respects_quiet_hours(
    db_session, patch_session_local, capture_delay
):
    # Slot at 08:00 PT — 2h before is 06:00 PT which is quiet-hours territory.
    start_pt = datetime(2030, 6, 4, 8, 0, tzinfo=PT)
    start = start_pt.astimezone(timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="quiet")
    now = (start_pt - timedelta(hours=2)).astimezone(timezone.utc)

    r = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now)
    assert r.sent is False and r.reason == "quiet_hours"
    assert capture_delay == []


def test_send_reminder_force_bypasses_quiet_hours(
    db_session, patch_session_local, capture_delay
):
    start_pt = datetime(2030, 6, 4, 8, 0, tzinfo=PT)
    start = start_pt.astimezone(timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="qforce")
    now = (start_pt - timedelta(hours=2)).astimezone(timezone.utc)

    r = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now, force=True)
    assert r.sent is True and r.reason == "ok"
    assert len(capture_delay) == 1


def test_send_reminder_force_still_honors_opt_out(
    db_session, patch_session_local, capture_delay
):
    start = datetime(2030, 6, 4, 18, 0, tzinfo=timezone.utc)
    s = _seed(db_session, start_time=start, email_tag="foptout")
    reminder_service.update_preferences(
        db_session, s.volunteer.email, email_reminders_enabled=False
    )
    now = datetime(2030, 6, 4, 16, 0, tzinfo=timezone.utc)

    r = reminder_service.send_reminder(db_session, s.id, "pre_2h", now=now, force=True)
    assert r.sent is False and r.reason == "opted_out"


def test_list_upcoming_reminders_includes_all_three_kinds(
    db_session, patch_session_local
):
    # Event Wed 2030-06-05 14:00 PT
    start_pt = datetime(2030, 6, 5, 14, 0, tzinfo=PT)
    _seed(db_session, start_time=start_pt.astimezone(timezone.utc), email_tag="preview")
    # Anchor "now" before the event's ISO week's Monday
    with freeze_time(datetime(2030, 6, 2, 6, 0, tzinfo=timezone.utc)):
        rows = reminder_service.list_upcoming_reminders(db_session, days=10)
    kinds = {r["kind"] for r in rows}
    assert {"kickoff", "pre_24h", "pre_2h"}.issubset(kinds)
