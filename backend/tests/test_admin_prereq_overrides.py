"""Integration tests for admin prereq override endpoints (Plan 04-03)."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import (
    AuditLog,
    ModuleTemplate,
    PrereqOverride,
    UserRole,
)
from tests.fixtures.helpers import auth_headers, make_user


def _ensure_seed_templates(db):
    if db.get(ModuleTemplate, "orientation") is None:
        db.add(ModuleTemplate(slug="orientation", name="Orientation", prereq_slugs=[]))
        db.add(ModuleTemplate(slug="intro-bio", name="Intro to Biology", prereq_slugs=["orientation"]))
        db.add(ModuleTemplate(slug="intro-chem", name="Intro to Chemistry", prereq_slugs=["orientation"]))
        db.flush()


class TestAdminCreatePrereqOverride:
    def test_non_admin_blocked(self, client, db_session):
        """Regular participant gets 403."""
        _ensure_seed_templates(db_session)
        user = make_user(db_session, role=UserRole.participant)
        headers = auth_headers(client, user)
        resp = client.post(
            f"/api/v1/admin/users/{user.id}/prereq-overrides",
            json={"module_slug": "orientation", "reason": "student completed equivalent training"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_create_happy_path(self, client, db_session):
        """Admin creates override successfully."""
        _ensure_seed_templates(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        student = make_user(db_session)
        headers = auth_headers(client, admin)
        resp = client.post(
            f"/api/v1/admin/users/{student.id}/prereq-overrides",
            json={"module_slug": "orientation", "reason": "student unable to attend orientation"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["module_slug"] == "orientation"
        assert data["user_id"] == str(student.id)
        assert data["created_by"] == str(admin.id)
        assert data["revoked_at"] is None

        # AuditLog created
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "prereq_override_admin_create"
        ).first()
        assert audit is not None

    def test_reason_too_short(self, client, db_session):
        """Reason < 10 chars returns 400."""
        _ensure_seed_templates(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        student = make_user(db_session)
        headers = auth_headers(client, admin)
        resp = client.post(
            f"/api/v1/admin/users/{student.id}/prereq-overrides",
            json={"module_slug": "orientation", "reason": "short"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_unknown_module_slug(self, client, db_session):
        """Unknown module_slug returns 404."""
        _ensure_seed_templates(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        student = make_user(db_session)
        headers = auth_headers(client, admin)
        resp = client.post(
            f"/api/v1/admin/users/{student.id}/prereq-overrides",
            json={"module_slug": "nonexistent", "reason": "this module does not exist at all"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_unknown_user_id(self, client, db_session):
        """Unknown user_id returns 404."""
        _ensure_seed_templates(db_session)
        admin = make_user(db_session, role=UserRole.admin)
        headers = auth_headers(client, admin)
        fake_user_id = uuid.uuid4()
        resp = client.post(
            f"/api/v1/admin/users/{fake_user_id}/prereq-overrides",
            json={"module_slug": "orientation", "reason": "user does not exist in the system"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestAdminRevokePrereqOverride:
    def _create_override(self, db_session, admin, student):
        _ensure_seed_templates(db_session)
        override = PrereqOverride(
            id=uuid.uuid4(),
            user_id=student.id,
            module_slug="orientation",
            reason="student completed equivalent training",
            created_by=admin.id,
        )
        db_session.add(override)
        db_session.flush()
        return override

    def test_revoke_happy_path(self, client, db_session):
        """DELETE soft-revokes the override."""
        admin = make_user(db_session, role=UserRole.admin)
        student = make_user(db_session)
        override = self._create_override(db_session, admin, student)
        headers = auth_headers(client, admin)
        resp = client.delete(
            f"/api/v1/admin/prereq-overrides/{override.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revoked_at"] is not None

        # AuditLog created
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "prereq_override_admin_revoke"
        ).first()
        assert audit is not None

    def test_double_revoke(self, client, db_session):
        """Second DELETE returns 409."""
        admin = make_user(db_session, role=UserRole.admin)
        student = make_user(db_session)
        override = self._create_override(db_session, admin, student)
        headers = auth_headers(client, admin)
        # First revoke
        resp1 = client.delete(f"/api/v1/admin/prereq-overrides/{override.id}", headers=headers)
        assert resp1.status_code == 200
        # Second revoke
        resp2 = client.delete(f"/api/v1/admin/prereq-overrides/{override.id}", headers=headers)
        assert resp2.status_code == 409

    def test_revoke_unknown_id(self, client, db_session):
        """DELETE unknown ID returns 404."""
        admin = make_user(db_session, role=UserRole.admin)
        headers = auth_headers(client, admin)
        fake_id = uuid.uuid4()
        resp = client.delete(f"/api/v1/admin/prereq-overrides/{fake_id}", headers=headers)
        assert resp.status_code == 404
