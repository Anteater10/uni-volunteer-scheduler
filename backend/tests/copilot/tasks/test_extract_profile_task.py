"""Phase 34-06 Task 20: extract_profile_facts Celery task tests.

Covers the wiring between the Celery task and
:mod:`app.copilot.memory.extractor`:

- Happy path: a fresh session runs the extractor once and stamps
  ``profile_extracted_at``.
- Idempotency: invoking the task twice on the same session is a no-op
  on the second call — no DB write, no LLM call.
- Retry: the LLM raises on the first attempt and succeeds on the
  second; we drive the retry path explicitly so the test doesn't depend
  on Celery's eager-retry semantics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app import models
from app.config import settings
from app.tasks import extract_profile as task_mod
from tests.fixtures.helpers import make_user


@pytest.fixture(autouse=True)
def _enable_profile_extraction(monkeypatch):
    """K31: extraction now ships off, so these tests must turn it on.

    They are the tests *of* extraction — asserting the machinery works when
    someone asks for it. The default being off is asserted separately, in
    tests/copilot/test_profile_extraction_is_off.py, so flipping it here
    does not hide the shipped state.
    """
    monkeypatch.setattr(settings, "copilot_profile_extraction_enabled", True)


class _StubLLM:
    def __init__(self, text="Stable profile blob."):
        self.text = text
        self.calls = 0

    def chat(self, *, messages, tools=None):
        self.calls += 1
        return {"final_answer": self.text}


class _RaisingThenStubLLM:
    """LLM that raises once, then returns a clean response on retry."""

    def __init__(self, text="Stable profile blob."):
        self.text = text
        self.calls = 0

    def chat(self, *, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient LLM failure")
        return {"final_answer": self.text}


@pytest.fixture
def _patch_session_local(db_session, monkeypatch):
    """Force the Celery task to use the pytest db_session.

    The task constructs its own SessionLocal() so writes happen in a
    separate connection by default; monkeypatching the symbol on the
    task module hands back the test session and stubs out close() so
    the fixture's transactional cleanup still owns teardown.
    """
    monkeypatch.setattr(task_mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)


def _mk_session(db_session, user, *, profile_extracted_at=None):
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
        last_message_at=datetime.now(timezone.utc),
        profile_extracted_at=profile_extracted_at,
    )
    db_session.add(sess)
    db_session.flush()
    return sess


def _add_msg(db_session, session, role, content):
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=session.id,
            role=models.CopilotMessageRole(role),
            content=content,
        )
    )
    db_session.flush()


def test_task_happy_path_writes_profile_and_stamps_session(
    db_session, _patch_session_local, monkeypatch
):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _mk_session(db_session, user)
    _add_msg(db_session, sess, "user", "I coordinate Tuesday outreach.")
    db_session.commit()

    llm = _StubLLM("Admin who coordinates Tuesday outreach.")
    monkeypatch.setattr(task_mod, "_build_llm", lambda: llm)

    task_mod.extract_profile_facts(str(sess.id))

    db_session.expire_all()
    refreshed = db_session.get(models.CopilotSession, sess.id)
    assert refreshed.profile_extracted_at is not None
    profile = db_session.get(models.CopilotUserProfile, user.id)
    assert profile is not None
    assert profile.version == 1
    assert llm.calls == 1


def test_task_is_idempotent_when_profile_already_extracted(
    db_session, _patch_session_local, monkeypatch
):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    already = datetime.now(timezone.utc)
    sess = _mk_session(db_session, user, profile_extracted_at=already)
    _add_msg(db_session, sess, "user", "anything")
    db_session.commit()

    llm = _StubLLM()
    monkeypatch.setattr(task_mod, "_build_llm", lambda: llm)

    task_mod.extract_profile_facts(str(sess.id))

    assert llm.calls == 0  # short-circuited; no LLM call
    db_session.expire_all()
    # No profile row written, marker unchanged.
    assert db_session.get(models.CopilotUserProfile, user.id) is None
    refreshed = db_session.get(models.CopilotSession, sess.id)
    assert refreshed.profile_extracted_at == already


def test_task_retry_succeeds_on_second_attempt(
    db_session, _patch_session_local, monkeypatch
):
    """First LLM call raises; we drive the task a second time (the
    equivalent of Celery's autoretry rescheduling) and assert the final
    state is a successful write.

    We don't rely on Celery's eager-mode autoretry here because eager
    mode runs autoretries synchronously without honouring backoff, and
    the test we care about is the *semantics*: the task is safe to
    re-invoke after a transient LLM failure and converges to a written
    profile.
    """
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _mk_session(db_session, user)
    _add_msg(db_session, sess, "user", "I run Wednesday outreach.")
    db_session.commit()

    llm = _RaisingThenStubLLM("Admin who runs Wednesday outreach.")
    monkeypatch.setattr(task_mod, "_build_llm", lambda: llm)

    # First attempt raises — extractor wrapper rolls back and re-raises.
    with pytest.raises(RuntimeError):
        task_mod.extract_profile_facts.run(str(sess.id))

    db_session.expire_all()
    sess_after_fail = db_session.get(models.CopilotSession, sess.id)
    assert sess_after_fail.profile_extracted_at is None
    assert db_session.get(models.CopilotUserProfile, user.id) is None

    # Second attempt succeeds.
    task_mod.extract_profile_facts.run(str(sess.id))

    db_session.expire_all()
    sess_after_ok = db_session.get(models.CopilotSession, sess.id)
    assert sess_after_ok.profile_extracted_at is not None
    profile = db_session.get(models.CopilotUserProfile, user.id)
    assert profile is not None
    assert profile.version == 1
    assert llm.calls == 2
