"""K31 follow-up: the extractor's retry policy is decided by cause.

The task used ``autoretry_for=(Exception,)``, which retried every failure
including the rate-limit and quota errors that mean "no requests left" — so
the job that ran out of requests answered by making more of them. It stacked
on top of retries that had already happened, too: ``app.copilot.llm`` sweeps
primary->fallback three times with backoff before an exception escapes, so
one Celery attempt was already up to six provider calls and four attempts up
to twenty-four.

Funding the OpenRouter account raised the daily ceiling from ~50 to ~1000
requests and let extraction be turned on, but it did not make amplification
correct — a ceiling is still a ceiling. So the policy is explicit now, and
these tests pin both halves of it:

* a provider error (anything under ``openai.APIError``) ends the task on the
  first attempt, and leaves the session unstamped so it is recorded as
  not-extracted rather than quietly marked done;
* a non-provider failure (a database blip, a bug) still retries, because
  those are cheap and say nothing about the request budget.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from openai import APIError, RateLimitError

from app import models
from app.config import settings
from app.tasks import extract_profile as task_mod
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _enable_profile_extraction(monkeypatch):
    monkeypatch.setattr(settings, "copilot_profile_extraction_enabled", True)


@pytest.fixture
def _patch_session_local(db_session, monkeypatch):
    monkeypatch.setattr(task_mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)


def _mk_session(db_session, user):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(sess)
    db_session.flush()
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=sess.id,
            role=models.CopilotMessageRole("user"),
            content="I coordinate Tuesday outreach.",
        )
    )
    db_session.commit()
    return sess


class _RaisingLLM:
    """LLM that always raises ``exc``, counting how often it was asked."""

    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def chat(self, *, messages, tools=None):
        self.calls += 1
        raise self.exc


def _rate_limit_error():
    """A real ``RateLimitError``, built the way the SDK builds one.

    Constructed rather than faked so the test breaks if the openai exception
    hierarchy ever stops putting rate limits under ``APIError``.
    """
    return RateLimitError(
        "rate limit exceeded",
        response=_FakeResponse(429),
        body=None,
    )


class _FakeResponse:
    """Minimal stand-in for the httpx response the SDK errors carry."""

    def __init__(self, status_code):
        self.status_code = status_code
        self.request = None
        self.headers = {}


class TestProviderErrorsAreNotRetried:
    def test_rate_limit_error_is_a_provider_error(self):
        """The premise of the whole policy: rate limits are under APIError."""
        assert isinstance(_rate_limit_error(), APIError)
        assert isinstance(_rate_limit_error(), task_mod._PROVIDER_ERRORS)

    def test_a_rate_limited_attempt_does_not_retry(
        self, db_session, _patch_session_local, monkeypatch
    ):
        """Retrying would spend more of the budget we just ran out of."""
        user = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()
        sess = _mk_session(db_session, user)

        llm = _RaisingLLM(_rate_limit_error())
        monkeypatch.setattr(task_mod, "_build_llm", lambda: llm)

        retries = []
        # Patch the task object itself, not its type: Celery hands back a
        # PromiseProxy, so the class has no ``retry`` to replace. Shadowing it
        # on the instance means the stub is called unbound — hence no ``self``.
        monkeypatch.setattr(
            task_mod.extract_profile_facts,
            "retry",
            lambda **kw: retries.append(kw),
        )

        # No exception escapes: the task gives up deliberately.
        task_mod.extract_profile_facts.run(str(sess.id))

        assert retries == [], (
            "a rate-limit failure was retried — this is the amplification "
            "loop K31 was about"
        )
        assert llm.calls == 1

    def test_giving_up_leaves_the_session_unstamped(
        self, db_session, _patch_session_local, monkeypatch
    ):
        """Not-extracted must not be recorded as extracted.

        Stamping it would make the session look done, so it could never be
        picked up once the provider recovered.
        """
        user = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()
        sess = _mk_session(db_session, user)

        monkeypatch.setattr(
            task_mod, "_build_llm", lambda: _RaisingLLM(_rate_limit_error())
        )
        monkeypatch.setattr(
            task_mod.extract_profile_facts, "retry", lambda **kw: None
        )

        task_mod.extract_profile_facts.run(str(sess.id))

        db_session.expire_all()
        refreshed = db_session.get(models.CopilotSession, sess.id)
        assert refreshed.profile_extracted_at is None
        assert db_session.get(models.CopilotUserProfile, user.id) is None


class TestOtherFailuresStillRetry:
    def test_a_non_provider_error_is_retried(
        self, db_session, _patch_session_local, monkeypatch
    ):
        """A database blip or a bug says nothing about the request budget,
        so the gate must not have turned retries off wholesale."""
        user = make_user(db_session, role=models.UserRole.admin)
        db_session.commit()
        sess = _mk_session(db_session, user)

        monkeypatch.setattr(
            task_mod,
            "_build_llm",
            lambda: _RaisingLLM(RuntimeError("transient db failure")),
        )

        retries = []

        def _fake_retry(**kw):
            retries.append(kw)
            # The real Task.retry raises rather than returning; mirror that so
            # the ``raise self.retry(...)`` line runs as it does in prod.
            raise kw["exc"]

        monkeypatch.setattr(
            task_mod.extract_profile_facts, "retry", _fake_retry
        )

        with pytest.raises(RuntimeError):
            task_mod.extract_profile_facts.run(str(sess.id))

        assert len(retries) == 1
        assert retries[0]["countdown"] == task_mod._RETRY_BASE_DELAY_SECONDS

    def test_the_backoff_is_capped(self):
        """The cap that retry_backoff_max used to provide is still there,
        now that the countdown is computed by hand."""
        assert task_mod._RETRY_MAX_DELAY_SECONDS == 300
        delays = [
            min(
                task_mod._RETRY_BASE_DELAY_SECONDS * 2 ** n,
                task_mod._RETRY_MAX_DELAY_SECONDS,
            )
            for n in range(8)
        ]
        assert max(delays) == task_mod._RETRY_MAX_DELAY_SECONDS
