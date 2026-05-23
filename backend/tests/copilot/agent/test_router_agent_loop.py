"""Phase 33-09 Task 38: chat endpoint streams ReAct-loop events when the
``copilot_agent_loop_enabled`` flag is on.

Mocks both retrieval (so no embed/hybrid hits the DB) and the structured
LLM (so no live OpenRouter calls). Asserts the SSE stream contains a
``tool_call`` -> ``tool_result`` -> ``final_answer`` -> ``done`` sequence.
"""
from __future__ import annotations

import re

import pytest

from app import models
from app.config import settings
from app.copilot import router as copilot_router_mod
from app.copilot.agent import confirmation as cf_mod
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_flags(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_agent_loop_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")


@pytest.fixture(autouse=True)
def _reset():
    registry._reset_for_tests()
    cf_mod._reset_for_tests()
    yield
    registry._reset_for_tests()
    cf_mod._reset_for_tests()


def _admin(db_session, email="agent_admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


class _StubLLM:
    def __init__(self, scripted):
        self._responses = list(scripted)

    def chat(self, *, messages, tools):
        return self._responses.pop(0)


def _stub_retrieval(monkeypatch):
    monkeypatch.setattr(
        copilot_router_mod,
        "_run_retrieval",
        lambda db, q: ([], 0, 0),
    )


def test_chat_endpoint_emits_tool_call_then_result_then_final_answer(
    client, db_session, monkeypatch
):
    admin = _admin(db_session)
    db_session.commit()

    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    assert rc.status_code == 201, rc.text
    sid = rc.json()["id"]

    fake = Tool(
        name="fake_read",
        description="",
        json_schema={"type": "object"},
        allowed_roles=["admin"],
        requires_confirmation=False,
        pii_schema=[],
        handler=lambda db, scope, args: {"rows": [1, 2, 3]},
    )
    registry.register(fake)

    llm = _StubLLM(
        [
            {"tool_calls": [{"name": "fake_read", "args": {"x": 1}}]},
            {"final_answer": "There are 3 rows."},
        ]
    )
    monkeypatch.setattr(copilot_router_mod, "_get_agent_llm", lambda: llm)
    _stub_retrieval(monkeypatch)

    body_bytes = bytearray()
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "how many rows?"},
    ) as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_bytes():
            body_bytes.extend(chunk)

    text = body_bytes.decode("utf-8")

    # Parse SSE event names in order.
    event_names = re.findall(r"event: (\S+)", text)
    # meta arrives first per Phase 32 contract, then tool_call/result/final
    assert event_names[0] == "meta"
    assert "tool_call" in event_names
    assert "tool_result" in event_names
    assert "final_answer" in event_names
    assert event_names[-1] == "done"
    # tool_call precedes tool_result precedes final_answer
    assert event_names.index("tool_call") < event_names.index("tool_result")
    assert event_names.index("tool_result") < event_names.index("final_answer")
    # final answer text is on the wire
    assert "There are 3 rows." in text


def test_chat_endpoint_emits_confirmation_request_and_pauses(
    client, db_session, monkeypatch
):
    admin = _admin(db_session, email="agent_admin_c@example.com")
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    write_tool = Tool(
        name="fake_write_agent",
        description="",
        json_schema={"type": "object"},
        allowed_roles=["admin"],
        requires_confirmation=True,
        pii_schema=[],
        handler=lambda db, scope, args: {"sent": True},
    )
    registry.register(write_tool)

    llm = _StubLLM(
        [
            {
                "tool_calls": [
                    {"name": "fake_write_agent", "args": {"to": "x@example.com"}}
                ]
            },
        ]
    )
    monkeypatch.setattr(copilot_router_mod, "_get_agent_llm", lambda: llm)
    _stub_retrieval(monkeypatch)

    body_bytes = bytearray()
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "please email them"},
    ) as resp:
        for chunk in resp.iter_bytes():
            body_bytes.extend(chunk)

    text = body_bytes.decode("utf-8")
    event_names = re.findall(r"event: (\S+)", text)
    assert "tool_call" in event_names
    assert "confirmation_request" in event_names
    # No final_answer because the loop paused
    assert "final_answer" not in event_names


def test_chat_endpoint_unchanged_when_flag_off(client, db_session, monkeypatch):
    """Regression: with the flag off the Phase 30 token stream is preserved."""
    monkeypatch.setattr(settings, "copilot_agent_loop_enabled", False)
    admin = _admin(db_session, email="agent_admin_off@example.com")
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    def fake_stream(**kwargs):
        yield "ok", {}
        yield "", {
            "model_id": "primary/test:free",
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "latency_ms": 1,
            "completion_text": "ok",
        }

    monkeypatch.setattr(copilot_router_mod.llm, "stream_completion", fake_stream)
    _stub_retrieval(monkeypatch)

    body_bytes = bytearray()
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "hi"},
    ) as resp:
        for chunk in resp.iter_bytes():
            body_bytes.extend(chunk)

    text = body_bytes.decode("utf-8")
    assert "event: token" in text
    assert "event: tool_call" not in text
