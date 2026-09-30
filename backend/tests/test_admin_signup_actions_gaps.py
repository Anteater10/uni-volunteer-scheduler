"""Staff signup actions in routers/admin.py that had no test: reinstating a
cancelled shift commitment, promote/move/reorder guard rails, resending a
signup email, event notify skipping address-less volunteers, and the
overview's fill-rate colours."""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    book_shift,
    make_event_with_slot,
    make_shift,
    make_user,
)


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay", lambda **kw: calls.append(kw)
    )
    monkeypatch.setattr(
        "app.celery_app.send_broadcast_email.delay", lambda *a, **kw: calls.append(("broadcast", a))
    )
    return calls


@pytest.fixture
def admin(db_session):
    return make_user(db_session, email=f"act{uuid.uuid4().hex[:6]}@x.com", role=models.UserRole.admin)


def _signup(db_session, slot, status, **vol):
    _bind_factories(db_session)
    s = SignupFactory(volunteer=VolunteerFactory(**vol), slot=slot, status=status)
    db_session.flush()
    return s


def _post(client, user, path, json=None):
    return client.post(f"/api/v1/admin{path}", json=json, headers=auth_headers(client, user))


# --- Reinstate a cancelled shift commitment ---------------------------------


def _cancelled_commitment(db_session, admin, *, capacity=2, current=0):
    event, _ = make_event_with_slot(db_session, owner=admin)
    shift = make_shift(db_session, event.id, capacity=capacity)
    shift.current_count = current
    _bind_factories(db_session)
    ss = book_shift(db_session, shift, VolunteerFactory(), status=models.SignupStatus.cancelled)
    db_session.commit()
    return shift, ss


def test_uncancel_shift_signup_restores_seat_and_emails(client, db_session, admin, sent):
    shift, ss = _cancelled_commitment(db_session, admin)
    resp = _post(client, admin, f"/shift-signups/{ss.id}/uncancel")
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(models.ShiftSignup, ss.id).status == models.SignupStatus.confirmed
    assert db_session.get(models.Shift, shift.id).current_count == 1
    assert sent[0]["kind"] == "resignup" and sent[0]["shift_signup_id"] == str(ss.id)
    assert db_session.query(models.AuditLog).filter_by(action="admin_shift_signup_uncancel").count() == 1


def test_uncancel_shift_signup_refuses_active_commitment(client, db_session, admin, sent):
    event, _ = make_event_with_slot(db_session, owner=admin)
    shift = make_shift(db_session, event.id)
    _bind_factories(db_session)
    ss = book_shift(db_session, shift, VolunteerFactory(), status=models.SignupStatus.confirmed)
    db_session.commit()
    resp = _post(client, admin, f"/shift-signups/{ss.id}/uncancel")
    assert resp.status_code == 400
    assert "Only cancelled" in resp.text
    assert sent == []


def test_uncancel_shift_signup_refuses_when_full(client, db_session, admin, sent):
    _, ss = _cancelled_commitment(db_session, admin, capacity=1, current=1)
    resp = _post(client, admin, f"/shift-signups/{ss.id}/uncancel")
    assert resp.status_code == 400
    assert "Shift is full" in resp.text


def test_uncancel_shift_signup_unknown_is_404(client, db_session, admin, sent):
    db_session.commit()
    assert _post(client, admin, f"/shift-signups/{uuid.uuid4()}/uncancel").status_code == 404


def test_uncancel_signup_corrects_a_drifted_count(client, db_session, admin, sent):
    """The slot counter drifted above the real number of held seats; reinstating
    recounts before judging capacity, so the stale count cannot block it."""
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.cancelled)
    slot.current_count = 1  # stale: nobody actually holds the seat
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/uncancel")
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(models.Slot, slot.id).current_count == 1


# --- Promote ------------------------------------------------------------------


def test_promote_refuses_a_signup_not_on_the_waitlist(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.confirmed)
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/promote")
    assert resp.status_code == 400
    assert "Only waitlisted" in resp.text


def test_promote_recounts_then_refuses_a_full_slot(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _signup(db_session, slot, models.SignupStatus.confirmed)
    w = _signup(db_session, slot, models.SignupStatus.waitlisted)
    slot.current_count = 0  # drifted low; the real count is 1
    db_session.commit()
    resp = _post(client, admin, f"/signups/{w.id}/promote")
    # The stale 0 would have let the promote through; refusing proves the
    # recount ran. Nothing is saved on a refusal.
    assert resp.status_code == 400
    assert "Slot is full" in resp.text


def test_promote_maps_a_service_value_error_to_400(client, db_session, admin, sent, monkeypatch):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    w = _signup(db_session, slot, models.SignupStatus.waitlisted)
    db_session.commit()

    def refuse(*a, **k):
        raise ValueError("cannot promote")

    monkeypatch.setattr("app.services.waitlist_service.manual_promote", refuse)
    resp = _post(client, admin, f"/signups/{w.id}/promote")
    assert resp.status_code == 400
    assert "cannot promote" in resp.text


# --- Reorder waitlist ---------------------------------------------------------


def test_reorder_waitlist_slot_from_another_event_is_404(client, db_session, admin, sent):
    event, _ = make_event_with_slot(db_session, owner=admin)
    _, other_slot = make_event_with_slot(db_session, owner=admin)
    db_session.commit()
    resp = client.patch(
        f"/api/v1/admin/events/{event.id}/slots/{other_slot.id}/waitlist-order",
        json={"ordered_signup_ids": []},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 404


def test_reorder_waitlist_needs_a_list(client, db_session, admin, sent):
    event, slot = make_event_with_slot(db_session, owner=admin)
    db_session.commit()
    resp = client.patch(
        f"/api/v1/admin/events/{event.id}/slots/{slot.id}/waitlist-order",
        json={"ordered_signup_ids": "not-a-list"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 422


# --- Move -----------------------------------------------------------------------


def _second_orientation(db_session, event_id):
    start = datetime.now(timezone.utc) + timedelta(days=2)
    slot = models.Slot(
        id=uuid.uuid4(), event_id=event_id, start_time=start, end_time=start + timedelta(hours=1),
        capacity=5, current_count=0, slot_type=models.SlotType.ORIENTATION, date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def test_move_to_the_same_slot_is_400(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.confirmed)
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/move", {"target_slot_id": str(slot.id)})
    assert resp.status_code == 400
    assert "must be different" in resp.text


def test_move_to_an_unknown_slot_is_404(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.confirmed)
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/move", {"target_slot_id": str(uuid.uuid4())})
    assert resp.status_code == 404


def test_move_to_another_event_is_400(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    _, elsewhere = make_event_with_slot(db_session, capacity=2, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.confirmed)
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/move", {"target_slot_id": str(elsewhere.id)})
    assert resp.status_code == 400
    assert "same event" in resp.text


# --- Resend --------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,kind",
    [
        (models.SignupStatus.confirmed, "confirmation"),
        (models.SignupStatus.pending, "confirmation"),
        (models.SignupStatus.cancelled, "cancellation"),
        (models.SignupStatus.waitlisted, None),
    ],
)
def test_resend_picks_the_email_for_the_status(client, db_session, admin, sent, status, kind):
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)
    s = _signup(db_session, slot, status)
    db_session.commit()
    resp = _post(client, admin, f"/signups/{s.id}/resend")
    assert resp.status_code == 204
    assert [c.get("kind") for c in sent] == ([kind] if kind else [])
    db_session.expire_all()
    assert db_session.query(models.AuditLog).filter_by(action="admin_signup_resend").count() == 1


def test_resend_unknown_signup_is_404(client, db_session, admin, sent):
    db_session.commit()
    assert _post(client, admin, f"/signups/{uuid.uuid4()}/resend").status_code == 404


def test_resend_is_staff_only(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, owner=admin)
    s = _signup(db_session, slot, models.SignupStatus.confirmed)
    user = make_user(db_session, email="resend-p@x.com")
    db_session.commit()
    assert _post(client, user, f"/signups/{s.id}/resend").status_code == 403


# --- Notify ---------------------------------------------------------------------


def test_notify_skips_volunteers_without_an_address(client, db_session, admin, sent):
    _, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    _signup(db_session, slot, models.SignupStatus.confirmed, email="has@x.com")
    _signup(db_session, slot, models.SignupStatus.confirmed, email="")
    db_session.commit()
    resp = _post(
        client, admin, f"/events/{slot.event_id}/notify", {"subject": "S", "body": "B"}
    )
    assert resp.status_code == 204
    assert [c[1][0] for c in sent] == ["has@x.com"]


# --- Overview fill-rate colours ------------------------------------------------


@pytest.mark.parametrize(
    "days,capacity,filled,colour",
    [
        (1, 10, 1, "red"),      # under 30% and within 3 days
        (5, 10, 1, "amber"),    # under 30% but further out
        (1, 10, 4, "amber"),    # 30-50%
        (1, 10, 6, "green"),    # 50% or more
    ],
)
def test_summary_fill_rate_colour(client, db_session, admin, days, capacity, filled, colour):
    event, slot = make_event_with_slot(db_session, capacity=capacity, owner=admin, starts_in_days=days)
    slot.current_count = filled
    db_session.commit()
    resp = client.get("/api/v1/admin/summary", headers=auth_headers(client, admin))
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["fill_rate_attention"] if r["event_id"] == str(event.id))
    assert row["status"] == colour


def test_anonymous_participant_payload():
    from app.routers.admin import _volunteer_participant_payload

    v = models.Volunteer(first_name="Ana", last_name="Diaz", email="a@x.com")
    assert _volunteer_participant_payload(v, models.PrivacyMode.anonymous) == {
        "name": "Volunteer", "email": None, "phone": None, "university_id": None,
    }
