"""K25 / B0.2 / B0.3 — confirmation, from the card to the closing sentence.

Approve had never once worked.

``loop.py`` yielded ``ConfirmationRequestEvent`` and returned without ever
calling ``store_pending`` — that lived in ``tools/base.invoke()``, which the
live loop does not use; it uses the ``_begin``/``_complete`` split. So
``POST /confirm/{id}`` with ``approved=True`` looked up a ``call_id`` that had
never been stored, and 404'd. Every test that covered the approve path parked
the entry by hand first, which is why nothing caught it: the tests set up a
state the product could not reach.

Reject *appeared* to work, because it only stamps the audit row and never
consults the store at all.

And even once parked, the turn dead-ended. The loop returned, the stream
persisted an assistant message with empty content, and the drawer threw the
confirm response away — so the user clicked Confirm, the card vanished, and
nothing was ever said about whether 47 emails had gone out or nothing had
happened. The model never learned the outcome either, so it could not
continue.

B0.3: the store is Redis now. The old dict was process-local, so under more
than one worker the confirm request usually landed somewhere that had never
heard of the call.
"""
from __future__ import annotations

import itertools
import json
import uuid

import pytest
from sqlalchemy import text

from app import models
from app.config import settings
from app.copilot import router as copilot_router
from app.copilot.agent import confirmation as cf
from app.copilot.agent.tools import registry
from app.copilot.agent.tools.base import Tool
from tests.fixtures.helpers import auth_headers, make_user


_seq = itertools.count()


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_agent_loop_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(copilot_router, "_run_retrieval", lambda db, q: ([], 0, 0))
    cf._reset_for_tests()
    yield
    cf._reset_for_tests()


# ---------------------------------------------------------------------------
# A write tool that records whether it actually ran
# ---------------------------------------------------------------------------


@pytest.fixture
def write_tool():
    ran = {"count": 0, "args": None}

    def handler(db, scope, args):
        ran["count"] += 1
        ran["args"] = args
        return {"sent_count": 47, "failed_count": 0}

    registry.register(
        Tool(
            name="fake_send",
            description="Send a thing.",
            json_schema={
                "type": "object",
                "properties": {"template": {"type": "string"}},
                "required": ["template"],
            },
            allowed_roles=["admin"],
            requires_confirmation=True,
            pii_schema=["sent_count", "failed_count"],
            handler=handler,
        )
    )
    yield ran
    registry._reset_for_tests()


class _ScriptedLLM:
    """Asks for the write tool, then narrates once the result comes back."""

    def __init__(self, closing="I sent 47 reminders. None failed."):
        self.closing = closing
        self.calls = []
        self.usage = {"prompt_tokens": 5, "completion_tokens": 5, "model_id": "m"}

    def chat(self, *, messages, tools=None):
        self.calls.append(messages)
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if has_tool_result:
            return {"final_answer": self.closing}
        return {
            "tool_calls": [
                {"name": "fake_send", "args": {"template": "reminder"}}
            ]
        }


def _admin(db_session):
    return make_user(
        db_session,
        email=f"confirm_admin_{next(_seq)}@example.com",
        role=models.UserRole.admin,
    )


def _open(client, db_session, monkeypatch, llm=None):
    llm = llm or _ScriptedLLM()
    monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: llm)
    admin = _admin(db_session)
    sid = client.post(
        "/api/v1/copilot/sessions", headers=auth_headers(client, admin)
    ).json()["id"]
    return admin, sid, llm


def _ask(client, admin, sid, text="remind everyone"):
    """Run one turn and return the parsed SSE events."""
    events = []
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": text},
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode()
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
            events.append((kind, json.loads(data) if data else None))
    return events


def _confirmation_id(events):
    for kind, payload in events:
        if kind == "confirmation_request":
            return payload["call_id"]
    raise AssertionError(f"no confirmation_request in {[k for k, _ in events]}")


# ---------------------------------------------------------------------------
# The loop parks the call (K25a)
# ---------------------------------------------------------------------------


class TestTheCallIsActuallyParked:
    def test_reaching_a_write_tool_stores_a_pending_entry(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        events = _ask(client, admin, sid)
        call_id = _confirmation_id(events)
        # This is the assertion the whole defect reduces to.
        assert cf.is_pending(call_id)

    def test_the_parked_entry_carries_what_the_tool_needs(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        p = cf.peek(call_id)
        assert p.tool_name == "fake_send"
        assert p.args == {"template": "reminder"}
        assert p.session_id == sid

    def test_the_tool_has_not_run_yet(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        _ask(client, admin, sid)
        assert write_tool["count"] == 0


# ---------------------------------------------------------------------------
# Approve works (K25b)
# ---------------------------------------------------------------------------


class TestApprove:
    def test_approve_runs_the_tool_and_returns_200(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))

        resp = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        # Before the fix this was a 404: nothing had ever been stored.
        assert resp.status_code == 200, resp.text
        assert write_tool["count"] == 1
        assert write_tool["args"] == {"template": "reminder"}
        assert resp.json()["result"]["sent_count"] == 47

    def test_approve_answers_the_question_that_was_left_hanging(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))

        body = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        ).json()
        # The user clicked Confirm. Something has to be said back.
        assert body["message"]["content"] == "I sent 47 reminders. None failed."

    def test_the_closing_message_is_persisted_for_replay(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        db_session.expire_all()
        rows = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role
                == models.CopilotMessageRole.assistant,
            )
            .all()
        )
        assert [r.content for r in rows] == ["I sent 47 reminders. None failed."]

    def test_the_model_is_told_what_the_tool_returned(
        self, client, db_session, monkeypatch, write_tool
    ):
        """Otherwise it cannot say "I sent 47" — only "I did the thing"."""
        admin, sid, llm = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        narration_messages = llm.calls[-1]
        tool_msgs = [m for m in narration_messages if m.get("role") == "tool"]
        assert tool_msgs, "the tool result never reached the model"
        assert "47" in tool_msgs[0]["content"]

    def test_a_paused_turn_writes_no_empty_bubble(
        self, client, db_session, monkeypatch, write_tool
    ):
        """The pause used to persist content="" and replay a blank turn."""
        admin, sid, _ = _open(client, db_session, monkeypatch)
        _ask(client, admin, sid)
        db_session.expire_all()
        rows = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role
                == models.CopilotMessageRole.assistant,
            )
            .all()
        )
        assert rows == []

    def test_the_entry_is_consumed_so_approve_is_not_replayable(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        headers = auth_headers(client, admin)
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=headers,
            json={"approved": True},
        )
        second = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=headers,
            json={"approved": True},
        )
        assert second.status_code == 404
        # Double-sending 47 emails is the failure this prevents.
        assert write_tool["count"] == 1

    def test_the_audit_row_is_stamped_executed(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        db_session.expire_all()
        status = db_session.execute(
            text(
                "SELECT confirmation_status FROM copilot_tool_calls "
                "WHERE call_id = :c"
            ),
            {"c": call_id},
        ).scalar()
        assert status == "executed"


class TestNarrationIsBestEffort:
    def test_a_dead_model_does_not_undo_a_write_that_landed(
        self, client, db_session, monkeypatch, write_tool
    ):
        """The side effect already happened and is already audited.

        Failing the request here would tell the user nothing went out while
        47 emails were in flight — the worst of both readings.
        """
        admin, sid, llm = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))

        class _Dead:
            usage = {}

            def chat(self, *, messages, tools=None):
                raise RuntimeError("upstream is down")

        monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: _Dead())
        resp = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["sent_count"] == 47
        assert "message" not in resp.json()
        assert write_tool["count"] == 1

    def test_an_empty_narration_is_not_persisted_as_a_blank_bubble(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))

        class _Mute:
            usage = {}

            def chat(self, *, messages, tools=None):
                return {}

        monkeypatch.setattr(copilot_router, "_get_agent_llm", lambda: _Mute())
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        db_session.expire_all()
        rows = (
            db_session.query(models.CopilotMessage)
            .filter(
                models.CopilotMessage.session_id == uuid.UUID(sid),
                models.CopilotMessage.role
                == models.CopilotMessageRole.assistant,
            )
            .all()
        )
        assert rows == []


# ---------------------------------------------------------------------------
# Reject still works, and now for the right reason
# ---------------------------------------------------------------------------


class TestReject:
    def test_reject_does_not_run_the_tool(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        resp = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": False},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert write_tool["count"] == 0

    def test_reject_clears_the_parked_entry(
        self, client, db_session, monkeypatch, write_tool
    ):
        """It used to pop from a dict that had nothing in it — which is why
        reject looked healthy while approve was broken."""
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": False},
        )
        assert not cf.is_pending(call_id)

    def test_a_rejected_call_cannot_then_be_approved(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        headers = auth_headers(client, admin)
        client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=headers,
            json={"approved": False},
        )
        second = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=headers,
            json={"approved": True},
        )
        assert second.status_code == 404
        assert write_tool["count"] == 0


# ---------------------------------------------------------------------------
# B0.3 — the store outlives the process that made the entry
# ---------------------------------------------------------------------------


class TestTheStoreIsShared:
    def test_the_entry_lives_in_redis_not_in_this_process(
        self, client, db_session, monkeypatch, write_tool
    ):
        """The old dict was process-local, so with more than one worker the
        confirm request usually landed somewhere that had never heard of the
        call. What fixes that is the state being *outside* the process — so
        that is what this asserts, by reading the key straight off Redis."""
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))

        raw = cf._redis().get(f"{cf._KEY_PREFIX}{call_id}")
        assert raw is not None, "nothing reached Redis; a peer worker sees nothing"
        assert json.loads(raw)["tool_name"] == "fake_send"

    def test_reads_go_back_to_redis_every_time(
        self, client, db_session, monkeypatch, write_tool
    ):
        """No in-process cache in front of the store: a key removed by
        somebody else must be gone here on the very next read."""
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        assert cf.is_pending(call_id)

        cf._redis().delete(f"{cf._KEY_PREFIX}{call_id}")
        assert not cf.is_pending(call_id)

    def test_expiry_is_enforced_on_read(self, monkeypatch):
        cf.store_pending(
            call_id="ttl-1", tool_name="fake_send", args={}, session_id="s"
        )
        assert cf.is_pending("ttl-1")
        monkeypatch.setattr(cf.time, "time", lambda: 10**12)
        # First read past TTL reports expiry *and* drops the key, so the
        # endpoint can answer 410 once and 404 thereafter. Redis' own `ex=`
        # would eventually do the same; this makes it deterministic.
        with pytest.raises(cf.ConfirmationExpired):
            cf.peek("ttl-1")
        with pytest.raises(cf.ConfirmationNotFound):
            cf.peek("ttl-1")
        assert not cf.is_pending("ttl-1")

    def test_an_expired_call_returns_410_not_404(
        self, client, db_session, monkeypatch, write_tool
    ):
        admin, sid, _ = _open(client, db_session, monkeypatch)
        call_id = _confirmation_id(_ask(client, admin, sid))
        monkeypatch.setattr(cf.time, "time", lambda: 10**12)
        resp = client.post(
            f"/api/v1/copilot/confirm/{call_id}",
            headers=auth_headers(client, admin),
            json={"approved": True},
        )
        assert resp.status_code == 410
        assert write_tool["count"] == 0
