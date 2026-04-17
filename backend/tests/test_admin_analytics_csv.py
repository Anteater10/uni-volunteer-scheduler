"""/admin/analytics/{attendance,no-show}-rates.csv — Phase 16 Plan 02 (D-47)."""
from app import models
from tests.fixtures.helpers import auth_headers, make_user


def test_attendance_rates_csv_returns_text_csv(client, db_session):
    admin = make_user(
        db_session, email="csv-att-admin@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/analytics/attendance-rates.csv", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Header row present
    first_line = resp.text.splitlines()[0]
    assert "Event" in first_line
    assert "Attendance Rate" in first_line


def test_no_show_rates_csv_returns_text_csv(client, db_session):
    admin = make_user(
        db_session, email="csv-ns-admin@example.com", role=models.UserRole.admin
    )
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/analytics/no-show-rates.csv", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    first_line = resp.text.splitlines()[0]
    assert "Volunteer" in first_line
    assert "No-Show Rate" in first_line


def test_attendance_rates_csv_requires_admin(client, db_session):
    organizer = make_user(
        db_session, email="csv-org@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.get("/api/v1/admin/analytics/attendance-rates.csv", headers=headers)
    assert resp.status_code == 403
