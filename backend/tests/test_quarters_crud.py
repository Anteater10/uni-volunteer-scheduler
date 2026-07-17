"""Issue #24 Phase 5: admin quarters CRUD + GET /public/quarters.

Admins transcribe quarter dates from the UCSB academic calendar; weeks
self-populate from the range. Create/update relink matching events and
surface a {linked, weeks_changed, unlinked} summary so recategorization
is visible, never silent.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.helpers import auth_headers, make_user

SPRING = {
    "season": "spring",
    "year": 2026,
    "start_date": "2026-03-30",
    "end_date": "2026-06-14",
}
SESSION_A = {
    "season": "summer",
    "year": 2026,
    "label": "Session A",
    "start_date": "2026-06-22",
    "end_date": "2026-07-31",
}
SESSION_B = {
    "season": "summer",
    "year": 2026,
    "label": "Session B",
    "start_date": "2026-08-03",
    "end_date": "2026-09-11",
}


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="q-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


def _make_event_on(db_session, when, **kwargs):
    owner = make_user(db_session)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="CRUD event",
        start_date=when,
        end_date=when + timedelta(hours=2),
        **kwargs,
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_create_returns_quarter_and_relink_summary(client, db_session, admin_headers):
    resp = client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    q = body["quarter"]
    assert q["season"] == "spring"
    assert q["year"] == 2026
    assert q["label"] == ""
    assert q["weeks_in_quarter"] == 11
    assert q["display_name"] == "Spring 2026"
    assert body["relink_summary"] == {"linked": 0, "weeks_changed": 0, "unlinked": 0}


def test_create_links_existing_events(client, db_session, admin_headers):
    inside = _make_event_on(db_session, datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc))
    stale = _make_event_on(
        db_session,
        datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=1,  # stale — Jun 10 is week 11 of the entered range
    )
    outside = _make_event_on(db_session, datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc))
    db_session.commit()

    resp = client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["relink_summary"] == {"linked": 2, "weeks_changed": 1, "unlinked": 0}

    db_session.expire_all()
    assert str(inside.quarter_id) == body["quarter"]["id"]
    assert inside.week_number == 3
    assert stale.week_number == 11
    assert outside.quarter_id is None


def test_create_summer_sessions_coexist(client, db_session, admin_headers):
    assert client.post("/api/v1/admin/quarters", json=SESSION_A, headers=admin_headers).status_code == 201
    resp = client.post("/api/v1/admin/quarters", json=SESSION_B, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    q = resp.json()["quarter"]
    assert q["weeks_in_quarter"] == 6
    assert q["display_name"] == "Summer 2026 · Session B"


def test_create_duplicate_key_rejected(client, db_session, admin_headers):
    assert client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers).status_code == 201
    dup = {**SPRING, "start_date": "2027-03-29", "end_date": "2027-06-13"}  # no overlap
    resp = client.post("/api/v1/admin/quarters", json=dup, headers=admin_headers)
    assert resp.status_code == 409, resp.text


def test_create_overlap_rejected(client, db_session, admin_headers):
    assert client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers).status_code == 201
    overlapping = {
        "season": "winter",
        "year": 2026,
        "start_date": "2026-01-05",
        "end_date": "2026-03-30",  # collides with spring's (inclusive) first day
    }
    resp = client.post("/api/v1/admin/quarters", json=overlapping, headers=admin_headers)
    assert resp.status_code == 409, resp.text
    assert "overlap" in str(resp.json()["detail"]).lower()


def test_create_bad_dates_rejected(client, db_session, admin_headers):
    bad = {**SPRING, "start_date": "2026-06-14", "end_date": "2026-03-30"}
    resp = client.post("/api/v1/admin/quarters", json=bad, headers=admin_headers)
    assert resp.status_code == 422, resp.text


def test_patch_dates_relinks_and_unlinks(client, db_session, admin_headers):
    created = client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers).json()
    quarter_id = created["quarter"]["id"]
    event = _make_event_on(db_session, datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc))
    db_session.commit()

    # Link it via a no-op-range PATCH first
    resp = client.patch(
        f"/api/v1/admin/quarters/{quarter_id}",
        json={"end_date": "2026-06-14"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["relink_summary"]["linked"] == 1

    # Shrink spring so the event falls out of range
    resp = client.patch(
        f"/api/v1/admin/quarters/{quarter_id}",
        json={"end_date": "2026-06-07"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quarter"]["weeks_in_quarter"] == 10
    assert body["relink_summary"]["unlinked"] == 1

    db_session.expire_all()
    assert event.quarter_id is None
    assert event.week_number is None


def test_delete_unreferenced_quarter(client, db_session, admin_headers):
    created = client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers).json()
    quarter_id = created["quarter"]["id"]

    resp = client.delete(f"/api/v1/admin/quarters/{quarter_id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text
    assert client.get("/api/v1/admin/quarters", headers=admin_headers).json() == []


def test_delete_referenced_quarter_rejected(client, db_session, admin_headers):
    created = client.post("/api/v1/admin/quarters", json=SPRING, headers=admin_headers).json()
    quarter_id = created["quarter"]["id"]
    _make_event_on(
        db_session,
        datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        quarter_id=uuid.UUID(quarter_id),
    )
    db_session.commit()

    resp = client.delete(f"/api/v1/admin/quarters/{quarter_id}", headers=admin_headers)
    assert resp.status_code == 409, resp.text


def test_list_ordered_by_start_date(client, db_session, admin_headers):
    for payload in (SESSION_B, SPRING, SESSION_A):
        assert client.post("/api/v1/admin/quarters", json=payload, headers=admin_headers).status_code == 201

    resp = client.get("/api/v1/admin/quarters", headers=admin_headers)
    assert resp.status_code == 200
    names = [q["display_name"] for q in resp.json()]
    assert names == ["Spring 2026", "Summer 2026 · Session A", "Summer 2026 · Session B"]


def test_requires_admin(client, db_session):
    organizer = make_user(db_session, email="q-org@example.com", role=models.UserRole.organizer)
    db_session.commit()
    headers = auth_headers(client, organizer)

    assert client.get("/api/v1/admin/quarters", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/quarters", json=SPRING, headers=headers).status_code == 403


def test_public_quarters_list(client, db_session, admin_headers):
    for payload in (SPRING, SESSION_A):
        assert client.post("/api/v1/admin/quarters", json=payload, headers=admin_headers).status_code == 201

    resp = client.get("/api/v1/public/quarters")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["display_name"] for r in rows] == ["Spring 2026", "Summer 2026 · Session A"]
    assert rows[0]["weeks_in_quarter"] == 11
    assert rows[1]["weeks_in_quarter"] == 6
    assert rows[0]["start_date"] == "2026-03-30"
