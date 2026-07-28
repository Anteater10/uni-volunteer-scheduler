"""Expanded /admin/summary response shape — Phase 16 Plan 02 (D-14..D-29).

Locks the keys the frontend Overview page consumes. Values are checked for
type/presence only; actual aggregation correctness is exercised by narrower
unit tests elsewhere.

Issue #24: "this quarter" aggregates now use the admin-entered quarter rows
(active quarter, else the most recently ended one), and quarter_progress
derives from the entered range — null during gaps / with no quarters.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="sum-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


def _make_quarter(db_session, *, start, end, season=models.Quarter.SPRING, year=None):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=season, year=year or start.year, start_date=start, end_date=end,
    )
    db_session.flush()
    return q


def _make_event_on(db_session, owner, when):
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Summary event",
        start_date=when,
        end_date=when + timedelta(hours=2),
    )
    db_session.add(event)
    db_session.flush()
    return event


def test_admin_summary_returns_expanded_shape(client, db_session, admin_headers):
    # An active quarter covering today, exactly 11 weeks long.
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=35)
    _make_quarter(db_session, start=start, end=start + timedelta(days=76))

    resp = client.get("/api/v1/admin/summary", headers=admin_headers)
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
    assert set(qp.keys()) == {"week", "of", "day", "days", "pct"}
    assert qp["of"] == 11  # derives from the entered 11-week range
    assert qp["week"] == 6  # 35 days in = week 6
    assert qp["days"] == 77  # 11 whole weeks
    assert qp["day"] == 36  # 35 days in, counting today
    assert qp["pct"] == round(36 / 77, 2)
    assert isinstance(body["fill_rate_attention"], list)
    # last_updated is ISO format
    assert "T" in body["last_updated"]


def test_admin_summary_gap_uses_most_recent_quarter(client, db_session, admin_headers):
    """During a gap the quarter aggregates cover the last ended quarter and
    quarter_progress is null."""
    admin = make_user(db_session, email="gap-owner@example.com", role=models.UserRole.admin)
    now = datetime.now(timezone.utc)
    today = now.date()

    past_q = _make_quarter(
        db_session,
        start=today - timedelta(days=100),
        end=today - timedelta(days=40),
    )
    _make_event_on(db_session, admin, now - timedelta(days=50))  # inside past quarter
    _make_event_on(db_session, admin, now - timedelta(days=10))  # in the gap
    db_session.commit()

    resp = client.get("/api/v1/admin/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quarter_progress"] is None
    assert body["events_quarter"] == 1
    assert body["events_total"] == 2
    assert past_q is not None


def test_admin_summary_without_quarters_zeroes_quarter_aggregates(
    client, db_session, admin_headers
):
    admin = make_user(db_session, email="noq-owner@example.com", role=models.UserRole.admin)
    _make_event_on(db_session, admin, datetime.now(timezone.utc) - timedelta(days=3))
    db_session.commit()

    resp = client.get("/api/v1/admin/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quarter_progress"] is None
    assert body["events_quarter"] == 0
    assert body["users_quarter"] == 0
    assert body["events_total"] == 1


def test_admin_summary_requires_admin(client, db_session):
    organizer = make_user(
        db_session, email="sum-org@example.com", role=models.UserRole.organizer
    )
    db_session.commit()
    headers = auth_headers(client, organizer)

    resp = client.get("/api/v1/admin/summary", headers=headers)
    assert resp.status_code == 403
