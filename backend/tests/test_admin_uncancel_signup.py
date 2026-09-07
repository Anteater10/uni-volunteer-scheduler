"""SCRUM-155: an admin can reverse a cancellation.

Cancelling used to be one-way. A volunteer who emailed "I can't make it" and
then found they could was stuck — staff had cancelled them, and the public
page refuses a second signup while a row already exists for them.
"""
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import SignupFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _make_admin(db_session, email="admin_uncancel@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _cancelled_signup(db_session, slot, email):
    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory

    vol = VolunteerFactory(email=email)
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.cancelled,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    return signup


def test_uncancel_restores_the_signup_and_takes_the_seat(client, db_session):
    admin = _make_admin(db_session)
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    signup = _cancelled_signup(db_session, slot, "back_on@example.com")
    slot.current_count = 0
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{signup.id}/uncancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    row = db_session.query(models.Signup).filter(models.Signup.id == signup.id).one()
    assert row.status == models.SignupStatus.confirmed
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 1


def test_uncancel_emails_the_volunteer(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda **kw: sent.append(kw),
    )
    admin = _make_admin(db_session, email="admin_uncancel_mail@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    signup = _cancelled_signup(db_session, slot, "mailed@example.com")
    slot.current_count = 0
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{signup.id}/uncancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    kinds = {(kw["kind"], kw["signup_id"]) for kw in sent}
    assert ("resignup", str(signup.id)) in kinds


def test_each_uncancel_gets_its_own_dedup_marker(client, db_session, monkeypatch):
    """Cancel, reinstate, cancel, reinstate is a real sequence.

    sent_notifications dedups on (anchor, kind), so a fixed "resignup" kind
    would silently swallow the second mail. The dispatch-time suffix is what
    keeps each genuine reinstatement audible while a Celery retry of one
    dispatch still dedups.
    """
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda **kw: sent.append(kw),
    )
    admin = _make_admin(db_session, email="admin_uncancel_twice@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    signup = _cancelled_signup(db_session, slot, "twice@example.com")
    slot.current_count = 0
    db_session.commit()
    headers = auth_headers(client, admin)

    assert (
        client.post(
            f"/api/v1/admin/signups/{signup.id}/uncancel", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/admin/signups/{signup.id}/cancel", headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/admin/signups/{signup.id}/uncancel", headers=headers
        ).status_code
        == 200
    )

    dedup_kinds = [kw["dedup_kind"] for kw in sent if kw.get("kind") == "resignup"]
    assert len(dedup_kinds) == 2
    assert dedup_kinds[0] != dedup_kinds[1]
    # kind is String(32) — a marker that overflows would fail on insert.
    assert all(len(k) <= 32 for k in dedup_kinds)


def test_uncancel_is_refused_when_the_seat_was_taken(client, db_session):
    """A cancel frees the seat, so someone else may hold it by now."""
    admin = _make_admin(db_session, email="admin_uncancel_full@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory

    cancelled = _cancelled_signup(db_session, slot, "was_out@example.com")
    taker = VolunteerFactory(email="took_it@example.com")
    SignupFactory(
        volunteer=taker,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc),
    )
    slot.current_count = 1
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{cancelled.id}/uncancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 400
    assert "full" in resp.json()["detail"].lower()

    db_session.expire_all()
    row = db_session.query(models.Signup).filter(models.Signup.id == cancelled.id).one()
    assert row.status == models.SignupStatus.cancelled


def test_uncancel_is_refused_for_a_signup_that_is_not_cancelled(client, db_session):
    admin = _make_admin(db_session, email="admin_uncancel_active@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory

    vol = VolunteerFactory(email="already_on@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.confirmed
    )
    slot.current_count = 1
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{signup.id}/uncancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 400

    db_session.expire_all()
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    # The guard runs before any counting, so a no-op cannot inflate the seat.
    assert slot_row.current_count == 1


def test_uncancel_of_a_missing_signup_is_404(client, db_session):
    import uuid

    admin = _make_admin(db_session, email="admin_uncancel_404@example.com")
    db_session.commit()
    resp = client.post(
        f"/api/v1/admin/signups/{uuid.uuid4()}/uncancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404
