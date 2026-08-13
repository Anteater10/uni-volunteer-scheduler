"""BASE-CONFIG-02 companion: startup prewarm of the two local models.

The weights are baked into the image now, but they are still loaded lazily per
worker process, so the first copilot question after a deploy paid for a ~1.1GB
reranker load while an admin watched. Prewarming moves that off the request
path. Two properties matter more than the speedup:

* readiness must not wait on it — a container healthcheck that fails while
  1.3GB of weights load would fail the deploy this was meant to smooth;
* it must not be able to break the API — every non-copilot route works with no
  model at all, so a prewarm failure is a log line, not a boot failure.
"""
import asyncio
import logging

import importlib

import pytest
from fastapi import FastAPI

from app import main as main_mod

# `app.copilot.retrieval` re-exports a *function* named `rerank`, which shadows
# the submodule of the same name — so the dotted-string form of monkeypatch
# resolves to the function and fails. Grab the modules explicitly.
rerank_mod = importlib.import_module("app.copilot.retrieval.rerank")
embeddings_mod = importlib.import_module("app.corpus.embeddings")


def test_a_prewarm_failure_does_not_propagate(monkeypatch, caplog):
    """The whole point: a copilot that cannot warm up must not stop the API."""
    def _boom():
        raise RuntimeError("no weights on disk")

    monkeypatch.setattr(rerank_mod, "_model", _boom, raising=True)
    # Stub the other component too, or this test reaches for real weights (and,
    # without a baked cache, the network) to warm something it isn't testing.
    monkeypatch.setattr(
        embeddings_mod,
        "LocalBgeEmbeddingProvider",
        lambda model: type("_P", (), {"embed": lambda self, texts: ([], None)})(),
        raising=True,
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        main_mod._prewarm_models()  # must not raise

    assert "model_prewarm_failed" in caplog.text


def test_both_components_are_warmed_and_logged(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(
        rerank_mod, "_model", lambda: calls.append("reranker"), raising=True
    )

    class _FakeLocalProvider:
        def __init__(self, model):
            self.model = model

        def embed(self, texts):
            calls.append("embeddings")
            return [], None

    monkeypatch.setattr(
        embeddings_mod, "LocalBgeEmbeddingProvider", _FakeLocalProvider, raising=True
    )

    with caplog.at_level(logging.INFO, logger="app.main"):
        main_mod._prewarm_models()

    assert calls == ["reranker", "embeddings"]
    assert caplog.text.count("model_prewarm_ok") == 2


def test_embeddings_warm_the_local_model_even_when_jina_is_primary(monkeypatch):
    """Warming the *configured* primary would spend a paid API call on a request
    nobody made. The point of prewarming is to touch the on-disk weights."""
    monkeypatch.setattr(main_mod.settings, "corpus_embedding_primary", "jina")
    seen = {}

    class _FakeLocalProvider:
        def __init__(self, model):
            seen["model"] = model

        def embed(self, texts):
            seen["embedded"] = list(texts)
            return [], None

    monkeypatch.setattr(
        embeddings_mod, "LocalBgeEmbeddingProvider", _FakeLocalProvider, raising=True
    )
    monkeypatch.setattr(rerank_mod, "_model", lambda: None, raising=True)

    main_mod._prewarm_models()

    assert seen["model"] == main_mod.settings.local_embedding_model
    assert seen["embedded"] == ["warmup"]


@pytest.mark.parametrize(
    "copilot_enabled,prewarm,expected",
    [
        (True, True, 1),
        (True, False, 0),   # the documented escape hatch for a small instance
        (False, True, 0),   # no copilot, no reason to hold 1.3GB per worker
    ],
)
def test_the_lifespan_only_starts_the_thread_when_asked(
    monkeypatch, copilot_enabled, prewarm, expected
):
    monkeypatch.setattr(main_mod.settings, "copilot_enabled", copilot_enabled)
    monkeypatch.setattr(main_mod.settings, "copilot_prewarm_on_startup", prewarm)

    started = []

    class _FakeThread:
        def __init__(self, *a, **kw):
            self.kw = kw

        def start(self):
            started.append(self.kw.get("name"))

    monkeypatch.setattr(main_mod.threading, "Thread", _FakeThread)

    async def _run():
        async with main_mod.lifespan(FastAPI()):
            pass

    asyncio.run(_run())

    assert len(started) == expected
    if expected:
        assert started == ["model-prewarm"]


def test_the_prewarm_thread_is_a_daemon(monkeypatch):
    """A non-daemon thread mid-load would delay every restart by the load time."""
    import inspect

    source = inspect.getsource(main_mod.lifespan)
    assert "daemon=True" in source
