"""Signup cancel + waitlist integration tests.

Tests the admin cancel path (POST /api/v1/admin/signups/{id}/cancel) and the
authed staff cancel path (POST /api/v1/signups/{id}/cancel) with
volunteer-keyed signups created via VolunteerFactory + SignupFactory.

Phase 12 rewrite: old tests exercised POST /api/v1/signups/ (deleted in Phase 09).
2026-08-02 read-only signups (Task 4): neither surviving cancel endpoint
auto-promotes the waitlist anymore — they free the seat and stop.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app import models
from app.celery_app import send_email_notification
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _make_admin(db_session, email="admin_sig@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _seed_confirmed(db_session, slot, vol):
    """Create a confirmed signup for vol on slot (holds one capacity slot)."""
    _bind_factories(db_session)
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    slot.current_count = slot.current_count + 1
    db_session.flush()
    return signup


def _seed_waitlisted(db_session, slot, vol, *, when=None):
    """Create a waitlisted signup for vol on slot."""
    _bind_factories(db_session)
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup


def test_admin_cancel_changes_status_to_cancelled(client, db_session):
    """Admin cancel changes the signup status to cancelled."""
    admin = _make_admin(db_session, email="admin_s1@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_s1@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    headers = auth_headers(client, admin)
    rc = client.post(
        f"/api/v1/admin/signups/{signup.id}/cancel",
        headers=headers,
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "cancelled"


def test_admin_cancel_decrements_current_count(client, db_session):
    """Admin cancel frees a capacity slot on the slot row."""
    admin = _make_admin(db_session, email="admin_s2@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_s2@example.com")
    _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    count_before = slot.current_count
    headers = auth_headers(client, admin)
    signup = db_session.query(models.Signup).filter(
        models.Signup.volunteer_id == vol.id,
        models.Signup.slot_id == slot.id,
    ).first()
    client.post(f"/api/v1/admin/signups/{signup.id}/cancel", headers=headers)

    db_session.expire_all()
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == count_before - 1


def test_admin_cancel_does_not_promote_oldest_waitlisted(client, db_session):
    """2026-08-02 read-only signups (Task 4): cancelling a confirmed signup
    frees the seat but leaves every waitlisted volunteer alone — no FIFO
    promotion, regardless of how long they've been waiting."""
    admin = _make_admin(db_session, email="admin_s3@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)

    vol_a = VolunteerFactory(email="v_s3a@example.com")
    vol_b = VolunteerFactory(email="v_s3b@example.com")
    vol_c = VolunteerFactory(email="v_s3c@example.com")

    signup_a = _seed_confirmed(db_session, slot, vol_a)
    # B waitlisted first (older)
    older = datetime.now(timezone.utc) - timedelta(minutes=10)
    signup_b = _seed_waitlisted(db_session, slot, vol_b, when=older)
    # C waitlisted second (newer)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    signup_c = _seed_waitlisted(db_session, slot, vol_c, when=newer)
    db_session.commit()

    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/admin/signups/{signup_a.id}/cancel", headers=headers)
    assert rc.status_code == 200, rc.text

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    # Neither B (older) nor C (newer) gets promoted — cancel never promotes.
    assert b_row.status == models.SignupStatus.waitlisted
    assert c_row.status == models.SignupStatus.waitlisted
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 0


def test_admin_cancel_does_not_promote_regardless_of_tiebreak(client, db_session):
    """Identical-timestamp waitlisted volunteers both stay waitlisted — the
    old id tiebreaker only mattered when cancel used to promote."""
    admin = _make_admin(db_session, email="admin_s4@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)

    vol_a = VolunteerFactory(email="v_s4a@example.com")
    vol_b = VolunteerFactory(email="v_s4b@example.com")
    vol_c = VolunteerFactory(email="v_s4c@example.com")

    signup_a = _seed_confirmed(db_session, slot, vol_a)
    same_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    signup_b = _seed_waitlisted(db_session, slot, vol_b, when=same_ts)
    signup_c = _seed_waitlisted(db_session, slot, vol_c, when=same_ts)
    db_session.commit()

    headers = auth_headers(client, admin)
    client.post(f"/api/v1/admin/signups/{signup_a.id}/cancel", headers=headers)

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    assert b_row.status == models.SignupStatus.waitlisted
    assert c_row.status == models.SignupStatus.waitlisted


def test_admin_cancel_already_cancelled_is_idempotent(client, db_session):
    """Cancelling an already-cancelled signup returns 200 without error."""
    admin = _make_admin(db_session, email="admin_s5@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_s5@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.cancelled,
    )
    db_session.commit()

    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/admin/signups/{signup.id}/cancel", headers=headers)
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "cancelled"


def test_admin_cancel_enqueues_cancellation_email(client, db_session, monkeypatch):
    """Admin cancel enqueues a cancellation email notification via Celery."""
    admin = _make_admin(db_session, email="admin_s6@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_s6@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    calls = []

    def fake_delay(*args, **kwargs):
        calls.append(kwargs)

        class _R:
            id = "fake"

        return _R()

    monkeypatch.setattr(send_email_notification, "delay", fake_delay)

    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/admin/signups/{signup.id}/cancel", headers=headers)
    assert rc.status_code == 200, rc.text

    kinds = [c.get("kind") for c in calls]
    assert "cancellation" in kinds


def test_admin_cancel_waitlisted_sends_waitlist_copy(client, db_session, monkeypatch):
    """Cancelling a signup that was only ever waitlisted (never held a seat)
    must send waitlist-appropriate copy, not the standard 'your signup has
    been cancelled' text."""
    admin = _make_admin(db_session, email="admin_s9@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    holder = VolunteerFactory(email="v_s9_holder@example.com")
    _seed_confirmed(db_session, slot, holder)  # fills the only seat
    vol = VolunteerFactory(email="v_s9@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification, "delay",
        lambda *a, **k: calls.append(k),
    )

    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/admin/signups/{signup.id}/cancel", headers=headers)
    assert rc.status_code == 200, rc.text

    kinds = [c.get("kind") for c in calls]
    assert "cancellation_waitlisted" in kinds
    assert "cancellation" not in kinds


def test_staff_cancel_waitlisted_sends_waitlist_copy(client, db_session, monkeypatch):
    """Same fix, via the staff /signups/{id}/cancel route (routers/signups.py),
    which has its own independent cancellation-email dispatch."""
    admin = _make_admin(db_session, email="admin_s10@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    holder = VolunteerFactory(email="v_s10_holder@example.com")
    _seed_confirmed(db_session, slot, holder)
    vol = VolunteerFactory(email="v_s10@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        send_email_notification, "delay",
        lambda *a, **k: calls.append(k),
    )

    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/signups/{signup.id}/cancel", headers=headers)
    assert rc.status_code == 200, rc.text

    kinds = [c.get("kind") for c in calls]
    assert "cancellation_waitlisted" in kinds
    assert "cancellation" not in kinds


def test_cancel_via_signups_router_requires_admin_or_organizer(client, db_session):
    """POST /signups/{id}/cancel returns 403 for participant-role user."""
    participant = make_user(db_session, email="p_cancel@example.com")
    admin = _make_admin(db_session, email="admin_s7@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_s7@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    headers = auth_headers(client, participant)
    rc = client.post(f"/api/v1/signups/{signup.id}/cancel", headers=headers)
    assert rc.status_code == 403


def test_cancel_not_found_returns_404(client, db_session):
    """Cancel a non-existent signup returns 404."""
    admin = _make_admin(db_session, email="admin_s8@example.com")
    db_session.commit()

    import uuid
    headers = auth_headers(client, admin)
    rc = client.post(f"/api/v1/admin/signups/{uuid.uuid4()}/cancel", headers=headers)
    assert rc.status_code == 404


def test_staff_cancel_leaves_waitlist_untouched(client, db_session, monkeypatch):
    """Canonical Task 4 regression for the authed staff endpoint
    (routers/signups.py cancel_signup): cancelling a confirmed signup frees
    the seat and stops — no FIFO promotion, no promotion email,
    current_count stays down."""
    sent = []
    monkeypatch.setattr(
        "app.routers.signups.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = _make_admin(db_session, email="admin_s11@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    vol_confirmed = VolunteerFactory(email="v_s11_confirmed@example.com")
    vol_wait = VolunteerFactory(email="v_s11_wait@example.com")
    confirmed_signup = _seed_confirmed(db_session, slot, vol_confirmed)
    waitlisted_signup = _seed_waitlisted(db_session, slot, vol_wait)
    db_session.commit()

    headers = auth_headers(client, admin)
    resp = client.post(f"/api/v1/signups/{confirmed_signup.id}/cancel", headers=headers)
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    waitlisted = db_session.get(models.Signup, waitlisted_signup.id)
    assert waitlisted.status == models.SignupStatus.waitlisted
    slot_row = db_session.get(models.Slot, slot.id)
    assert slot_row.current_count == 0
    assert sent == []
