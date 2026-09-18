"""display_week: the week an event's *title* claims, which is what volunteers
browse by.

week_number is the event's calendar position, derived from start_date. The two
diverge on purpose: an orientation for the week 8 module is routinely scheduled
to run during week 2, and it has to appear under week 8 on the browse page.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.event_title import week_from_title
from app.models import Event, Quarter
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


def _make_event(db_session, *, title, week_number, quarter_id, days_out=1):
    owner = make_user(db_session)
    start = datetime.now(timezone.utc) + timedelta(days=days_out)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title=title,
        start_date=start,
        end_date=start + timedelta(hours=3),
        quarter=Quarter.FALL,
        year=2024,
        week_number=week_number,
        quarter_id=quarter_id,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _make_quarter(db_session, **kwargs):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(**kwargs)
    db_session.flush()
    return q


class TestWeekFromTitle:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Week 7 - Conservation of Mass - GVJH", 7),
            ("Week 10 - Germs - Dos Pueblos High School", 10),
            ("  Week 2 - Germs - GVJH", 2),
            # The loose-hyphen titles that exist in real data. They fail the
            # canonical validator but must still yield their week.
            ("Week 7-Conservation of Mass- GVJH", 7),
            ("Week 5- Germs- LaCumbre", 5),
            ("Week8 - Germs - GVJH", 8),
            ("week 4 - germs - sbjh", 4),
            ("Week 3", 3),
        ],
    )
    def test_extracts_the_stated_week(self, title, expected):
        assert week_from_title(title) == expected

    @pytest.mark.parametrize(
        "title",
        [
            "Conservation of Mass - GVJH",  # no week stated
            "Week seven - Germs - GVJH",  # not a number
            "Weekend Cleanup",  # "Week" is not a word here
            "SciTrek Module 3 - Chemistry - Lincoln",  # pre-SCRUM-154 scheme
            "E2E Seed Event",
            "",
            None,
        ],
    )
    def test_returns_none_when_no_week_is_stated(self, title):
        assert week_from_title(title) is None

    def test_a_three_digit_run_yields_nothing_rather_than_a_truncated_week(self):
        """"Week 123" must not silently parse as week 12."""
        assert week_from_title("Week 123 - Germs - GVJH") is None


class TestModelKeepsDisplayWeekInSyncWithTitle:
    def test_set_on_construction(self, db_session):
        quarter = _make_quarter(db_session)
        event = _make_event(
            db_session,
            title="Week 8 - Germs - GVJH",
            week_number=2,
            quarter_id=quarter.id,
        )
        assert event.display_week == 8
        assert event.week_number == 2  # the calendar week is untouched

    def test_retitling_an_event_moves_it(self, db_session):
        quarter = _make_quarter(db_session)
        event = _make_event(
            db_session,
            title="Week 3 - Germs - GVJH",
            week_number=3,
            quarter_id=quarter.id,
        )
        assert event.display_week == 3

        event.title = "Week 9 - Germs - GVJH"
        db_session.flush()
        assert event.display_week == 9

    def test_a_title_stating_no_week_clears_it(self, db_session):
        quarter = _make_quarter(db_session)
        event = _make_event(
            db_session,
            title="Week 6 - Germs - GVJH",
            week_number=6,
            quarter_id=quarter.id,
        )
        assert event.display_week == 6

        event.title = "Germs - GVJH"
        db_session.flush()
        assert event.display_week is None


class TestPublicListGroupsByTheTitlesWeek:
    def test_orientation_running_early_lists_under_its_modules_week(
        self, client, db_session
    ):
        """The bug this fixes: a week 8 orientation held during week 2 was
        being listed under week 2, because the date said so."""
        quarter = _make_quarter(db_session)
        _make_event(
            db_session,
            title="Week 3 - Conservation of Mass - SBJH",
            week_number=3,
            quarter_id=quarter.id,
            days_out=30,
        )
        # Runs during calendar week 2, but belongs to the week 8 module.
        _make_event(
            db_session,
            title="Week 8 - Germs - LaCumbre",
            week_number=2,
            quarter_id=quarter.id,
            days_out=1,
        )
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={quarter.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert [e["display_week"] for e in body] == [3, 8]
        assert [e["title"] for e in body] == [
            "Week 3 - Conservation of Mass - SBJH",
            "Week 8 - Germs - LaCumbre",
        ]

    def test_titles_stating_no_week_fall_back_to_the_calendar_week(
        self, client, db_session
    ):
        """Legacy names predating SCRUM-154 keep their old ordering."""
        quarter = _make_quarter(db_session)
        _make_event(
            db_session,
            title="Week 5 - Germs - GVJH",
            week_number=5,
            quarter_id=quarter.id,
        )
        _make_event(
            db_session,
            title="SciTrek Event",  # no week in the title
            week_number=1,
            quarter_id=quarter.id,
        )
        db_session.commit()

        resp = client.get(f"/api/v1/public/events?quarter_id={quarter.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert [e["title"] for e in body] == ["SciTrek Event", "Week 5 - Germs - GVJH"]
        assert body[0]["display_week"] is None
        assert body[0]["week_number"] == 1
