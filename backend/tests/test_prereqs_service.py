"""Unit tests for the prereq check service (Plan 04-02)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    Event,
    ModuleTemplate,
    PrereqOverride,
    Signup,
    SignupStatus,
    Slot,
    User,
)
from app.services.prereqs import check_missing_prereqs, find_next_orientation_slot


# ---- helpers ----

def _make_user(db):
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="fakehash",
    )
    db.add(user)
    db.flush()
    return user


def _ensure_seed_templates(db):
    if db.get(ModuleTemplate, "orientation") is None:
        db.add(ModuleTemplate(slug="orientation", name="Orientation", prereq_slugs=[]))
        db.add(ModuleTemplate(slug="intro-bio", name="Intro to Biology", prereq_slugs=["orientation"]))
        db.add(ModuleTemplate(slug="intro-chem", name="Intro to Chemistry", prereq_slugs=["orientation"]))
        db.flush()


def _make_event_with_slot(db, owner, module_slug=None, starts_in_days=1):
    start = datetime.now(timezone.utc) + timedelta(days=starts_in_days)
    event = Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title=f"Event {uuid.uuid4().hex[:6]}",
        start_date=start,
        end_date=start + timedelta(days=1),
        module_slug=module_slug,
    )
    db.add(event)
    db.flush()
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=10,
    )
    db.add(slot)
    db.flush()
    return event, slot


# ---- tests ----

class TestCheckMissingPrereqs:
    def test_no_prereqs_returns_empty(self, db_session):
        """Module with empty prereq_slugs returns []."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        result = check_missing_prereqs(db_session, user.id, "orientation")
        assert result == []

    def test_missing_single_prereq(self, db_session):
        """User has no attended signup on orientation -> missing."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        result = check_missing_prereqs(db_session, user.id, "intro-bio")
        assert result == ["orientation"]

    def test_satisfied_via_attended(self, db_session):
        """User has attended orientation -> no missing prereqs for intro-bio."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        owner = _make_user(db_session)
        event, slot = _make_event_with_slot(db_session, owner, module_slug="orientation", starts_in_days=-1)
        signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=slot.id,
            status=SignupStatus.attended,
        )
        db_session.add(signup)
        db_session.flush()
        result = check_missing_prereqs(db_session, user.id, "intro-bio")
        assert result == []

    def test_not_satisfied_via_checked_in(self, db_session):
        """checked_in does NOT satisfy prereq — only attended counts."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        owner = _make_user(db_session)
        event, slot = _make_event_with_slot(db_session, owner, module_slug="orientation", starts_in_days=-1)
        signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=slot.id,
            status=SignupStatus.checked_in,
        )
        db_session.add(signup)
        db_session.flush()
        result = check_missing_prereqs(db_session, user.id, "intro-bio")
        assert result == ["orientation"]

    def test_satisfied_via_override(self, db_session):
        """Active PrereqOverride satisfies the prereq."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        admin = _make_user(db_session)
        override = PrereqOverride(
            id=uuid.uuid4(),
            user_id=user.id,
            module_slug="orientation",
            reason="Student completed equivalent training",
            created_by=admin.id,
        )
        db_session.add(override)
        db_session.flush()
        result = check_missing_prereqs(db_session, user.id, "intro-bio")
        assert result == []

    def test_revoked_override_does_not_satisfy(self, db_session):
        """Revoked override does NOT satisfy the prereq."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        admin = _make_user(db_session)
        override = PrereqOverride(
            id=uuid.uuid4(),
            user_id=user.id,
            module_slug="orientation",
            reason="Student completed equivalent training",
            created_by=admin.id,
            revoked_at=datetime.now(timezone.utc),
        )
        db_session.add(override)
        db_session.flush()
        result = check_missing_prereqs(db_session, user.id, "intro-bio")
        assert result == ["orientation"]

    def test_unknown_module_slug_returns_empty(self, db_session):
        """Unknown module_slug returns [] (no crash)."""
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        result = check_missing_prereqs(db_session, user.id, "nonexistent-module")
        assert result == []


class TestFindNextOrientationSlot:
    def test_returns_future_slot(self, db_session):
        """Returns the soonest future orientation slot."""
        _ensure_seed_templates(db_session)
        owner = _make_user(db_session)

        # Past orientation event
        _make_event_with_slot(db_session, owner, module_slug="orientation", starts_in_days=-3)

        # Future orientation event
        future_event, future_slot = _make_event_with_slot(
            db_session, owner, module_slug="orientation", starts_in_days=5
        )

        result = find_next_orientation_slot(db_session)
        assert result is not None
        assert result["slot_id"] == str(future_slot.id)
        assert result["event_id"] == str(future_event.id)
        assert "starts_at" in result

    def test_returns_none_when_no_future(self, db_session):
        """Returns None when no future orientation slot exists."""
        _ensure_seed_templates(db_session)
        owner = _make_user(db_session)

        # Only a past orientation event
        _make_event_with_slot(db_session, owner, module_slug="orientation", starts_in_days=-3)

        result = find_next_orientation_slot(db_session)
        assert result is None
