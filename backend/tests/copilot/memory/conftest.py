"""Fixtures for copilot memory (Phase 34) tests."""
import pytest

from app.models import UserRole
from tests.fixtures.helpers import make_user


@pytest.fixture
def test_user(db_session):
    """A single participant user for memory model round-trip tests."""
    user = make_user(db_session, role=UserRole.participant)
    db_session.flush()
    return user
