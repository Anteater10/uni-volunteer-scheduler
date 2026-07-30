"""Phase 30 — coverage for app.copilot.{router, llm, prompts, schemas}.

Mocks ``llm.stream_completion`` so tests never hit OpenRouter. The
streaming SSE response is consumed via ``client.stream(...)`` so we
exercise the iterator path including the persisted assistant row.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError

from app import models
from app.copilot import llm as copilot_llm
from app.copilot import prompts as copilot_prompts
from app.copilot import router as copilot_router_mod
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "copilot_fallback_model", "fallback/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")


def _admin(db_session, email="cop_admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _organizer(db_session, email="cop_org@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.organizer)


def _participant(db_session, email="cop_part@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.participant)


def _patch_stream(monkeypatch, chunks=("Hi ", "there."), meta=None, exc=None):
    """Replace llm.stream_completion with a deterministic generator."""
    if meta is None:
        meta = {
            "model_id": "primary/test:free",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_ms": 42,
            "completion_text": "".join(chunks),
        }

    def fake_stream(**kwargs):
        if exc is not None:
            raise exc
        for c in chunks:
            yield c, {}
        yield "", meta

    monkeypatch.setattr(copilot_router_mod.llm, "stream_completion", fake_stream)


# ---------------------------------------------------------------------------
# Flag gate
# ---------------------------------------------------------------------------


def test_router_404s_when_flag_off(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", False)
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    assert rc.status_code == 404


def test_create_session_requires_auth(client):
    rc = client.post("/api/v1/copilot/sessions")
    assert rc.status_code == 401


def test_create_session_rejects_volunteer(client, db_session):
    p = _participant(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, p))
    assert rc.status_code == 403


# ---------------------------------------------------------------------------
# Session create / list / fetch
# ---------------------------------------------------------------------------


def test_create_session_admin_succeeds(client, db_session):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    assert rc.status_code == 201, rc.text
    body = rc.json()
    assert body["model_id"] == "primary/test:free"
    assert body["system_prompt_version"] == copilot_prompts.SYSTEM_PROMPT_VERSION
    db_session.expire_all()
    sess = db_session.query(models.CopilotSession).filter_by(id=body["id"]).one()
    assert sess.user_id == admin.id
    sysmsgs = [m for m in sess.messages if m.role == models.CopilotMessageRole.system]
    assert len(sysmsgs) == 1


def test_create_session_organizer_succeeds(client, db_session):
    org = _organizer(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, org))
    assert rc.status_code == 201
    body = rc.json()
    db_session.expire_all()
    sess = db_session.query(models.CopilotSession).filter_by(id=body["id"]).one()
    sysmsg = sess.messages[0]
    assert "organizer" in sysmsg.content.lower()


def test_list_sessions_returns_only_callers_sessions(client, db_session):
    a = _admin(db_session, email="cop_la@example.com")
    b = _admin(db_session, email="cop_lb@example.com")
    db_session.commit()

    client.post("/api/v1/copilot/sessions", headers=auth_headers(client, a))
    client.post("/api/v1/copilot/sessions", headers=auth_headers(client, a))
    client.post("/api/v1/copilot/sessions", headers=auth_headers(client, b))

    rc = client.get("/api/v1/copilot/sessions", headers=auth_headers(client, a))
    assert rc.status_code == 200
    bodies = rc.json()
    assert len(bodies) == 2


def test_list_sessions_flag_off_404s(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    monkeypatch.setattr(settings, "copilot_enabled", False)
    rc = client.get("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    assert rc.status_code == 404


def test_list_sessions_volunteer_forbidden(client, db_session):
    p = _participant(db_session)
    db_session.commit()
    rc = client.get("/api/v1/copilot/sessions", headers=auth_headers(client, p))
    assert rc.status_code == 403


def test_get_session_returns_messages(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch)
    with client.stream(
        "POST", f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "Hello"},
    ) as resp:
        for _ in resp.iter_bytes():
            pass

    rc = client.get(f"/api/v1/copilot/sessions/{sid}", headers=auth_headers(client, admin))
    assert rc.status_code == 200
    body = rc.json()
    roles = [m["role"] for m in body["messages"]]
    assert "system" in roles and "user" in roles and "assistant" in roles


def test_get_session_other_users_404s(client, db_session):
    a = _admin(db_session, email="cop_ga@example.com")
    b = _admin(db_session, email="cop_gb@example.com")
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, a))
    sid = rc.json()["id"]

    rc = client.get(f"/api/v1/copilot/sessions/{sid}", headers=auth_headers(client, b))
    assert rc.status_code == 404


def test_get_session_flag_off_404s(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]
    monkeypatch.setattr(settings, "copilot_enabled", False)
    rc = client.get(f"/api/v1/copilot/sessions/{sid}", headers=auth_headers(client, admin))
    assert rc.status_code == 404


def test_get_session_volunteer_forbidden(client, db_session):
    p = _participant(db_session)
    db_session.commit()
    rc = client.get(
        f"/api/v1/copilot/sessions/{uuid.uuid4()}", headers=auth_headers(client, p),
    )
    assert rc.status_code == 403


# ---------------------------------------------------------------------------
# Message streaming
# ---------------------------------------------------------------------------


def test_post_message_streams_and_persists_telemetry(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch, chunks=("Hello ", "world!"))
    body_bytes = bytearray()
    with client.stream(
        "POST", f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "Say hi"},
    ) as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_bytes():
            body_bytes.extend(chunk)

    text = body_bytes.decode("utf-8")
    assert "event: token" in text
    assert "event: done" in text

    db_session.expire_all()
    msgs = (
        db_session.query(models.CopilotMessage)
        .filter_by(session_id=sid)
        .order_by(models.CopilotMessage.created_at.asc())
        .all()
    )
    asst = [m for m in msgs if m.role == models.CopilotMessageRole.assistant][0]
    assert asst.content == "Hello world!"
    assert asst.latency_ms == 42
    assert asst.prompt_tokens == 10
    assert asst.completion_tokens == 5
    assert asst.model_id == "primary/test:free"
    assert asst.prompt_hash and asst.response_hash
    assert asst.error is None


def test_post_message_records_error_when_stream_fails(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]

    _patch_stream(monkeypatch, exc=RuntimeError("boom"))
    with client.stream(
        "POST", f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "Hi"},
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")
    assert "event: error" in body

    db_session.expire_all()
    asst = (
        db_session.query(models.CopilotMessage)
        .filter_by(session_id=sid, role=models.CopilotMessageRole.assistant)
        .one()
    )
    assert asst.error == "RuntimeError"
    assert asst.content == ""
    assert asst.response_hash is None


def test_post_message_404s_for_unknown_session(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    _patch_stream(monkeypatch)
    rc = client.post(
        f"/api/v1/copilot/sessions/{uuid.uuid4()}/messages",
        headers=auth_headers(client, admin),
        json={"content": "x"},
    )
    assert rc.status_code == 404


def test_post_message_404s_for_other_users_session(client, db_session, monkeypatch):
    a = _admin(db_session, email="cop_pa@example.com")
    b = _admin(db_session, email="cop_pb@example.com")
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, a))
    sid = rc.json()["id"]
    _patch_stream(monkeypatch)
    rc = client.post(
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, b),
        json={"content": "x"},
    )
    assert rc.status_code == 404


def test_post_message_flag_off_404s(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]
    monkeypatch.setattr(settings, "copilot_enabled", False)
    _patch_stream(monkeypatch)
    rc = client.post(
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": "x"},
    )
    assert rc.status_code == 404


def test_post_message_volunteer_forbidden(client, db_session):
    p = _participant(db_session)
    db_session.commit()
    rc = client.post(
        f"/api/v1/copilot/sessions/{uuid.uuid4()}/messages",
        headers=auth_headers(client, p),
        json={"content": "x"},
    )
    assert rc.status_code == 403


def test_post_message_validates_content_length(client, db_session):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    sid = rc.json()["id"]
    rc = client.post(
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": ""},
    )
    assert rc.status_code == 422


# ---------------------------------------------------------------------------
# llm.py — primary/fallback selection + meta extraction
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, p, c):
        self.prompt_tokens = p
        self.completion_tokens = c


class _FakeDelta:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.delta = _FakeDelta(content)


class _FakeEvent:
    def __init__(self, *, content=None, usage=None):
        self.choices = [_FakeChoice(content)] if content is not None else []
        self.usage = usage


class _FakeStream:
    def __init__(self, events):
        self._events = list(events)

    def __iter__(self):
        return iter(self._events)


class _FakeChat:
    def __init__(self, behaviors):
        """behaviors is a list per-call: either a list of events or an exception."""
        self._behaviors = list(behaviors)
        self.completions = self  # so `.chat.completions.create(...)` works
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        b = self._behaviors.pop(0)
        if isinstance(b, Exception):
            raise b
        return _FakeStream(b)


class _FakeClient:
    def __init__(self, behaviors):
        self.chat = _FakeChat(behaviors)


def _events_for(text, *, prompt_tokens=3, completion_tokens=2):
    return [
        _FakeEvent(content=text[: len(text) // 2]),
        _FakeEvent(content=text[len(text) // 2 :]),
        _FakeEvent(usage=_FakeUsage(prompt_tokens, completion_tokens)),
    ]


def test_llm_streams_primary_and_collects_meta(monkeypatch):
    fake = _FakeClient([_events_for("Hello!")])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    out = list(copilot_llm.stream_completion(messages=[{"role": "user", "content": "hi"}]))
    text_parts = [c for c, m in out if not m]
    final_meta = [m for c, m in out if m][0]
    assert "".join(text_parts) == "Hello!"
    assert final_meta["model_id"] == settings.copilot_primary_model
    assert final_meta["prompt_tokens"] == 3
    assert final_meta["completion_tokens"] == 2
    assert final_meta["latency_ms"] >= 0


def test_llm_falls_back_on_retryable_failure(monkeypatch):
    fake = _FakeClient([
        APITimeoutError(request=None),
        _events_for("From fallback"),
    ])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    text, meta = copilot_llm.complete(messages=[{"role": "user", "content": "hi"}])
    assert text == "From fallback"
    assert meta["model_id"] == settings.copilot_fallback_model
    assert len(fake.chat.calls) == 2


def test_llm_reraises_when_both_models_fail(monkeypatch):
    # One failure per model per sweep: the candidate list is swept
    # _MAX_SWEEPS times before the error surfaces, so a transient whole-list
    # outage recovers instead of ending the turn. Only after every sweep has
    # failed does the exception reach the caller.
    fake = _FakeClient(
        [APIConnectionError(request=None)] * (2 * copilot_llm._MAX_SWEEPS)
    )
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    monkeypatch.setattr(copilot_llm.time, "sleep", lambda _s: None)
    with pytest.raises(APIConnectionError):
        list(copilot_llm.stream_completion(messages=[{"role": "user", "content": "hi"}]))


def test_llm_passes_max_tokens(monkeypatch):
    fake = _FakeClient([_events_for("ok")])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    list(copilot_llm.stream_completion(
        messages=[{"role": "user", "content": "hi"}], max_tokens=42,
    ))
    assert fake.chat.calls[0]["max_tokens"] == 42


def test_llm_handles_empty_choice_event(monkeypatch):
    """Some providers emit chunks with empty/missing choices — must be skipped."""
    events = [
        _FakeEvent(),  # empty choices
        _FakeEvent(content=None),  # delta with no content
        _FakeEvent(content="ok"),
        _FakeEvent(usage=_FakeUsage(1, 1)),
    ]
    fake = _FakeClient([events])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    out = list(copilot_llm.stream_completion(messages=[{"role": "user", "content": "x"}]))
    text = "".join(c for c, m in out if not m)
    assert text == "ok"


def test_llm_skips_event_with_none_delta(monkeypatch):
    """Provider may emit a choice whose delta is None — must skip without yielding."""
    class _NoDeltaChoice:
        delta = None
    class _NoDeltaEvent:
        choices = [_NoDeltaChoice()]
        usage = None

    events = [_NoDeltaEvent(), _FakeEvent(content="ok"), _FakeEvent(usage=_FakeUsage(1, 1))]
    fake = _FakeClient([events])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    out = list(copilot_llm.stream_completion(messages=[{"role": "user", "content": "x"}]))
    text = "".join(c for c, m in out if not m)
    assert text == "ok"


def test_llm_falls_back_on_rate_limit(monkeypatch):
    """RateLimitError on primary should retry against fallback."""
    import httpx

    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(429, request=req)
    fake = _FakeClient([
        RateLimitError("rate", response=resp, body=None),
        _events_for("ok"),
    ])
    monkeypatch.setattr(copilot_llm, "_client", lambda: fake)
    text, meta = copilot_llm.complete(messages=[{"role": "user", "content": "hi"}])
    assert text == "ok"
    assert meta["model_id"] == settings.copilot_fallback_model


def test_llm_real_client_constructible():
    """Building the real client doesn't blow up — covers _client()."""
    c = copilot_llm._client()
    assert c is not None


# ---------------------------------------------------------------------------
# prompts.py — error path for unsupported role
# ---------------------------------------------------------------------------


def test_prompt_for_unsupported_role_raises():
    with pytest.raises(ValueError, match="not defined"):
        copilot_prompts.system_prompt_for(models.UserRole.participant)


def test_hash_prompt_is_stable():
    h1 = copilot_prompts.hash_prompt("hello")
    h2 = copilot_prompts.hash_prompt("hello")
    assert h1 == h2 and len(h1) == 64
