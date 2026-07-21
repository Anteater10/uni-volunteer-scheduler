"""Phase 1 (issue #24): AcademicQuarter model, events.quarter_id FK, DB constraints.

Quarters are admin-entered rows — (season, year, label) + inclusive start/end
dates. Summer Sessions A/B are separate rows distinguished by label; regular
quarters leave label as ''. Overlapping date ranges are rejected at the DB
level so a date maps to at most one quarter.
"""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from tests.fixtures.factories import AcademicQuarterFactory, EventFactory, UserFactory


@pytest.fixture(autouse=True)
def _factories(db_session):
    for f in (AcademicQuarterFactory, EventFactory, UserFactory):
        f._meta.sqlalchemy_session = db_session


def test_quarter_round_trip(db_session):
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 15),
    )
    db_session.flush()

    row = db_session.get(models.AcademicQuarter, q.id)
    assert row.season == models.Quarter.SPRING
    assert row.year == 2026
    assert row.label == ""  # regular quarters carry no session label
    assert row.start_date == date(2026, 3, 30)
    assert row.end_date == date(2026, 6, 15)
    assert row.created_at is not None


def test_summer_sessions_coexist_with_distinct_labels(db_session):
    AcademicQuarterFactory(
        season=models.Quarter.SUMMER,
        year=2026,
        label="Session A",
        start_date=date(2026, 6, 22),
        end_date=date(2026, 7, 31),
    )
    AcademicQuarterFactory(
        season=models.Quarter.SUMMER,
        year=2026,
        label="Session B",
        start_date=date(2026, 8, 3),
        end_date=date(2026, 9, 11),
    )
    db_session.flush()

    rows = (
        db_session.query(models.AcademicQuarter)
        .filter_by(season=models.Quarter.SUMMER, year=2026)
        .all()
    )
    assert {r.label for r in rows} == {"Session A", "Session B"}


def test_duplicate_season_year_label_rejected(db_session):
    AcademicQuarterFactory(
        season=models.Quarter.FALL,
        year=2026,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 12, 12),
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        # Same (fall, 2026, '') key; dates deliberately non-overlapping so
        # only the uniqueness constraint can be the reason for the failure.
        AcademicQuarterFactory(
            season=models.Quarter.FALL,
            year=2026,
            start_date=date(2027, 9, 20),
            end_date=date(2027, 12, 11),
        )
        db_session.flush()
    db_session.rollback()


def test_overlapping_date_ranges_rejected(db_session):
    AcademicQuarterFactory(
        season=models.Quarter.WINTER,
        year=2026,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 3, 20),
    )
    db_session.flush()

    with pytest.raises(IntegrityError):
        # Starts on winter's (inclusive) last day — one-day overlap.
        AcademicQuarterFactory(
            season=models.Quarter.SPRING,
            year=2026,
            start_date=date(2026, 3, 20),
            end_date=date(2026, 6, 15),
        )
        db_session.flush()
    db_session.rollback()


def test_start_must_precede_end(db_session):
    with pytest.raises(IntegrityError):
        AcademicQuarterFactory(
            season=models.Quarter.WINTER,
            year=2027,
            start_date=date(2027, 3, 19),
            end_date=date(2027, 1, 4),
        )
        db_session.flush()
    db_session.rollback()


def test_event_links_to_quarter(db_session):
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 15),
    )
    event = EventFactory(quarter_id=q.id)
    db_session.flush()

    assert event.academic_quarter.id == q.id
    assert db_session.get(models.Event, event.id).quarter_id == q.id


def test_event_quarter_id_is_optional(db_session):
    event = EventFactory()
    db_session.flush()
    assert event.quarter_id is None


def test_deleting_referenced_quarter_blocked(db_session):
    q = AcademicQuarterFactory(
        season=models.Quarter.SPRING,
        year=2026,
        start_date=date(2026, 3, 30),
        end_date=date(2026, 6, 15),
    )
    EventFactory(quarter_id=q.id)
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.delete(q)
        db_session.flush()
    db_session.rollback()
