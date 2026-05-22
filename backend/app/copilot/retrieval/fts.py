"""FTS (tsvector) retrieval with provider filter pushed into SQL.

Two non-negotiable safety constraints:

1. ``plainto_tsquery('english', :q)`` ONLY. The operator-form variant
   interprets ``&``, ``|``, ``!``, ``:*`` as FTS operators and accepts
   user-controlled expression syntax — that is the operator-injection
   class of bug (ASVS V5, RESEARCH §Pitfall 1).

2. ``WHERE embedding_provider = :provider`` — the per-provider invariant
   is enforced even on FTS so the fused result set never includes a
   chunk that lacks a dense score in the active provider's space
   (RESEARCH §Pattern 3, §Pitfall 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from sqlalchemy import text

_K_MAX = 100


@dataclass(frozen=True)
class FtsHit:
    """One row of FTS retrieval output (1-based rank for RRF input)."""

    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    char_start: int
    char_end: int
    rank: int


# Note: ``plainto_tsquery('english', :q)`` is the ONLY allowed form for
# user input here. Operator escaping is automatic.
FTS_SQL = text(
    """
    SELECT id, document_id, content, char_start, char_end,
           row_number() OVER (ORDER BY ts_rank_cd(fts, q) DESC) AS rank
    FROM corpus_chunks, plainto_tsquery('english', :q) AS q
    WHERE fts @@ q
      AND embedding_provider = :provider
    ORDER BY ts_rank_cd(fts, q) DESC
    LIMIT :k
    """
)


def fts_search(
    session: Any,
    *,
    query_text: str,
    provider: str,
    k: int = 20,
) -> list[FtsHit]:
    """Top-``k`` chunks by ``ts_rank_cd``, scoped to ``provider``.

    Short-circuits on empty / whitespace-only input — no DB roundtrip.
    """
    if not query_text or not query_text.strip():
        return []
    k = max(1, min(_K_MAX, int(k)))
    rows = session.execute(
        FTS_SQL,
        {"q": query_text, "provider": provider, "k": k},
    ).all()
    return [
        FtsHit(
            id=r.id,
            document_id=r.document_id,
            content=r.content,
            char_start=r.char_start,
            char_end=r.char_end,
            rank=int(r.rank),
        )
        for r in rows
    ]
