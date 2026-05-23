"""Phase 34-06 Task 20: extractor unit tests.

Covers :mod:`app.copilot.memory.extractor`:

- :func:`build_prompt` renders the prior profile + transcript into the
  spec §5 template, including the ``NONE`` placeholder when the prior
  blob is empty.
- :func:`run` happy path writes the candidate blob and bumps ``version``.
- :func:`run` drops the rewrite when the redactor produces a
  HIGH-severity event (PII leaked into the candidate).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app import models
from app.copilot.memory.extractor import build_prompt, run
from tests.fixtures.helpers import make_user


class _StubLLM:
    """LLM stub matching the ``.chat(messages, tools=None)`` contract."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[list[dict]] = []

    def chat(self, *, messages, tools=None):
        self.calls.append(messages)
        return {"final_answer": self.response_text}


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
    return sess


def _add_msg(db_session, session, role, content):
    msg = models.CopilotMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role=models.CopilotMessageRole(role),
        content=content,
    )
    db_session.add(msg)
    db_session.flush()
    return msg


# ----- build_prompt -------------------------------------------------------


def test_build_prompt_empty_prior_uses_none_placeholder():
    msgs = build_prompt("", [{"role": "user", "content": "hi"}])
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    body = msgs[0]["content"]
    assert "Current profile:\nNONE" in body
    assert "user: hi" in body
    assert "under 500 words" in body
    assert "Do not invent facts" in body


def test_build_prompt_populated_prior_inlines_blob():
    prior = "Admin who runs Tuesday outreach sessions."
    transcript = [
        {"role": "user", "content": "schedule next week"},
        {"role": "assistant", "content": "sure, draft below"},
    ]
    msgs = build_prompt(prior, transcript)
    body = msgs[0]["content"]
    assert f"Current profile:\n{prior}" in body
    assert "user: schedule next week" in body
    assert "assistant: sure, draft below" in body


# ----- run: happy path ----------------------------------------------------


def test_run_happy_path_creates_profile_and_bumps_version(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _mk_session(db_session, user)
    _add_msg(db_session, sess, "user", "I run the Tuesday clinic")
    _add_msg(db_session, sess, "assistant", "Got it — scheduling Tuesdays.")
    db_session.commit()

    llm = _StubLLM(
        "Admin user who runs the Tuesday outreach clinic. "
        "Prefers week-based scheduling."
    )

    blob, events = run(db_session, sess.id, llm)
    db_session.commit()

    assert blob is not None
    assert "Tuesday" in blob
    assert events == []
    assert len(llm.calls) == 1
    profile = db_session.get(models.CopilotUserProfile, user.id)
    assert profile is not None
    assert profile.version == 1
    assert profile.profile_text == blob


def test_run_existing_profile_bumps_version(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.add(
        models.CopilotUserProfile(
            user_id=user.id, profile_text="old blob", version=3
        )
    )
    db_session.commit()
    sess = _mk_session(db_session, user)
    _add_msg(db_session, sess, "user", "new info: I also coordinate carpools")
    db_session.commit()

    llm = _StubLLM("Updated blob with carpool coordination duty.")
    blob, events = run(db_session, sess.id, llm)
    db_session.commit()

    assert blob is not None
    assert events == []
    profile = db_session.get(models.CopilotUserProfile, user.id)
    assert profile.version == 4
    assert profile.profile_text == blob


# ----- run: HIGH-severity PII drop ----------------------------------------


def test_run_drops_candidate_with_high_severity_pii(db_session):
    user = make_user(db_session, role=models.UserRole.admin)
    db_session.commit()
    sess = _mk_session(db_session, user)
    _add_msg(db_session, sess, "user", "hello")
    db_session.commit()

    llm = _StubLLM(
        "Admin user. Reach them at phone (805) 555-1234 in case of "
        "scheduling conflicts."
    )

    blob, events = run(db_session, sess.id, llm)
    db_session.commit()

    assert blob is None
    assert any(e.severity == "HIGH" and e.kind == "phone" for e in events)
    # No profile row written.
    assert db_session.get(models.CopilotUserProfile, user.id) is None
