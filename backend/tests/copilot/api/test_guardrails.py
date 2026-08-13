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
    """Minimal INCR/EXPIRE/TTL stand-in so unit tests don't need live Redis."""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def ttl(self, key):
        # -1 is real Redis' answer for "key exists, no expiry" — the exact
        # state the self-healing repair in enforce_user_rate_limit exists for.
        return self.ttls.get(key, -1)


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


class TestGenericUserRateLimit:
    """BASE-CONFIG-37 — the shared per-user, per-action limiter."""

    def test_counts_per_action_not_globally(self, db_session):
        from app.copilot.guardrails import enforce_user_rate_limit

        user = _staff(db_session, "gr_gen_actions@example.com")
        fake = _FakeRedis()
        # Two different actions, limit 1 each: neither should trip the other.
        enforce_user_rate_limit(user, "alpha", 1, detail="a", redis=fake)
        enforce_user_rate_limit(user, "beta", 1, detail="b", redis=fake)
        assert sorted(fake.store) == [
            f"rate:copilot_alpha:{user.id}",
            f"rate:copilot_beta:{user.id}",
        ]

    def test_counts_per_user_not_per_ip(self, db_session):
        from app.copilot.guardrails import enforce_user_rate_limit

        a = _staff(db_session, "gr_gen_a@example.com")
        b = _staff(db_session, "gr_gen_b@example.com")
        fake = _FakeRedis()
        enforce_user_rate_limit(a, "alpha", 1, detail="a", redis=fake)
        # Same action, same notional IP, different user — must not be throttled.
        enforce_user_rate_limit(b, "alpha", 1, detail="a", redis=fake)

    def test_429_carries_the_supplied_detail(self, db_session):
        from app.copilot.guardrails import enforce_user_rate_limit

        user = _staff(db_session, "gr_gen_detail@example.com")
        fake = _FakeRedis()
        enforce_user_rate_limit(user, "alpha", 1, detail="slow down", redis=fake)
        with pytest.raises(HTTPException) as exc:
            enforce_user_rate_limit(user, "alpha", 1, detail="slow down", redis=fake)
        assert exc.value.status_code == 429
        assert exc.value.detail == "slow down"

    def test_custom_window_is_applied(self, db_session):
        from app.copilot.guardrails import enforce_user_rate_limit

        user = _staff(db_session, "gr_gen_window@example.com")
        fake = _FakeRedis()
        enforce_user_rate_limit(
            user, "alpha", 5, detail="a", window_seconds=300, redis=fake
        )
        assert list(fake.ttls.values()) == [300]

    def test_lost_ttl_is_repaired(self, db_session):
        """A key that outlived its expiry must not lock the user out forever."""
        from app.copilot.guardrails import enforce_user_rate_limit

        user = _staff(db_session, "gr_gen_ttl_lost@example.com")
        fake = _FakeRedis()
        key = f"rate:copilot_alpha:{user.id}"
        # Simulate a counter that survived without an expiry attached.
        fake.store[key] = 1
        enforce_user_rate_limit(user, "alpha", 5, detail="a", redis=fake)
        assert fake.ttls[key] == 60

    def test_fails_open_when_redis_is_down(self, db_session, caplog):
        """A Redis outage must not stop staff from working."""
        from app.copilot.guardrails import enforce_user_rate_limit

        class _Broken:
            def incr(self, key):
                raise RuntimeError("connection refused")

        user = _staff(db_session, "gr_gen_down@example.com")
        with caplog.at_level("WARNING"):
            enforce_user_rate_limit(user, "alpha", 1, detail="a", redis=_Broken())
        assert any("rate_limit_unavailable" in r.message for r in caplog.records)

    def test_ttl_failure_still_enforces_the_ceiling(self, db_session, caplog):
        """Failing to set the window must not discard the count we just took."""
        from app.copilot.guardrails import enforce_user_rate_limit

        class _NoExpire(_FakeRedis):
            def expire(self, key, seconds):
                raise RuntimeError("expire failed")

        user = _staff(db_session, "gr_gen_ttl_fail@example.com")
        fake = _NoExpire()
        with caplog.at_level("WARNING"):
            enforce_user_rate_limit(user, "alpha", 1, detail="a", redis=fake)
            with pytest.raises(HTTPException) as exc:
                enforce_user_rate_limit(user, "alpha", 1, detail="a", redis=fake)
        assert exc.value.status_code == 429
        assert any("rate_limit_ttl_failed" in r.message for r in caplog.records)

    def test_e2e_bypass(self, db_session, monkeypatch):
        from app.copilot.guardrails import enforce_user_rate_limit

        monkeypatch.setenv("EXPOSE_TOKENS_FOR_TESTING", "1")
        user = _staff(db_session, "gr_gen_bypass@example.com")
        enforce_user_rate_limit(user, "alpha", 0, detail="a", redis=_FakeRedis())


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


class TestUnmeteredEndpointsAreNowMetered:
    """BASE-CONFIG-37 — the four endpoints that had no ceiling at all.

    Each asserts the 429 arrives *before* the endpoint's own lookup, using
    ids that do not exist: if the limiter ran after the lookup these would
    be 404s instead.
    """

    @pytest.fixture(autouse=True)
    def _no_bypass(self, monkeypatch):
        monkeypatch.delenv("EXPOSE_TOKENS_FOR_TESTING", raising=False)

    def test_confirm_is_rate_limited(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "copilot_rate_limit_confirms_per_minute", 0)
        user = _staff(db_session, "gr_confirm@example.com")
        resp = client.post(
            f"/api/v1/copilot/confirm/{uuid.uuid4()}",
            json={"approved": True},
            headers=auth_headers(client, user),
        )
        assert resp.status_code == 429

    def test_message_rating_is_rate_limited(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "copilot_rate_limit_feedback_per_minute", 0)
        user = _staff(db_session, "gr_msgrating@example.com")
        resp = client.post(
            f"/api/v1/copilot/messages/{uuid.uuid4()}/rating",
            json={"value": "up"},
            headers=auth_headers(client, user),
        )
        assert resp.status_code == 429

    def test_session_rating_is_rate_limited(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "copilot_rate_limit_feedback_per_minute", 0)
        user = _staff(db_session, "gr_sessrating@example.com")
        resp = client.post(
            f"/api/v1/copilot/sessions/{uuid.uuid4()}/rating",
            json={"value": 5},
            headers=auth_headers(client, user),
        )
        assert resp.status_code == 429

    def test_profile_read_is_rate_limited(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "copilot_rate_limit_feedback_per_minute", 0)
        user = _staff(db_session, "gr_profread@example.com")
        resp = client.get(
            "/api/v1/copilot/profile", headers=auth_headers(client, user)
        )
        assert resp.status_code == 429

    def test_profile_delete_is_rate_limited(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "copilot_rate_limit_feedback_per_minute", 0)
        user = _staff(db_session, "gr_profdel@example.com")
        resp = client.delete(
            "/api/v1/copilot/profile", headers=auth_headers(client, user)
        )
        assert resp.status_code == 429

    def test_a_normal_session_is_not_throttled(self, client, db_session):
        """Defaults must be loose enough that ordinary use never sees a 429."""
        user = _staff(db_session, "gr_normal@example.com")
        headers = auth_headers(client, user)
        for _ in range(10):
            resp = client.get("/api/v1/copilot/profile", headers=headers)
            assert resp.status_code == 200, resp.text
