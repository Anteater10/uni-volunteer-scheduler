"""BASE-SEC-18 — the "ask, don't guess" precheck never ran in production.

Every write tool declares a ``precheck`` whose job is to refuse when a value
the user never stated would otherwise be invented. ``_ask.py`` opens with the
case that taught us the rule: a tool filled a missing start time with 09:00,
the event looked correct in every visible respect, and would have gone on
looking correct until somebody stood in an empty classroom at nine.

The guard was real, tested, and unreachable. ``precheck`` was only ever
called from ``tools/base.invoke()`` — and the live agent loop does not use
``invoke``; it uses the ``_begin`` / ``_complete`` split. So on the one path
that matters, the question was never asked and the confirmation card showed
the invented value as though the user had supplied it.

These tests exercise the loop, not ``invoke``, precisely because that is
where the coverage was missing.
"""
from __future__ import annotations

import itertools
import json

import pytest

from app import models
from app.config import settings
from app.copilot import router as copilot_router
from app.copilot.agent import confirmation as cf
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.fixtures.helpers import auth_headers, make_user

_seq = itertools.count()


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_agent_loop_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0))
    cf._reset_for_tests()
    yield
    cf._reset_for_tests()
    registry._reset_for_tests()


@pytest.fixture
def objecting_tool():
    """A write tool whose precheck always refuses."""
    ran = {"count": 0}

    def handler(db, scope, args):
        ran["count"] += 1
        return {"ok": True}

    def precheck(db, scope, args):
        return {
            "needs_answers": ["what time does it start"],
            "question": "I can't do this yet.",
        }

    registry.register(
        Tool(
            name="fake_needs_answers",
            description="Do a thing.",
            json_schema={"type": "object", "properties": {}},
            allowed_roles=["admin"],
            requires_confirmation=True,
            pii_schema=["ok"],
            handler=handler,
            precheck=precheck,
        )
    )
    yield ran
    registry._reset_for_tests()


class _ScriptedLLM:
    """Calls the tool once, then narrates whatever came back."""

    def __init__(self):
        self.usage = {"prompt_tokens": 5, "completion_tokens": 5, "model_id": "m"}
        self.seen = []

    def chat(self, *, messages, tools=None):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        if tool_msgs:
            self.seen.append(tool_msgs[-1]["content"])
            return {"final_answer": "What time does it start?"}
        return {"tool_calls": [{"name": "fake_needs_answers", "args": {}}]}


def _admin(db_session):
    return make_user(
        db_session,
        email=f"precheck_admin_{next(_seq)}@example.com",
        role=models.UserRole.admin,
    )


def _events(client, db_session, monkeypatch):
    llm = _ScriptedLLM()
    monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: llm)
    admin = _admin(db_session)
    sid = client.post(
        "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
    ).json()["id"]
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "make the event"},
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode()
    out = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        kind = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if kind:
            out.append((kind, json.loads(data) if data else None))
    return out, llm


def test_precheck_objection_stops_the_call(
    client, db_session, monkeypatch, objecting_tool
):
    events, _ = _events(client, db_session, monkeypatch)
    kinds = [k for k, _ in events]

    # No card, because there is nothing safe to put on one yet.
    assert "confirmation_request" not in kinds
    # And the handler certainly did not run.
    assert objecting_tool["count"] == 0


def test_precheck_objection_is_handed_back_to_the_model(
    client, db_session, monkeypatch, objecting_tool
):
    """The refusal is a tool result, not a dead end — the model relays it."""
    events, llm = _events(client, db_session, monkeypatch)

    results = [p for k, p in events if k == "tool_result"]
    assert results, [k for k, _ in events]
    assert "needs_answers" in results[0]["result"]
    assert llm.seen and "needs_answers" in llm.seen[0]


def test_precheck_objection_nothing_is_parked(
    client, db_session, monkeypatch, objecting_tool
):
    events, _ = _events(client, db_session, monkeypatch)
    for kind, payload in events:
        if kind == "tool_call":
            assert not cf.is_pending(payload["call_id"])
