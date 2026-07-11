"""Logging configuration + optional Sentry init (release ops minimum)."""
import logging
import sys

import pytest

from app.config import settings


class TestConfigureLogging:
    def test_sets_root_level_from_settings(self, monkeypatch):
        from app.observability import configure_logging

        monkeypatch.setattr(settings, "log_level", "WARNING")
        configure_logging()
        assert logging.getLogger().level == logging.WARNING
        # restore for other tests in this process
        monkeypatch.setattr(settings, "log_level", "INFO")
        configure_logging()

    def test_idempotent_no_handler_stacking(self):
        from app.observability import configure_logging

        configure_logging()
        first = len(logging.getLogger().handlers)
        configure_logging()
        configure_logging()
        assert len(logging.getLogger().handlers) == first

    def test_invalid_level_falls_back_to_info(self, monkeypatch):
        from app.observability import configure_logging

        monkeypatch.setattr(settings, "log_level", "NOT_A_LEVEL")
        configure_logging()
        assert logging.getLogger().level == logging.INFO


class TestInitSentry:
    def test_noop_without_dsn(self, monkeypatch):
        from app.observability import init_sentry

        monkeypatch.setattr(settings, "sentry_dsn", "")
        assert init_sentry() is False

    def test_missing_package_warns_instead_of_crashing(self, monkeypatch, caplog):
        from app.observability import init_sentry

        monkeypatch.setattr(settings, "sentry_dsn", "https://x@sentry.example/1")
        # None in sys.modules makes `import sentry_sdk` raise ImportError.
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)
        with caplog.at_level("WARNING"):
            assert init_sentry() is False
        assert any("sentry" in r.message.lower() for r in caplog.records)
