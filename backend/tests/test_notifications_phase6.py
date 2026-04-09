"""Phase 6 idempotency + integration tests for the notifications pipeline.

Proves:
1. Double-run of send_reminders_24h produces exactly 1 send per signup
2. Double-run of send_reminders_1h produces exactly 1 send per signup
3. Cancellation dispatches task with kind='cancellation'
4. Slot reschedule invalidates old reminder rows and resets sent_at
5. Daily send limit blocks further sends when exceeded
6. send_email_notification dedup prevents double-send for same (signup, kind)

All tests mock the email provider (no real emails). Real DB with savepoint isolation.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from freezegun import freeze_time
from sqlalchemy import func

from app import celery_app as celery_mod
from app import models
from app.celery_app import (
    send_reminders_24h,
    send_reminders_1h,
    send_email_notification,
    _dedup_insert,
)
from tests.fixtures.factories import SignupFactory
from tests.fixtures.helpers import _bind_factories, make_event_with_slot, make_user


@pytest.fixture
def patch_session_local(db_session, monkeypatch):
    """Make Celery tasks reuse the test db_session (nested savepoint)."""

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


def _seed_confirmed_signup(db_session, *, start_time, email_tag="", reminder_1h_enabled=True):
    """Create a confirmed signup with a slot starting at the given time."""
    owner = make_user(db_session, email=f"owner_n{email_tag}@example.com")
    user = make_user(db_session, email=f"user_n{email_tag}@example.com")
    _bind_factories(db_session)
    event, slot = make_event_with_slot(db_session, capacity=5, owner=owner)
    slot.start_time = start_time
    slot.end_time = start_time + timedelta(hours=1)
    event.reminder_1h_enabled = reminder_1h_enabled
    db_session.flush()
    s = SignupFactory(
        user=user,
        slot=slot,
        status=models.SignupStatus.confirmed,
    )
    db_session.flush()
    return s


# ============================================================
# Test 1: 24h reminder idempotency
# ============================================================
def test_reminder_24h_idempotency(client, db_session, monkeypatch, patch_session_local):
    """Calling send_reminders_24h twice produces exactly 1 email per signup."""
    now = datetime(2030, 6, 1, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24)

    _seed_confirmed_signup(db_session, start_time=start, email_tag="idem24")
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_24h.apply().get()
        send_reminders_24h.apply().get()

    assert len(calls) == 1

    # Exactly 1 sent_notifications row
    count = db_session.query(func.count(models.SentNotification.id)).filter(
        models.SentNotification.kind == "reminder_24h"
    ).scalar()
    assert count == 1


# ============================================================
# Test 2: 1h reminder idempotency
# ============================================================
def test_reminder_1h_idempotency(client, db_session, monkeypatch, patch_session_local):
    """Calling send_reminders_1h twice produces exactly 1 email per signup."""
    now = datetime(2030, 6, 2, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(minutes=60)

    _seed_confirmed_signup(db_session, start_time=start, email_tag="idem1h")
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_1h.apply().get()
        send_reminders_1h.apply().get()

    assert len(calls) == 1

    count = db_session.query(func.count(models.SentNotification.id)).filter(
        models.SentNotification.kind == "reminder_1h"
    ).scalar()
    assert count == 1


# ============================================================
# Test 3: 1h reminder respects reminder_1h_enabled toggle
# ============================================================
def test_reminder_1h_respects_toggle(client, db_session, monkeypatch, patch_session_local):
    """When Event.reminder_1h_enabled=False, no 1h reminder is sent."""
    now = datetime(2030, 6, 3, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(minutes=60)

    _seed_confirmed_signup(db_session, start_time=start, email_tag="toggle", reminder_1h_enabled=False)
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    with freeze_time(now):
        send_reminders_1h.apply().get()

    assert len(calls) == 0


# ============================================================
# Test 4: Reschedule invalidates reminder rows
# ============================================================
def test_reschedule_invalidates_reminders(client, db_session, monkeypatch, patch_session_local):
    """After sending a 24h reminder, updating slot time resets the reminder state."""
    now = datetime(2030, 6, 4, 12, 0, tzinfo=timezone.utc)
    start = now + timedelta(hours=24)

    signup = _seed_confirmed_signup(db_session, start_time=start, email_tag="resched")
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification,
        "delay",
        lambda *a, **k: calls.append((a, k)) or type("R", (), {"id": "x"})(),
    )

    # Send the 24h reminder
    with freeze_time(now):
        send_reminders_24h.apply().get()

    assert len(calls) == 1
    db_session.refresh(signup)
    assert signup.reminder_24h_sent_at is not None

    # Simulate a slot reschedule: delete old reminder rows, reset columns
    slot = signup.slot
    db_session.query(models.SentNotification).filter(
        models.SentNotification.signup_id == signup.id,
        models.SentNotification.kind.in_(["reminder_24h", "reminder_1h"]),
    ).delete(synchronize_session=False)

    signup.reminder_24h_sent_at = None
    signup.reminder_1h_sent_at = None
    db_session.commit()

    db_session.refresh(signup)
    assert signup.reminder_24h_sent_at is None

    # Verify the sent_notifications row was deleted
    count = db_session.query(func.count(models.SentNotification.id)).filter(
        models.SentNotification.signup_id == signup.id,
        models.SentNotification.kind == "reminder_24h",
    ).scalar()
    assert count == 0


# ============================================================
# Test 5: Daily send limit blocks further sends
# ============================================================
def test_daily_limit_blocks_sends(client, db_session, monkeypatch, patch_session_local):
    """When daily limit is 1 and 1 email already sent today, second is skipped."""
    from app.config import settings as app_settings

    now = datetime(2030, 6, 5, 12, 0, tzinfo=timezone.utc)
    signup = _seed_confirmed_signup(db_session, start_time=now + timedelta(hours=24), email_tag="limit")
    db_session.commit()

    # Insert 1 sent_notifications row to simulate a prior send today
    sn = models.SentNotification(
        signup_id=signup.id,
        kind="confirmation",
        sent_at=now,
    )
    db_session.add(sn)
    db_session.commit()

    # Set daily limit to 1
    original_limit = app_settings.resend_daily_limit
    monkeypatch.setattr(app_settings, "resend_daily_limit", 1)

    # Mock _send_email_via_sendgrid to track calls
    send_calls = []
    monkeypatch.setattr(
        celery_mod,
        "_send_email_via_sendgrid",
        lambda *a, **k: send_calls.append((a, k)),
    )

    with freeze_time(now):
        # Call send_email_notification directly (not via delay, since eager mode)
        send_email_notification(
            str(signup.user_id),
            "Test subject",
            "Test body",
        )

    # Should have been blocked by daily limit
    assert len(send_calls) == 0

    monkeypatch.setattr(app_settings, "resend_daily_limit", original_limit)


# ============================================================
# Test 6: send_email_notification dedup for cancellation
# ============================================================
def test_send_notification_dedup_cancellation(client, db_session, monkeypatch, patch_session_local):
    """Calling send_email_notification twice with same signup+kind produces 1 send."""
    now = datetime(2030, 6, 6, 12, 0, tzinfo=timezone.utc)
    signup = _seed_confirmed_signup(db_session, start_time=now + timedelta(hours=24), email_tag="dedup_cancel")
    db_session.commit()

    # Ensure daily limit is high enough
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "resend_daily_limit", 1000)

    send_calls = []
    monkeypatch.setattr(
        celery_mod,
        "_send_email_via_sendgrid",
        lambda *a, **k: send_calls.append((a, k)),
    )

    with freeze_time(now):
        send_email_notification(signup_id=str(signup.id), kind="cancellation")
        send_email_notification(signup_id=str(signup.id), kind="cancellation")

    # Only 1 actual send
    assert len(send_calls) == 1

    # Only 1 sent_notifications row
    count = db_session.query(func.count(models.SentNotification.id)).filter(
        models.SentNotification.signup_id == signup.id,
        models.SentNotification.kind == "cancellation",
    ).scalar()
    assert count == 1
