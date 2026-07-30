"""Full coverage for app.routers.signups (cancel + ICS + swap endpoints).

Targets the authenticated /api/v1/signups router (admin/organizer only).
Volunteer self-serve cancel/swap flows live under /api/v1/public/signups.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import SignupFactory, SlotFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _make_admin(db_session, email="admin_sf@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _make_organizer(db_session, email="org_sf@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


def _seed_confirmed(db_session, slot, vol):
    _bind_factories(db_session)
    s = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    slot.current_count = slot.current_count + 1
    db_session.flush()
    return s


# ---------------------------------------------------------------------------
# POST /signups/{id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_via_signups_admin_succeeds(client, db_session):
    admin = _make_admin(db_session, email="adm_sf1@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_sf1@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "cancelled"


def test_cancel_via_signups_organizer_succeeds(client, db_session):
    org = _make_organizer(db_session, email="org_sf2@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=org)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_sf2@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/cancel",
        headers=auth_headers(client, org),
    )
    assert rc.status_code == 200, rc.text


def test_cancel_via_signups_not_found(client, db_session):
    admin = _make_admin(db_session, email="adm_sf3@example.com")
    db_session.commit()
    rc = client.post(
        f"/api/v1/signups/{uuid.uuid4()}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 404


def test_cancel_via_signups_already_cancelled_idempotent(client, db_session):
    admin = _make_admin(db_session, email="adm_sf4@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_sf4@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.cancelled,
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200
    assert rc.json()["status"] == "cancelled"


def test_cancel_via_signups_promotes_waitlisted(client, db_session):
    admin = _make_admin(db_session, email="adm_sf5@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    vol_a = VolunteerFactory(email="v_sf5a@example.com")
    vol_b = VolunteerFactory(email="v_sf5b@example.com")
    signup_a = _seed_confirmed(db_session, slot, vol_a)
    older = datetime.now(timezone.utc) - timedelta(minutes=10)
    signup_b = SignupFactory(
        volunteer=vol_b, slot=slot, status=models.SignupStatus.waitlisted,
        timestamp=older,
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup_a.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text


def test_cancel_via_signups_heals_count_drift(client, db_session):
    """If slot.current_count drifts above actual confirmed, cancel heals it."""
    admin = _make_admin(db_session, email="adm_sf6@example.com")
    _, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_sf6@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    # Inflate count to simulate drift
    slot.current_count = 99
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text
    db_session.expire_all()
    refreshed = db_session.query(models.Slot).filter_by(id=slot.id).one()
    # After heal + cancel, only count goes from 1 (actual confirmed) → 0
    assert refreshed.current_count == 0


# Slot/event missing 404 branches in cancel are FK-protected at the DB level
# and marked # pragma: no cover.


# ---------------------------------------------------------------------------
# GET /signups/{id}/ics
# ---------------------------------------------------------------------------


def test_ics_admin_returns_calendar(client, db_session):
    admin = _make_admin(db_session, email="adm_ics1@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_ics1@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.get(
        f"/api/v1/signups/{signup.id}/ics",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200
    body = rc.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in body
    assert "END:VCALENDAR" in body
    assert rc.headers["content-type"].startswith("text/calendar")
    assert "attachment" in rc.headers["content-disposition"]


def test_ics_organizer_allowed(client, db_session):
    org = _make_organizer(db_session, email="org_ics2@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=org)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_ics2@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.get(
        f"/api/v1/signups/{signup.id}/ics",
        headers=auth_headers(client, org),
    )
    assert rc.status_code == 200


def test_ics_participant_forbidden(client, db_session):
    p = make_user(db_session, email="p_ics3@example.com")
    admin = _make_admin(db_session, email="adm_ics3@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_ics3@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.get(
        f"/api/v1/signups/{signup.id}/ics",
        headers=auth_headers(client, p),
    )
    assert rc.status_code == 403


def test_ics_signup_not_found(client, db_session):
    admin = _make_admin(db_session, email="adm_ics4@example.com")
    db_session.commit()
    rc = client.get(
        f"/api/v1/signups/{uuid.uuid4()}/ics",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 404


# Slot/event missing 404 branches in ICS are FK-protected at the DB level
# and marked # pragma: no cover.


def test_ics_handles_event_without_title_or_location(client, db_session):
    """event.location may be null — code falls back to empty string."""
    admin = _make_admin(db_session, email="adm_ics7@example.com")
    event, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    event.location = None
    _bind_factories(db_session)
    vol = VolunteerFactory(email="v_ics7@example.com")
    signup = _seed_confirmed(db_session, slot, vol)
    db_session.commit()

    rc = client.get(
        f"/api/v1/signups/{signup.id}/ics",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200
    assert "LOCATION:" in rc.text


# ---------------------------------------------------------------------------
# POST /signups/{id}/swap
# ---------------------------------------------------------------------------


def test_swap_admin_succeeds(client, db_session):
    admin = _make_admin(db_session, email="adm_sw1@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw1@example.com")
    signup = _seed_confirmed(db_session, slot_a, vol)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, admin),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["slot_id"] == str(slot_b.id)


def test_swap_organizer_succeeds(client, db_session):
    org = _make_organizer(db_session, email="org_sw2@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=2, owner=org)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw2@example.com")
    signup = _seed_confirmed(db_session, slot_a, vol)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, org),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 200, rc.text


def test_swap_participant_forbidden(client, db_session):
    p = make_user(db_session, email="p_sw3@example.com")
    admin = _make_admin(db_session, email="adm_sw3@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=2, owner=admin)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw3@example.com")
    signup = _seed_confirmed(db_session, slot_a, vol)
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, p),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 403


def test_cancel_via_signups_sends_waitlist_promote_email(client, db_session, monkeypatch):
    """Cancel-triggered promotion must email the promoted volunteer, same as
    the organizer manual-promote path does."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda **kw: sent.append(kw),
    )
    promoted_emails = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: promoted_emails.append(kw),
    )
    admin = _make_admin(db_session, email="admin_wpe@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    vol_a = VolunteerFactory(email="vol_a_wpe@example.com")
    vol_b = VolunteerFactory(email="vol_b_wpe@example.com")
    a = _seed_confirmed(db_session, slot, vol_a)
    b = SignupFactory(
        volunteer=vol_b,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    rc = client.post(f"/api/v1/signups/{a.id}/cancel", headers=auth_headers(client, admin))
    assert rc.status_code == 200, rc.text

    pairs = {(kw["kind"], kw["signup_id"]) for kw in sent}
    assert ("cancellation", str(a.id)) in pairs
    assert any(kw["signup_id"] == str(b.id) for kw in promoted_emails), (
        f"promoted volunteer got no waitlist promotion email (sent: {promoted_emails})"
    )


def test_swap_admin_of_waitlisted_signup_lands_pending_with_email(
    client, db_session, monkeypatch
):
    """2026-07-29 sweep, Task 8: a staff swap of a waitlisted signup is not
    volunteer intent — it must land 'pending' with its own promotion confirm
    email, same as the admin move path (Task 4), not silently 'confirmed'."""
    promoted_emails = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: promoted_emails.append(kw),
    )
    admin = _make_admin(db_session, email="adm_sw4@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw4@example.com")
    signup = SignupFactory(
        volunteer=vol,
        slot=slot_a,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, admin),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "pending"
    assert rc.json()["slot_id"] == str(slot_b.id)
    assert any(kw["signup_id"] == str(signup.id) for kw in promoted_emails), (
        f"promoted signup got no promotion confirm email (sent: {promoted_emails})"
    )


def test_swap_admin_of_cancelled_signup_is_refused(client, db_session):
    """2026-07-29 sweep: staff correcting an attendance mistake use the
    roster's attendance controls, not swap — a cancelled signup must not be
    resurrected to 'confirmed' by moving it to a different slot."""
    admin = _make_admin(db_session, email="adm_sw5@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw5@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot_a, status=models.SignupStatus.cancelled,
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, admin),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 422, rc.text
    assert rc.json()["code"] == "SIGNUP_NOT_SWAPPABLE"
    db_session.expire_all()
    untouched = db_session.get(models.Signup, signup.id)
    assert untouched.status == models.SignupStatus.cancelled
    assert untouched.slot_id == slot_a.id


def test_swap_admin_of_attended_signup_succeeds(client, db_session):
    """Deliberate asymmetry (2026-07-29 sweep, hours-inflation fix): a
    participant swap of an attended signup is refused (self-serve credited-
    hours inflation — see swap_service.py), but staff retain the ability to
    swap one, e.g. to correct a mis-resolved slot."""
    admin = _make_admin(db_session, email="adm_sw6@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    slot_b = SlotFactory(
        event=event,
        start_time=slot_a.start_time + timedelta(hours=4),
        end_time=slot_a.end_time + timedelta(hours=4),
        capacity=2,
        current_count=0,
    )
    vol = VolunteerFactory(email="v_sw6@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot_a, status=models.SignupStatus.attended,
    )
    slot_a.current_count = 1
    db_session.commit()

    rc = client.post(
        f"/api/v1/signups/{signup.id}/swap",
        headers=auth_headers(client, admin),
        json={"target_slot_id": str(slot_b.id)},
    )
    assert rc.status_code == 200, rc.text
    assert rc.json()["status"] == "attended"
    assert rc.json()["slot_id"] == str(slot_b.id)
