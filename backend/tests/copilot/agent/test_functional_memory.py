"""Phase 34 sub-phase 34-09 / Task 28: functional integration tests F1-F5.

The plan (docs/superpowers/plans/2026-05-23-phase-34-memory-multi-turn.md,
section 34-09) defines five scenarios spanning the within-session
summariser, the end-of-session extractor, and the profile-block
session-start retrieval path:

F1 — Two-turn session: the second turn's LLM call does NOT see a
     "## Conversation so far" synopsis (compression must not fire on a
     trivially short history).
F2 — Six-turn session: when compression DOES fire (small context
     window + long prior history), the resulting LLM call sees a
     synthetic synopsis system message. The agent loop is stateless
     between turns (it rebuilds ``[system, user]`` each ``run_turn``),
     so we exercise the compression seam by injecting a six-turn
     history via the same monkeypatch pattern used in
     ``test_loop_memory.test_run_turn_compresses_long_history_before_first_chat``.
F3 — End-of-session extractor populates a profile row; a fresh call to
     ``load_profile_block`` then returns the new blob (which is what
     the next session's system prompt will render).
F4 — A user-initiated profile wipe (``profile_text = ""``) makes
     subsequent ``load_profile_block`` calls return the empty string.
F5 — A leaky LLM that parrots a phone number back into the candidate
     blob is caught by the Phase 33 redactor (``declared=False`` =
     strict) and the profile row is NOT created.

All five tests use scripted LLM stubs — no network calls to OpenRouter.
"""
from __future__ import annotations

import uuid

import pytest

from app import models
from app.copilot.agent import loop as loop_mod
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.agent.tools import registry
from app.copilot.memory.extractor import run as run_extractor
from app.copilot.memory.profile_block import load_profile_block
from tests.fixtures.helpers import make_user
from tests.copilot.prompt_fixture import TEST_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db_session):
    """A single admin user, matching the pattern in
    ``tests/copilot/memory/test_profile_block.py``.
    """
    return make_user(db_session, role=models.UserRole.admin)


class _ScriptedLLM:
    """LLM stub that pops scripted responses and records every call."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def chat(self, *, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._scripted:
            return {"final_answer": "done"}
        return self._scripted.pop(0)


def _seed_session(db_session, user) -> models.CopilotSession:
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.flush()
    return sess


def _build_six_turn_history() -> list[dict]:
    """Six user/assistant pairs — enough that ``compress_if_needed``
    (working_set_pairs=2) rolls four older pairs into a synopsis.
    """
    msgs: list[dict] = [
        {"role": "system", "content": "system prompt " + ("x " * 200)}
    ]
    for i in range(6):
        msgs.append(
            {
                "role": "user",
                "content": f"user turn {i}: " + ("lorem ipsum " * 50),
            }
        )
        msgs.append(
            {
                "role": "assistant",
                "content": f"assistant turn {i}: " + ("dolor sit " * 50),
            }
        )
    return msgs


# ---------------------------------------------------------------------------
# F1 — within-session, short history, NO synopsis
# ---------------------------------------------------------------------------


def test_F1_two_turn_session_no_synopsis(db_session, admin_user):
    """Two short user turns should never trigger the summariser, so no
    LLM call should carry a synthetic ``"## Conversation so far"``
    system message.
    """
    sess = _seed_session(db_session, admin_user)
    scope = scope_for(role="admin", caller_id=admin_user.id)

    llm = _ScriptedLLM(
        [{"final_answer": "answer 1"}, {"final_answer": "answer 2"}]
    )

    list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            system_prompt=TEST_SYSTEM_PROMPT,
            session_id=str(sess.id),
            user_message="hi 1",
            retrieval_context="",
        )
    )
    list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            system_prompt=TEST_SYSTEM_PROMPT,
            session_id=str(sess.id),
            user_message="hi 2",
            retrieval_context="",
        )
    )

    # Every LLM call should have received a clean [system, user] pair
    # with no synthetic synopsis system message.
    for call in llm.calls:
        for m in call["messages"]:
            content = m.get("content") or ""
            assert "## Conversation so far" not in content, (
                "summariser must not fire on a short two-turn history"
            )


# ---------------------------------------------------------------------------
# F2 — long history triggers compression, working-set tail survives
# ---------------------------------------------------------------------------


def test_F2_six_turn_session_compresses(
    db_session, admin_user, monkeypatch
):
    """Inject a six-turn history at the compression seam, then run a
    turn with a small context window — the LLM should see a synthetic
    synopsis system message AND the working-set tail (turns 4, 5)
    verbatim. Older turns (0..3) must have been rolled into the
    synopsis.

    The agent loop is stateless between turns: it rebuilds
    ``[system, user]`` on entry, so a "natural" six-turn session
    cannot exercise compression. We therefore patch
    ``compress_if_needed`` to swap in a pre-built six-turn history
    and delegate to the real implementation — the same pattern used
    by the unit-level loop summariser test.
    """
    sess = _seed_session(db_session, admin_user)
    registry._reset_for_tests()
    scope = scope_for(role="admin", caller_id=admin_user.id)

    real_compress = loop_mod.compress_if_needed
    six_turn = _build_six_turn_history()

    def patched(messages, **kwargs):
        return real_compress(six_turn, **kwargs)

    monkeypatch.setattr(loop_mod, "compress_if_needed", patched)

    summariser_response = {"final_answer": "SYNOPSIS_TEXT"}
    main_response = {"final_answer": "final answer"}
    llm = _ScriptedLLM([summariser_response, main_response])

    list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            system_prompt=TEST_SYSTEM_PROMPT,
            session_id=str(sess.id),
            user_message="latest question",
            retrieval_context="",
            model="gpt-3.5-turbo",
            context_window=512,  # tiny -> force compression
        )
    )

    # Two chat calls: (1) summariser, (2) post-compression main turn.
    assert len(llm.calls) == 2

    # The summariser is invoked without tools=...
    assert llm.calls[0]["tools"] is None

    post_compress = llm.calls[1]["messages"]
    joined = "\n".join((m.get("content") or "") for m in post_compress)

    # Working-set tail (turns 4 and 5) survives verbatim.
    assert "user turn 4" in joined
    assert "assistant turn 4" in joined
    assert "user turn 5" in joined
    assert "assistant turn 5" in joined

    # Synthetic synopsis system message carries the summariser's text.
    synopsis_msgs = [
        m
        for m in post_compress
        if m.get("role") == "system"
        and "Conversation so far" in (m.get("content") or "")
    ]
    assert synopsis_msgs, "expected synthetic synopsis system message"
    assert "SYNOPSIS_TEXT" in synopsis_msgs[0]["content"]

    # Older turns rolled into the synopsis — no longer verbatim.
    assert "user turn 0" not in joined
    assert "user turn 3" not in joined


# ---------------------------------------------------------------------------
# F3 — close session, run extractor, profile block visible to next session
# ---------------------------------------------------------------------------


def test_F3_close_extract_then_next_session_sees_profile(
    db_session, admin_user
):
    """Seed a transcript with a stable fact, run the extractor, and
    confirm ``load_profile_block`` (the call the session-start path
    uses) returns the new blob wrapped in the standard fence.
    """
    sess = _seed_session(db_session, admin_user)
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=sess.id,
            role=models.CopilotMessageRole.user,
            content="I run Forces modules every Tuesday.",
        )
    )
    db_session.flush()

    class _LLM:
        def chat(self, *, messages, tools=None):
            return {"final_answer": "Runs Forces modules."}

    new_blob, events = run_extractor(db_session, session_id=sess.id, llm=_LLM())
    db_session.flush()

    assert new_blob == "Runs Forces modules."
    assert events == []

    block = load_profile_block(db_session, user_id=admin_user.id)
    assert "## What you know about this user" in block
    assert "Runs Forces modules." in block


# ---------------------------------------------------------------------------
# F4 — delete (blank) the profile, next session has no block
# ---------------------------------------------------------------------------


def test_F4_delete_profile_clears_block(db_session, admin_user):
    """A profile wipe (DELETE /profile rewrites the row to blank +
    bumps version) makes ``load_profile_block`` return the empty
    string, so the next session's system prompt omits the block.
    """
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin_user.id,
            profile_text="something stored from a prior session",
            version=1,
        )
    )
    db_session.flush()
    assert load_profile_block(db_session, user_id=admin_user.id) != ""

    row = (
        db_session.query(models.CopilotUserProfile)
        .filter_by(user_id=admin_user.id)
        .one()
    )
    row.profile_text = ""
    row.version = (row.version or 0) + 1
    db_session.flush()

    assert load_profile_block(db_session, user_id=admin_user.id) == ""


# ---------------------------------------------------------------------------
# F5 — leaky transcript: extractor drops candidate when PII leaks in
# ---------------------------------------------------------------------------


def test_F5_pii_in_transcript_does_not_leak_to_blob(
    db_session, admin_user
):
    """A leaky LLM that parrots a phone number back into the candidate
    blob is caught by the Phase 33 redactor (``declared=False`` =
    strict mode → any hit = HIGH-severity event). The extractor must
    drop the rewrite and not create a profile row.
    """
    sess = _seed_session(db_session, admin_user)
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=sess.id,
            role=models.CopilotMessageRole.user,
            content="my phone is 805-555-1234",
        )
    )
    db_session.flush()

    class _LeakyLLM:
        def chat(self, *, messages, tools=None):
            return {"final_answer": "User phone: 805-555-1234"}

    new_blob, events = run_extractor(
        db_session, session_id=sess.id, llm=_LeakyLLM()
    )
    db_session.flush()

    assert new_blob is None
    assert any(e.severity == "HIGH" for e in events), (
        "redactor must surface a HIGH-severity event for declared=False PII"
    )

    row = (
        db_session.query(models.CopilotUserProfile)
        .filter_by(user_id=admin_user.id)
        .first()
    )
    assert row is None, "no profile row should be created on PII-leak path"
