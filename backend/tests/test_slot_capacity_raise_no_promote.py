"""Task 6: raising a slot's capacity no longer chain-promotes its waitlist.

The waitlist is now a pure holding list — the only remaining promotion
paths are explicit staff actions (admin promote, admin move, staff swap
of a waitlisted signup). PATCH /slots/{id} widens (or narrows) `capacity`
only: `current_count` and every waitlisted signup's status are untouched,
and no promotion email is enqueued either way.
"""
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, auth_headers, make_event_with_slot, make_user


def _seed_waitlisted(db_session, slot, vol, *, when=None):
    _bind_factories(db_session)
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup


def _organizer(db_session, email="cap_raise_organizer@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


def test_raising_capacity_promotes_nobody(client, db_session, monkeypatch):
    organizer = _organizer(db_session)
    event, slot = make_event_with_slot(db_session, capacity=1, owner=organizer)
    _bind_factories(db_session)
    confirmed_vol = VolunteerFactory(email="cap_raise_confirmed@example.com")
    SignupFactory(
        volunteer=confirmed_vol,
        slot=slot,
        status=models.SignupStatus.confirmed,
    )
    slot.current_count = 1  # full
    vol_b = VolunteerFactory(email="cap_raise_b@example.com")
    vol_c = VolunteerFactory(email="cap_raise_c@example.com")
    older = datetime.now(timezone.utc) - timedelta(minutes=10)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    signup_b = _seed_waitlisted(db_session, slot, vol_b, when=older)
    signup_c = _seed_waitlisted(db_session, slot, vol_c, when=newer)
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )

    headers = auth_headers(client, organizer)
    # Room for two more seats — if promotion still ran, both waitlisted
    # rows would move to pending. It must not.
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 3}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.capacity == 3
    assert slot_row.current_count == 1  # unchanged
    statuses = [s.status for s in slot_row.signups]
    assert statuses.count(models.SignupStatus.waitlisted) == 2
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    assert b_row.status == models.SignupStatus.waitlisted
    assert c_row.status == models.SignupStatus.waitlisted
    assert sent == []  # no promotion emails


def test_lowering_capacity_still_does_not_promote(client, db_session, monkeypatch):
    organizer = _organizer(db_session, email="cap_raise_organizer4@example.com")
    event, slot = make_event_with_slot(db_session, capacity=5, owner=organizer)
    slot.current_count = 2
    _bind_factories(db_session)
    vol = VolunteerFactory(email="cap_lower@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )

    headers = auth_headers(client, organizer)
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 3}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    still_waitlisted = db_session.query(models.Signup).filter(models.Signup.id == signup.id).one()
    assert still_waitlisted.status == models.SignupStatus.waitlisted
    assert sent == []
