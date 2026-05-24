"""Phase 34-07 Task 22: ``load_profile_block`` helper tests."""
from __future__ import annotations

import pytest

from app import models
from app.config import settings
from app.copilot.memory.profile_block import load_profile_block
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


@pytest.fixture
def admin_user(db_session):
    return make_user(db_session, role=models.UserRole.admin)


@pytest.fixture
def other_admin_user(db_session):
    return make_user(db_session, role=models.UserRole.admin)


def test_load_profile_block_empty_returns_empty_string(db_session, admin_user):
    assert load_profile_block(db_session, user_id=admin_user.id) == ""


def test_load_profile_block_whitespace_only_returns_empty_string(
    db_session, admin_user
):
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin_user.id, profile_text="   \n  ", version=1,
        )
    )
    db_session.commit()
    assert load_profile_block(db_session, user_id=admin_user.id) == ""


def test_load_profile_block_populated_returns_wrapped(db_session, admin_user):
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin_user.id, profile_text="Runs Forces.", version=1,
        )
    )
    db_session.commit()
    block = load_profile_block(db_session, user_id=admin_user.id)
    assert block.startswith("## What you know about this user")
    assert "Runs Forces." in block
    assert "ignore it when irrelevant" in block


def test_load_profile_block_scoped_to_user(
    db_session, admin_user, other_admin_user
):
    db_session.add(
        models.CopilotUserProfile(
            user_id=other_admin_user.id, profile_text="other user", version=1,
        )
    )
    db_session.commit()
    assert load_profile_block(db_session, user_id=admin_user.id) == ""
    block_other = load_profile_block(db_session, user_id=other_admin_user.id)
    assert "other user" in block_other


# ---------------------------------------------------------------------------
# Task 23: wiring into the system prompt
# ---------------------------------------------------------------------------


def test_agent_system_prompt_includes_profile_block_when_present(
    db_session, admin_user
):
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin_user.id, profile_text="Runs Forces.", version=1,
        )
    )
    db_session.commit()

    from app.copilot.agent.loop import _system_prompt
    from app.copilot.agent.boundary.role_scope import scope_for

    scope = scope_for(role="admin", caller_id=admin_user.id)
    prompt = _system_prompt(
        scope,
        retrieval_context="",
        profile_block=load_profile_block(db_session, user_id=admin_user.id),
    )
    assert "Runs Forces." in prompt
    assert "## What you know about this user" in prompt


def test_agent_system_prompt_omits_section_when_blank(db_session, admin_user):
    from app.copilot.agent.loop import _system_prompt
    from app.copilot.agent.boundary.role_scope import scope_for

    scope = scope_for(role="admin", caller_id=admin_user.id)
    prompt = _system_prompt(scope, retrieval_context="", profile_block="")
    assert "What you know about this user" not in prompt


def test_render_with_profile_appends_block(db_session, admin_user):
    """``prompts.render_with_profile`` returns prompt + hash including block."""
    from app.copilot import prompts

    base = prompts.system_prompt_for(models.UserRole.admin)
    text, digest = prompts.render_with_profile(
        models.UserRole.admin,
        profile_block="## What you know about this user\nx\n\nUse this context when it helps; ignore it when irrelevant.",
    )
    assert text.startswith(base)
    assert "## What you know about this user" in text
    assert digest == prompts.hash_prompt(text)
    assert digest != prompts.hash_prompt(base)


def test_render_with_profile_no_block_matches_base(db_session, admin_user):
    from app.copilot import prompts

    base = prompts.system_prompt_for(models.UserRole.admin)
    text, digest = prompts.render_with_profile(
        models.UserRole.admin, profile_block=""
    )
    assert text == base
    assert digest == prompts.hash_prompt(base)


def test_create_session_persists_prompt_with_profile_block(
    client, db_session
):
    """Integration: a new session for a user with a populated profile
    has the profile block stored in its system message."""
    from tests.fixtures.helpers import auth_headers

    user = make_user(db_session, role=models.UserRole.admin)
    db_session.add(
        models.CopilotUserProfile(
            user_id=user.id,
            profile_text="Prefers concise replies.",
            version=1,
        )
    )
    db_session.commit()

    headers = auth_headers(client, user)
    resp = client.post("/api/v1/copilot/sessions", headers=headers)
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["id"]

    sysmsg = (
        db_session.query(models.CopilotMessage)
        .filter(
            models.CopilotMessage.session_id == session_id,
            models.CopilotMessage.role == models.CopilotMessageRole.system,
        )
        .first()
    )
    assert sysmsg is not None
    assert "Prefers concise replies." in sysmsg.content
    assert "## What you know about this user" in sysmsg.content


def test_create_session_no_profile_omits_block(client, db_session):
    from tests.fixtures.helpers import auth_headers

    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()

    headers = auth_headers(client, user)
    resp = client.post("/api/v1/copilot/sessions", headers=headers)
    assert resp.status_code == 201, resp.text
    session_id = resp.json()["id"]

    sysmsg = (
        db_session.query(models.CopilotMessage)
        .filter(
            models.CopilotMessage.session_id == session_id,
            models.CopilotMessage.role == models.CopilotMessageRole.system,
        )
        .first()
    )
    assert sysmsg is not None
    assert "What you know about this user" not in sysmsg.content
