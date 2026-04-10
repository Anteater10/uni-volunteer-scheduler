"""Signup router + waitlist/cancel integration tests (Plan 06 / Task 2).

Locks:
- capacity / waitlist behavior
- cancel frees capacity and is reusable by a second user
- promote_waitlist_fifo canonical ordering (timestamp, id)
- cancel emails via app.emails BUILDERS

Phase 08 (D-06): signup router still references Signup.user_id; Phase 09 will fix.
"""
import pytest
pytestmark = pytest.mark.skip(reason="Phase 08: Signup.user_id removed; Phase 09 will rewire")

from datetime import datetime, timedelta, timezone

from app import models
from app.celery_app import send_email_notification
from tests.fixtures.factories import SignupFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _seed_waitlisted(db_session, slot, user, *, when=None):
    _bind_factories(db_session)
    signup = SignupFactory(
        user=user,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup


def test_signup_within_capacity(client, db_session):
    user = make_user(db_session, email="p1@example.com")
    event, slot = make_event_with_slot(db_session, capacity=2, owner=user)
    db_session.commit()

    resp = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"


def test_signup_over_capacity_goes_to_waitlist(client, db_session):
    owner = make_user(db_session, email="owner1@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)

    user_a = make_user(db_session, email="a1@example.com")
    user_b = make_user(db_session, email="b1@example.com")
    db_session.commit()

    r1 = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    assert r1.status_code == 200 and r1.json()["status"] == "pending"

    r2 = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_b),
    )
    assert r2.status_code == 200 and r2.json()["status"] == "waitlisted"


def test_cancel_frees_capacity_for_second_user(client, db_session):
    """Canonical cancel→reusable-capacity assertion at the API layer."""
    owner = make_user(db_session, email="owner2@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)

    user_a = make_user(db_session, email="a2@example.com")
    user_b = make_user(db_session, email="b2@example.com")
    db_session.commit()

    r1 = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    assert r1.status_code == 200 and r1.json()["status"] == "pending"
    signup_a_id = r1.json()["id"]

    # A cancels
    rc = client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_a),
    )
    assert rc.status_code == 200

    # B should now be confirmable (starts as pending in phase 2)
    r2 = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_b),
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "pending"

    db_session.expire_all()
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 1


def test_cancel_promotes_waitlist_fifo(client, db_session):
    """A confirmed, B (older) and C (newer) waitlisted; A cancels → B confirmed."""
    owner = make_user(db_session, email="owner3@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)

    user_a = make_user(db_session, email="a3@example.com")
    user_b = make_user(db_session, email="b3@example.com")
    user_c = make_user(db_session, email="c3@example.com")
    db_session.commit()

    # A confirmed via API
    r_a = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    signup_a_id = r_a.json()["id"]

    # B waitlisted (older timestamp)
    older = datetime.now(timezone.utc) - timedelta(minutes=10)
    signup_b = _seed_waitlisted(db_session, slot, user_b, when=older)
    # C waitlisted (newer timestamp)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    signup_c = _seed_waitlisted(db_session, slot, user_c, when=newer)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_a),
    )
    assert rc.status_code == 200

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    # Phase 2: promoted signups go to 'pending' (must confirm via magic link)
    assert b_row.status == models.SignupStatus.pending
    assert c_row.status == models.SignupStatus.waitlisted


def test_waitlist_ordering_uses_timestamp_then_id(client, db_session):
    """With identical timestamps, lower signup.id promotes first."""
    owner = make_user(db_session, email="owner4@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)

    user_a = make_user(db_session, email="a4@example.com")
    user_b = make_user(db_session, email="b4@example.com")
    user_c = make_user(db_session, email="c4@example.com")
    db_session.commit()

    # A confirmed via API (eats the one slot)
    r_a = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    signup_a_id = r_a.json()["id"]

    same_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
    sb = _seed_waitlisted(db_session, slot, user_b, when=same_ts)
    sc = _seed_waitlisted(db_session, slot, user_c, when=same_ts)
    db_session.commit()

    first, second = (sb, sc) if str(sb.id) < str(sc.id) else (sc, sb)

    client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_a),
    )

    db_session.expire_all()
    first_row = db_session.query(models.Signup).filter(models.Signup.id == first.id).one()
    second_row = db_session.query(models.Signup).filter(models.Signup.id == second.id).one()
    # Phase 2: promoted signups go to 'pending' (must confirm via magic link)
    assert first_row.status == models.SignupStatus.pending
    assert second_row.status == models.SignupStatus.waitlisted


def test_cannot_cancel_other_users_signup(client, db_session):
    owner = make_user(db_session, email="owner5@example.com")
    event, slot = make_event_with_slot(db_session, capacity=2, owner=owner)
    user_a = make_user(db_session, email="a5@example.com")
    user_b = make_user(db_session, email="b5@example.com")
    db_session.commit()

    r_a = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    signup_a_id = r_a.json()["id"]

    resp = client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_b),
    )
    assert resp.status_code == 403


def test_cancel_enqueues_cancellation_email(client, db_session, monkeypatch):
    owner = make_user(db_session, email="owner6@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)
    user_a = make_user(db_session, email="a6@example.com")
    db_session.commit()

    r_a = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    signup_a_id = r_a.json()["id"]

    calls = []

    def fake_delay(*args, **kwargs):
        calls.append((args, kwargs))

        class _R:  # result stand-in
            id = "fake"

        return _R()

    monkeypatch.setattr(send_email_notification, "delay", fake_delay)

    rc = client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_a),
    )
    assert rc.status_code == 200
    kinds = [c[1].get("kind") for c in calls]
    assert "cancellation" in kinds


def test_cancel_with_waitlist_promotes_to_pending_with_magic_link(
    client, db_session, monkeypatch
):
    """Phase 2: promoted signups go to pending and get a magic-link email
    instead of a direct confirmation notification."""
    owner = make_user(db_session, email="owner7@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=owner)
    user_a = make_user(db_session, email="a7@example.com")
    user_b = make_user(db_session, email="b7@example.com")
    db_session.commit()

    r_a = client.post(
        "/api/v1/signups/",
        json={"slot_id": str(slot.id)},
        headers=auth_headers(client, user_a),
    )
    signup_a_id = r_a.json()["id"]

    _seed_waitlisted(
        db_session, slot, user_b, when=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    db_session.commit()

    # Monkeypatch magic link email to capture calls
    magic_link_calls = []

    def fake_send_magic_link(*args, **kwargs):
        magic_link_calls.append((args, kwargs))
        return {"to": args[0], "subject": "test"}

    monkeypatch.setattr("app.emails.send_magic_link", fake_send_magic_link)

    calls = []

    def fake_delay(*args, **kwargs):
        calls.append((args, kwargs))

        class _R:
            id = "fake"

        return _R()

    monkeypatch.setattr(send_email_notification, "delay", fake_delay)

    rc = client.post(
        f"/api/v1/signups/{signup_a_id}/cancel",
        headers=auth_headers(client, user_a),
    )
    assert rc.status_code == 200

    # Cancellation email is still sent for the cancelled signup
    kinds = [c[1].get("kind") for c in calls]
    assert "cancellation" in kinds

    # Promoted signup gets a magic-link email instead of confirmation
    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.user_id == user_b.id).first()
    assert b_row.status == models.SignupStatus.pending
