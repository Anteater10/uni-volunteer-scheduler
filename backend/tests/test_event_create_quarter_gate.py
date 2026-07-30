"""Issue #24 decision 6: event creation is gated on an admin-entered quarter.

Every event belongs to a quarter — creating one whose date falls in no
defined quarter is rejected with an actionable 422, and the cache columns
(quarter/year/week_number) always derive from the entered range (explicit
stale values in the payload are overridden).
"""
import uuid
from datetime import date, timedelta

import pytest

from app import models
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import auth_headers, make_user


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
        slug=f"gate-bio-{uuid.uuid4().hex[:8]}",
        name="Intro Bio",
        default_capacity=20,
        duration_minutes=90,
        session_count=1,
    )
    db_session.add(tpl)
    db_session.flush()
    return tpl


def _seed_spring(db_session):
    # Sweep remediation task 5 (ended quarters are read-only): dates are
    # relative to real today so this quarter never lapses into read-only
    # history as wall-clock time passes. Span (76 days) and day offsets used
    # by callers below (_payload day 16/51/gap+3) are preserved from the
    # original fixed Spring 2026 range (Mar 30 - Jun 14) so the week_number
    # assertions keep meaning; `year=2026` stays as the quarter's own label,
    # independent of the actual start_date used here.
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    start = date.today() - timedelta(days=1)
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=start,
        end_date=start + timedelta(days=76),
    )
    db_session.flush()
    return q


def _payload(day: str, module_slug: str) -> dict:
    return {
        "title": "Intro Bio",
        "start_date": f"{day}T16:00:00Z",
        "end_date": f"{day}T18:00:00Z",
        "module_slug": module_slug,
    }


def test_create_derives_quarter_from_entered_range(
    client, db_session, organizer_headers, module_template
):
    spring = _seed_spring(db_session)
    day = (spring.start_date + timedelta(days=16)).isoformat()

    resp = client.post("/api/v1/events/", json=_payload(day, module_template.slug), headers=organizer_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quarter"] == "spring"
    assert body["year"] == 2026
    assert body["week_number"] == 3
    assert body["quarter_id"] == str(spring.id)

    event = db_session.get(models.Event, uuid.UUID(body["id"]))
    assert event.quarter_id == spring.id


def test_create_rejected_on_gap_date(client, db_session, organizer_headers, module_template):
    spring = _seed_spring(db_session)

    # 3 days after spring ends, with nothing entered after it
    gap_day = (spring.end_date + timedelta(days=3)).isoformat()
    resp = client.post("/api/v1/events/", json=_payload(gap_day, module_template.slug), headers=organizer_headers)
    assert resp.status_code == 422, resp.text
    assert "No quarter covers" in str(resp.json()["detail"])


def test_create_rejected_when_no_quarters_entered(
    client, db_session, organizer_headers, module_template
):
    resp = client.post("/api/v1/events/", json=_payload("2026-04-15", module_template.slug), headers=organizer_headers)
    assert resp.status_code == 422, resp.text


def test_update_rederives_quarter_when_date_moves(
    client, db_session, organizer_headers, module_template
):
    spring = _seed_spring(db_session)
    day = (spring.start_date + timedelta(days=16)).isoformat()
    created = client.post(
        "/api/v1/events/", json=_payload(day, module_template.slug), headers=organizer_headers
    ).json()
    assert created["week_number"] == 3

    moved_day = (spring.start_date + timedelta(days=51)).isoformat()
    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"start_date": f"{moved_day}T16:00:00Z", "end_date": f"{moved_day}T18:00:00Z"},
        headers=organizer_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["week_number"] == 8


def test_update_rejected_when_new_date_uncovered(
    client, db_session, organizer_headers, module_template
):
    spring = _seed_spring(db_session)
    day = (spring.start_date + timedelta(days=16)).isoformat()
    created = client.post(
        "/api/v1/events/", json=_payload(day, module_template.slug), headers=organizer_headers
    ).json()

    gap_day = (spring.end_date + timedelta(days=3)).isoformat()
    resp = client.put(
        f"/api/v1/events/{created['id']}",
        json={"start_date": f"{gap_day}T16:00:00Z", "end_date": f"{gap_day}T18:00:00Z"},
        headers=organizer_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "No quarter covers" in str(resp.json()["detail"])


def test_explicit_stale_quarter_values_are_overridden(
    client, db_session, organizer_headers, module_template
):
    spring = _seed_spring(db_session)
    day = (spring.start_date + timedelta(days=16)).isoformat()

    payload = {**_payload(day, module_template.slug), "quarter": "fall", "year": 2031, "week_number": 11}
    resp = client.post("/api/v1/events/", json=payload, headers=organizer_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quarter"] == "spring"
    assert body["year"] == 2026
    assert body["week_number"] == 3
