"""Adversarial suite fixtures.

Provides ``seed_full_world`` (a copy of the rich fixture from the agent
conftest — sibling conftests aren't auto-discovered, so we replicate it) and
an autouse fixture that registers every production tool so cat 2
(role-escalation) cases can exercise the loop's role-check on admin-only
tools.
"""
import pytest

from app.copilot.agent import confirmation
from app.copilot.agent.tools import registry
from app.models import UserRole
from tests.fixtures.helpers import make_user

from .seed import register_all_tools
from .seed import seed_full_world as _seed_full_world


@pytest.fixture
def admin_user(db_session):
    """Phase 34-10 adversarial: lightweight admin user for memory cases."""
    return make_user(db_session, role=UserRole.admin)


@pytest.fixture
def other_admin_user(db_session):
    """Phase 34-10 adversarial: a second, isolated admin user for cross-user
    profile-leak cases."""
    return make_user(db_session, role=UserRole.admin)


@pytest.fixture
def seed_full_world(db_session):
    """Mirror of ``tests/copilot/agent/conftest.py::seed_full_world``.

    The seeding body lives in ``seed.py`` so the offline
    ``app.eval.adversarial._run_one_case`` driver can reuse it outside
    pytest. The fixture just calls it and yields the sentinel dict.
    """
    yield _seed_full_world(db_session)


@pytest.fixture(autouse=True)
def _reset_and_register_all_tools():
    """Reset registry + confirmation store, then register every tool."""
    register_all_tools()
    yield
    registry._reset_for_tests()
    confirmation._reset_for_tests()
