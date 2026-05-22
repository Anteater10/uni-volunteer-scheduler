"""Hybrid retrieval — RRF (k=60) over dense + FTS in ONE SQL round-trip.

Why one round-trip:
- Two retrievers, one Postgres connection. Doing dense + fts as separate
  queries doubles network latency and rules out planner reuse.
- The fusion happens in SQL, not Python: ``COALESCE(1.0/(60+dense.rank), 0)
  + COALESCE(1.0/(60+fts.rank), 0)``. UNION-side-missing is the COALESCE
  default of 0 — a chunk found by only one retriever still gets a score.

Why k=60:
- Cormack/Clarke/Büttcher 2009 (the RRF paper). Stable across corpora;
  the de-facto default in Elasticsearch, Vespa, Weaviate, and the LangChain /
  LlamaIndex ecosystems. Locked in RESEARCH §Pattern 2 + D-03.

Per-provider invariant:
- Both CTEs filter on ``embedding_provider = :provider``. The FTS side
  needs it too because the fused result set MUST be in a single embedding
  space (RESEARCH §Pitfall 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text

_TOP_N_MAX = 100
_PER_RETRIEVER_LIMIT = 20  # RESEARCH §Pattern 2 — Tiger Data default


@dataclass(frozen=True)
class HybridHit:
    """One row of fused hybrid retrieval output."""

    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    char_start: int
    char_end: int
    rrf_score: float


# Single CTE: dense + fts → fusion. Per-provider filter on BOTH sides.
# RRF formula uses k=60 (hard-coded — do not parameterize per RESEARCH §D-03).
# Final ORDER BY id ASC is the deterministic tiebreak (Pitfall 6).
HYBRID_SQL = text(
    f"""
    WITH dense AS (
      SELECT id, document_id, content, char_start, char_end,
             row_number() OVER (ORDER BY embedding <=> :qvec) AS rank
      FROM corpus_chunks
      WHERE embedding_provider = :provider
      ORDER BY embedding <=> :qvec
      LIMIT {_PER_RETRIEVER_LIMIT}
    ),
    fts AS (
      SELECT id, document_id, content, char_start, char_end,
             row_number() OVER (ORDER BY ts_rank_cd(fts, q) DESC) AS rank
      FROM corpus_chunks, plainto_tsquery('english', :qtext) AS q
      WHERE fts @@ q
        AND embedding_provider = :provider
      ORDER BY ts_rank_cd(fts, q) DESC
      LIMIT {_PER_RETRIEVER_LIMIT}
    ),
    fused AS (
      SELECT id FROM dense
      UNION
      SELECT id FROM fts
    )
    SELECT
      f.id,
      COALESCE(d.document_id, t.document_id) AS document_id,
      COALESCE(d.content, t.content)         AS content,
      COALESCE(d.char_start, t.char_start)   AS char_start,
      COALESCE(d.char_end,   t.char_end)     AS char_end,
      COALESCE(1.0 / (60 + d.rank), 0)
        + COALESCE(1.0 / (60 + t.rank), 0)   AS rrf_score
    FROM fused f
    LEFT JOIN dense d USING (id)
    LEFT JOIN fts   t USING (id)
    ORDER BY rrf_score DESC, f.id ASC
    LIMIT :top_n
    """
).bindparams(bindparam("qvec", type_=Vector(1024)))


def hybrid_search(
    session: Any,
    *,
    query_text: str,
    query_embedding: list[float],
    provider: str,
    top_n: int = 20,
) -> list[HybridHit]:
    """Fuse dense + FTS via RRF (k=60) in one SQL round-trip.

    Empty / whitespace ``query_text`` → ``[]`` without DB roundtrip
    (FTS half would be empty; running just dense would silently degrade
    "hybrid" to "dense" which is a contract surprise).
    """
    if not query_text or not query_text.strip():
        return []
    top_n = max(1, min(_TOP_N_MAX, int(top_n)))
    rows = session.execute(
        HYBRID_SQL,
        {
            "qvec": query_embedding,
            "qtext": query_text,
            "provider": provider,
            "top_n": top_n,
        },
    ).all()
    return [
        HybridHit(
            id=r.id,
            document_id=r.document_id,
            content=r.content,
            char_start=r.char_start,
            char_end=r.char_end,
            rrf_score=float(r.rrf_score),
        )
        for r in rows
    ]
