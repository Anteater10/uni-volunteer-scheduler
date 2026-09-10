"""Release hardening — staff-only /events surface, production guardrails,
and security headers.

The public (anonymous) event surface is /public/events with PublicEventRead;
the /events routes return EventRead including owner_id and non-public events,
so they must be staff-only.
"""
import pytest

from tests.fixtures.helpers import auth_headers, make_event_with_slot, make_user

from app.models import UserRole


class TestRefreshEndpointHardening:
    """Phase L3: /auth/refresh had zero rate limiting and no CSRF check
    before this — it's unauthenticated (only a cookie is required) and
    becomes the CSRF target once the refresh token moves off localStorage."""

    def test_refresh_rate_limited_429(self, client, db_session, monkeypatch):
        """120/min, deliberately higher than the 30/min on login — /auth/refresh
        is on the boot path of every page load and the bucket is per-IP, so
        staff behind one NAT share it."""
        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)
        client.cookies.set("refresh_token", "not-a-real-token")
        client.cookies.set("csrf_token", "whatever")
        headers = {"X-CSRF-Token": "whatever"}
        statuses = [
            client.post("/api/v1/auth/refresh", headers=headers).status_code
            for _ in range(121)
        ]
        assert 429 not in statuses[:120]
        assert statuses[120] == 429

    def test_refresh_missing_csrf_header_is_forbidden(self, client, db_session):
        client.cookies.set("refresh_token", "not-a-real-token")
        client.cookies.set("csrf_token", "the-real-value")
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 403

    def test_refresh_mismatched_csrf_header_is_forbidden(self, client, db_session):
        client.cookies.set("refresh_token", "not-a-real-token")
        client.cookies.set("csrf_token", "the-real-value")
        resp = client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": "an-attackers-guess"}
        )
        assert resp.status_code == 403


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

    def test_settings_environment_defaults_to_production(self):
        """W5 S-05: this test used to assert the default was "development", and
        that assertion is why the unsafe default survived.

        A default of "development" means forgetting the variable produces the
        relaxed behaviour — /docs served publicly, and the
        EXPOSE_TOKENS_FOR_TESTING refusal inert. That is exactly what happened
        on the live Render service, which was found on 2026-08-13 running
        ENVIRONMENT=development with /docs public. The default now fails safe.

        Note this reads the process-wide ``settings`` singleton, so it asserts
        the *ambient* value, not the class default — it passes here because CI
        sets no ENVIRONMENT. The rigorous version, which disables .env loading
        so it cannot be fooled by an ambient value, is
        ``test_environment_guard.py::test_the_default_is_production``.
        """
        from app.config import Settings

        assert Settings.model_fields["environment"].default == "production"


class TestSecurityHeaders:
    def test_csp_header_on_api_responses(self, client):
        resp = client.get("/api/v1/health")
        assert (
            resp.headers.get("Content-Security-Policy")
            == "default-src 'none'; frame-ancestors 'none'"
        )

    def test_docs_paths_are_exempt_from_csp(self, client):
        """The exemption is path-based, so it holds whether or not docs are
        mounted.

        This previously asserted ``status_code == 200``, which silently made it
        a test of two things: the CSP exemption *and* the app being in
        development. Once the default environment became production (W5 S-05)
        the second half broke the first. Status is deliberately not asserted —
        whether /docs is served is the environment's business, and
        ``test_docs_are_not_served_under_the_default_environment`` below covers
        that separately.
        """
        resp = client.get("/docs")
        assert "Content-Security-Policy" not in resp.headers
        # Still passed through the middleware, so the non-CSP headers are set.
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_docs_are_not_served_under_the_default_environment(self, client):
        """The actual security property, which nothing asserted before.

        /docs, /redoc and /openapi.json together publish every route, schema and
        required field in the app. With no ENVIRONMENT set — the state the Render
        service was found in — they must not be served.
        """
        from app.config import settings

        if settings.environment == "development":
            pytest.skip(
                "ENVIRONMENT=development is set (a local .env), so docs are "
                "served here by design; this asserts the default, not dev."
            )
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404, (
                f"{path} is being served outside development — the S-05 "
                "docs suppression is not in effect"
            )
