"""/admin/site-settings endpoints — including the show_audit_logs_tab flag.

The Audit Logs admin tab is gated behind ``SiteSettings.show_audit_logs_tab``
(migration 0028, off by default). These tests lock the endpoint contract the
frontend AdminLayout/SiteSettingsCard rely on:

- GET  /admin/site-settings — admin AND organizer may read (the nav needs it)
- PATCH /admin/site-settings — admin only; partial update (None fields kept)
- ``show_audit_logs_tab`` defaults to False for the lazily-created singleton
- every PATCH writes a ``site_settings_updated`` audit row with the changes
"""
from __future__ import annotations

from app import models
from tests.fixtures.helpers import auth_headers, make_user


def _admin_headers(client, db_session, email="settings-admin@example.com"):
    admin = make_user(db_session, email=email, role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


def _organizer_headers(client, db_session, email="settings-org@example.com"):
    org = make_user(db_session, email=email, role=models.UserRole.organizer)
    db_session.commit()
    return auth_headers(client, org)


def test_get_defaults_show_audit_logs_tab_false(client, db_session):
    """The lazily-created singleton row defaults the new flag to False."""
    # Drop any row left over from another test's savepoint so the endpoint
    # exercises lazy creation with column defaults.
    db_session.query(models.SiteSettings).delete()
    db_session.flush()

    headers = _admin_headers(client, db_session)
    res = client.get("/api/v1/admin/site-settings", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["show_audit_logs_tab"] is False
    assert body["hide_past_events_from_public"] is True


def test_admin_can_toggle_show_audit_logs_tab(client, db_session):
    headers = _admin_headers(client, db_session)

    res = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"show_audit_logs_tab": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["show_audit_logs_tab"] is True

    # Persists across a fresh read.
    res2 = client.get("/api/v1/admin/site-settings", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["show_audit_logs_tab"] is True

    # And back off again.
    res3 = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"show_audit_logs_tab": False},
    )
    assert res3.status_code == 200
    assert res3.json()["show_audit_logs_tab"] is False


def test_patch_is_partial_and_leaves_other_fields_alone(client, db_session):
    """PATCHing only the new flag must not clobber hide_past_events_from_public."""
    headers = _admin_headers(client, db_session)

    # Establish a non-default value for the neighbouring flag.
    res = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"hide_past_events_from_public": False},
    )
    assert res.status_code == 200, res.text

    res2 = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"show_audit_logs_tab": True},
    )
    assert res2.status_code == 200
    body = res2.json()
    assert body["show_audit_logs_tab"] is True
    assert body["hide_past_events_from_public"] is False


def test_patch_writes_audit_row_with_changes(client, db_session):
    headers = _admin_headers(client, db_session)

    res = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"show_audit_logs_tab": True},
    )
    assert res.status_code == 200, res.text

    row = (
        db_session.query(models.AuditLog)
        .filter(models.AuditLog.action == "site_settings_updated")
        .order_by(models.AuditLog.timestamp.desc())
        .first()
    )
    assert row is not None, "PATCH /admin/site-settings must write an audit row"
    assert row.extra["changes"] == {"show_audit_logs_tab": True}


def test_organizer_can_read_but_not_write(client, db_session):
    headers = _organizer_headers(client, db_session)

    res = client.get("/api/v1/admin/site-settings", headers=headers)
    assert res.status_code == 200, res.text
    assert "show_audit_logs_tab" in res.json()

    res2 = client.patch(
        "/api/v1/admin/site-settings",
        headers=headers,
        json={"show_audit_logs_tab": True},
    )
    assert res2.status_code == 403


def test_unauthenticated_cannot_read_or_write(client):
    assert client.get("/api/v1/admin/site-settings").status_code == 401
    assert (
        client.patch(
            "/api/v1/admin/site-settings", json={"show_audit_logs_tab": True}
        ).status_code
        == 401
    )
