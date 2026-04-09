"""Phase 4 model tests: ModuleTemplate, PrereqOverride, Event.module_slug."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Event,
    ModuleTemplate,
    PrereqOverride,
    Signup,
    SignupStatus,
    Slot,
    User,
)


class TestModuleTemplateSeed:
    """Verify seed templates can be created and queried."""

    def test_orientation_exists(self, db_session):
        _ensure_seed_templates(db_session)
        t = db_session.get(ModuleTemplate, "orientation")
        assert t is not None
        assert t.name == "Orientation"
        assert t.prereq_slugs == []

    def test_intro_bio_prereqs(self, db_session):
        _ensure_seed_templates(db_session)
        t = db_session.get(ModuleTemplate, "intro-bio")
        assert t is not None
        assert t.prereq_slugs == ["orientation"]

    def test_intro_chem_prereqs(self, db_session):
        _ensure_seed_templates(db_session)
        t = db_session.get(ModuleTemplate, "intro-chem")
        assert t is not None
        assert t.prereq_slugs == ["orientation"]


class TestEventModuleSlug:
    def test_event_with_module_slug(self, db_session):
        # Ensure seed templates exist
        _ensure_seed_templates(db_session)

        user = _make_user(db_session)
        event = Event(
            id=uuid.uuid4(),
            owner_id=user.id,
            title="Orientation Session",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
            module_slug="orientation",
        )
        db_session.add(event)
        db_session.flush()
        assert event.module_slug == "orientation"


class TestPrereqOverride:
    def test_valid_override(self, db_session):
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        admin = _make_user(db_session)

        override = PrereqOverride(
            id=uuid.uuid4(),
            user_id=user.id,
            module_slug="orientation",
            reason="Student completed equivalent training externally",
            created_by=admin.id,
        )
        db_session.add(override)
        db_session.flush()
        assert override.revoked_at is None

    def test_short_reason_raises_integrity_error(self, db_session):
        _ensure_seed_templates(db_session)
        user = _make_user(db_session)
        admin = _make_user(db_session)

        override = PrereqOverride(
            id=uuid.uuid4(),
            user_id=user.id,
            module_slug="orientation",
            reason="short",  # 5 chars, minimum is 10
            created_by=admin.id,
        )
        db_session.add(override)
        with pytest.raises(IntegrityError, match="prereq_overrides_reason_min_len"):
            db_session.flush()
        db_session.rollback()


# ---- helpers ----

def _make_user(db_session):
    user = User(
        id=uuid.uuid4(),
        name="Test User",
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="fakehash",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _ensure_seed_templates(db_session):
    """Ensure the seed module templates exist (create_all doesn't run migrations)."""
    if db_session.get(ModuleTemplate, "orientation") is None:
        db_session.add(ModuleTemplate(slug="orientation", name="Orientation", prereq_slugs=[]))
        db_session.add(ModuleTemplate(slug="intro-bio", name="Intro to Biology", prereq_slugs=["orientation"]))
        db_session.add(ModuleTemplate(slug="intro-chem", name="Intro to Chemistry", prereq_slugs=["orientation"]))
        db_session.flush()
