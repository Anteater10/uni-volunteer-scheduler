"""Admin router integration tests (Plan 06 / Task 2).

Locks basic admin CRUD + audit-log filtering. 2026-08-02 read-only signups
(Task 4): admin_cancel_signup no longer auto-promotes the waitlist — it
frees the seat and stops. promote_waitlist_fifo is still exercised by the
manual promote (admin_promote_signup) and move (admin_signup_move) paths.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import SignupFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _make_admin(db_session, email="admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def test_admin_list_users_requires_admin(client, db_session):
    participant = make_user(db_session, email="plain@example.com")
    db_session.commit()
    headers = auth_headers(client, participant)

    resp = client.get("/api/v1/users/", headers=headers)
    assert resp.status_code == 403


def test_admin_create_user(client, db_session):
    admin = _make_admin(db_session)
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.post(
        "/api/v1/users/",
        json={
            "name": "Created By Admin",
            "email": "cba@example.com",
            "role": "participant",
            "password": "somepassword!",
            "notify_email": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    created = db_session.query(models.User).filter(models.User.email == "cba@example.com").first()
    assert created is not None


def test_admin_delete_user(client, db_session):
    admin = _make_admin(db_session, email="admin_del@example.com")
    target = make_user(db_session, email="todelete@example.com")
    db_session.commit()

    headers = auth_headers(client, admin)
    resp = client.delete(f"/api/v1/admin/users/{target.id}", headers=headers)
    assert resp.status_code == 204

    gone = db_session.query(models.User).filter(models.User.id == target.id).first()
    assert gone is None


def test_admin_cancel_signup_does_not_promote_waitlist(client, db_session):
    """2026-08-02 read-only signups (Task 4): admin cancel frees the seat
    but leaves the waitlist untouched — the waitlist only moves by explicit
    staff promotion now, never as a side effect of a cancel."""
    admin = _make_admin(db_session, email="admin_pf@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol_a = VolunteerFactory(email="vol_a_pf@example.com")
    vol_b = VolunteerFactory(email="vol_b_pf@example.com")

    # A gets the one confirmed slot
    a_signup = SignupFactory(
        volunteer=vol_a,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    slot.current_count = 1
    # B is waitlisted
    b_signup = SignupFactory(
        volunteer=vol_b,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    # Admin cancels A
    rc = client.post(
        f"/api/v1/admin/signups/{a_signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text

    db_session.expire_all()
    b_row = db_session.query(models.Signup).filter(models.Signup.id == b_signup.id).one()
    # No auto-promotion — B stays waitlisted, the freed seat sits open.
    assert b_row.status == models.SignupStatus.waitlisted
    slot_row = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert slot_row.current_count == 0


def test_admin_cancel_of_attended_signup_is_refused(client, db_session):
    """2026-07-29 sweep — mirrors
    test_cancel_via_signups_of_attended_signup_is_refused (test_signups_
    router_full.py) for the admin router's own cancel endpoint. Same guard
    (check_in_service.ensure_signup_cancellable), same no-staff-exception
    rationale: cancelling an attended signup would erase a settled
    attendance record that volunteer hours/course credit are computed from,
    and nothing else in the app reverses attended/no_show for staff either
    (the one sanctioned undo, reopen_event, is event-wide and audited)."""
    admin = _make_admin(db_session, email="admin_ac1@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol = VolunteerFactory(email="vol_ac1@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.attended,
    )
    slot.current_count = 1
    db_session.commit()

    rc = client.post(
        f"/api/v1/admin/signups/{signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 422, rc.text
    assert rc.json()["code"] == "SIGNUP_NOT_CANCELLABLE"
    db_session.expire_all()
    untouched = db_session.query(models.Signup).filter(models.Signup.id == signup.id).one()
    assert untouched.status == models.SignupStatus.attended
    refreshed_slot = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert refreshed_slot.current_count == 1


def test_admin_cancel_of_no_show_signup_is_refused(client, db_session):
    """no_show sibling of the attended guard above."""
    admin = _make_admin(db_session, email="admin_ac2@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)
    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol = VolunteerFactory(email="vol_ac2@example.com")
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.no_show,
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/admin/signups/{signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 422, rc.text
    assert rc.json()["code"] == "SIGNUP_NOT_CANCELLABLE"
    db_session.expire_all()
    untouched = db_session.query(models.Signup).filter(models.Signup.id == signup.id).one()
    assert untouched.status == models.SignupStatus.no_show
    refreshed_slot = db_session.query(models.Slot).filter(models.Slot.id == slot.id).one()
    assert refreshed_slot.current_count == 0


def test_admin_summary_requires_admin(client, db_session):
    admin = _make_admin(db_session, email="admin_sum@example.com")
    db_session.commit()

    resp = client.get("/api/v1/admin/summary", headers=auth_headers(client, admin))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Phase 16 Plan 02: summary shape expanded per D-14..D-29.
    for key in ("users_total", "events_total", "slots_total", "signups_total"):
        assert key in body


def test_admin_audit_logs_filter(client, db_session):
    admin = _make_admin(db_session, email="admin_audit@example.com")
    db_session.commit()

    # Generate a log entry by calling /admin/summary (logs admin_summary action).
    client.get("/api/v1/admin/summary", headers=auth_headers(client, admin))

    resp = client.get(
        "/api/v1/admin/audit_logs",
        params={"action": "admin_summary"},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert any(entry["action"] == "admin_summary" for entry in body["items"])


def test_admin_cancel_sends_no_waitlist_promote_email(client, db_session, monkeypatch):
    """2026-08-02 read-only signups (Task 4): admin cancel still sends the
    cancellation email, but must never enqueue a waitlist promotion email —
    cancel no longer promotes anyone."""
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
    admin = _make_admin(db_session, email="admin_pf_email@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol_a = VolunteerFactory(email="vol_a_pfe@example.com")
    vol_b = VolunteerFactory(email="vol_b_pfe@example.com")
    a_signup = SignupFactory(
        volunteer=vol_a,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    slot.current_count = 1
    b_signup = SignupFactory(
        volunteer=vol_b,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    rc = client.post(
        f"/api/v1/admin/signups/{a_signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert rc.status_code == 200, rc.text

    pairs = {(kw["kind"], kw["signup_id"]) for kw in sent}
    assert ("cancellation", str(a_signup.id)) in pairs
    assert promoted_emails == [], (
        f"cancel must never enqueue a promotion email (sent: {promoted_emails})"
    )


def test_admin_cancel_leaves_waitlist_untouched(client, db_session, monkeypatch):
    """Canonical Task 4 regression: cancelling a confirmed signup frees the
    seat and stops — no FIFO promotion, no promotion email, current_count
    stays down."""
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    admin = _make_admin(db_session, email="admin_leave_wl@example.com")
    _, slot = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol_confirmed = VolunteerFactory(email="admin_leave_wl_conf@example.com")
    vol_wait = VolunteerFactory(email="admin_leave_wl_wait@example.com")
    confirmed_signup = SignupFactory(
        volunteer=vol_confirmed,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    slot.current_count = 1
    waitlisted_signup = SignupFactory(
        volunteer=vol_wait,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{confirmed_signup.id}/cancel",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    waitlisted = db_session.get(models.Signup, waitlisted_signup.id)
    assert waitlisted.status == models.SignupStatus.waitlisted
    slot_row = db_session.get(models.Slot, slot.id)
    assert slot_row.current_count == 0
    assert sent == []


def test_admin_promote_signup_goes_pending_with_confirm_email(client, db_session, monkeypatch):
    """admin_promote_signup (WAIT-03 admin path) now delegates to
    manual_promote/mark_promoted_pending like the organizer path: the
    promoted signup goes to 'pending' (not instantly 'confirmed'), the
    confirm-your-spot email goes out via send_waitlist_promotion_email
    (previously wrong kind="confirmation", which the (signup_id, kind)
    dedup could silently swallow), and slot.current_count is incremented
    exactly once — manual_promote owns the increment now, so the endpoint
    must not also do it (regression: double-counting)."""
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
    admin = _make_admin(db_session, email="admin_promote_pending@example.com")
    _, slot = make_event_with_slot(db_session, capacity=2, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import VolunteerFactory
    vol_confirmed = VolunteerFactory(email="admin_promote_conf@example.com")
    vol_wait = VolunteerFactory(email="admin_promote_wait@example.com")
    SignupFactory(
        volunteer=vol_confirmed,
        slot=slot,
        status=models.SignupStatus.confirmed,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    slot.current_count = 1
    wait_signup = SignupFactory(
        volunteer=vol_wait,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{wait_signup.id}/promote",
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"

    db_session.expire_all()
    row = db_session.query(models.Signup).filter_by(id=wait_signup.id).one()
    assert row.status == models.SignupStatus.pending
    refreshed_slot = db_session.query(models.Slot).filter_by(id=slot.id).one()
    assert refreshed_slot.current_count == 2, (
        "capacity must be incremented exactly once, not double-counted"
    )

    assert any(kw["signup_id"] == str(wait_signup.id) for kw in promoted_emails), (
        f"promoted volunteer got no confirm-your-spot email (sent: {promoted_emails})"
    )
    assert not any(
        kw.get("kind") == "confirmation" and kw.get("signup_id") == str(wait_signup.id)
        for kw in sent
    ), "promote must not use the generic confirmation kind (dedup can swallow it)"


def test_admin_move_pending_signup_frees_source_capacity(client, db_session):
    """Moving a pending signup must free its source seat — pending holds
    capacity (see _confirmed_count_for_slot), so skipping the decrement
    leaves the source slot overcounted forever."""
    admin = _make_admin(db_session, email="admin_mv_pending@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import SlotFactory, VolunteerFactory
    slot_b = SlotFactory(event=event, event_id=event.id, capacity=1, current_count=0)
    vol = VolunteerFactory(email="mv_pending@example.com")
    pending = SignupFactory(
        volunteer=vol,
        slot=slot_a,
        status=models.SignupStatus.pending,
    )
    slot_a.current_count = 1
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{pending.id}/move",
        json={"target_slot_id": str(slot_b.id)},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    slot_a_row = db_session.get(models.Slot, slot_a.id)
    slot_b_row = db_session.get(models.Slot, slot_b.id)
    assert slot_a_row.current_count == 0, (
        "source slot still counts the moved pending signup"
    )
    assert slot_b_row.current_count == 1


def test_admin_move_pending_signup_promotes_source_waitlist(client, db_session):
    """Freeing a seat by moving a pending signup must promote the source
    waitlist, exactly as moving a confirmed signup does."""
    admin = _make_admin(db_session, email="admin_mv_wl@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import SlotFactory, VolunteerFactory
    slot_b = SlotFactory(event=event, event_id=event.id, capacity=1, current_count=0)
    vol_p = VolunteerFactory(email="mv_wl_pending@example.com")
    vol_w = VolunteerFactory(email="mv_wl_waiting@example.com")
    pending = SignupFactory(
        volunteer=vol_p,
        slot=slot_a,
        status=models.SignupStatus.pending,
    )
    slot_a.current_count = 1
    waitlisted = SignupFactory(
        volunteer=vol_w,
        slot=slot_a,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{pending.id}/move",
        json={"target_slot_id": str(slot_b.id)},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    w = db_session.get(models.Signup, waitlisted.id)
    slot_a_row = db_session.get(models.Slot, slot_a.id)
    assert w.status == models.SignupStatus.pending, (
        "source waitlist was not promoted after the pending move freed a seat"
    )
    assert slot_a_row.current_count == 1


def test_admin_move_pending_signup_stays_pending_when_target_has_room(client, db_session):
    """Preserve-status fix: moving a pending signup into an open target slot
    must NOT silently upgrade it to confirmed — the volunteer never clicked
    a confirm link. Regression for admin_move_signup's preserve-status arm
    (previously new_status was unconditionally 'confirmed' whenever the
    target had room)."""
    admin = _make_admin(db_session, email="admin_mv_stays_pending@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import SlotFactory, VolunteerFactory
    slot_b = SlotFactory(event=event, event_id=event.id, capacity=1, current_count=0)
    vol = VolunteerFactory(email="mv_stays_pending@example.com")
    pending = SignupFactory(
        volunteer=vol,
        slot=slot_a,
        status=models.SignupStatus.pending,
    )
    slot_a.current_count = 1
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{pending.id}/move",
        json={"target_slot_id": str(slot_b.id)},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending", (
        "move silently upgraded a pending signup to confirmed"
    )

    db_session.expire_all()
    moved = db_session.get(models.Signup, pending.id)
    slot_b_row = db_session.get(models.Slot, slot_b.id)
    assert moved.status == models.SignupStatus.pending
    assert str(moved.slot_id) == str(slot_b.id)
    assert slot_b_row.current_count == 1, "target slot should have incremented"


def test_admin_move_sends_waitlist_promotion_email_for_source_promotion(
    client, db_session, monkeypatch
):
    """Regression: the move path must enqueue send_waitlist_promotion_email
    for anyone promoted off the source slot's waitlist when the move frees a
    seat — the move previously promoted silently with no email at all."""
    promoted_emails = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: promoted_emails.append(kw),
    )
    admin = _make_admin(db_session, email="admin_mv_email@example.com")
    event, slot_a = make_event_with_slot(db_session, capacity=1, owner=admin)

    _bind_factories(db_session)
    from tests.fixtures.factories import SlotFactory, VolunteerFactory
    slot_b = SlotFactory(event=event, event_id=event.id, capacity=1, current_count=0)
    vol_p = VolunteerFactory(email="mv_email_pending@example.com")
    vol_w = VolunteerFactory(email="mv_email_waiting@example.com")
    pending = SignupFactory(
        volunteer=vol_p,
        slot=slot_a,
        status=models.SignupStatus.pending,
    )
    slot_a.current_count = 1
    waitlisted = SignupFactory(
        volunteer=vol_w,
        slot=slot_a,
        status=models.SignupStatus.waitlisted,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/signups/{pending.id}/move",
        json={"target_slot_id": str(slot_b.id)},
        headers=auth_headers(client, admin),
    )
    assert resp.status_code == 200, resp.text

    assert len(promoted_emails) == 1, (
        f"expected exactly one promotion email, got: {promoted_emails}"
    )
    assert promoted_emails[0]["signup_id"] == str(waitlisted.id)
    assert promoted_emails[0]["token"], "raw token must travel to the email task"
