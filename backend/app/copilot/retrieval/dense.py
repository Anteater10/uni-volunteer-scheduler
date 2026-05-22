"""Cosine (dense) retrieval over ``corpus_chunks`` with the per-provider
filter pushed into SQL (RESEARCH §Pattern 3 — the invariant must be a
SQL-level guarantee, not an application-layer hope).

Every cosine SQL touch MUST include ``WHERE embedding_provider = :provider``.
That line is load-bearing: cross-embedding-space cosine values are
meaningless. Phase 31 SUMMARY flagged this as INVARIANT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text

# Per-call k clamp — caller may pass anything; we cap. Threat T-32-02-03.
_K_MAX = 100


@dataclass(frozen=True)
class DenseHit:
    """One row of cosine retrieval output.

    ``rank`` is 1-based within this retriever, used as the input to RRF.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    char_start: int
    char_end: int
    rank: int


# NOTE: every cosine SELECT must keep ``WHERE embedding_provider = :provider``.
# Tests `grep` for this substring; do not refactor it into a Python-side
# filter without updating the threat-model + tests.
DENSE_SQL = text(
    """
    SELECT id, document_id, content, char_start, char_end,
           row_number() OVER (ORDER BY embedding <=> :qvec) AS rank
    FROM corpus_chunks
    WHERE embedding_provider = :provider
    ORDER BY embedding <=> :qvec
    LIMIT :k
    """
).bindparams(bindparam("qvec", type_=Vector(1024)))


def dense_search(
    session: Any,
    *,
    query_embedding: list[float],
    provider: str,
    k: int = 20,
) -> list[DenseHit]:
    """Top-``k`` chunks by cosine distance, scoped to ``provider``.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Live session bound to the corpus database.
    query_embedding : list[float]
        1024-dim vector for the query (must come from the SAME provider
        as ``provider`` — caller's responsibility).
    provider : str
        ``embedding_provider`` value to filter on (e.g. ``"local-bge"``,
        ``"jina-v3-embeddings"``).
    k : int
        Maximum results. Clamped to ``[1, 100]`` (DoS mitigation).
    """
    k = max(1, min(_K_MAX, int(k)))
    rows = session.execute(
        DENSE_SQL,
        {"qvec": query_embedding, "provider": provider, "k": k},
    ).all()
    return [
        DenseHit(
            id=r.id,
            document_id=r.document_id,
            content=r.content,
            char_start=r.char_start,
            char_end=r.char_end,
            rank=int(r.rank),
        )
        for r in rows
    ]
