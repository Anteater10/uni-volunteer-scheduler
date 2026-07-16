"""Release guardrails on the copilot LLM surface — per-user message rate
limit + org-wide daily token budget, both enforced before any OpenRouter
call is made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app import models
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)


class _FakeRedis:
    """Minimal INCR/EXPIRE stand-in so unit tests don't need live Redis."""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds


def _staff(db_session, email):
    u = make_user(db_session, email=email, role=models.UserRole.organizer)
    db_session.commit()
    return u


def _copilot_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.commit()
    return sess


def _assistant_row(db_session, sess, *, prompt=0, completion=0):
    db_session.add(models.CopilotMessage(
        session_id=sess.id,
        role=models.CopilotMessageRole.assistant,
        content="x",
        prompt_tokens=prompt,
        completion_tokens=completion,
    ))
    db_session.flush()


class TestMessageRateLimit:
    def test_allows_under_limit(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_message_rate_limit

        monkeypatch.setattr(settings, "copilot_rate_limit_messages_per_minute", 3)
        user = _staff(db_session, "gr_under@example.com")
        fake = _FakeRedis()
        for _ in range(3):
            enforce_message_rate_limit(user, redis=fake)

    def test_429_over_limit(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_message_rate_limit

        monkeypatch.setattr(settings, "copilot_rate_limit_messages_per_minute", 3)
        user = _staff(db_session, "gr_over@example.com")
        fake = _FakeRedis()
        for _ in range(3):
            enforce_message_rate_limit(user, redis=fake)
        with pytest.raises(HTTPException) as exc:
            enforce_message_rate_limit(user, redis=fake)
        assert exc.value.status_code == 429

    def test_window_expiry_is_set_on_first_hit(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_message_rate_limit

        monkeypatch.setattr(settings, "copilot_rate_limit_messages_per_minute", 3)
        user = _staff(db_session, "gr_ttl@example.com")
        fake = _FakeRedis()
        enforce_message_rate_limit(user, redis=fake)
        assert list(fake.ttls.values()) == [60]

    def test_e2e_bypass(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_message_rate_limit

        monkeypatch.setattr(settings, "copilot_rate_limit_messages_per_minute", 0)
        monkeypatch.setenv("EXPOSE_TOKENS_FOR_TESTING", "1")
        user = _staff(db_session, "gr_bypass@example.com")
        # limit 0 would otherwise reject the first message
        enforce_message_rate_limit(user, redis=_FakeRedis())


class TestDailyTokenBudget:
    def test_allows_under_budget(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_daily_token_budget

        monkeypatch.setattr(settings, "copilot_daily_token_budget", 1000)
        user = _staff(db_session, "gr_budget_ok@example.com")
        sess = _copilot_session(db_session, user)
        _assistant_row(db_session, sess, prompt=100, completion=100)
        enforce_daily_token_budget(db_session)

    def test_429_at_budget(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_daily_token_budget

        monkeypatch.setattr(settings, "copilot_daily_token_budget", 1000)
        user = _staff(db_session, "gr_budget_hit@example.com")
        sess = _copilot_session(db_session, user)
        _assistant_row(db_session, sess, prompt=600, completion=400)
        with pytest.raises(HTTPException) as exc:
            enforce_daily_token_budget(db_session)
        assert exc.value.status_code == 429

    def test_warns_at_80_percent(self, db_session, monkeypatch, caplog):
        from app.copilot.guardrails import enforce_daily_token_budget

        monkeypatch.setattr(settings, "copilot_daily_token_budget", 1000)
        user = _staff(db_session, "gr_budget_warn@example.com")
        sess = _copilot_session(db_session, user)
        _assistant_row(db_session, sess, prompt=500, completion=300)
        with caplog.at_level("WARNING"):
            enforce_daily_token_budget(db_session)
        assert any("budget" in r.message.lower() for r in caplog.records)

    def test_zero_budget_disables_check(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_daily_token_budget

        monkeypatch.setattr(settings, "copilot_daily_token_budget", 0)
        enforce_daily_token_budget(db_session)

    def test_null_token_rows_do_not_crash(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_daily_token_budget

        monkeypatch.setattr(settings, "copilot_daily_token_budget", 1000)
        user = _staff(db_session, "gr_budget_null@example.com")
        sess = _copilot_session(db_session, user)
        db_session.add(models.CopilotMessage(
            session_id=sess.id,
            role=models.CopilotMessageRole.assistant,
            content="x",
        ))
        db_session.flush()
        enforce_daily_token_budget(db_session)


class TestRouterWiring:
    def test_post_message_429_before_any_llm_work(self, client, db_session, monkeypatch):
        """When the limiter trips, the endpoint must return 429 without
        touching retrieval or the LLM."""
        monkeypatch.setattr(settings, "copilot_rate_limit_messages_per_minute", 0)
        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)
        user = _staff(db_session, "gr_router@example.com")
        sess = _copilot_session(db_session, user)

        def _fail(*a, **k):
            raise AssertionError("retrieval reached despite rate limit")

        with patch("app.copilot.router._run_retrieval", _fail):
            resp = client.post(
                f"/api/v1/copilot/sessions/{sess.id}/messages",
                json={"content": "hello"},
                headers=auth_headers(client, user),
            )
        assert resp.status_code == 429
