"""Pluggable embedding providers for the Phase 31 corpus pipeline.

Two implementations, both locked to the schema column dim ``vector(1024)``
on ``corpus_chunks``:

* :class:`JinaEmbeddingProvider` — Jina v3 over the public free-tier HTTPS
  API. Native 1024-dim. Raises :class:`RateLimitError` on HTTP 429 so the
  ingest orchestrator can transparently switch to the local fallback
  (mirrors the primary→fallback discipline in :mod:`app.copilot.llm`).
* :class:`LocalBgeEmbeddingProvider` — ``sentence-transformers`` running the
  ``BAAI/bge-small-en-v1.5`` model in-process. Native 384-dim, right-padded
  with zeros to 1024 so it can co-exist in the same ``vector(1024)`` column
  as Jina vectors. **Cross-provider cosine comparisons are not meaningful;**
  Phase 32 retrieval must filter by ``embedding_provider``.

The model is lazy-loaded on first :meth:`embed` call to keep import cheap
(model weights are ~130 MB, downloaded once per container into the HF
cache directory).
"""

from __future__ import annotations

import time
from typing import NamedTuple, Protocol

import httpx
import numpy as np

from ..config import settings


EMBEDDING_DIM = 1024  # locked, matches Vector(1024) on corpus_chunks


_JINA_URL = "https://api.jina.ai/v1/embeddings"
_BGE_NATIVE_DIM = 384  # BAAI/bge-small-en-v1.5 (documentation constant)


class RateLimitError(RuntimeError):
    """Raised by the Jina provider on HTTP 429 so callers can fall back."""


class EmbedMeta(NamedTuple):
    """Per-call telemetry returned alongside the embedding vectors."""

    provider: str  # 'jina' | 'local-bge'
    model_id: str  # 'jina-embeddings-v3' | 'BAAI/bge-small-en-v1.5+pad1024'
    api_calls: int
    latency_ms: int
    tokens: int  # 0 for local; provider-reported for Jina


class EmbeddingProvider(Protocol):
    name: str
    model_id: str

    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]: ...


class JinaEmbeddingProvider:
    """Jina v3 HTTPS provider. 1024-dim native; raises on 429 for fallback."""

    name = "jina"

    def __init__(self, api_key: str, model: str = "jina-embeddings-v3") -> None:
        self._api_key = api_key
        self.model_id = model

    def __repr__(self) -> str:  # T-31-07: never include the key
        return f"JinaEmbeddingProvider(model_id={self.model_id!r})"

    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]:
        started = time.monotonic()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {"model": self.model_id, "input": list(texts)}
        with httpx.Client(timeout=settings.copilot_request_timeout_seconds) as client:
            resp = client.post(_JINA_URL, json=body, headers=headers)
        if resp.status_code == 429:
            raise RateLimitError(f"Jina rate-limited: {getattr(resp, 'text', '')!r}")
        resp.raise_for_status()
        payload = resp.json()

        rows: list[list[float]] = []
        for entry in payload.get("data", []):
            vec = entry.get("embedding") or []
            if len(vec) != EMBEDDING_DIM:
                raise ValueError(
                    f"Jina returned embedding of length {len(vec)}; expected {EMBEDDING_DIM}"
                )
            rows.append([float(x) for x in vec])

        usage = payload.get("usage") or {}
        tokens = int(usage.get("prompt_tokens", 0) or 0)
        latency_ms = int((time.monotonic() - started) * 1000)
        meta = EmbedMeta(
            provider=self.name,
            model_id=self.model_id,
            api_calls=1,
            latency_ms=latency_ms,
            tokens=tokens,
        )
        return rows, meta


class LocalBgeEmbeddingProvider:
    """Local sentence-transformers fallback. 384-dim native, padded to 1024."""

    name = "local-bge"

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model = model
        self.model_id = f"{model}+pad1024"
        self._st_model = None  # lazy

    def __repr__(self) -> str:
        return f"LocalBgeEmbeddingProvider(model={self.model!r})"

    def _ensure_loaded(self):
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer  # heavy import

            self._st_model = SentenceTransformer(self.model)
        return self._st_model

    def embed(self, texts: list[str]) -> tuple[list[list[float]], EmbedMeta]:
        started = time.monotonic()
        model = self._ensure_loaded()
        arr = model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        # encode() returns shape (N, native_dim). Right-pad (or truncate)
        # to ``EMBEDDING_DIM`` so vectors live in the locked ``vector(1024)``
        # column regardless of the underlying local model.
        native = arr.shape[1]
        if native < EMBEDDING_DIM:
            padded = np.pad(arr, ((0, 0), (0, EMBEDDING_DIM - native)), "constant")
        else:
            padded = arr[:, :EMBEDDING_DIM]

        latency_ms = int((time.monotonic() - started) * 1000)
        meta = EmbedMeta(
            provider=self.name,
            model_id=self.model_id,
            api_calls=0,
            latency_ms=latency_ms,
            tokens=0,
        )
        return padded.tolist(), meta


def get_primary_and_fallback() -> tuple[EmbeddingProvider, EmbeddingProvider | None]:
    """Return ``(primary, fallback)`` based on :mod:`app.config` settings.

    * ``corpus_embedding_primary='jina'`` → Jina primary + Local BGE fallback.
    * ``corpus_embedding_primary='local'`` → Local BGE only (no fallback —
      we're already at the safest provider).
    """
    primary_name = settings.corpus_embedding_primary
    if primary_name == "jina":
        primary: EmbeddingProvider = JinaEmbeddingProvider(
            api_key=settings.jina_api_key, model=settings.jina_embedding_model
        )
        fallback: EmbeddingProvider | None = LocalBgeEmbeddingProvider(
            model=settings.local_embedding_model
        )
        return primary, fallback
    return LocalBgeEmbeddingProvider(model=settings.local_embedding_model), None


__all__ = [
    "EMBEDDING_DIM",
    "EmbedMeta",
    "EmbeddingProvider",
    "JinaEmbeddingProvider",
    "LocalBgeEmbeddingProvider",
    "RateLimitError",
    "get_primary_and_fallback",
]
