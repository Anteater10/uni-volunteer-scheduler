"""Task 7 item 5: raising a slot's capacity chain-promotes its waitlist.

PATCH /slots/{id} historically only changed the capacity number — a
waitlisted volunteer sitting behind a slot that just grew never got
promoted until some unrelated cancel/reap touched the slot. Raising
capacity now chain-promotes via the canonical promote_waitlist_fifo
(2026-07-28 spec: pending + confirm email, not straight to confirmed),
inheriting the centralized ended-slot guard (silent skip, matching every
other FIFO auto-promotion site).
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


def test_raising_capacity_promotes_oldest_waitlisted_to_pending(client, db_session, monkeypatch):
    organizer = _organizer(db_session)
    event, slot = make_event_with_slot(db_session, capacity=1, owner=organizer)
    slot.current_count = 1  # full
    _bind_factories(db_session)
    vol_b = VolunteerFactory(email="cap_raise_b@example.com")
    vol_c = VolunteerFactory(email="cap_raise_c@example.com")
    older = datetime.now(timezone.utc) - timedelta(minutes=10)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    signup_b = _seed_waitlisted(db_session, slot, vol_b, when=older)
    signup_c = _seed_waitlisted(db_session, slot, vol_c, when=newer)
    db_session.commit()

    headers = auth_headers(client, organizer)
    # One additional seat: exactly one promotion, oldest-first (FIFO).
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 2}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    assert b_row.status == models.SignupStatus.pending
    assert c_row.status == models.SignupStatus.waitlisted
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 2


def test_raising_capacity_enqueues_promotion_email(client, db_session, monkeypatch):
    organizer = _organizer(db_session, email="cap_raise_organizer2@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=organizer)
    slot.current_count = 1
    _bind_factories(db_session)
    vol = VolunteerFactory(email="cap_raise_email@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )

    headers = auth_headers(client, organizer)
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 2}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert len(sent) == 1
    assert sent[0]["signup_id"] == str(signup.id)


def test_raising_capacity_beyond_waitlist_size_promotes_all(client, db_session, monkeypatch):
    organizer = _organizer(db_session, email="cap_raise_organizer3@example.com")
    event, slot = make_event_with_slot(db_session, capacity=1, owner=organizer)
    slot.current_count = 1
    _bind_factories(db_session)
    vol_b = VolunteerFactory(email="cap_raise_all_b@example.com")
    vol_c = VolunteerFactory(email="cap_raise_all_c@example.com")
    signup_b = _seed_waitlisted(db_session, slot, vol_b, when=datetime.now(timezone.utc) - timedelta(minutes=10))
    signup_c = _seed_waitlisted(db_session, slot, vol_c, when=datetime.now(timezone.utc) - timedelta(minutes=1))
    db_session.commit()

    headers = auth_headers(client, organizer)
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 10}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == signup_b.id).one()
    c_row = db_session.query(models.Signup).filter(models.Signup.id == signup_c.id).one()
    assert b_row.status == models.SignupStatus.pending
    assert c_row.status == models.SignupStatus.pending
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 3


def test_lowering_capacity_does_not_promote(client, db_session, monkeypatch):
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


def test_raising_capacity_on_ended_slot_does_not_promote(client, db_session, monkeypatch):
    """Inherits the centralized ended-slot guard: promote_waitlist_fifo skips
    silently (matches every other auto-promotion site), no error, no email."""
    organizer = _organizer(db_session, email="cap_raise_organizer5@example.com")
    now = datetime.now(timezone.utc)
    event, slot = make_event_with_slot(db_session, capacity=1, owner=organizer, starts_in_days=-2)
    # make_event_with_slot anchors start_time to "starts_in_days" and end to +2h;
    # both are already in the past, so the slot has ended.
    slot.current_count = 1
    _bind_factories(db_session)
    vol = VolunteerFactory(email="cap_raise_ended@example.com")
    signup = _seed_waitlisted(db_session, slot, vol)
    db_session.commit()

    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )

    headers = auth_headers(client, organizer)
    resp = client.patch(
        f"/api/v1/slots/{slot.id}", json={"capacity": 2}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    still_waitlisted = db_session.query(models.Signup).filter(models.Signup.id == signup.id).one()
    assert still_waitlisted.status == models.SignupStatus.waitlisted
    assert sent == []
