"""Staff accounts, and the one thing that must never happen.

Every test in TestTheLastAdminIsUntouchable exists for the same failure: an
admin asks the copilot to tidy up the user list, it does, and now nobody
can reach the admin surface — including the person who asked, from the
chat window they asked in. There is no recovery path from that, so both
write tools refuse rather than confirm.
"""
import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.staff import (
    INVITE_STAFF_TOOL,
    LIST_STAFF_TOOL,
    SET_STAFF_ACTIVE_TOOL,
    SET_STAFF_ROLE_TOOL,
)
from app.models import User, UserRole
from tests.fixtures.helpers import make_user

_TOOLS = (
    LIST_STAFF_TOOL,
    INVITE_STAFF_TOOL,
    SET_STAFF_ROLE_TOOL,
    SET_STAFF_ACTIVE_TOOL,
)


@pytest.fixture(autouse=True)
def _register_tools():
    for tool in _TOOLS:
        registry.register(tool)
    yield


@pytest.fixture(autouse=True)
def _no_real_invite_email(monkeypatch):
    """The invite path sends mail best-effort; nothing here needs SendGrid."""
    import app.services.invite as invite

    sent = []
    monkeypatch.setattr(
        invite, "send_invite_email", lambda user, db: sent.append(user.email)
    )
    return sent


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


def _run(db_session, tool, args, *, role="admin", caller=None):
    user = caller or make_user(db_session, role=getattr(UserRole, role))
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
def organizer(db_session):
    return make_user(db_session, role=UserRole.organizer)


class TestListStaff:
    def test_lists_accounts_with_the_id_the_write_tools_need(
        self, db_session, organizer
    ):
        _, result = _run(db_session, LIST_STAFF_TOOL, {})
        row = next(r for r in result["staff"] if r["user_id"] == str(organizer.id))
        assert row["role"] == "organizer"
        assert row["active"] is True

    def test_it_can_be_filtered_by_role(self, db_session, organizer):
        _, result = _run(db_session, LIST_STAFF_TOOL, {"role": "organizer"})
        assert all(r["role"] == "organizer" for r in result["staff"])

    def test_inactive_accounts_are_hidden_by_default(self, db_session, organizer):
        organizer.is_active = False
        db_session.flush()
        _, result = _run(db_session, LIST_STAFF_TOOL, {})
        assert all(r["user_id"] != str(organizer.id) for r in result["staff"])

    def test_inactive_can_be_asked_for(self, db_session, organizer):
        organizer.is_active = False
        db_session.flush()
        _, result = _run(db_session, LIST_STAFF_TOOL, {"include_inactive": True})
        assert any(r["user_id"] == str(organizer.id) for r in result["staff"])

    def test_it_carries_no_email_back(self, db_session, organizer):
        """The redactor would rewrite it anyway; better to not pretend."""
        _, result = _run(db_session, LIST_STAFF_TOOL, {})
        assert "email" not in result["staff"][0]

    def test_a_bad_role_filter(self, db_session, organizer):
        _, result = _run(db_session, LIST_STAFF_TOOL, {"role": "wizard"})
        assert "role must be one of" in result["error"]

    def test_organizers_cannot_read_the_staff_list(self):
        assert LIST_STAFF_TOOL.allowed_roles == ["admin"]


class TestInviteStaff:
    def test_creates_an_account_and_sends_the_link(
        self, db_session, _no_real_invite_email
    ):
        _, result = _run(
            db_session,
            INVITE_STAFF_TOOL,
            {
                "email": "new.organizer@ucsb.edu",
                "name": "New Organizer",
                "role": "organizer",
            },
        )
        assert result["invited"] is True
        assert result["invite_email_sent"] is True
        assert "new.organizer@ucsb.edu" in _no_real_invite_email

    def test_the_account_has_no_password(self, db_session):
        """Invites are magic links; that is the whole recovery story."""
        _run(
            db_session,
            INVITE_STAFF_TOOL,
            {
                "email": "new.organizer@ucsb.edu",
                "name": "New Organizer",
                "role": "organizer",
            },
        )
        user = (
            db_session.query(User)
            .filter(User.email == "new.organizer@ucsb.edu")
            .one()
        )
        assert user.hashed_password is None
        assert user.is_active is True

    def test_it_never_picks_the_role(self, db_session):
        """Organizer and admin are not near-neighbours — one runs a
        classroom, the other can delete the quarter."""
        out, result = _run(
            db_session,
            INVITE_STAFF_TOOL,
            {"email": "someone@ucsb.edu", "name": "Someone"},
        )
        assert out.get("status") != "pending_confirmation"
        assert "organizer or an admin" in " ".join(result["needs_answers"])
        assert (
            db_session.query(User).filter(User.email == "someone@ucsb.edu").count()
            == 0
        )

    def test_it_asks_for_the_email(self, db_session):
        _, result = _run(
            db_session, INVITE_STAFF_TOOL, {"name": "Someone", "role": "admin"}
        )
        assert "email address" in " ".join(result["needs_answers"])

    def test_a_duplicate_address_points_at_the_other_tools(
        self, db_session, organizer
    ):
        _, result = _run(
            db_session,
            INVITE_STAFF_TOOL,
            {"email": organizer.email, "name": "Again", "role": "admin"},
        )
        assert "already exists" in result["error"]
        assert "Change its role or reactivate" in result["error"]

    def test_an_email_failure_does_not_undo_the_account(
        self, db_session, monkeypatch
    ):
        """Otherwise the admin is left with neither an account nor an invite."""
        import app.services.invite as invite

        def _boom(user, db):
            raise RuntimeError("sendgrid is down")

        monkeypatch.setattr(invite, "send_invite_email", _boom)
        _, result = _run(
            db_session,
            INVITE_STAFF_TOOL,
            {
                "email": "new.organizer@ucsb.edu",
                "name": "New Organizer",
                "role": "organizer",
            },
        )
        assert result["invited"] is True
        assert result["invite_email_sent"] is False
        assert (
            db_session.query(User)
            .filter(User.email == "new.organizer@ucsb.edu")
            .count()
            == 1
        )

    def test_it_confirms_before_creating(self, db_session):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=INVITE_STAFF_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={
                "email": "new.organizer@ucsb.edu",
                "name": "New Organizer",
                "role": "organizer",
            },
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert (
            db_session.query(User)
            .filter(User.email == "new.organizer@ucsb.edu")
            .count()
            == 0
        )


class TestSetStaffRole:
    def test_promotes_an_organizer(self, db_session, organizer):
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(organizer.id), "role": "admin"},
        )
        assert result["from_role"] == "organizer"
        assert result["to_role"] == "admin"
        db_session.refresh(organizer)
        assert organizer.role == UserRole.admin

    def test_demotes_an_admin_when_another_remains(self, db_session):
        keeper = make_user(db_session, role=UserRole.admin)
        spare = make_user(db_session, role=UserRole.admin)
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(spare.id), "role": "organizer"},
            caller=keeper,
        )
        assert result["to_role"] == "organizer"

    def test_a_no_op_says_so(self, db_session, organizer):
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(organizer.id), "role": "organizer"},
        )
        assert "already organizer" in result["error"]

    def test_it_asks_which_role(self, db_session, organizer):
        _, result = _run(
            db_session, SET_STAFF_ROLE_TOOL, {"user_id": str(organizer.id)}
        )
        asked = " ".join(result["needs_answers"])
        assert "which role" in asked
        assert "currently organizer" in asked

    def test_it_asks_whose_role(self, db_session):
        _, result = _run(db_session, SET_STAFF_ROLE_TOOL, {"role": "admin"})
        assert "whose role" in " ".join(result["needs_answers"])

    def test_an_unknown_id(self, db_session):
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(uuid.uuid4()), "role": "admin"},
        )
        assert "no staff account" in result["error"]

    def test_a_junk_id_is_an_error_not_a_crash(self, db_session):
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": "not-a-uuid", "role": "admin"},
        )
        assert "no staff account" in result["error"]


class TestSetStaffActive:
    def test_deactivates_someone_who_has_left(self, db_session, organizer):
        _, result = _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(organizer.id), "active": False},
        )
        assert result["active"] is False
        db_session.refresh(organizer)
        assert organizer.is_active is False

    def test_deactivating_keeps_the_row(self, db_session, organizer):
        """Unlike deletion, which is the CCPA erasure flow and not something
        to trigger from a sentence."""
        _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(organizer.id), "active": False},
        )
        assert db_session.query(User).filter(User.id == organizer.id).count() == 1

    def test_it_is_reversible(self, db_session, organizer):
        organizer.is_active = False
        db_session.flush()
        _, result = _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(organizer.id), "active": True},
        )
        assert result["active"] is True

    def test_a_no_op_says_so(self, db_session, organizer):
        _, result = _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(organizer.id), "active": True},
        )
        assert "already active" in result["error"]

    def test_it_asks_which_direction(self, db_session, organizer):
        _, result = _run(
            db_session, SET_STAFF_ACTIVE_TOOL, {"user_id": str(organizer.id)}
        )
        assert "deactivate or reactivate" in " ".join(result["needs_answers"])

    def test_it_confirms_first(self, db_session, organizer):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=SET_STAFF_ACTIVE_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"user_id": str(organizer.id), "active": False},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        db_session.refresh(organizer)
        assert organizer.is_active is True


class TestTheLastAdminIsUntouchable:
    def test_the_last_admin_cannot_be_demoted(self, db_session):
        only = make_user(db_session, role=UserRole.admin)
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(only.id), "role": "organizer"},
            caller=only,
        )
        assert "last active admin" in result["error"]
        db_session.refresh(only)
        assert only.role == UserRole.admin

    def test_the_last_admin_cannot_be_deactivated(self, db_session):
        only = make_user(db_session, role=UserRole.admin)
        other = make_user(db_session, role=UserRole.admin)
        other.is_active = False
        db_session.flush()
        _, result = _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(only.id), "active": False},
            caller=other,
        )
        assert "last active admin" in result["error"]
        db_session.refresh(only)
        assert only.is_active is True

    def test_you_cannot_deactivate_yourself(self, db_session):
        """Even with other admins around — it ends the session doing it."""
        me = make_user(db_session, role=UserRole.admin)
        make_user(db_session, role=UserRole.admin)
        _, result = _run(
            db_session,
            SET_STAFF_ACTIVE_TOOL,
            {"user_id": str(me.id), "active": False},
            caller=me,
        )
        assert "your own account" in result["error"]

    def test_an_inactive_admin_does_not_count_as_cover(self, db_session):
        """The guard counts *active* admins; a switched-off one cannot let
        anybody back in."""
        keeper = make_user(db_session, role=UserRole.admin)
        sleeping = make_user(db_session, role=UserRole.admin)
        sleeping.is_active = False
        db_session.flush()
        _, result = _run(
            db_session,
            SET_STAFF_ROLE_TOOL,
            {"user_id": str(keeper.id), "role": "organizer"},
            caller=sleeping,
        )
        assert "last active admin" in result["error"]


class TestEveryWriteHereAsksFirst:
    def test_no_confirming_tool_ships_without_a_precheck(self):
        for tool in _TOOLS:
            if tool.requires_confirmation:
                assert tool.precheck is not None, tool.name
