"""Integration tests for POST /signups prereq enforcement (Plan 04-03)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import (
    AuditLog,
    Event,
    ModuleTemplate,
    Signup,
    SignupStatus,
    Slot,
    User,
)
from tests.fixtures.helpers import auth_headers, make_user, make_event_with_slot


def _ensure_seed_templates(db):
    if db.get(ModuleTemplate, "orientation") is None:
        db.add(ModuleTemplate(slug="orientation", name="Orientation", prereq_slugs=[]))
        db.add(ModuleTemplate(slug="intro-bio", name="Intro to Biology", prereq_slugs=["orientation"]))
        db.add(ModuleTemplate(slug="intro-chem", name="Intro to Chemistry", prereq_slugs=["orientation"]))
        db.flush()


def _make_module_event(db, owner, module_slug, starts_in_days=1, capacity=10):
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


class TestSignupPrereqs:
    def test_no_module_slug_succeeds(self, client, db_session):
        """Event with module_slug=None -> signup succeeds without prereq check."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        headers = auth_headers(client, user)
        event, slot = make_event_with_slot(db_session, capacity=10)
        resp = client.post("/api/v1/signups/", json={"slot_id": str(slot.id)}, headers=headers)
        assert resp.status_code == 200

    def test_no_missing_prereqs_succeeds(self, client, db_session):
        """Event with module_slug=orientation (no prereqs) -> signup succeeds."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)
        event, slot = _make_module_event(db_session, owner, "orientation")
        resp = client.post("/api/v1/signups/", json={"slot_id": str(slot.id)}, headers=headers)
        assert resp.status_code == 200

    def test_missing_prereqs_returns_422(self, client, db_session):
        """Event with intro-bio, user hasn't attended orientation -> 422."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)
        event, slot = _make_module_event(db_session, owner, "intro-bio")
        resp = client.post("/api/v1/signups/", json={"slot_id": str(slot.id)}, headers=headers)
        assert resp.status_code == 422
        data = resp.json()
        assert data["code"] == "PREREQ_MISSING"
        assert data["missing"] == ["orientation"]
        # next_slot may be dict or None
        assert "next_slot" in data

    def test_acknowledge_bypass_creates_signup_and_audit(self, client, db_session):
        """acknowledge_prereq_override=true -> signup created + audit log."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)
        event, slot = _make_module_event(db_session, owner, "intro-bio")
        resp = client.post(
            "/api/v1/signups/?acknowledge_prereq_override=true",
            json={"slot_id": str(slot.id)},
            headers=headers,
        )
        assert resp.status_code == 200
        # Check audit log
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "prereq_override_self"
        ).first()
        assert audit is not None
        assert "missing_prereqs" in (audit.extra or {})

    def test_satisfied_via_attended_orientation(self, client, db_session):
        """User attended orientation -> intro-bio signup succeeds."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        # Create and attend orientation
        ori_event, ori_slot = _make_module_event(db_session, owner, "orientation", starts_in_days=-1)
        ori_signup = Signup(
            id=uuid.uuid4(),
            user_id=user.id,
            slot_id=ori_slot.id,
            status=SignupStatus.attended,
        )
        db_session.add(ori_signup)
        db_session.flush()

        # Now sign up for intro-bio
        bio_event, bio_slot = _make_module_event(db_session, owner, "intro-bio")
        resp = client.post("/api/v1/signups/", json={"slot_id": str(bio_slot.id)}, headers=headers)
        assert resp.status_code == 200

        # No prereq_override_self audit log
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "prereq_override_self"
        ).first()
        assert audit is None

    def test_next_slot_populated(self, client, db_session):
        """422 response includes next_slot when a future orientation slot exists."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session)
        owner = make_user(db_session)
        headers = auth_headers(client, user)

        # Create a future orientation event
        ori_event, ori_slot = _make_module_event(db_session, owner, "orientation", starts_in_days=5)

        # Try to sign up for intro-bio (will fail with 422)
        bio_event, bio_slot = _make_module_event(db_session, owner, "intro-bio")
        resp = client.post("/api/v1/signups/", json={"slot_id": str(bio_slot.id)}, headers=headers)
        assert resp.status_code == 422
        data = resp.json()
        assert data["next_slot"] is not None
        assert data["next_slot"]["slot_id"] == str(ori_slot.id)
