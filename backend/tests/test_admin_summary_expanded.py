"""Expanded /admin/summary response shape — Phase 16 Plan 02 (D-14..D-29).

Locks the keys the frontend Overview page consumes. Values are checked for
type/presence only; actual aggregation correctness is exercised by narrower
unit tests elsewhere.
"""
from app import models
from tests.fixtures.helpers import auth_headers, make_user


def test_admin_summary_returns_expanded_shape(client, db_session):
    admin = make_user(db_session, email="sum-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    headers = auth_headers(client, admin)

    resp = client.get("/api/v1/admin/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    required_keys = {
        "users_total",
        "events_total",
        "slots_total",
        "signups_total",
        "signups_confirmed_total",
        "users_quarter",
        "events_quarter",
        "slots_quarter",
        "signups_quarter",
        "signups_confirmed_quarter",
        "this_week_events",
        "this_week_open_slots",
        "volunteer_hours_quarter",
        "attendance_rate_quarter",
        "week_over_week",
        "quarter_progress",
        "fill_rate_attention",
        "last_updated",
    }
    missing = required_keys - set(body.keys())
    assert not missing, f"Missing summary keys: {missing}"

    # D-23: signups_last_7d must be absent (field was removed).
    assert "signups_last_7d" not in body

    # Shape checks
    assert isinstance(body["users_total"], int)
    assert isinstance(body["volunteer_hours_quarter"], (int, float))
    assert isinstance(body["attendance_rate_quarter"], (int, float))

    wow = body["week_over_week"]
    assert set(wow.keys()) == {"users", "events", "signups"}
    for v in wow.values():
        assert isinstance(v, int)

    qp = body["quarter_progress"]
    assert set(qp.keys()) == {"week", "of", "pct"}
    assert qp["of"] == 11
    assert 1 <= qp["week"] <= 11

    assert isinstance(body["fill_rate_attention"], list)
    # last_updated is ISO format
    assert "T" in body["last_updated"]


def test_admin_summary_requires_admin(client, db_session):
    organizer = make_user(
        db_session, email="sum-org@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.get("/api/v1/admin/summary", headers=headers)
    assert resp.status_code == 403
