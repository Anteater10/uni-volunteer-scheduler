"""Integration tests for GET /me/module-timeline (Plan 04-05)."""
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
    UserRole,
)
from tests.fixtures.helpers import auth_headers, make_user


def _ensure_seed_templates(db):
    if db.get(ModuleTemplate, "orientation") is None:
        db.add(ModuleTemplate(slug="orientation", name="Orientation", prereq_slugs=[]))
        db.add(ModuleTemplate(slug="intro-bio", name="Intro to Biology", prereq_slugs=["orientation"]))
        db.add(ModuleTemplate(slug="intro-chem", name="Intro to Chemistry", prereq_slugs=["orientation"]))
        db.flush()


def _make_module_event(db, owner, module_slug, starts_in_days=-1, capacity=10):
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
        capacity=capacity,
    )
    db.add(slot)
    db.flush()
    return event, slot


class TestModuleTimeline:
    def test_empty_timeline(self, client, db_session):
        """User with no signups -> empty list."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        headers = auth_headers(client, user)
        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_completed_module(self, client, db_session):
        """User attended orientation -> status=completed."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        event, slot = _make_module_event(db_session, owner, "orientation")
        signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=slot.id,
            status=SignupStatus.attended,
        )
        db_session.add(signup)
        db_session.flush()

        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        ori = next(m for m in data if m["slug"] == "orientation")
        assert ori["status"] == "completed"
        assert ori["override_active"] is False

    def test_locked_module(self, client, db_session):
        """User signed up for intro-bio but never attended orientation -> intro-bio locked."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        # Sign up for intro-bio (confirmed, not attended)
        bio_event, bio_slot = _make_module_event(db_session, owner, "intro-bio")
        signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=bio_slot.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        bio = next(m for m in data if m["slug"] == "intro-bio")
        assert bio["status"] == "locked"

    def test_unlocked_module(self, client, db_session):
        """User attended orientation, signed up for intro-bio (confirmed) -> intro-bio unlocked."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        # Attend orientation
        ori_event, ori_slot = _make_module_event(db_session, owner, "orientation")
        db_session.add(Signup(
            id=uuid.uuid4(), user_id=user.id, slot_id=ori_slot.id,
            status=SignupStatus.attended,
        ))
        db_session.flush()

        # Sign up for intro-bio (confirmed)
        bio_event, bio_slot = _make_module_event(db_session, owner, "intro-bio")
        db_session.add(Signup(
            id=uuid.uuid4(), user_id=user.id, slot_id=bio_slot.id,
            status=SignupStatus.confirmed,
        ))
        db_session.flush()

        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        bio = next(m for m in data if m["slug"] == "intro-bio")
        assert bio["status"] == "unlocked"

    def test_override_active(self, client, db_session):
        """Admin override on intro-bio -> override_active=True, status=unlocked."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        # Sign up for intro-bio (no orientation attended)
        bio_event, bio_slot = _make_module_event(db_session, owner, "intro-bio")
        db_session.add(Signup(
            id=uuid.uuid4(), user_id=user.id, slot_id=bio_slot.id,
            status=SignupStatus.confirmed,
        ))

        # Admin override on orientation prereq
        db_session.add(PrereqOverride(
            id=uuid.uuid4(), user_id=user.id, module_slug="orientation",
            reason="Completed equivalent training externally",
            created_by=admin.id,
        ))
        db_session.flush()

        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        bio = next(m for m in data if m["slug"] == "intro-bio")
        assert bio["status"] == "unlocked"
        # Check orientation override active
        ori = next(m for m in data if m["slug"] == "orientation")
        assert ori["override_active"] is True

    def test_last_activity_populated(self, client, db_session):
        """last_activity matches signup timestamp."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        event, slot = _make_module_event(db_session, owner, "orientation")
        signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=slot.id,
            status=SignupStatus.attended,
        )
        db_session.add(signup)
        db_session.flush()

        resp = client.get("/api/v1/users/me/module-timeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        ori = next(m for m in data if m["slug"] == "orientation")
        assert ori["last_activity"] is not None
