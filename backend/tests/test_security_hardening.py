"""Release hardening — staff-only /events surface, production guardrails,
and security headers.

The public (anonymous) event surface is /public/events with PublicEventRead;
the /events routes return EventRead including owner_id and non-public events,
so they must be staff-only.
"""
import pytest

from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import UserRole


class TestEventsStaffOnly:
    def test_anonymous_cannot_list_events(self, client, db_session):
        resp = client.get("/api/v1/events/")
        assert resp.status_code == 401

    def test_participant_cannot_list_events(self, client, db_session):
        participant = make_user(db_session, role=UserRole.participant)
        resp = client.get("/api/v1/events/", headers=auth_headers(client, participant))
        assert resp.status_code == 403

    def test_organizer_can_list_events(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        make_event_with_slot(db_session, owner=organizer)
        resp = client.get("/api/v1/events/", headers=auth_headers(client, organizer))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_anonymous_cannot_get_event(self, client, db_session):
        organizer = make_user(db_session, role=UserRole.organizer)
        event, _slot = make_event_with_slot(db_session, owner=organizer)
        resp = client.get(f"/api/v1/events/{event.id}")
        assert resp.status_code == 401

    def test_admin_can_get_event(self, client, db_session):
        admin = make_user(db_session, role=UserRole.admin)
        event, _slot = make_event_with_slot(db_session, owner=admin)
        resp = client.get(
            f"/api/v1/events/{event.id}", headers=auth_headers(client, admin)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(event.id)


class TestProductionGuardrail:
    def test_guard_raises_when_test_mode_meets_production(self):
        from app.config import assert_test_mode_allowed

        with pytest.raises(RuntimeError):
            assert_test_mode_allowed("production", expose_tokens=True)

    def test_guard_allows_test_mode_in_development(self):
        from app.config import assert_test_mode_allowed

        assert_test_mode_allowed("development", expose_tokens=True)

    def test_guard_allows_production_without_test_mode(self):
        from app.config import assert_test_mode_allowed

        assert_test_mode_allowed("production", expose_tokens=False)

    def test_settings_environment_defaults_to_development(self):
        from app.config import settings

        assert settings.environment == "development"


class TestSecurityHeaders:
    def test_csp_header_on_api_responses(self, client):
        resp = client.get("/api/v1/health")
        assert (
            resp.headers.get("Content-Security-Policy")
            == "default-src 'none'; frame-ancestors 'none'"
        )

    def test_docs_exempt_from_csp_in_dev(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "Content-Security-Policy" not in resp.headers
