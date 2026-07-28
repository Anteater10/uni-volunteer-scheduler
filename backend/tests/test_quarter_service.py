"""Phase 2 (issue #24): quarter_service domain logic.

The acceptance boundary suite for #24 lives here: last week of a quarter,
gaps between quarters, first week of each summer session, skipped seasons,
and the no-quarters-entered state. All quarter rows are test-entered —
mirroring the product rule that dates are admin-entered, never guessed.
"""
from datetime import date, datetime, timezone

import pytest

from app import models
from app.services import quarter_service
from tests.fixtures.factories import AcademicQuarterFactory, EventFactory, UserFactory

# Clean fixtures based on the UCSB 2026 calendar (11-week regular quarters,
# two 6-week summer sessions, gaps between all of them).
WINTER = dict(
    season=models.Quarter.WINTER, year=2026,
    start_date=date(2026, 1, 5), end_date=date(2026, 3, 22),
)
SPRING = dict(
    season=models.Quarter.SPRING, year=2026,
    start_date=date(2026, 3, 30), end_date=date(2026, 6, 14),
)
SUMMER_A = dict(
    season=models.Quarter.SUMMER, year=2026, label="Session A",
    start_date=date(2026, 6, 22), end_date=date(2026, 7, 31),
)
SUMMER_B = dict(
    season=models.Quarter.SUMMER, year=2026, label="Session B",
    start_date=date(2026, 8, 3), end_date=date(2026, 9, 11),
)
FALL = dict(
    season=models.Quarter.FALL, year=2026,
    start_date=date(2026, 9, 21), end_date=date(2026, 12, 6),
)


@pytest.fixture(autouse=True)
def _factories(db_session):
    for f in (AcademicQuarterFactory, EventFactory, UserFactory):
        f._meta.sqlalchemy_session = db_session


# ---------- pure range math ----------


def test_weeks_in_derives_from_range(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    session_a = AcademicQuarterFactory(**SUMMER_A)
    assert quarter_service.weeks_in(spring) == 11
    assert quarter_service.weeks_in(session_a) == 6


def test_week_number_boundaries(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    assert quarter_service.week_number_for(spring, date(2026, 3, 30)) == 1
    assert quarter_service.week_number_for(spring, date(2026, 4, 5)) == 1  # Sunday of wk 1
    assert quarter_service.week_number_for(spring, date(2026, 4, 6)) == 2
    # Last day of the quarter is the last day of the final week.
    assert quarter_service.week_number_for(spring, date(2026, 6, 14)) == 11


def test_week_start(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    assert quarter_service.week_start(spring, 1) == date(2026, 3, 30)
    assert quarter_service.week_start(spring, 11) == date(2026, 6, 8)


def test_display_name(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    session_a = AcademicQuarterFactory(**SUMMER_A)
    assert quarter_service.display_name(spring) == "Spring 2026"
    assert quarter_service.display_name(session_a) == "Summer 2026 · Session A"


# ---------- date → quarter resolution ----------


def test_get_quarter_for_date(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()
    assert quarter_service.get_quarter_for_date(db_session, date(2026, 4, 15)).id == spring.id
    # Inclusive boundaries
    assert quarter_service.get_quarter_for_date(db_session, date(2026, 3, 30)).id == spring.id
    assert quarter_service.get_quarter_for_date(db_session, date(2026, 6, 14)).id == spring.id
    # Day after the end is a gap
    assert quarter_service.get_quarter_for_date(db_session, date(2026, 6, 15)) is None
    # Before all quarters
    assert quarter_service.get_quarter_for_date(db_session, date(2026, 1, 1)) is None


def test_derive_quarter_week_in_each_summer_session(db_session):
    session_a = AcademicQuarterFactory(**SUMMER_A)
    session_b = AcademicQuarterFactory(**SUMMER_B)
    db_session.flush()

    # First week of Session A and of Session B — each session numbers its own weeks
    assert quarter_service.derive_quarter_week(db_session, date(2026, 6, 22)) == (
        "summer", 2026, 1, session_a.id,
    )
    assert quarter_service.derive_quarter_week(db_session, date(2026, 8, 3)) == (
        "summer", 2026, 1, session_b.id,
    )
    assert quarter_service.derive_quarter_week(db_session, date(2026, 8, 12)) == (
        "summer", 2026, 2, session_b.id,
    )


def test_derive_quarter_week_gap_returns_none(db_session):
    AcademicQuarterFactory(**SPRING)
    AcademicQuarterFactory(**SUMMER_A)
    db_session.flush()
    # Spring→Session A gap: no more silent clamping into "week 11"
    assert quarter_service.derive_quarter_week(db_session, date(2026, 6, 17)) is None


# ---------- current-week resolution ----------


def test_resolve_current_week_active_quarter(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()

    info = quarter_service.resolve_current_week(db_session, date(2026, 4, 15))
    assert info.quarter == "spring"
    assert info.year == 2026
    assert info.week_number == 3
    assert info.weeks_in_quarter == 11
    assert info.quarter_id == spring.id
    assert info.label == ""
    assert info.is_gap is False
    assert info.starts_on is None


def test_resolve_current_week_session_gap_points_to_session_b(db_session):
    AcademicQuarterFactory(**SUMMER_A)
    session_b = AcademicQuarterFactory(**SUMMER_B)
    db_session.flush()

    # Aug 1 is the weekend between Session A (ends Jul 31) and Session B (starts Aug 3)
    info = quarter_service.resolve_current_week(db_session, date(2026, 8, 1))
    assert info.is_gap is True
    assert info.quarter_id == session_b.id
    assert info.label == "Session B"
    assert info.week_number == 1
    assert info.starts_on == date(2026, 8, 3)


def test_resolve_current_week_skipped_summer(db_session):
    AcademicQuarterFactory(**SPRING)
    fall = AcademicQuarterFactory(**FALL)
    db_session.flush()

    # No summer entered at all — a July date looks ahead to fall
    info = quarter_service.resolve_current_week(db_session, date(2026, 7, 10))
    assert info.is_gap is True
    assert info.quarter_id == fall.id
    assert info.quarter == "fall"
    assert info.week_number == 1
    assert info.starts_on == date(2026, 9, 21)


def test_resolve_current_week_after_all_quarters(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()

    # Nothing upcoming entered yet: fall back to the last quarter's final week.
    # starts_on None + is_gap True is the "no upcoming quarter" banner condition.
    info = quarter_service.resolve_current_week(db_session, date(2026, 7, 10))
    assert info.is_gap is True
    assert info.quarter_id == spring.id
    assert info.week_number == 11
    assert info.starts_on is None


def test_resolve_current_week_before_all_quarters(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()

    info = quarter_service.resolve_current_week(db_session, date(2026, 2, 1))
    assert info.is_gap is True
    assert info.quarter_id == spring.id
    assert info.week_number == 1
    assert info.starts_on == date(2026, 3, 30)


def test_resolve_current_week_no_quarters_entered(db_session):
    assert quarter_service.resolve_current_week(db_session, date(2026, 4, 15)) is None


# ---------- dashboard helpers ----------


def test_active_or_recent_quarter(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    session_a = AcademicQuarterFactory(**SUMMER_A)
    db_session.flush()

    assert (
        quarter_service.active_or_recent_quarter(db_session, date(2026, 4, 15)).id == spring.id
    )
    # Gap after Session A ended: most recently ended row wins
    assert (
        quarter_service.active_or_recent_quarter(db_session, date(2026, 8, 1)).id == session_a.id
    )
    # Before everything: nothing active or ended
    assert quarter_service.active_or_recent_quarter(db_session, date(2026, 1, 1)) is None


def test_quarter_bounds_utc(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    start, end = quarter_service.quarter_bounds_utc(spring)
    assert start == datetime(2026, 3, 30, tzinfo=timezone.utc)
    # end_date is inclusive, so the exclusive UTC bound is the next midnight
    assert end == datetime(2026, 6, 15, tzinfo=timezone.utc)


def test_quarter_progress(db_session):
    AcademicQuarterFactory(**SPRING)
    db_session.flush()

    progress = quarter_service.quarter_progress(
        db_session, datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    )
    # Apr 15 is day 17 of the 77-day (11-week) range, not "3 weeks done"
    assert progress == {
        "week": 3, "of": 11, "day": 17, "days": 77, "pct": round(17 / 77, 2)
    }

    # Day one is barely started, not 1/11th done
    first_day = quarter_service.quarter_progress(
        db_session, datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    )
    assert first_day == {
        "week": 1, "of": 11, "day": 1, "days": 77, "pct": round(1 / 77, 2)
    }

    # The final day reads as complete
    last_day = quarter_service.quarter_progress(
        db_session, datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)
    )
    assert last_day == {"week": 11, "of": 11, "day": 77, "days": 77, "pct": 1.0}

    # In a gap there is no progress to report
    assert (
        quarter_service.quarter_progress(
            db_session, datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
        )
        is None
    )


def test_quarter_progress_varies_with_session_length(db_session):
    AcademicQuarterFactory(**SUMMER_A)
    db_session.flush()

    progress = quarter_service.quarter_progress(
        db_session, datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    )
    # Jun 30 is day 9 of the 40-day Session A range. Note "of": 6 rounds the
    # partial final week (5 days) up — day/days carry the true denominator.
    assert progress == {
        "week": 2, "of": 6, "day": 9, "days": 40, "pct": round(9 / 40, 2)
    }


# ---------- event linking ----------


def _event_on(db_session, when, **kwargs):
    return EventFactory(start_date=when, end_date=when, **kwargs)


def test_relink_links_matching_events_and_computes_cache(db_session):
    e1 = _event_on(db_session, datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc))
    e2 = _event_on(db_session, datetime(2026, 3, 30, 8, 0, tzinfo=timezone.utc))
    outside = _event_on(db_session, datetime(2026, 6, 22, 8, 0, tzinfo=timezone.utc))
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()

    summary = quarter_service.relink_events_for_quarter(db_session, spring)
    db_session.flush()

    assert summary == {"linked": 2, "weeks_changed": 0, "unlinked": 0}
    assert e1.quarter_id == spring.id
    assert (e1.quarter, e1.year, e1.week_number) == (models.Quarter.SPRING, 2026, 3)
    assert (e2.quarter, e2.year, e2.week_number) == (models.Quarter.SPRING, 2026, 1)
    assert outside.quarter_id is None


def test_relink_counts_corrected_week_numbers(db_session):
    # Stale cache from the old clamp-to-11 system: event actually in week 3
    event = _event_on(
        db_session,
        datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc),
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=11,
    )
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()

    summary = quarter_service.relink_events_for_quarter(db_session, spring)

    assert summary == {"linked": 1, "weeks_changed": 1, "unlinked": 0}
    assert event.week_number == 3


def test_relink_unlinks_events_that_fell_out_of_range(db_session):
    spring = AcademicQuarterFactory(**SPRING)
    db_session.flush()
    event = _event_on(
        db_session,
        datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        quarter_id=spring.id,
        quarter=models.Quarter.SPRING,
        year=2026,
        week_number=11,
    )
    db_session.flush()

    # Admin shortens spring so it now ends Jun 7 — the event falls outside
    spring.end_date = date(2026, 6, 7)
    db_session.flush()
    summary = quarter_service.relink_events_for_quarter(db_session, spring)

    assert summary["unlinked"] == 1
    assert event.quarter_id is None
    assert event.quarter is None
    assert event.year is None
    assert event.week_number is None
