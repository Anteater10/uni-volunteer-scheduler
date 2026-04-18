"""Admin router integration tests (Plan 06 / Task 2).

Proves admin paths use the same canonical promote_waitlist_fifo as the
participant cancel path, and locks basic admin CRUD + audit-log filtering.
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


def test_admin_cancel_signup_promotes_waitlist(client, db_session):
    """Admin cancel path uses promote_waitlist_fifo — B waitlisted, A cancelled, B promoted."""
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
    # Promoted signups go directly to 'confirmed' — the volunteer already
    # consented at initial signup time; no double-confirm needed.
    assert b_row.status == models.SignupStatus.confirmed


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
