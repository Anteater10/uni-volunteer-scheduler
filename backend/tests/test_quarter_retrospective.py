"""Issue #38: admin quarter retrospective — per-event attendance breakdown.

GET /admin/quarters/{id}/retrospective returns every event linked to the
quarter (by quarter_id FK) with signup/capacity/attended/no-show counts,
plus quarter-level totals. Works for any quarter by id — admins review a
past quarter before archiving it; the frontend decides where to link.
"""
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest

from app import models
from tests.fixtures.factories import (
    AcademicQuarterFactory,
    EventFactory,
    SignupFactory,
    SlotFactory,
    UserFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import auth_headers, make_user

TODAY = date.today()


@pytest.fixture
def admin_headers(client, db_session):
    admin = make_user(db_session, email="retro-admin@example.com", role=models.UserRole.admin)
    db_session.commit()
    return auth_headers(client, admin)


@pytest.fixture
def organizer_headers(client, db_session):
    organizer = make_user(db_session, role=models.UserRole.organizer)
    db_session.commit()
    return auth_headers(client, organizer)


def _bind(db_session):
    for f in (
        UserFactory,
        EventFactory,
        SlotFactory,
        VolunteerFactory,
        SignupFactory,
        AcademicQuarterFactory,
    ):
        f._meta.sqlalchemy_session = db_session


def _past_quarter(db_session, *, weeks_back=20, season=models.Quarter.SPRING, year=2020, label=""):
    _bind(db_session)
    start = TODAY - timedelta(weeks=weeks_back)
    q = AcademicQuarterFactory(
        season=season, year=year, label=label,
        start_date=start, end_date=start + timedelta(days=76),  # 11 weeks
    )
    db_session.flush()
    return q


def _event_in(db_session, q, *, day=0, week=1, title=None):
    """Event linked to q via the quarter_id FK, starting `day` days into it."""
    _bind(db_session)
    start = datetime.combine(q.start_date + timedelta(days=day), time(9), tzinfo=timezone.utc)
    kwargs = {"title": title} if title else {}
    event = EventFactory(
        start_date=start,
        end_date=start + timedelta(hours=6),
        quarter_id=q.id,
        quarter=q.season,
        year=q.year,
        week_number=week,
        **kwargs,
    )
    db_session.flush()
    return event


def _slot(db_session, event, *, capacity=10):
    _bind(db_session)
    slot = SlotFactory(event=event, capacity=capacity)
    db_session.flush()
    return slot


def _signups(db_session, slot, *statuses):
    _bind(db_session)
    for status in statuses:
        SignupFactory(slot=slot, status=status)
    db_session.flush()


def _get(client, headers, quarter_id):
    return client.get(
        f"/api/v1/admin/quarters/{quarter_id}/retrospective", headers=headers
    )


class TestPerEventBreakdown:
    def test_per_event_breakdown_counts_statuses(self, client, db_session, admin_headers):
        q = _past_quarter(db_session)
        event = _event_in(db_session, q)
        slot = _slot(db_session, event, capacity=10)
        _signups(
            db_session, slot,
            models.SignupStatus.confirmed,
            models.SignupStatus.confirmed,
            models.SignupStatus.pending,
            models.SignupStatus.attended,
            models.SignupStatus.checked_in,
            models.SignupStatus.no_show,
            models.SignupStatus.waitlisted,
            models.SignupStatus.cancelled,
        )
        db_session.commit()

        resp = _get(client, admin_headers, q.id)
        assert resp.status_code == 200, resp.text
        rows = resp.json()["events"]
        assert len(rows) == 1
        row = rows[0]
        assert row["event_id"] == str(event.id)
        assert row["slot_count"] == 1
        # capacity is the slot sum, NOT multiplied by the signup join
        assert row["capacity"] == 10
        # waitlisted + cancelled never held a seat — excluded
        assert row["signups"] == 6
        assert row["attended"] == 2  # attended + checked_in
        assert row["no_shows"] == 1

    def test_checked_in_counts_as_attended(self, client, db_session, admin_headers):
        # A past-quarter signup left at checked_in was physically present even
        # if never promoted to attended — same bucket as roster checked_in_count.
        q = _past_quarter(db_session)
        slot = _slot(db_session, _event_in(db_session, q))
        _signups(db_session, slot, models.SignupStatus.checked_in)
        db_session.commit()

        row = _get(client, admin_headers, q.id).json()["events"][0]
        assert row["attended"] == 1
        assert row["no_shows"] == 0

    def test_events_ordered_by_start_date(self, client, db_session, admin_headers):
        q = _past_quarter(db_session)
        _event_in(db_session, q, day=14, week=3, title="Later event")
        _event_in(db_session, q, day=0, week=1, title="First event")
        db_session.commit()

        rows = _get(client, admin_headers, q.id).json()["events"]
        assert [r["title"] for r in rows] == ["First event", "Later event"]
        assert [r["week_number"] for r in rows] == [1, 3]

    def test_zero_slot_and_zero_signup_events_show_zeroes(
        self, client, db_session, admin_headers
    ):
        q = _past_quarter(db_session)
        _event_in(db_session, q, day=0, title="No slots")
        empty = _event_in(db_session, q, day=7, week=2, title="Empty slots")
        _slot(db_session, empty, capacity=5)
        db_session.commit()

        rows = {r["title"]: r for r in _get(client, admin_headers, q.id).json()["events"]}
        assert rows["No slots"] == {
            **rows["No slots"], "slot_count": 0, "capacity": 0,
            "signups": 0, "attended": 0, "no_shows": 0,
        }
        assert rows["Empty slots"]["capacity"] == 5
        assert rows["Empty slots"]["signups"] == 0

    def test_events_of_other_quarters_excluded(self, client, db_session, admin_headers):
        target = _past_quarter(db_session, weeks_back=40, season=models.Quarter.WINTER)
        other = _past_quarter(db_session, weeks_back=20, season=models.Quarter.SPRING)
        _event_in(db_session, target, title="Target event")
        _event_in(db_session, other, title="Other event")
        db_session.commit()

        rows = _get(client, admin_headers, target.id).json()["events"]
        assert [r["title"] for r in rows] == ["Target event"]


class TestTotals:
    def test_totals_and_attendance_rate(self, client, db_session, admin_headers):
        q = _past_quarter(db_session)
        slot_a = _slot(db_session, _event_in(db_session, q, day=0), capacity=10)
        slot_b = _slot(db_session, _event_in(db_session, q, day=7, week=2), capacity=8)
        _signups(
            db_session, slot_a,
            models.SignupStatus.attended,
            models.SignupStatus.attended,
            models.SignupStatus.no_show,
        )
        _signups(db_session, slot_b, models.SignupStatus.confirmed)
        db_session.commit()

        totals = _get(client, admin_headers, q.id).json()["totals"]
        assert totals["events"] == 2
        assert totals["slots"] == 2
        assert totals["capacity"] == 18
        assert totals["signups"] == 4
        assert totals["attended"] == 2
        assert totals["no_shows"] == 1
        assert totals["attendance_rate"] == round(2 / 4, 4)

    def test_quarter_with_no_events_returns_empty_list_and_zero_totals(
        self, client, db_session, admin_headers
    ):
        q = _past_quarter(db_session)
        db_session.commit()

        resp = _get(client, admin_headers, q.id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["events"] == []
        assert data["totals"] == {
            "events": 0, "slots": 0, "capacity": 0,
            "signups": 0, "attended": 0, "no_shows": 0,
            "attendance_rate": 0.0,
        }


class TestAccess:
    def test_works_for_unarchived_past_quarter(self, client, db_session, admin_headers):
        # Admins review a quarter BEFORE archiving it — no archived_at gate.
        q = _past_quarter(db_session)
        db_session.commit()

        resp = _get(client, admin_headers, q.id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["quarter"]["archived_at"] is None

    def test_quarter_payload_echoes_archived_quarter(
        self, client, db_session, admin_headers
    ):
        q = _past_quarter(db_session)
        db_session.commit()
        archived = client.post(
            f"/api/v1/admin/quarters/{q.id}/archive", headers=admin_headers
        )
        assert archived.status_code == 200, archived.text

        quarter = _get(client, admin_headers, q.id).json()["quarter"]
        assert quarter["display_name"] == q.display_name
        assert quarter["archived_at"] is not None

    def test_unknown_quarter_returns_404(self, client, admin_headers):
        resp = _get(client, admin_headers, uuid4())
        assert resp.status_code == 404, resp.text

    def test_non_admin_forbidden(self, client, db_session, organizer_headers):
        q = _past_quarter(db_session)
        db_session.commit()

        resp = _get(client, organizer_headers, q.id)
        assert resp.status_code == 403, resp.text
