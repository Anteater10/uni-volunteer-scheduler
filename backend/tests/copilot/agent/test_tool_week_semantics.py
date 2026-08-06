"""K7 — the copilot week tools read ISO weeks off a quarter-relative column.

``Event.week_number`` is week-within-the-academic-quarter: 1..11, reset every
quarter. The copilot tools took an ISO week string from the LLM ("2026-W22")
and compared its number straight to that column, and formatted that column
back out as if it were an ISO week.

Every pre-existing test passed because the fixtures stamped ``week_number=22``
on events — a value the real system never produces. These tests build events
the way production does: a real ``start_date``, and a ``week_number`` in the
1..11 range that the quarter cache actually holds.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools._iso_week import iso_week_bounds, iso_week_label
from app.copilot.agent.tools.find_module_by_name import FIND_MODULE_BY_NAME_TOOL
from app.copilot.agent.tools.find_understaffed_modules import (
    FIND_UNDERSTAFFED_MODULES_TOOL,
)
from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL
from app.copilot.agent.tools.signup_stats_for_week import SIGNUP_STATS_FOR_WEEK_TOOL
from app.models import Event, UserRole
from tests.fixtures.helpers import make_shift, make_user

# 2026-W22 is Mon 25 May 2026. In a Spring quarter starting 30 Mar 2026 that
# is week 9 — the number production would cache on the row.
ISO_YEAR, ISO_WEEK = 2026, 22
QUARTER_WEEK = 9


def _monday(year: int, week: int) -> datetime:
    return datetime.combine(
        date.fromisocalendar(year, week, 1), time(9, 0), tzinfo=timezone.utc
    )


def _event(db, owner_id, *, iso_week, quarter_week, title, capacity=0):
    """An event as production makes them: real date, quarter-relative cache."""
    start = _monday(ISO_YEAR, iso_week)
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=start,
        end_date=start + timedelta(hours=2),
        year=ISO_YEAR,
        week_number=quarter_week,
        school="Adams Elementary",
    )
    db.add(ev)
    db.flush()
    if capacity:
        make_shift(db, ev.id, name=f"{title} shift", capacity=capacity)
        db.flush()
    return ev


@pytest.fixture
def realistic_week(db_session):
    owner = make_user(db_session, role=UserRole.organizer)
    ev = _event(
        db_session,
        owner.id,
        iso_week=ISO_WEEK,
        quarter_week=QUARTER_WEEK,
        title="Germs at Goleta Valley",
        capacity=6,
    )
    return owner, ev


class TestIsoWeekHelpers:
    def test_bounds_are_monday_to_next_monday(self):
        start, end = iso_week_bounds("2026-W22")
        assert start == datetime(2026, 5, 25, tzinfo=timezone.utc)
        assert end == datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert start.weekday() == 0

    def test_label_round_trips_through_bounds(self):
        start, end = iso_week_bounds("2026-W22")
        assert iso_week_label(start) == "2026-W22"
        # The last instant inside the range is still the same week.
        assert iso_week_label(end - timedelta(seconds=1)) == "2026-W22"
        # The first instant outside it is not.
        assert iso_week_label(end) == "2026-W23"

    def test_label_of_nothing_is_nothing(self):
        assert iso_week_label(None) is None

    def test_bad_input_raises(self):
        with pytest.raises(ValueError):
            iso_week_bounds("next week")
        with pytest.raises(ValueError):
            # 2026 has 53 ISO weeks; 2027 has 52.
            iso_week_bounds("2027-W53")


class TestListModules:
    def test_finds_the_event_by_the_week_it_is_really_in(self, db_session, realistic_week):
        _owner, ev = realistic_week
        scope = scope_for(role="admin", caller_id=None)

        out = LIST_MODULES_TOOL.handler(db_session, scope, {"week": "2026-W22"})

        names = [m["name"] for m in out["modules"]]
        assert ev.title in names

    def test_does_not_answer_to_the_quarter_week_number(self, db_session, realistic_week):
        # The old code matched Event.week_number == 9, so "2026-W09" — a week
        # in early March — returned a module that runs in late May.
        scope = scope_for(role="admin", caller_id=None)

        out = LIST_MODULES_TOOL.handler(
            db_session, scope, {"week": f"{ISO_YEAR}-W{QUARTER_WEEK:02d}"}
        )

        assert out["modules"] == []

    def test_reports_the_real_week_back(self, db_session, realistic_week):
        scope = scope_for(role="admin", caller_id=None)
        out = LIST_MODULES_TOOL.handler(db_session, scope, {"week": "2026-W22"})
        assert [m["week"] for m in out["modules"]] == ["2026-W22"]

    def test_same_quarter_week_in_two_quarters_stays_separate(self, db_session):
        # Both rows carry week_number=3. Before the fix a query for any W03
        # returned both, because that is all the filter looked at.
        owner = make_user(db_session, role=UserRole.organizer)
        _event(db_session, owner.id, iso_week=3, quarter_week=3, title="Winter wk3")
        _event(db_session, owner.id, iso_week=15, quarter_week=3, title="Spring wk3")
        scope = scope_for(role="admin", caller_id=None)

        winter = LIST_MODULES_TOOL.handler(db_session, scope, {"week": "2026-W03"})
        spring = LIST_MODULES_TOOL.handler(db_session, scope, {"week": "2026-W15"})

        assert [m["name"] for m in winter["modules"]] == ["Winter wk3"]
        assert [m["name"] for m in spring["modules"]] == ["Spring wk3"]


class TestSignupStatsForWeek:
    def test_counts_a_week_that_exists(self, db_session, realistic_week):
        scope = scope_for(role="admin", caller_id=None)
        out = SIGNUP_STATS_FOR_WEEK_TOOL.handler(
            db_session, scope, {"week": "2026-W22"}
        )
        # The bug's signature: modules_count 0 for a week with a module in it.
        assert out["modules_count"] == 1

    def test_beyond_week_11_is_no_longer_always_empty(self, db_session, realistic_week):
        # Quarter weeks stop at ~11, so every ISO week past W11 used to report
        # a flat zero — for a term that runs into June.
        scope = scope_for(role="admin", caller_id=None)
        out = SIGNUP_STATS_FOR_WEEK_TOOL.handler(
            db_session, scope, {"week": "2026-W22"}
        )
        assert out["total_signups"] == 0  # nobody booked yet
        assert out["modules_count"] == 1  # but the module is there

    def test_an_empty_week_is_still_reported_as_empty(self, db_session, realistic_week):
        scope = scope_for(role="admin", caller_id=None)
        out = SIGNUP_STATS_FOR_WEEK_TOOL.handler(
            db_session, scope, {"week": "2026-W40"}
        )
        assert out["modules_count"] == 0
        assert out["fill_rate"] == 0.0


class TestWeekLabelsHandedToTheModel:
    def test_find_module_by_name_labels_the_real_week(self, db_session, realistic_week):
        scope = scope_for(role="admin", caller_id=None)
        out = FIND_MODULE_BY_NAME_TOOL.handler(
            db_session, scope, {"query": "Germs"}
        )
        assert [m["week"] for m in out["modules"]] == ["2026-W22"]

    def test_understaffed_labels_the_real_week(self, db_session, realistic_week):
        scope = scope_for(role="admin", caller_id=None)
        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope, {"threshold": 0.5, "include_past": True}
        )
        weeks = [m["week"] for m in out["modules"]]
        assert weeks == ["2026-W22"]

    def test_the_label_it_emits_is_one_it_can_read_back(self, db_session, realistic_week):
        # This is the whole point: the model reads a week off one tool and
        # passes it to another. Before the fix it got "2026-W09" out and found
        # nothing when it asked about it.
        scope = scope_for(role="admin", caller_id=None)
        found = FIND_MODULE_BY_NAME_TOOL.handler(db_session, scope, {"query": "Germs"})
        label = found["modules"][0]["week"]

        back = LIST_MODULES_TOOL.handler(db_session, scope, {"week": label})

        assert [m["name"] for m in back["modules"]] == ["Germs at Goleta Valley"]
