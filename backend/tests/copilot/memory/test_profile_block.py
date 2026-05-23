"""Phase 34-07 Task 22: ``load_profile_block`` helper tests."""
from __future__ import annotations

import pytest

from app import models
from app.copilot.memory.profile_block import load_profile_block
from tests.fixtures.helpers import make_user


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
