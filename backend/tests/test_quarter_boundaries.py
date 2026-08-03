"""Issue #24 Phase 7: HTTP-level acceptance tests for quarter boundaries.

End-to-end (router → service → DB) checks of the #24 acceptance criteria:
the last week of a quarter, the first week of each summer session, and
entering a quarter linking pre-existing events. Gap-date rejection lives in
test_event_create_quarter_gate.py; gap current-week resolution lives in
test_public_events.py::TestCurrentWeek.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user

@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="qb-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


@pytest.fixture
def organizer_headers(client, db_session):
    organizer = make_user(db_session, role=models.UserRole.organizer)
    db_session.commit()
    return auth_headers(client, organizer)


@pytest.fixture
def module_template(db_session):
    # Unique slug: data migrations seed real template rows, and the alembic
    # round-trip tests leave that seeded state in the shared test DB.
    tpl = models.Module(
        slug=f"boundary-bio-{uuid.uuid4().hex[:8]}",
        name="Boundary Bio",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


def _seed_quarter(db_session, **kwargs):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(**kwargs)
    db_session.flush()
    return q


def _event_payload(day: str, module_slug: str) -> dict:
    return {
        "title": "Boundary event",
        "start_date": f"{day}T16:00:00Z",
        "end_date": f"{day}T18:00:00Z",
        "module_slug": module_slug,
    }


def test_event_on_last_day_of_quarter_gets_final_week(
    client, db_session, organizer_headers, module_template
):
    # Sweep remediation task 5 (ended quarters are read-only): dates are
    # relative to real today — end_date == today keeps the quarter writable
    # (is_quarter_read_only only trips once end_date < today) regardless of
    # when this suite runs. Span (76 days) preserves the original Mar 30 -
    # Jun 14 2026 range so the week 11 assertion still holds.
    today = date.today()
    spring = _seed_quarter(
        db_session,
        season=models.Quarter.SPRING,
        year=2026,
        start_date=today - timedelta(days=76),
        end_date=today,
    )

    resp = client.post(
        "/api/v1/events/",
        json=_event_payload(today.isoformat(), module_template.slug),
        headers=organizer_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["week_number"] == 11
    assert body["quarter"] == "spring"
    assert body["quarter_id"] == str(spring.id)


def test_first_week_of_each_summer_session(
    client, db_session, organizer_headers, module_template
):
    # Sweep remediation task 5 (ended quarters are read-only): dates are
    # relative to real today, like the last-day test above. The original
    # hardcoded Jun 22 - Jul 31 / Aug 3 - Sep 11 2026 ranges passed until
    # 2026-07-31 and failed every run after, because event creation rejects
    # a quarter whose end_date has passed. Both sessions now start today or
    # later so neither is read-only whenever this suite runs. The original
    # shape is preserved: two 40-day sessions with a 2-day gap between them,
    # and an event on each session's first day.
    today = datetime.now(timezone.utc).date()  # is_quarter_read_only uses UTC
    a_start = today
    a_end = a_start + timedelta(days=39)
    b_start = a_end + timedelta(days=3)
    b_end = b_start + timedelta(days=39)

    session_a = _seed_quarter(
        db_session,
        season=models.Quarter.SUMMER,
        year=a_start.year,
        label="Session A",
        start_date=a_start,
        end_date=a_end,
    )
    session_b = _seed_quarter(
        db_session,
        season=models.Quarter.SUMMER,
        year=b_start.year,
        label="Session B",
        start_date=b_start,
        end_date=b_end,
    )

    on_a_start = client.post(
        "/api/v1/events/",
        json=_event_payload(a_start.isoformat(), module_template.slug),
        headers=organizer_headers,
    )
    assert on_a_start.status_code == 200, on_a_start.text
    assert on_a_start.json()["week_number"] == 1
    assert on_a_start.json()["quarter_id"] == str(session_a.id)

    on_b_start = client.post(
        "/api/v1/events/",
        json=_event_payload(b_start.isoformat(), module_template.slug),
        headers=organizer_headers,
    )
    assert on_b_start.status_code == 200, on_b_start.text
    assert on_b_start.json()["week_number"] == 1
    assert on_b_start.json()["quarter_id"] == str(session_b.id)


def test_entering_a_quarter_links_preexisting_events_end_to_end(
    client, db_session, admin_headers
):
    # A legacy row: predates the quarters table, so its cache is stale and
    # it has no quarter_id. Only direct-DB rows can exist in this state —
    # the API refuses uncovered dates. Dates are relative to real today:
    # the public browse check must survive hide_past_events_from_public,
    # which filters events that already ended.
    today = date.today()
    quarter_payload = {
        "season": "spring",
        "year": 2033,
        "start_date": (today - timedelta(days=7)).isoformat(),
        "end_date": (today + timedelta(days=63)).isoformat(),
    }
    event_day = today + timedelta(days=1)  # day 8 of the range → week 2

    owner = make_user(db_session)
    legacy = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Legacy event",
        start_date=datetime(event_day.year, event_day.month, event_day.day, 16, 0, tzinfo=timezone.utc),
        end_date=datetime(event_day.year, event_day.month, event_day.day, 18, 0, tzinfo=timezone.utc),
        quarter=models.Quarter.FALL,
        year=2031,
        week_number=1,
    )
    db_session.add(legacy)
    db_session.commit()

    resp = client.post("/api/v1/admin/quarters", json=quarter_payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["relink_summary"]["linked"] == 1
    quarter_id = body["quarter"]["id"]

    db_session.expire_all()
    refreshed = db_session.get(models.Event, legacy.id)
    assert str(refreshed.quarter_id) == quarter_id
    assert refreshed.quarter == models.Quarter.SPRING
    assert refreshed.year == 2033
    assert refreshed.week_number == 2

    listed = client.get(
        "/api/v1/public/events",
        params={"quarter_id": quarter_id, "week_number": 2},
    )
    assert listed.status_code == 200, listed.text
    assert str(legacy.id) in [e["id"] for e in listed.json()]
