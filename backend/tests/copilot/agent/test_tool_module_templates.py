"""Module templates: the recipe, not the calendar.

Two things share the word "module" in this app, and the copilot has to keep
them apart — a ``modules`` row is a template, an ``Event`` is a scheduled
run of one. These tests hold that line, and hold the ask-first rule on the
two numbers every event inherits: default capacity and session length.
"""
import uuid

import pytest
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.confirmation import execute_after_confirmation
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import invoke
from app.copilot.agent.tools.module_templates import (
    ARCHIVE_MODULE_TEMPLATE_TOOL,
    CREATE_MODULE_TEMPLATE_TOOL,
    LIST_MODULE_TEMPLATES_TOOL,
    UPDATE_MODULE_TEMPLATE_TOOL,
)
from app.models import Module, UserRole
from tests.fixtures.helpers import make_user

_TOOLS = (
    LIST_MODULE_TEMPLATES_TOOL,
    CREATE_MODULE_TEMPLATE_TOOL,
    UPDATE_MODULE_TEMPLATE_TOOL,
    ARCHIVE_MODULE_TEMPLATE_TOOL,
)


@pytest.fixture(autouse=True)
def _register_tools():
    """execute_after_confirmation resolves the tool by name from the registry."""
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
def crispr(db_session):
    template = Module(
        slug="crispr-gene-editing-basics",
        name="CRISPR Module 1 — Gene Editing Basics",
        default_capacity=12,
        duration_minutes=120,
        session_count=2,
        family_key="crispr",
    )
    db_session.add(template)
    db_session.flush()
    return template


class TestListModuleTemplates:
    def test_lists_the_recipes(self, db_session, crispr):
        _, result = _run(db_session, LIST_MODULE_TEMPLATES_TOOL, {})
        slugs = [t["slug"] for t in result["templates"]]
        assert "crispr-gene-editing-basics" in slugs

    def test_carries_the_numbers_an_event_will_inherit(self, db_session, crispr):
        _, result = _run(db_session, LIST_MODULE_TEMPLATES_TOOL, {})
        row = next(
            t
            for t in result["templates"]
            if t["slug"] == "crispr-gene-editing-basics"
        )
        assert row["default_capacity"] == 12
        assert row["duration_minutes"] == 120
        assert row["family_key"] == "crispr"

    def test_archived_are_hidden_by_default(self, db_session, crispr):
        _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics"},
        )
        _, result = _run(db_session, LIST_MODULE_TEMPLATES_TOOL, {})
        assert result["templates"] == []

    def test_archived_can_be_asked_for(self, db_session, crispr):
        _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics"},
        )
        _, result = _run(
            db_session, LIST_MODULE_TEMPLATES_TOOL, {"include_archived": True}
        )
        assert result["templates"][0]["archived"] is True

    def test_organizers_can_read(self, db_session, crispr):
        assert "organizer" in LIST_MODULE_TEMPLATES_TOOL.allowed_roles

    def test_reading_needs_no_confirmation(self, db_session, crispr):
        out, _ = _run(db_session, LIST_MODULE_TEMPLATES_TOOL, {})
        assert out.get("status") != "pending_confirmation"


class TestCreateModuleTemplate:
    def test_creates_a_template_events_can_use(self, db_session):
        _, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {
                "slug": "bioinformatics",
                "name": "Bioinformatics",
                "default_capacity": 12,
                "duration_minutes": 120,
            },
        )
        assert result["slug"] == "bioinformatics"
        assert (
            db_session.query(Module).filter(Module.slug == "bioinformatics").count()
            == 1
        )

    def test_it_asks_for_the_capacity_it_will_not_invent(self, db_session):
        """The two numbers every event stamped out of this inherits."""
        out, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {"slug": "bioinformatics", "name": "Bioinformatics"},
        )
        assert out.get("status") != "pending_confirmation"
        asked = " ".join(result["needs_answers"])
        assert "how many volunteers" in asked
        assert "how long one session runs" in asked
        assert db_session.query(Module).count() == 0

    def test_it_asks_for_a_slug(self, db_session):
        _, result = _run(
            db_session, CREATE_MODULE_TEMPLATE_TOOL, {"name": "Bioinformatics"}
        )
        assert "slug" in " ".join(result["needs_answers"])

    def test_a_module_is_its_own_orientation_family_by_default(self, db_session):
        _, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {
                "slug": "bioinformatics",
                "name": "Bioinformatics",
                "default_capacity": 12,
                "duration_minutes": 120,
            },
        )
        assert result["family_key"] == "bioinformatics"

    def test_modules_can_share_an_orientation(self, db_session, crispr):
        _, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {
                "slug": "crispr-advanced",
                "name": "CRISPR Module 2",
                "default_capacity": 12,
                "duration_minutes": 120,
                "family_key": "crispr",
            },
        )
        assert result["family_key"] == "crispr"

    def test_a_bad_slug_comes_back_worded_for_the_model(self, db_session):
        _, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {
                "slug": "Not A Slug",
                "name": "Whatever",
                "default_capacity": 12,
                "duration_minutes": 120,
            },
        )
        assert "lowercase alphanumeric" in result["error"]

    def test_a_duplicate_slug_is_refused(self, db_session, crispr):
        _, result = _run(
            db_session,
            CREATE_MODULE_TEMPLATE_TOOL,
            {
                "slug": "crispr-gene-editing-basics",
                "name": "Duplicate",
                "default_capacity": 12,
                "duration_minutes": 120,
            },
        )
        assert "already exists" in result["error"]

    def test_it_confirms_before_writing(self, db_session):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=CREATE_MODULE_TEMPLATE_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={
                "slug": "bioinformatics",
                "name": "Bioinformatics",
                "default_capacity": 12,
                "duration_minutes": 120,
            },
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        assert db_session.query(Module).count() == 0

    def test_organizers_cannot_create_templates(self, db_session):
        assert CREATE_MODULE_TEMPLATE_TOOL.allowed_roles == ["admin"]


class TestUpdateModuleTemplate:
    def test_changes_a_default(self, db_session, crispr):
        _, result = _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "default_capacity": 20},
        )
        assert result["default_capacity"] == 20
        assert result["changed"] == ["default_capacity"]

    def test_leaves_omitted_fields_alone(self, db_session, crispr):
        _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "name": "CRISPR I"},
        )
        db_session.refresh(crispr)
        assert crispr.name == "CRISPR I"
        assert crispr.duration_minutes == 120

    def test_it_says_how_many_events_it_did_not_touch(self, db_session, crispr):
        """A changed default does not reach back into events already built."""
        _, result = _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "default_capacity": 20},
        )
        assert result["events_using_it"] == 0

    def test_it_asks_what_to_change(self, db_session, crispr):
        _, result = _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics"},
        )
        assert "what to change" in result["needs_answers"][0]
        assert "CRISPR Module 1" in result["needs_answers"][0]

    def test_it_asks_which_template(self, db_session, crispr):
        _, result = _run(
            db_session, UPDATE_MODULE_TEMPLATE_TOOL, {"default_capacity": 20}
        )
        assert "which template" in result["needs_answers"][0]

    def test_an_unknown_slug_is_an_error_the_model_can_fix(
        self, db_session, crispr
    ):
        _, result = _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "no-such-module", "default_capacity": 20},
        )
        assert "not found" in result["error"]

    def test_an_out_of_range_session_count_is_refused(self, db_session, crispr):
        _, result = _run(
            db_session,
            UPDATE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "session_count": 99},
        )
        assert "between 1 and 10" in result["error"]


class TestArchiveModuleTemplate:
    def test_archiving_hides_the_recipe(self, db_session, crispr):
        _, result = _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics"},
        )
        assert result["archived"] is True

    def test_it_is_reversible(self, db_session, crispr):
        _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics"},
        )
        _, result = _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "restore": True},
        )
        assert result["archived"] is False

    def test_restoring_something_live_is_refused(self, db_session, crispr):
        _, result = _run(
            db_session,
            ARCHIVE_MODULE_TEMPLATE_TOOL,
            {"slug": "crispr-gene-editing-basics", "restore": True},
        )
        assert "not archived" in result["error"]

    def test_it_asks_which_template(self, db_session, crispr):
        _, result = _run(db_session, ARCHIVE_MODULE_TEMPLATE_TOOL, {})
        assert "which template to archive" in result["needs_answers"][0]

    def test_it_confirms_first(self, db_session, crispr):
        user = make_user(db_session, role=UserRole.admin)
        out = invoke(
            db_session,
            tool=ARCHIVE_MODULE_TEMPLATE_TOOL,
            scope=scope_for(role="admin", caller_id=user.id),
            args={"slug": "crispr-gene-editing-basics"},
            session_id=_make_session(db_session, user.id),
        )
        assert out["status"] == "pending_confirmation"
        db_session.refresh(crispr)
        assert crispr.deleted_at is None


class TestEveryWriteHereAsksFirst:
    def test_no_confirming_tool_ships_without_a_precheck(self):
        """A confirming tool's handler runs after the admin has already said
        yes, so a question raised there arrives too late to inform it."""
        for tool in _TOOLS:
            if tool.requires_confirmation:
                assert tool.precheck is not None, tool.name
