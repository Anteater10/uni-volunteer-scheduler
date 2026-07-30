"""Phase 32 Plan 04 — retrieval-augmented copilot router integration tests.

Covers the new ``event: meta`` SSE event, the ``<retrieved_context>``
prompt block, the Phase 30 system-prompt preservation invariant, and the
graceful-degradation behaviour when the retrieval step finds nothing.

The hybrid retriever, reranker, and embedding provider are all mocked so
these tests never touch Postgres, the BGE weights, or the Jina API.
``llm.stream_completion`` is mocked to return a deterministic token
sequence — the OpenRouter SDK is never instantiated.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import models
from app.copilot import llm as copilot_llm
from app.copilot import router as copilot_router_mod
from app.copilot.retrieval.hybrid import HybridHit
from app.copilot.schemas import MetaEvent
from app.config import settings
from tests.fixtures.helpers import auth_headers, make_user


# The admin prompt, verbatim, as of SYSTEM_PROMPT_VERSION v0.2.0. Editing the
# prompt means regenerating this file AND bumping the version in prompts.py —
# that pairing is the whole point of the check below. v0.1.0 told admins they
# manage "quarterly imports", a surface that had been deleted, so the model
# recommended a feature that no longer existed on every schedule question.
PHASE_30_FIXTURE = (
    Path(__file__).parent / "fixtures" / "phase_30_system_prompt.txt"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_copilot(monkeypatch):
    monkeypatch.setattr(settings, "copilot_enabled", True)
    monkeypatch.setattr(settings, "copilot_primary_model", "primary/test:free")
    monkeypatch.setattr(settings, "copilot_fallback_model", "fallback/test:free")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "corpus_embedding_primary", "local")


def _admin(db_session, email="ret_admin@example.com"):
    return make_user(db_session, email=email, role=models.UserRole.admin)


def _make_hits(n: int = 3) -> list[HybridHit]:
    out: list[HybridHit] = []
    for i in range(n):
        out.append(
            HybridHit(
                id=uuid.UUID(int=i + 1),
                document_id=uuid.UUID(int=1000 + i),
                content=f"chunk content {i}: the answer is forty-two number {i}",
                char_start=0,
                char_end=64,
                rrf_score=1.0 / (i + 1),
            )
        )
    return out


def _reranked_from(hits: list[HybridHit]) -> list[dict]:
    out = []
    for h in hits:
        out.append(
            {
                "id": h.id,
                "document_id": h.document_id,
                "content": h.content,
                "char_start": h.char_start,
                "char_end": h.char_end,
                "rrf_score": h.rrf_score,
                "rerank_score": 0.9 - 0.1 * len(out),
            }
        )
    return out


def _patch_retrieval(
    monkeypatch,
    *,
    hits=None,
    reranked=None,
    embedding=None,
    hybrid_kwargs_capture=None,
    path_resolver_paths=None,
):
    """Patch the retrieval pipeline + embedding provider in one helper."""
    if hits is None:
        hits = _make_hits(3)
    if reranked is None:
        reranked = _reranked_from(hits)
    if embedding is None:
        embedding = [0.01] * 1024

    def fake_hybrid_search(session, **kwargs):
        if hybrid_kwargs_capture is not None:
            hybrid_kwargs_capture.update(kwargs)
        return hits

    def fake_rerank(query, candidates, top_k=5):
        return reranked[:top_k]

    paths = path_resolver_paths or {}

    def fake_path_resolver_factory(db, document_ids):
        def resolver(doc_id: str) -> str:
            return paths.get(str(doc_id), f"docs/{doc_id[:8]}.md")
        return resolver

    class FakeEmbProvider:
        name = "local-bge"
        model_id = "BAAI/bge-small-en-v1.5+pad1024"

        def embed(self, texts):
            from app.corpus.embeddings import EmbedMeta
            return [embedding for _ in texts], EmbedMeta(
                provider="local-bge",
                model_id=self.model_id,
                api_calls=0,
                latency_ms=1,
                tokens=0,
            )

    monkeypatch.setattr(copilot_router_mod, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(copilot_router_mod, "rerank", fake_rerank)
    monkeypatch.setattr(
        copilot_router_mod, "_build_path_resolver", fake_path_resolver_factory
    )
    monkeypatch.setattr(
        copilot_router_mod, "_get_embedding_provider", lambda: FakeEmbProvider()
    )


def _patch_stream(monkeypatch, chunks=("Hello ", "world", "!")):
    """Replace llm.stream_completion + capture the system prompt forwarded in."""
    captured: dict = {"system_prompt": None, "messages": None}

    def fake_stream(*, messages, max_tokens=None):
        captured["messages"] = messages
        # Convention: messages[0] is the system message.
        if messages and messages[0]["role"] == "system":
            captured["system_prompt"] = messages[0]["content"]
        for c in chunks:
            yield c, {}
        yield "", {
            "model_id": "primary/test:free",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_ms": 42,
            "completion_text": "".join(chunks),
        }

    monkeypatch.setattr(copilot_router_mod.llm, "stream_completion", fake_stream)
    return captured


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    """Parse an SSE byte body into a list of (event, data) pairs in order."""
    out: list[tuple[str, str]] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if event_name is not None:
            out.append((event_name, "\n".join(data_lines)))
    return out


def _open_session(client, db_session, monkeypatch):
    admin = _admin(db_session)
    db_session.commit()
    rc = client.post("/api/v1/copilot/sessions", headers=auth_headers(client, admin))
    assert rc.status_code == 201, rc.text
    return admin, rc.json()["id"]


def _post_and_collect(client, admin, sid, *, content="What is the answer?") -> str:
    body = bytearray()
    with client.stream(
        "POST",
        f"/api/v1/copilot/sessions/{sid}/messages",
        headers=auth_headers(client, admin),
        json={"content": content},
    ) as resp:
        assert resp.status_code == 200, resp.read()
        for chunk in resp.iter_bytes():
            body.extend(chunk)
    return body.decode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_sse_event_order(client, db_session, monkeypatch):
    """meta must appear exactly once, before the first token, followed by done."""
    _patch_retrieval(monkeypatch)
    _patch_stream(monkeypatch, chunks=("Hi ", "there", "!"))
    admin, sid = _open_session(client, db_session, monkeypatch)

    body = _post_and_collect(client, admin, sid)
    events = _parse_sse(body)
    names = [e for e, _ in events]
    assert names.count("meta") == 1, names
    assert names[0] == "meta", names
    assert "token" in names
    assert names[-1] == "done"
    # meta must precede the first token.
    first_token_idx = names.index("token")
    meta_idx = names.index("meta")
    assert meta_idx < first_token_idx


def test_meta_event_payload_shape(client, db_session, monkeypatch):
    _patch_retrieval(monkeypatch)
    _patch_stream(monkeypatch)
    admin, sid = _open_session(client, db_session, monkeypatch)

    events = _parse_sse(_post_and_collect(client, admin, sid))
    meta_data = next(d for e, d in events if e == "meta")
    meta = MetaEvent.model_validate_json(meta_data)
    assert len(meta.citations) <= 5
    assert meta.retrieval_latency_ms >= 0
    assert meta.rerank_latency_ms >= 0
    for c in meta.citations:
        # chunk_id is a UUID; pydantic coerces from string.
        assert c.chunk_id is not None
        assert c.source_path
        assert c.char_end >= c.char_start
        assert c.quote
        assert c.rrf_score is not None
        assert c.rerank_score is not None


def test_retrieval_uses_active_provider(client, db_session, monkeypatch):
    """settings.corpus_embedding_primary='local' → hybrid_search(provider='local-bge')."""
    capture: dict = {}
    _patch_retrieval(monkeypatch, hybrid_kwargs_capture=capture)
    _patch_stream(monkeypatch)
    admin, sid = _open_session(client, db_session, monkeypatch)

    _post_and_collect(client, admin, sid)
    assert capture.get("provider") == "local-bge", capture
    assert capture.get("query_text")
    assert capture.get("query_embedding")
    assert capture.get("top_n") == 20


def test_system_prompt_contains_retrieved_context(client, db_session, monkeypatch):
    _patch_retrieval(monkeypatch)
    captured = _patch_stream(monkeypatch)
    admin, sid = _open_session(client, db_session, monkeypatch)

    _post_and_collect(client, admin, sid)
    sp = captured["system_prompt"]
    assert sp is not None
    assert "<retrieved_context>" in sp
    assert "</retrieved_context>" in sp
    # Top-1 reranked chunk content appears in the block.
    assert "chunk content 0" in sp


def test_system_prompt_preserves_phase_30_baseline(client, db_session, monkeypatch):
    _patch_retrieval(monkeypatch)
    captured = _patch_stream(monkeypatch)
    admin, sid = _open_session(client, db_session, monkeypatch)

    _post_and_collect(client, admin, sid)
    baseline = PHASE_30_FIXTURE.read_text(encoding="utf-8")
    sp = captured["system_prompt"]
    assert sp is not None
    assert baseline in sp, (
        "Baseline system prompt was modified — load-bearing persona / refusal / "
        "role-differentiation must be preserved verbatim. If the change is "
        "intentional, bump SYSTEM_PROMPT_VERSION and regenerate the fixture."
    )


def test_meta_event_emitted_even_when_zero_results(client, db_session, monkeypatch):
    """Empty hybrid result → meta event with citations=[], LLM still streams."""
    _patch_retrieval(monkeypatch, hits=[], reranked=[])
    _patch_stream(monkeypatch, chunks=("ok",))
    admin, sid = _open_session(client, db_session, monkeypatch)

    events = _parse_sse(_post_and_collect(client, admin, sid))
    names = [e for e, _ in events]
    assert "meta" in names
    meta = MetaEvent.model_validate_json(next(d for e, d in events if e == "meta"))
    assert meta.citations == []
    # Stream still produced a token + done.
    assert "token" in names
    assert names[-1] == "done"


def test_existing_event_shapes_unchanged(client, db_session, monkeypatch):
    """token and done payloads match Phase 30 contract exactly."""
    _patch_retrieval(monkeypatch)
    _patch_stream(monkeypatch, chunks=("alpha", "beta"))
    admin, sid = _open_session(client, db_session, monkeypatch)

    events = _parse_sse(_post_and_collect(client, admin, sid))
    tokens = [d for e, d in events if e == "token"]
    # token data is json.dumps(chunk_str) — string roundtrip, nothing else.
    assert tokens, events
    assert json.loads(tokens[0]) == "alpha"
    assert json.loads(tokens[1]) == "beta"

    done = next(d for e, d in events if e == "done")
    done_payload = json.loads(done)
    # Phase 30 invariant: done carries ONLY message_id.
    assert set(done_payload.keys()) == {"message_id"}
    # message_id is a UUID string.
    uuid.UUID(done_payload["message_id"])
