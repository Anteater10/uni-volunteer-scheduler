"""Phase 35-01-D Task 13: SSE ``message_persisted`` event.

The streaming endpoint must emit::

    event: message_persisted
    data: {"id": "<uuid>", "role": "assistant"}

after the assistant ``copilot_messages`` row is persisted and BEFORE
the terminal ``event: done`` (or ``event: error``) marker. The change
is strictly additive — the existing ``token`` / ``done`` / ``error``
shapes are untouched (Phase 30 invariant).
"""
from __future__ import annotations

import json
import uuid

import pytest

from app import models
from app.copilot import router as copilot_router_mod
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "copilot_fallback_model", "fallback/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    # These tests are about the Phase 30 Q&A stream specifically, and they
    # script it by patching ``_stream_completion``. Once the agent loop
    # became the default (2026-08-07) the endpoint stopped reaching that
    # helper, so the patch bound to nothing and the unstubbed agent path
    # dialled openrouter.ai for real and 401'd. Pin the path under test.
    # The agent path's own ``message_persisted`` behaviour is covered in
    # tests/copilot/agent/.
    monkeypatch.setattr(settings, "copilot_agent_loop_enabled", False)


def _patch_stream(monkeypatch, chunks=("Hi ", "there."), exc=None):
    meta = {
        "model_id": "primary/test:free",
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "latency_ms": 1,
        "completion_text": "".join(chunks),
    }

    def fake_stream(**kwargs):
        if exc is not None:
            raise exc
        for c in chunks:
            yield c, {}
        yield "", meta

    monkeypatch.setattr(copilot_router_mod.llm, "stream_completion", fake_stream)


def _consume(client, admin, sid, content="hello"):
    body = bytearray()
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": content},
    ) as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_bytes():
            body.extend(chunk)
    return body.decode("utf-8")


def _events(text):
    """Parse SSE wire format → list of (event_name, data_str)."""
    out = []
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        ev_name = "message"
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].lstrip())
        out.append((ev_name, "\n".join(data_lines)))
    return out


def test_message_persisted_event_emitted_with_id_and_role(
    client, db_session, monkeypatch
):
    admin = make_user(db_session, email="mp_ok@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch)
    text = _consume(client, admin, sid)

    events = _events(text)
    names = [n for n, _ in events]
    assert "message_persisted" in names, names

    mp_idx = names.index("message_persisted")
    mp_data = json.loads(events[mp_idx][1])
    assert mp_data["role"] == "assistant"
    uuid.UUID(mp_data["id"])  # must be a parseable UUID


def test_message_persisted_precedes_done(client, db_session, monkeypatch):
    admin = make_user(db_session, email="mp_order@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch)
    text = _consume(client, admin, sid)

    names = [n for n, _ in _events(text)]
    assert "message_persisted" in names and "done" in names
    assert names.index("message_persisted") < names.index("done")


def test_message_persisted_id_matches_done_message_id(
    client, db_session, monkeypatch
):
    admin = make_user(db_session, email="mp_match@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch)
    text = _consume(client, admin, sid)

    events = _events(text)
    mp = next(d for n, d in events if n == "message_persisted")
    done = next(d for n, d in events if n == "done")
    assert json.loads(mp)["id"] == json.loads(done)["message_id"]


def test_message_persisted_id_matches_persisted_row(
    client, db_session, monkeypatch
):
    admin = make_user(db_session, email="mp_row@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch)
    text = _consume(client, admin, sid)

    mp = next(d for n, d in _events(text) if n == "message_persisted")
    persisted_id = uuid.UUID(json.loads(mp)["id"])

    db_session.expire_all()
    asst = (
        db_session.query(models.CopilotMessage)
        .filter_by(session_id=sid, role=models.CopilotMessageRole.assistant)
        .one()
    )
    assert asst.id == persisted_id


def test_message_persisted_emitted_even_on_stream_error(
    client, db_session, monkeypatch
):
    """When the LLM call raises, the assistant row is still persisted
    (with ``error`` stamped) and ``message_persisted`` is still emitted
    BEFORE the terminal ``error`` event — so the frontend can attach the
    id to the partial/empty bubble it shows on failure.
    """
    admin = make_user(db_session, email="mp_err@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch, exc=RuntimeError("boom"))
    text = _consume(client, admin, sid)

    names = [n for n, _ in _events(text)]
    assert "message_persisted" in names
    assert "error" in names
    assert names.index("message_persisted") < names.index("error")


def test_existing_event_shapes_unchanged(client, db_session, monkeypatch):
    """Strictly-additive invariant: token/done shapes are byte-for-byte
    the same as before this sub-phase (no new fields, no rename)."""
    admin = make_user(db_session, email="mp_invariant@example.com", role=models.UserRole.admin)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch, chunks=("Hi",))
    text = _consume(client, admin, sid)

    events = _events(text)
    # token data is a JSON-encoded string chunk
    tok = next(d for n, d in events if n == "token")
    assert json.loads(tok) == "Hi"
    # done payload is exactly {"message_id": "<uuid>"} — no extra keys
    done = json.loads(next(d for n, d in events if n == "done"))
    assert set(done.keys()) == {"message_id"}
    uuid.UUID(done["message_id"])
