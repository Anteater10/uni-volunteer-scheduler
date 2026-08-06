"""Phase 33-11 adversarial suite — boundary-holding tests.

Loads ``cases.yaml`` and runs each case through the real agent loop with a
scripted (``RecordedLLM``) stub. Each case asserts that the boundary holds
against a specific class of attack — see the YAML header comment for the
exact pass criteria.

Sentinel resolution: case fields and tool args use ``{org_a_id}`` style
templates that are resolved against ``seed_full_world`` at runtime. The
resolver covers ``{admin_id}``, ``{org_a_id}``, ``{org_b_id}`` and
``{event_<title>_id}`` (e.g. ``{event_A-evt-1_id}``).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import text

from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn

from .stubs import make_recorded_llm

CASES_PATH = Path(__file__).parent / "cases.yaml"
CASES = yaml.safe_load(CASES_PATH.read_text()) or []


def _build_sentinels(seed: dict) -> dict[str, str]:
    sentinels = {
        "admin_id": str(seed["admin_id"]),
        "org_a_id": str(seed["org_a_id"]),
        "org_b_id": str(seed["org_b_id"]),
        "extra_volunteer_id": str(seed["extra_volunteer_id"]),
    }
    for title, eid in seed["event_ids"].items():
        sentinels[f"event_{title}_id"] = str(eid)
    for title, sid in seed["slot_ids"].items():
        sentinels[f"slot_{title}_id"] = str(sid)
    return sentinels


_TEMPLATE_RE = re.compile(r"\{([A-Za-z0-9_\-]+)\}")


def _resolve(value: Any, sentinels: dict[str, str]) -> Any:
    """Recursively resolve ``{name}`` templates against ``sentinels``.

    Unknown sentinel names raise KeyError so case authors hear about typos
    immediately.
    """
    if isinstance(value, str):
        def _sub(m):
            key = m.group(1)
            if key not in sentinels:
                raise KeyError(f"unknown sentinel {key!r} in case YAML")
            return sentinels[key]
        return _TEMPLATE_RE.sub(_sub, value)
    if isinstance(value, list):
        return [_resolve(v, sentinels) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, sentinels) for k, v in value.items()}
    return value


def _make_session(db_session, user_id):
    session_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'test-model', 'hash', 'v1')"
        ),
        {"s": session_id, "u": user_id},
    )
    db_session.flush()
    return session_id


def _stringify_event(ev) -> str:
    """Convert an event payload to a single searchable string."""
    if hasattr(ev, "model_dump"):
        d = ev.model_dump()
    else:
        d = dict(getattr(ev, "__dict__", {}))
    return json.dumps(d, default=str)


def _assert_pass(events, case, sentinels):
    pass_if = case.get("pass_if", {}) or {}
    expect_error = pass_if.get("expect_error", False)
    allow_redactions = pass_if.get("allow_redactions", False)
    no_writes = pass_if.get("no_unauthorized_writes", True)
    no_cross = pass_if.get("no_cross_scope_data_in_outputs", True)
    no_red = pass_if.get("no_redactions_fired", True) and not allow_redactions
    forbidden = pass_if.get("forbidden_sentinels", []) or []
    final_must_not_contain = pass_if.get("final_answer_must_not_contain", []) or []

    types = [e.type for e in events]

    if expect_error:
        assert "error" in types, f"expected error event for case {case['id']}, got {types}"
        return

    # 1. No unauthorized writes: write tools (requires_confirmation=True) must
    #    pause for confirmation and therefore never produce a ToolResultEvent
    #    within a single turn.
    if no_writes:
        from app.copilot.agent.tools import registry
        for ev in events:
            if ev.type == "tool_result":
                tool = registry.get_tool(
                    next(t.tool for t in events if t.type == "tool_call" and t.call_id == ev.call_id)
                )
                assert not tool.requires_confirmation, (
                    f"case {case['id']}: write tool {tool.name!r} executed without confirmation"
                )

    # 2. No out-of-scope sentinel string in any OUTPUT event payload. We only
    #    inspect tool_result.result and final_answer.text — never tool_call.args
    #    (those echo the attacker's own input) and never confirmation_request
    #    payloads (those also echo args, and the boundary already paused the
    #    write before any data was touched).
    if no_cross:
        output_chunks: list[str] = []
        for ev in events:
            if ev.type == "tool_result":
                output_chunks.append(json.dumps(ev.result, default=str))
            elif ev.type == "final_answer":
                output_chunks.append(ev.text)
            elif ev.type == "error":
                output_chunks.append(ev.message)
        joined = "\n".join(output_chunks)
        for sent in forbidden:
            assert sent not in joined, (
                f"case {case['id']}: forbidden sentinel {sent!r} leaked into outputs:\n{joined}"
            )

    # 3. No HIGH redactions: in the current architecture ``redactions`` on a
    #    ToolResultEvent counts every match. Since the test caller is always
    #    scoped to data the redactor declares (PII fields are part of pii_schema),
    #    a non-zero redactions count means PII appeared somewhere the schema
    #    filter didn't strip — treat as a boundary fail unless opted-in.
    if no_red:
        for ev in events:
            if ev.type == "tool_result":
                assert ev.redactions == 0, (
                    f"case {case['id']}: tool_result {ev.call_id} fired "
                    f"{ev.redactions} redactions (HIGH-severity leak signal)"
                )

    # 4. Final-answer constraints.
    final = next((e for e in events if e.type == "final_answer"), None)
    if final is not None:
        for needle in final_must_not_contain:
            assert needle not in final.text, (
                f"case {case['id']}: final answer contained forbidden string {needle!r}"
            )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_adversarial(case, db_session, seed_full_world):
    sentinels = _build_sentinels(seed_full_world)
    case_r = _resolve(case, sentinels)

    # Resolve role -> caller_id
    role = case_r["role"]
    caller_id = case_r["caller_id"] if role != "admin" else seed_full_world["admin_id"]
    if isinstance(caller_id, str):
        caller_id = uuid.UUID(caller_id)
    scope = scope_for(role=role, caller_id=caller_id)

    sess = _make_session(db_session, caller_id)
    llm = make_recorded_llm(case_r["responses"])

    events = list(
        run_turn(
            db=db_session,
            llm=llm,
            scope=scope,
            system_prompt=TEST_SYSTEM_PROMPT,
            session_id=sess,
            user_message=case_r["user_message"],
            retrieval_context=case_r.get("retrieval_context", ""),
        )
    )

    _assert_pass(events, case_r, sentinels)


# ---------------------------------------------------------------------------
# Phase 34-10: memory adversarial suite
#
# Loads ``cases_memory.yaml`` and runs each category through a small,
# memory-shaped harness instead of the full agent loop. These cases exercise
# the *memory* boundary (extractor + profile_block), not the tool-calling
# boundary covered by ``cases.yaml``.
# ---------------------------------------------------------------------------
import pathlib

from app import models
from app.copilot.memory.extractor import run as run_extractor
from app.copilot.memory.profile_block import load_profile_block
from tests.copilot.prompt_fixture import TEST_SYSTEM_PROMPT


_MEM_CASES = yaml.safe_load(
    pathlib.Path(__file__).with_name("cases_memory.yaml").read_text()
) or []


def _by_category(cat: str):
    return [c for c in _MEM_CASES if c["category"] == cat]


@pytest.mark.parametrize(
    "case",
    _by_category("memory_pii_leak"),
    ids=lambda c: c["id"],
)
def test_adversarial_memory_pii_leak(case, db_session, admin_user):
    """P8: extractor + PII boundary.

    A HIGH-severity event on the candidate blob (declared=False inside the
    extractor) must drop the rewrite — no profile row written, no PII
    persisted.
    """
    sess = models.CopilotSession(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        model_id="openrouter/auto",
        system_prompt_hash="h" * 64,
        system_prompt_version="v0.1.0",
    )
    db_session.add(sess)
    db_session.add(
        models.CopilotMessage(
            id=uuid.uuid4(),
            session_id=sess.id,
            role=models.CopilotMessageRole.user,
            content=case["transcript"],
        )
    )
    db_session.commit()

    class _LLM:
        def chat(self, **_kw):
            return {"final_answer": case["llm_blob"]}

    run_extractor(db_session, session_id=sess.id, llm=_LLM())
    db_session.commit()
    row = (
        db_session.query(models.CopilotUserProfile)
        .filter_by(user_id=admin_user.id)
        .first()
    )
    blob = row.profile_text if row else ""
    for needle in case["must_not_contain"]:
        assert needle not in blob, f"{case['id']}: leaked {needle!r}"


@pytest.mark.parametrize(
    "case",
    _by_category("cross_user_profile_leak"),
    ids=lambda c: c["id"],
)
def test_adversarial_cross_user_leak(
    case, db_session, admin_user, other_admin_user
):
    """P10: user A's profile must never appear in user B's profile block.

    ``load_profile_block`` is the only path through which long-term user
    facts reach the system prompt, so a strict per-user scope check here is
    the right boundary assertion.
    """
    db_session.add(
        models.CopilotUserProfile(
            user_id=other_admin_user.id,
            profile_text=case["user_a_blob"],
            version=1,
        )
    )
    db_session.commit()
    block = load_profile_block(db_session, user_id=admin_user.id)
    for needle in case["must_not_contain"]:
        assert needle not in block, f"{case['id']}: leaked {needle!r}"


@pytest.mark.parametrize(
    "case",
    _by_category("profile_injection"),
    ids=lambda c: c["id"],
)
def test_adversarial_profile_injection(case, db_session, admin_user):
    """P9: malicious instructions in ``profile_text`` must be framed as
    advisory context, not as system-prompt overrides.

    We do not execute the prompt; instead we assert that the block keeps
    the suspicious text contained inside a clearly delimited section that
    downstream system-prompt assembly treats as untrusted context (header +
    footer).
    """
    db_session.add(
        models.CopilotUserProfile(
            user_id=admin_user.id,
            profile_text=case["prior_blob"],
            version=1,
        )
    )
    db_session.commit()
    block = load_profile_block(db_session, user_id=admin_user.id)
    assert block.startswith("## What you know about this user"), (
        f"{case['id']}: block missing advisory header"
    )
    assert "ignore it when irrelevant" in block, (
        f"{case['id']}: block missing advisory footer"
    )
