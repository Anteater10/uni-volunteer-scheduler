"""Task 7 item 3: frontend_base_url / frontend_url collapsed to one value.

The two names were independently-configurable settings that happened to
always be set to the same value in every .env (dev and prod alike) — a
single source of truth removes the chance they drift apart. frontend_url
is the real pydantic field; frontend_base_url is a read-only alias so
every existing caller of either name keeps working.
"""
from app.config import Settings, settings


class TestFrontendUrlAlias:
    def test_only_one_real_field_exists(self):
        assert "frontend_url" in Settings.model_fields
        assert "frontend_base_url" not in Settings.model_fields

    def test_frontend_base_url_reads_through_to_frontend_url(self, monkeypatch):
        monkeypatch.setattr(settings, "frontend_url", "https://example.test", raising=False)
        assert settings.frontend_base_url == "https://example.test"

    def test_frontend_base_url_tracks_frontend_url_changes(self, monkeypatch):
        """No stored duplicate value: changing frontend_url immediately
        changes what frontend_base_url reads, so the two can never drift."""
        monkeypatch.setattr(settings, "frontend_url", "https://first.test", raising=False)
        assert settings.frontend_base_url == "https://first.test"
        monkeypatch.setattr(settings, "frontend_url", "https://second.test", raising=False)
        assert settings.frontend_base_url == "https://second.test"
