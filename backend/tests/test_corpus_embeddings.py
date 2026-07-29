"""Phase 31 plan 04 — embedding provider tests.

Covers REQ-31-11 (dim locked to 1024) and the threat-model mitigations
T-31-05 (Jina wrong-dim defence) and T-31-06 (rate-limit fallback gate).

Notes:
    * Local BGE provider lazy-loads ``sentence-transformers``; first run in
      a fresh container downloads ~130 MB of model weights into
      ``~/.cache/huggingface``. Subsequent runs hit the cache and are fast.
    * Jina tests monkeypatch ``httpx.Client.post`` so no network IO occurs.
"""

from __future__ import annotations

import pytest


def test_embedding_dim_locked_to_1024():
    """REQ-31-11: column-locked 1024 dimensionality, BGE fallback padded."""
    from app.corpus.embeddings import EMBEDDING_DIM, LocalBgeEmbeddingProvider

    assert EMBEDDING_DIM == 1024
    p = LocalBgeEmbeddingProvider()
    vecs, _meta = p.embed(["hello"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 1024  # 384 native, padded to 1024


def test_local_bge_pads_with_zeros():
    """The last 1024 - 384 = 640 elements are exactly 0.0 (right-pad)."""
    from app.corpus.embeddings import LocalBgeEmbeddingProvider

    p = LocalBgeEmbeddingProvider()
    vecs, meta = p.embed(["hello world"])
    tail = vecs[0][384:]
    assert len(tail) == 640
    assert all(x == 0.0 for x in tail)
    assert meta.provider == "local-bge"
    assert meta.model_id.endswith("+pad1024")
    assert meta.tokens == 0
    assert meta.api_calls == 0


def test_local_bge_is_deterministic():
    """Same input → byte-identical vector (no dropout, no random seed)."""
    from app.corpus.embeddings import LocalBgeEmbeddingProvider

    p = LocalBgeEmbeddingProvider()
    a, _ = p.embed(["same string"])
    b, _ = p.embed(["same string"])
    assert a[0] == b[0]


def test_jina_provider_raises_on_429(monkeypatch):
    """HTTP 429 → ``RateLimitError`` so ingest.py can switch to fallback."""
    import httpx
    from app.corpus import embeddings as emb_mod

    class _Resp:
        status_code = 429
        text = "too many requests"

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "429", request=httpx.Request("POST", "http://x"), response=self  # type: ignore[arg-type]
            )

        def json(self):  # pragma: no cover - shouldn't be called
            return {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(emb_mod.httpx, "Client", _Client)

    provider = emb_mod.JinaEmbeddingProvider(api_key="fake-key")
    with pytest.raises(emb_mod.RateLimitError):
        provider.embed(["hello"])


def test_jina_provider_returns_1024_native(monkeypatch):
    """Happy path: mock 1024-dim response → 1024-len vector + meta with token count."""
    import httpx
    from app.corpus import embeddings as emb_mod

    payload = {
        "data": [{"embedding": [0.1] * 1024, "index": 0}],
        "usage": {"prompt_tokens": 3},
        "model": "jina-embeddings-v3",
    }

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None, headers=None):
            assert "embeddings" in url
            assert headers["Authorization"].startswith("Bearer ")
            assert json["model"] == "jina-embeddings-v3"
            assert json["input"] == ["hello"]
            return _Resp()

    monkeypatch.setattr(emb_mod.httpx, "Client", _Client)

    provider = emb_mod.JinaEmbeddingProvider(api_key="fake-key")
    vecs, meta = provider.embed(["hello"])
    assert len(vecs) == 1 and len(vecs[0]) == 1024
    assert meta.provider == "jina"
    assert meta.model_id == "jina-embeddings-v3"
    assert meta.api_calls == 1
    assert meta.tokens == 3
    assert meta.latency_ms >= 0


def test_jina_provider_rejects_wrong_dim(monkeypatch):
    """T-31-05 mitigation: server returns wrong-dim vector → ValueError before any write."""
    import httpx
    from app.corpus import embeddings as emb_mod

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.1] * 512, "index": 0}], "usage": {"prompt_tokens": 1}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(emb_mod.httpx, "Client", _Client)
    provider = emb_mod.JinaEmbeddingProvider(api_key="fake-key")
    with pytest.raises(ValueError, match="1024"):
        provider.embed(["hello"])


def test_jina_provider_raises_on_other_http_error(monkeypatch):
    """Non-429 HTTP errors propagate (no silent fallback) — auth, 500, etc."""
    import httpx
    from app.corpus import embeddings as emb_mod

    class _Resp:
        status_code = 500
        text = "server error"

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "500",
                request=httpx.Request("POST", "http://x"),
                response=self,  # type: ignore[arg-type]
            )

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(emb_mod.httpx, "Client", _Client)
    provider = emb_mod.JinaEmbeddingProvider(api_key="fake-key")
    with pytest.raises(httpx.HTTPStatusError):
        provider.embed(["hello"])


def test_get_primary_and_fallback_local_only(monkeypatch):
    """When primary='local', fallback is None (already local)."""
    from app.corpus import embeddings as emb_mod
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "corpus_embedding_primary", "local", raising=False)
    primary, fallback = emb_mod.get_primary_and_fallback()
    assert isinstance(primary, emb_mod.LocalBgeEmbeddingProvider)
    assert fallback is None


def test_get_primary_and_fallback_jina_default(monkeypatch):
    """When primary='jina', fallback is the local BGE provider."""
    from app.corpus import embeddings as emb_mod
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "corpus_embedding_primary", "jina", raising=False)
    monkeypatch.setattr(app_settings, "jina_api_key", "fake", raising=False)
    primary, fallback = emb_mod.get_primary_and_fallback()
    assert isinstance(primary, emb_mod.JinaEmbeddingProvider)
    assert isinstance(fallback, emb_mod.LocalBgeEmbeddingProvider)


def test_jina_provider_repr_does_not_leak_api_key():
    """T-31-07 mitigation: __repr__ never includes the API key."""
    from app.corpus.embeddings import JinaEmbeddingProvider

    p = JinaEmbeddingProvider(api_key="super-secret-key-abc123")
    assert "super-secret-key-abc123" not in repr(p)


def test_local_bge_truncates_when_model_dim_exceeds_1024(monkeypatch):
    """Defensive: if a future local model returns >1024 dim, truncate to lock."""
    import numpy as np
    from app.corpus.embeddings import EMBEDDING_DIM, LocalBgeEmbeddingProvider

    class _StubST:
        def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
            return np.ones((len(texts), EMBEDDING_DIM + 32), dtype="float32")

    p = LocalBgeEmbeddingProvider()
    monkeypatch.setattr(p, "_ensure_loaded", lambda: _StubST())
    vecs, _ = p.embed(["x"])
    assert len(vecs) == 1 and len(vecs[0]) == EMBEDDING_DIM


def test_local_bge_repr_includes_model_name():
    """Repr of the local provider includes the model name (no secrets to leak)."""
    from app.corpus.embeddings import LocalBgeEmbeddingProvider

    p = LocalBgeEmbeddingProvider(model="BAAI/bge-small-en-v1.5")
    assert "BAAI/bge-small-en-v1.5" in repr(p)


def test_default_embedding_primary_matches_the_shipped_corpus():
    """The class default must retrieve the chunks we actually ship.

    Every chunk written by the shipped ingest is embedded by the local BGE
    provider, and both halves of hybrid retrieval filter on that provider
    name. A deploy that configures nothing therefore has to default to the
    local provider — with the old ``jina`` default it got zero rows from
    dense AND FTS, silently: no citations, no error. Checked against the
    class field (not a ``Settings()`` instance) so a developer's ``.env``
    can't mask a bad default.
    """
    from app.config import Settings

    assert Settings.model_fields["corpus_embedding_primary"].default == "local"
