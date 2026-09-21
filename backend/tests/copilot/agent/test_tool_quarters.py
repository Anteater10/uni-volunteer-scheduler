"""Quarter tools: the wall the copilot could describe but not climb.

Every event write derives its quarter from the admin-entered ranges, so an
event outside them cannot exist. Until these tools the copilot answered
"add it in Admin → Quarters" and stopped — a refusal it was fully capable
of resolving. These tests hold that it can, and that it still asks before
changing a calendar the whole app reasons about.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.quarters import (
    CREATE_QUARTER_TOOL,
    LIST_QUARTERS_TOOL,
    UPDATE_QUARTER_TOOL,
)
from app.models import AcademicQuarter, Quarter, UserRole
from tests.fixtures.factories import AcademicQuarterFactory
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _register_tools():
    """The confirm path looks the tool up by name in the shared registry."""
    for tool in (LIST_QUARTERS_TOOL, CREATE_QUARTER_TOOL, UPDATE_QUARTER_TOOL):
        registry.register(tool)
    yield


@pytest.fixture
def summer(db_session):
    AcademicQuarterFactory._meta.sqlalchemy_session = db_session
    q = AcademicQuarterFactory(
        season=Quarter.SUMMER,
        year=2026,
        start_date=date(2026, 6, 22),
        end_date=date(2026, 8, 28),
    )
    db_session.flush()
    return q


def _make_session(db_session, user_id):
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.flush()
    return session_id


def _run(db_session, tool, args, *, role="admin"):
    user = make_user(db_session, role=getattr(UserRole, role))
    session_id = _make_session(db_session, user.id)
    out = invoke(
        db_session,
        tool=tool,
        scope=scope_for(role=role, caller_id=user.id),
        args=args,
        session_id=session_id,
    )
    if out.get("status") != "pending_confirmation":
        return out, out.get("result")
    confirmed = execute_after_confirmation(
        db_session, call_id=out["call_id"], scope_role=role, caller_id=user.id
    )
    return out, confirmed["result"]


class TestListQuarters:
    def test_it_reports_the_range_and_the_week_count(self, db_session, summer):
        _out, result = _run(db_session, LIST_QUARTERS_TOOL, {})
        row = next(
            q for q in result["quarters"] if q["quarter_id"] == str(summer.id)
        )
        assert row["starts"] == "2026-06-22"
        assert row["ends"] == "2026-08-28"
        assert row["weeks"] >= 1

    def test_organizers_may_read_it(self, db_session):
        """Knowing when the quarter ends is not privileged information."""
        assert "organizer" in LIST_QUARTERS_TOOL.allowed_roles
        assert LIST_QUARTERS_TOOL.requires_confirmation is False


class TestCreateQuarter:
    def test_it_creates_the_quarter_it_was_given(self, db_session):
        _out, result = _run(
            db_session,
            CREATE_QUARTER_TOOL,
            {
                "season": "fall",
                "year": 2026,
                "start_date": "2026-09-21",
                "end_date": "2026-12-04",
            },
        )
        row = db_session.query(AcademicQuarter).filter(
            AcademicQuarter.id == result["quarter_id"]
        ).one()
        assert row.start_date == date(2026, 9, 21)
        assert row.end_date == date(2026, 12, 4)

    def test_it_asks_rather_than_inventing_the_academic_calendar(
        self, db_session
    ):
        """A model "knows" when Fall quarter starts. It must not act on that."""
        out, result = _run(
            db_session, CREATE_QUARTER_TOOL, {"season": "fall", "year": 2026}
        )
        asked = " ".join(result["needs_answers"])
        assert "first day" in asked
        assert "last day" in asked
        assert out.get("status") != "pending_confirmation"
        assert db_session.query(AcademicQuarter).count() == 0

    def test_the_end_date_question_says_why_it_matters(self, db_session):
        _out, result = _run(
            db_session,
            CREATE_QUARTER_TOOL,
            {"season": "fall", "year": 2026, "start_date": "2026-09-21"},
        )
        asked = " ".join(result["needs_answers"])
        assert "silently blocks every event" in asked

    def test_an_overlap_comes_back_as_the_service_worded_it(
        self, db_session, summer
    ):
        """Not a 500 from the copilot — the complaint the service made."""
        _out, result = _run(
            db_session,
            CREATE_QUARTER_TOOL,
            {
                "season": "fall",
                "year": 2026,
                "start_date": "2026-08-01",
                "end_date": "2026-10-01",
            },
        )
        assert "overlap" in result["error"].lower()

    def test_an_unreadable_date_names_the_field(self, db_session):
        _out, result = _run(
            db_session,
            CREATE_QUARTER_TOOL,
            {
                "season": "fall",
                "year": 2026,
                "start_date": "the Monday after Labor Day",
                "end_date": "2026-12-04",
            },
        )
        assert "start_date" in result["error"]

    def test_organizers_cannot_reach_it(self):
        assert CREATE_QUARTER_TOOL.allowed_roles == ["admin"]
        assert "create_quarter" not in [
            t.name for t in registry.get_tools_for_role("organizer")
        ]


class TestUpdateQuarter:
    def test_extending_the_end_date_is_the_whole_point(self, db_session, summer):
        """The exact fix that needed raw SQL on 2026-08-07."""
        _out, result = _run(
            db_session,
            UPDATE_QUARTER_TOOL,
            {"quarter_id": str(summer.id), "end_date": "2026-09-30"},
        )
        db_session.refresh(summer)
        assert summer.end_date == date(2026, 9, 30)
        assert result["ends"] == "2026-09-30"

    def test_it_leaves_the_fields_it_was_not_given(self, db_session, summer):
        _run(
            db_session,
            UPDATE_QUARTER_TOOL,
            {"quarter_id": str(summer.id), "end_date": "2026-09-30"},
        )
        db_session.refresh(summer)
        assert summer.start_date == date(2026, 6, 22)
        assert summer.season == Quarter.SUMMER

    def test_it_asks_which_quarter_when_it_was_not_told(self, db_session, summer):
        _out, result = _run(
            db_session, UPDATE_QUARTER_TOOL, {"end_date": "2026-09-30"}
        )
        asked = " ".join(result["needs_answers"])
        assert "list_quarters" in asked

    def test_it_asks_what_to_change_when_nothing_was_given(
        self, db_session, summer
    ):
        _out, result = _run(
            db_session, UPDATE_QUARTER_TOOL, {"quarter_id": str(summer.id)}
        )
        asked = " ".join(result["needs_answers"])
        assert "what to change" in asked
        # And it says what the range is now, so the user can answer in one go.
        assert "2026-06-22" in asked

    def test_it_reports_events_the_change_stranded(self, db_session, summer):
        """Shortening a quarter unlinks the events left outside it."""
        _out, result = _run(
            db_session,
            UPDATE_QUARTER_TOOL,
            {"quarter_id": str(summer.id), "end_date": "2026-07-01"},
        )
        assert "events_unlinked" in result


# ------------------------------------------------ handler edges (roadmap #168)
#
# The paths below are the ones a model rarely takes but a real calendar edit
# can: no signed-in caller, a season it misspelled, a field it half-parsed.
# Called on the handlers directly — the confirm gate is covered above and
# would only add noise here.

from app.copilot.agent.boundary.role_scope import Scope  # noqa: E402
from app.copilot.agent.tools.quarters import (  # noqa: E402
    _create_handler,
    _parse_date,
    _update_handler,
)

_NO_CALLER = Scope(role="admin", caller_id=None, module_owner_id=None, see_all=True)


def _admin_scope(db_session):
    admin = make_user(db_session, role=UserRole.admin)
    db_session.flush()
    return scope_for(role="admin", caller_id=admin.id)


class TestHandlerEdges:
    def test_a_date_object_passes_straight_through(self):
        assert _parse_date(date(2026, 1, 5), "start_date") == date(2026, 1, 5)

    def test_create_with_no_caller_and_no_admin_refuses(self, db_session):
        out = _create_handler(
            db_session,
            _NO_CALLER,
            {"season": "fall", "year": 2026,
             "start_date": "2026-09-21", "end_date": "2026-12-04"},
        )
        assert out == {"error": "no admin available to record this change"}

    def test_update_with_no_caller_and_no_admin_refuses(self, db_session, summer):
        out = _update_handler(
            db_session, _NO_CALLER,
            {"quarter_id": str(summer.id), "end_date": "2026-09-30"},
        )
        assert out == {"error": "no admin available to record this change"}

    def test_no_caller_falls_back_to_an_admin(self, db_session, summer):
        """A system-initiated call is recorded against an admin, not nobody."""
        make_user(db_session, role=UserRole.admin)
        db_session.flush()
        out = _update_handler(
            db_session, _NO_CALLER,
            {"quarter_id": str(summer.id), "end_date": "2026-09-30"},
        )
        assert out["ends"] == "2026-09-30"

    def test_create_rejects_a_season_that_does_not_exist(self, db_session):
        out = _create_handler(
            db_session,
            _admin_scope(db_session),
            {"season": "monsoon", "year": 2026,
             "start_date": "2026-09-21", "end_date": "2026-12-04"},
        )
        assert "unknown season" in out["error"]
        assert db_session.query(AcademicQuarter).count() == 0

    def test_update_changes_season_year_and_label(self, db_session, summer):
        out = _update_handler(
            db_session,
            _admin_scope(db_session),
            {"quarter_id": str(summer.id), "season": " Fall ",
             "year": "2027", "label": "  Session B  "},
        )
        db_session.refresh(summer)
        assert summer.season == Quarter.FALL
        assert summer.year == 2027
        assert summer.label == "Session B"
        assert out["label"] == "Session B"

    def test_update_rejects_a_season_that_does_not_exist(self, db_session, summer):
        out = _update_handler(
            db_session,
            _admin_scope(db_session),
            {"quarter_id": str(summer.id), "season": "monsoon"},
        )
        assert "unknown season" in out["error"]
        db_session.refresh(summer)
        assert summer.season == Quarter.SUMMER

    def test_update_names_an_unreadable_date(self, db_session, summer):
        out = _update_handler(
            db_session,
            _admin_scope(db_session),
            {"quarter_id": str(summer.id), "end_date": "end of September"},
        )
        assert "end_date" in out["error"]
        db_session.refresh(summer)
        assert summer.end_date == date(2026, 8, 28)

    def test_update_refuses_a_year_that_is_not_a_number(self, db_session, summer):
        out = _update_handler(
            db_session,
            _admin_scope(db_session),
            {"quarter_id": str(summer.id), "year": "next year"},
        )
        assert "error" in out
        db_session.refresh(summer)
        assert summer.year == 2026

    def test_update_passes_the_service_complaint_back(self, db_session, summer):
        """An update that would overlap another quarter is refused in the
        service's words, not as a 500."""
        AcademicQuarterFactory(
            season=Quarter.FALL,
            year=2026,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 12, 4),
        )
        db_session.flush()
        out = _update_handler(
            db_session,
            _admin_scope(db_session),
            {"quarter_id": str(summer.id), "end_date": "2026-10-01"},
        )
        assert "overlap" in out["error"].lower()

    def test_create_with_nothing_asks_for_season_and_year_too(self, db_session):
        _out, result = _run(db_session, CREATE_QUARTER_TOOL, {})
        asked = " ".join(result["needs_answers"])
        assert "which season" in asked
        assert "which year" in asked
