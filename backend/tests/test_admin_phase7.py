"""Phase 7 admin dashboard integration tests.

Covers permissions enforcement, audit log pagination, analytics endpoints,
and CCPA export/delete with PII anonymization.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app import models
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import (
    _bind_factories,
    auth_headers,
    make_event_with_slot,
    make_user,
)


def _make_admin(db_session, email="admin7@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _make_organizer(db_session, email="org7@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


# =========================
# Permission tests
# =========================


@pytest.mark.integration
def test_audit_logs_requires_admin(client, db_session):
    """Non-admin users get 403 on audit logs."""
    participant = make_user(db_session, email="p_audit@example.com")
    db_session.commit()
    headers = auth_headers(client, participant)

    resp = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert resp.status_code == 403


@pytest.mark.integration
def test_ccpa_export_requires_admin(client, db_session):
    """Organizers cannot access CCPA export."""
    admin = _make_admin(db_session, email="a_ccpa1@example.com")
    org = _make_organizer(db_session, email="o_ccpa1@example.com")
    target = make_user(db_session, email="t_ccpa1@example.com")
    db_session.commit()

    headers = auth_headers(client, org)
    resp = client.get(
        f"/api/v1/admin/users/{target.id}/ccpa-export?reason=test+export+reason",
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_ccpa_delete_requires_admin(client, db_session):
    """Organizers cannot access CCPA delete."""
    org = _make_organizer(db_session, email="o_ccpa2@example.com")
    target = make_user(db_session, email="t_ccpa2@example.com")
    db_session.commit()

    headers = auth_headers(client, org)
    resp = client.post(
        f"/api/v1/admin/users/{target.id}/ccpa-delete",
        json={"reason": "test deletion reason"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.integration
def test_analytics_requires_admin(client, db_session):
    """Non-admin users get 403 on analytics endpoints."""
    participant = make_user(db_session, email="p_analytics@example.com")
    db_session.commit()
    headers = auth_headers(client, participant)

    for path in [
        "/api/v1/admin/analytics/volunteer-hours",
        "/api/v1/admin/analytics/attendance-rates",
        "/api/v1/admin/analytics/no-show-rates",
    ]:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 403, f"{path} should return 403, got {resp.status_code}"


# =========================
# Functional tests
# =========================


@pytest.mark.integration
def test_audit_logs_pagination(client, db_session):
    """Paginated audit logs return items, total, page, page_size, pages."""
    admin = _make_admin(db_session, email="a_paginate@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get(
        "/api/v1/admin/audit-logs?page=1&page_size=25",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data
    assert data["page"] == 1
    assert data["page_size"] == 25


@pytest.mark.integration
def test_audit_logs_csv_export(client, db_session):
    """CSV export returns text/csv with correct headers."""
    admin = _make_admin(db_session, email="a_csv@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/audit-logs.csv", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Check CSV has header row
    lines = resp.text.strip().split("\n")
    assert len(lines) >= 1
    # Phase 16 Plan 02 (D-19/D-34): CSV headers are now the humanized shape
    # (When, Who, Role, What, Target, Raw Action, Entity ID).
    assert "When" in lines[0]
    assert "Raw Action" in lines[0]


@pytest.mark.integration
def test_analytics_volunteer_hours_shape(client, db_session):
    """Volunteer hours endpoint returns list with volunteer-keyed fields."""
    admin = _make_admin(db_session, email="a_vhours@example.com")
    _bind_factories(db_session)
    # Seed an attended signup so we get at least one row back
    _, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.attended,
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/analytics/volunteer-hours", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    assert "volunteer_id" in row
    assert "volunteer_name" in row
    assert "email" in row
    assert "hours" in row
    assert "events" in row


@pytest.mark.integration
def test_analytics_attendance_rates_shape(client, db_session):
    """Attendance rates endpoint returns expected shape."""
    admin = _make_admin(db_session, email="a_attend@example.com")
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/analytics/attendance-rates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.integration
def test_ccpa_export_returns_user_data(client, db_session):
    """CCPA export returns all user data sections including signups via Volunteer email match."""
    admin = _make_admin(db_session, email="a_ccpaexp@example.com")
    target = make_user(db_session, email="target_ccpa@example.com", name="Jane Doe")
    _bind_factories(db_session)
    # Create a Volunteer with the same email as target so CCPA can link signups
    vol = VolunteerFactory(email="target_ccpa@example.com")
    _, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    SignupFactory(volunteer=vol, slot=slot, status=models.SignupStatus.confirmed)
    db_session.commit()

    headers = auth_headers(client, admin)
    resp = client.get(
        f"/api/v1/admin/users/{target.id}/ccpa-export?reason=CCPA+data+request",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert "signups" in data
    assert "audit_logs" in data
    assert "notifications" in data
    assert data["user"]["name"] == "Jane Doe"
    assert data["user"]["email"] == "target_ccpa@example.com"
    # signups should be non-empty — volunteer email matches user email
    assert len(data["signups"]) >= 1
    signup_row = data["signups"][0]
    assert "id" in signup_row
    assert "status" in signup_row


@pytest.mark.integration
def test_ccpa_delete_anonymizes_pii(client, db_session):
    """CCPA delete anonymizes name, email, university_id and sets deleted_at."""
    admin = _make_admin(db_session, email="a_ccpadel@example.com")
    target = make_user(db_session, email="todelete_ccpa@example.com", name="John Smith")
    target_id = target.id
    db_session.commit()

    headers = auth_headers(client, admin)
    resp = client.post(
        f"/api/v1/admin/users/{target_id}/ccpa-delete",
        json={"reason": "User requested account deletion"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"

    # Verify PII is anonymized in the database
    db_session.expire_all()
    user = db_session.query(models.User).filter(models.User.id == target_id).first()
    assert user is not None, "User row should still exist (soft delete)"
    assert user.name == "[deleted]"
    assert user.email.startswith("deleted-")
    assert user.email.endswith("@example.invalid")
    assert user.university_id is None
    assert user.hashed_password == "DELETED"
    assert user.deleted_at is not None


@pytest.mark.integration
def test_ccpa_delete_preserves_signups(client, db_session):
    """CCPA delete preserves signup rows for analytics integrity.

    Signups are keyed to Volunteer (not User), so deleting/anonymizing the User
    account must not cascade to the Volunteer's signup rows.
    """
    admin = _make_admin(db_session, email="a_ccpakeep@example.com")
    target = make_user(db_session, email="keep_signups@example.com", name="Keep User")
    _bind_factories(db_session)
    # Create a Volunteer + Signup; link by shared email so CCPA can find them
    vol = VolunteerFactory(email="keep_signups@example.com")
    _, slot = make_event_with_slot(db_session, capacity=5, owner=admin)
    signup = SignupFactory(volunteer=vol, slot=slot, status=models.SignupStatus.confirmed)
    signup_id = signup.id
    db_session.commit()

    admin_headers = auth_headers(client, admin)
    resp = client.post(
        f"/api/v1/admin/users/{target.id}/ccpa-delete",
        json={"reason": "User requested full deletion"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    # Verify signup still exists — Volunteer is independent of User
    db_session.expire_all()
    signup_row = db_session.query(models.Signup).filter(models.Signup.id == signup_id).first()
    assert signup_row is not None, "Signup should be preserved after CCPA delete"
    assert signup_row.volunteer_id == vol.id
