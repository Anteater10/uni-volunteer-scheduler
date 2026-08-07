"""Orientation credits: the thing that decides who can sign up at all.

Two properties these tests exist to hold. First, credit is granted against a
*family*, not a module, so granting for one CRISPR module admits a volunteer
to every CRISPR module — the tool has to say so before it happens. Second,
emails go in but never come out: the boundary redactor rewrites any address
in a result, so every tool here answers about one person the user already
named rather than handing back a list.
"""
import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.orientation_credits import (
    CHECK_ORIENTATION_CREDIT_TOOL,
    GRANT_ORIENTATION_CREDIT_TOOL,
    LIST_ORIENTATION_CREDITS_TOOL,
    REVOKE_ORIENTATION_CREDIT_TOOL,
)
from app.models import Module, OrientationCredit, UserRole
from tests.fixtures.helpers import make_user

_TOOLS = (
    CHECK_ORIENTATION_CREDIT_TOOL,
    LIST_ORIENTATION_CREDITS_TOOL,
    GRANT_ORIENTATION_CREDIT_TOOL,
    REVOKE_ORIENTATION_CREDIT_TOOL,
)

EMAIL = "jane.volunteer@ucsb.edu"


@pytest.fixture(autouse=True)
def _register_tools():
    for tool in _TOOLS:
        registry.register(tool)
    yield


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


@pytest.fixture
def solo(db_session):
    """A module in a family of one — granting it admits nobody elsewhere."""
    template = Module(
        slug="bioinformatics",
        name="Bioinformatics",
        default_capacity=12,
        duration_minutes=120,
        family_key="bioinformatics",
    )
    db_session.add(template)
    db_session.flush()
    return template


@pytest.fixture
def crispr_family(db_session):
    """Two modules sharing one orientation."""
    intro = Module(
        slug="crispr-intro",
        name="CRISPR Module 1",
        default_capacity=12,
        duration_minutes=120,
        family_key="crispr",
    )
    advanced = Module(
        slug="crispr-advanced",
        name="CRISPR Module 2",
        default_capacity=12,
        duration_minutes=120,
        family_key="crispr",
    )
    db_session.add_all([intro, advanced])
    db_session.flush()
    return intro, advanced


class TestCheckOrientationCredit:
    def test_no_credit_is_a_clear_no(self, db_session, solo):
        _, result = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        assert result["has_credit"] is False

    def test_it_names_every_module_the_credit_would_cover(
        self, db_session, crispr_family
    ):
        """A family is invisible from the outside; the answer has to say it."""
        _, result = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "crispr-intro"},
        )
        assert result["covers_modules"] == ["crispr-advanced", "crispr-intro"]

    def test_an_unknown_slug_says_where_to_look(self, db_session):
        _, result = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "no-such-module"},
        )
        assert "list_module_templates" in result["error"]

    def test_it_asks_which_module(self, db_session, solo):
        """Without a family there is nothing to check against, and the
        service fails closed — a bare "no" would read as a real answer."""
        _, result = _run(
            db_session, CHECK_ORIENTATION_CREDIT_TOOL, {"email": EMAIL}
        )
        assert "which module the orientation is for" in result["needs_answers"][0]

    def test_reading_needs_no_confirmation(self, db_session, solo):
        out, _ = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        assert out.get("status") != "pending_confirmation"

    def test_organizers_can_check(self):
        assert "organizer" in CHECK_ORIENTATION_CREDIT_TOOL.allowed_roles


class TestGrantOrientationCredit:
    def test_grants_credit_for_a_module_in_its_own_family(
        self, db_session, solo
    ):
        _, result = _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {
                "email": EMAIL,
                "module_slug": "bioinformatics",
                "notes": "walk-in, vouched for by the organizer",
            },
        )
        assert result["granted"] is True
        assert result["has_credit"] is True
        assert (
            db_session.query(OrientationCredit)
            .filter(OrientationCredit.volunteer_email == EMAIL)
            .count()
            == 1
        )

    def test_the_credit_is_then_visible_to_check(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, result = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        assert result["has_credit"] is True
        assert result["source"] == "grant"

    def test_it_warns_before_admitting_someone_to_a_whole_family(
        self, db_session, crispr_family
    ):
        out, result = _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "crispr-intro"},
        )
        assert out.get("status") != "pending_confirmation"
        assert "crispr-advanced" in result["needs_answers"][0]
        assert db_session.query(OrientationCredit).count() == 0

    def test_the_warning_can_be_answered(self, db_session, crispr_family):
        """Without an acknowledgement flag the model would re-send the same
        args and the precheck would object forever."""
        _, result = _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {
                "email": EMAIL,
                "module_slug": "crispr-intro",
                "acknowledged_family": True,
            },
        )
        assert result["granted"] is True

    def test_credit_reaches_the_other_module_in_the_family(
        self, db_session, crispr_family
    ):
        """The consequence the warning was about, verified rather than
        assumed."""
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {
                "email": EMAIL,
                "module_slug": "crispr-intro",
                "acknowledged_family": True,
            },
        )
        _, result = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "crispr-advanced"},
        )
        assert result["has_credit"] is True

    def test_granting_twice_changes_nothing(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, result = _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        assert result["granted"] is False
        assert db_session.query(OrientationCredit).count() == 1

    def test_it_asks_for_the_email(self, db_session, solo):
        _, result = _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"module_slug": "bioinformatics"},
        )
        assert "email" in " ".join(result["needs_answers"])

    def test_it_asks_which_module(self, db_session, solo):
        _, result = _run(
            db_session, GRANT_ORIENTATION_CREDIT_TOOL, {"email": EMAIL}
        )
        assert "which module" in " ".join(result["needs_answers"])

    def test_it_confirms_before_writing(self, db_session, solo):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=GRANT_ORIENTATION_CREDIT_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"email": EMAIL, "module_slug": "bioinformatics"},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert db_session.query(OrientationCredit).count() == 0

    def test_it_records_who_granted_it(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        credit = db_session.query(OrientationCredit).one()
        assert credit.granted_by_user_id is not None


class TestListOrientationCredits:
    def test_hands_back_the_id_needed_to_revoke(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, result = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        assert result["count"] == 1
        assert uuid.UUID(result["credits"][0]["credit_id"])
        assert result["credits"][0]["family_key"] == "bioinformatics"

    def test_it_carries_no_email_back(self, db_session, solo):
        """Not squeamishness — the redactor would rewrite it to
        [REDACTED:email] and the row would be worse than useless."""
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, result = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        assert "volunteer_email" not in result["credits"][0]

    def test_revoked_credits_are_hidden_by_default(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, listed = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        _run(
            db_session,
            REVOKE_ORIENTATION_CREDIT_TOOL,
            {"credit_id": listed["credits"][0]["credit_id"]},
        )
        _, after = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        assert after["count"] == 0

    def test_revoked_can_be_asked_for(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, listed = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        _run(
            db_session,
            REVOKE_ORIENTATION_CREDIT_TOOL,
            {"credit_id": listed["credits"][0]["credit_id"]},
        )
        _, after = _run(
            db_session,
            LIST_ORIENTATION_CREDITS_TOOL,
            {"email": EMAIL, "include_revoked": True},
        )
        assert after["count"] == 1
        assert after["credits"][0]["revoked_at"] is not None

    def test_somebody_with_nothing(self, db_session):
        _, result = _run(
            db_session,
            LIST_ORIENTATION_CREDITS_TOOL,
            {"email": "nobody@ucsb.edu"},
        )
        assert result["count"] == 0


class TestRevokeOrientationCredit:
    def test_revoking_removes_eligibility(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, listed = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        _, result = _run(
            db_session,
            REVOKE_ORIENTATION_CREDIT_TOOL,
            {"credit_id": listed["credits"][0]["credit_id"]},
        )
        assert result["revoked"] is True

        _, check = _run(
            db_session,
            CHECK_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        assert check["has_credit"] is False

    def test_it_asks_which_credit(self, db_session):
        _, result = _run(db_session, REVOKE_ORIENTATION_CREDIT_TOOL, {})
        assert "list_orientation_credits" in result["needs_answers"][0]

    def test_a_junk_id_is_an_error_not_a_crash(self, db_session):
        _, result = _run(
            db_session, REVOKE_ORIENTATION_CREDIT_TOOL, {"credit_id": "nope"}
        )
        assert "not a credit id" in result["error"]

    def test_an_unknown_id(self, db_session):
        _, result = _run(
            db_session,
            REVOKE_ORIENTATION_CREDIT_TOOL,
            {"credit_id": str(uuid.uuid4())},
        )
        assert "no credit with that id" in result["error"]

    def test_organizers_cannot_revoke(self):
        """They can grant — vouching for a walk-in is their job — but taking
        eligibility away is not."""
        assert REVOKE_ORIENTATION_CREDIT_TOOL.allowed_roles == ["admin"]
        assert "organizer" in GRANT_ORIENTATION_CREDIT_TOOL.allowed_roles

    def test_it_confirms_first(self, db_session, solo):
        _run(
            db_session,
            GRANT_ORIENTATION_CREDIT_TOOL,
            {"email": EMAIL, "module_slug": "bioinformatics"},
        )
        _, listed = _run(
            db_session, LIST_ORIENTATION_CREDITS_TOOL, {"email": EMAIL}
        )
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=REVOKE_ORIENTATION_CREDIT_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"credit_id": listed["credits"][0]["credit_id"]},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert (
            db_session.query(OrientationCredit)
            .filter(OrientationCredit.revoked_at.isnot(None))
            .count()
            == 0
        )


class TestEveryWriteHereAsksFirst:
    def test_no_confirming_tool_ships_without_a_precheck(self):
        for tool in _TOOLS:
            if tool.requires_confirmation:
                assert tool.precheck is not None, tool.name
