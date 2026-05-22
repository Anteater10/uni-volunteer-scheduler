"""Phase 32 retrieval package.

Plan 32-02 ships the SQL-layer retrievers — ``dense_search``,
``fts_search``, ``hybrid_search`` — with RRF (k=60) fusion in one SQL
round-trip (see ``hybrid.py``).

Plan 32-03 ships the local cross-encoder reranker (:func:`rerank`) and
pydantic citation conversion (:func:`chunks_to_citations`).
"""
from __future__ import annotations

from .citations import chunks_to_citations
from .dense import DenseHit, dense_search
from .fts import FtsHit, fts_search
from .hybrid import HybridHit, hybrid_search
from .rerank import rerank

__all__ = [
    "DenseHit",
    "FtsHit",
    "HybridHit",
    "chunks_to_citations",
    "dense_search",
    "fts_search",
    "hybrid_search",
    "rerank",
]
