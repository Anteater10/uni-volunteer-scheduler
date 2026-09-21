"""Roadmap #170 — the e2e seed's quarter planner.

The seed runs against whatever DB the stack points at, including a long-lived
dev DB with real history in it. It used to 409 there: its fallback only knew
how to widen a same-(season, year) row, and it counted archived rows as
covering today even though current-week ignores them.
"""
from datetime import date

import pytest

from tests.fixtures.seed_e2e import _plan_quarter

TODAY = date(2026, 9, 21)


def _row(id, start, end, *, season="fall", year=2026, label="", archived=False):
    return {
        "id": id,
        "season": season,
        "year": year,
        "label": label,
        "start_date": start,
        "end_date": end,
        "archived_at": "2026-09-09T03:30:00Z" if archived else None,
        "display_name": f"{season} {year} {label}".strip(),
    }


def test_empty_db_creates_a_window_around_today():
    action, p = _plan_quarter([], TODAY)
    assert action == "create"
    assert p["start_date"] == "2026-08-31"
    assert p["end_date"] == "2026-11-02"
    assert p["season"] == "summer" and p["label"] == ""


def test_a_live_covering_row_is_reused():
    rows = [_row("a", "2026-09-01", "2026-12-01")]
    assert _plan_quarter(rows, TODAY) == ("reuse", None)


def test_the_dev_db_that_used_to_409():
    """The exact dev DB on 2026-09-21: one archived Fall row, Sep 1-8.
    The new range must start after it instead of overlapping it."""
    rows = [_row("a", "2026-09-01", "2026-09-08", archived=True)]
    action, p = _plan_quarter(rows, TODAY)
    assert action == "create"
    assert p["start_date"] == "2026-09-09"
    assert p["start_date"] <= "2026-09-21" <= p["end_date"]


def test_an_archived_row_covering_today_is_not_reused():
    """current-week ignores archived rows, so reusing one leaves the seed
    with no current week. Nothing safe to do automatically: say so."""
    rows = [_row("a", "2026-09-01", "2026-12-01", archived=True)]
    with pytest.raises(RuntimeError, match="archived quarter"):
        _plan_quarter(rows, TODAY)


def test_a_live_row_ending_tomorrow_is_widened():
    rows = [_row("a", "2026-09-01", "2026-09-22")]
    action, p = _plan_quarter(rows, TODAY)
    assert action == "widen"
    assert p == {"id": "a", "start_date": "2026-09-01", "end_date": "2026-09-23"}


def test_a_live_row_starting_tomorrow_is_widened_back_to_today():
    rows = [_row("a", "2026-09-22", "2026-12-01")]
    action, p = _plan_quarter(rows, TODAY)
    assert action == "widen"
    assert p["start_date"] == "2026-09-21"
    assert p["end_date"] == "2026-12-01"


def test_a_row_starting_soon_after_clips_the_new_end():
    rows = [_row("b", "2026-10-01", "2026-12-01", season="fall")]
    action, p = _plan_quarter(rows, TODAY)
    assert action == "create"
    assert p["end_date"] == "2026-09-30"


def test_a_taken_season_key_gets_a_label():
    """uq_quarters_season_year_label: an old summer-2026 row that ended
    long ago still owns (summer, 2026, "")."""
    rows = [_row("a", "2026-06-22", "2026-08-01", season="summer")]
    action, p = _plan_quarter(rows, TODAY)
    assert action == "create"
    assert p["label"] == "E2E"
    assert p["start_date"] == "2026-08-31"


# ---------------------------------------------- roster booking ids (#170)

from tests.fixtures.seed_e2e import _booking_of  # noqa: E402


def test_a_shift_row_is_cancelled_by_its_shift_signup_id():
    row = {"signup_id": None, "shift_signup_id": "s-1", "student_name": "x"}
    assert _booking_of(row) == ("s-1", True)


def test_a_slot_row_is_cancelled_by_its_signup_id():
    row = {"signup_id": "g-1", "shift_signup_id": None, "student_name": "x"}
    assert _booking_of(row) == ("g-1", False)
