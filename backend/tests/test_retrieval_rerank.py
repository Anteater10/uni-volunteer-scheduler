"""Phase 32-03 — tests for the local cross-encoder reranker.

Hard constraints exercised here:

* Local-only: ``rerank.py`` MUST NOT reference any external rerank API.
  See ``test_rerank_no_external_apis`` below — a literal ``grep`` over
  the module source.
* Singleton model load: ``_model`` is wrapped in ``functools.lru_cache``
  so the 278 MB ``BAAI/bge-reranker-base`` weights load exactly once per
  worker process. See ``test_rerank_singleton_model_load``.
* Deterministic tiebreak by chunk_id ascending. See
  ``test_rerank_tiebreak_by_id``.

All tests stub out ``sentence_transformers.CrossEncoder`` so the real
weights never download in CI. The production code path still loads the
real model — the stub only intercepts the constructor.
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_cross_encoder(monkeypatch):
    """Patch ``CrossEncoder`` in ``app.copilot.retrieval.rerank``.

    Returns a tuple ``(constructor_mock, instance_mock)`` so tests can:

    * assert constructor call count + args (singleton + model name checks),
    * configure ``instance.predict`` return values per test.
    """
    import sys
    import importlib

    importlib.import_module("app.copilot.retrieval.rerank")
    rerank_mod = sys.modules["app.copilot.retrieval.rerank"]

    # Clear the lru_cache so each test starts fresh.
    rerank_mod._model.cache_clear()

    instance = MagicMock(name="CrossEncoderInstance")
    instance.predict = MagicMock(return_value=[0.0])
    constructor = MagicMock(name="CrossEncoderClass", return_value=instance)
    monkeypatch.setattr(rerank_mod, "CrossEncoder", constructor)
    yield constructor, instance
    rerank_mod._model.cache_clear()


def _mk(id_: str, content: str = "x") -> dict:
    return {
        "id": id_,
        "document_id": "doc-1",
        "content": content,
        "char_start": 0,
        "char_end": len(content),
        "rrf_score": 0.5,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rerank_empty_returns_empty(fake_cross_encoder):
    from app.copilot.retrieval.rerank import rerank

    assert rerank("query", []) == []
    constructor, _ = fake_cross_encoder
    # Empty short-circuit must NOT load the model.
    assert constructor.call_count == 0


def test_rerank_reorders_by_score(fake_cross_encoder):
    from app.copilot.retrieval.rerank import rerank

    _, instance = fake_cross_encoder
    instance.predict.return_value = [0.1, 0.9, 0.5]

    candidates = [_mk("a"), _mk("b"), _mk("c")]
    out = rerank("q", candidates, top_k=3)

    assert [c["id"] for c in out] == ["b", "c", "a"]
    # rerank_score attached and float-typed.
    assert out[0]["rerank_score"] == pytest.approx(0.9)
    assert out[1]["rerank_score"] == pytest.approx(0.5)
    assert out[2]["rerank_score"] == pytest.approx(0.1)


def test_rerank_respects_top_k(fake_cross_encoder):
    from app.copilot.retrieval.rerank import rerank

    _, instance = fake_cross_encoder
    instance.predict.return_value = [float(i) / 10 for i in range(10)]
    candidates = [_mk(f"id-{i:02d}") for i in range(10)]

    out = rerank("q", candidates, top_k=3)
    assert len(out) == 3
    # Top-3 by score descending — last three ids 09, 08, 07.
    assert [c["id"] for c in out] == ["id-09", "id-08", "id-07"]


def test_rerank_singleton_model_load(fake_cross_encoder):
    from app.copilot.retrieval.rerank import rerank

    constructor, instance = fake_cross_encoder
    instance.predict.return_value = [0.5]
    for _ in range(5):
        rerank("q", [_mk("only")])

    assert constructor.call_count == 1, (
        "CrossEncoder must be constructed exactly once across N rerank calls "
        "(lru_cache(maxsize=1) singleton — RESEARCH Pitfall 2)."
    )


def test_rerank_tiebreak_by_id(fake_cross_encoder):
    from app.copilot.retrieval.rerank import rerank

    _, instance = fake_cross_encoder
    # All identical scores — tiebreak must use id ascending.
    instance.predict.return_value = [0.5, 0.5, 0.5]
    candidates = [_mk("zeta"), _mk("alpha"), _mk("mu")]

    out = rerank("q", candidates, top_k=3)
    assert [c["id"] for c in out] == ["alpha", "mu", "zeta"]


def test_rerank_latency_budget(fake_cross_encoder):
    """With a mocked predict, 20 candidates must complete in <200ms.

    Real model latency is verified in Plan 04 smoke; this test catches
    accidental quadratic loops or per-candidate model loads.
    """
    from app.copilot.retrieval.rerank import rerank

    _, instance = fake_cross_encoder
    instance.predict.return_value = [0.5] * 20
    candidates = [_mk(f"id-{i:02d}") for i in range(20)]

    started = time.monotonic()
    out = rerank("q", candidates, top_k=5)
    elapsed_ms = (time.monotonic() - started) * 1000

    assert len(out) == 5
    assert elapsed_ms < 200, f"rerank wall-clock {elapsed_ms:.1f}ms exceeds 200ms"


def test_rerank_uses_bge_base_model_name(fake_cross_encoder):
    """Constraint C6 audit: must construct ``BAAI/bge-reranker-base`` w/ max_length=512."""
    from app.copilot.retrieval.rerank import rerank

    constructor, instance = fake_cross_encoder
    instance.predict.return_value = [0.1]
    rerank("q", [_mk("only")])

    args, kwargs = constructor.call_args
    assert args == ("BAAI/bge-reranker-base",), args
    assert kwargs.get("max_length") == 512, kwargs


def test_rerank_predict_batch_size_16(fake_cross_encoder):
    """RESEARCH §Pattern 4: predict called with batch_size=16."""
    from app.copilot.retrieval.rerank import rerank

    _, instance = fake_cross_encoder
    instance.predict.return_value = [0.1, 0.2]
    rerank("q", [_mk("a"), _mk("b")])

    _, kwargs = instance.predict.call_args
    assert kwargs.get("batch_size") == 16, kwargs
    assert kwargs.get("show_progress_bar") is False, kwargs


def test_rerank_no_external_apis():
    """Constraint C6 (load-bearing): no Jina/Cohere/Voyage references.

    A literal grep over the module source. If anyone adds an external
    rerank API call this test fails loudly.
    """
    src = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "copilot"
        / "retrieval"
        / "rerank.py"
    ).read_text()
    lowered = src.lower()
    for forbidden in ("jina", "cohere", "voyage"):
        assert forbidden not in lowered, (
            f"rerank.py references {forbidden!r} — constraint C6 forbids "
            "external rerank APIs."
        )


def test_rerank_module_uses_lru_cache():
    """Pitfall 2 audit: singleton must use functools.lru_cache."""
    src = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "copilot"
        / "retrieval"
        / "rerank.py"
    ).read_text()
    assert "lru_cache" in src, "rerank.py must use functools.lru_cache for singleton."


def test_rerank_exported_from_retrieval_package(fake_cross_encoder):
    from app.copilot.retrieval import rerank as rerank_fn

    assert callable(rerank_fn)
