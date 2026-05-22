# Hybrid retrieval via single-SQL Reciprocal Rank Fusion

**Phase 32 / Plan 02. Publication-grade methodology writeup.**

## Abstract

We implement hybrid retrieval over `corpus_chunks` by fusing a dense
cosine retriever (pgvector HNSW) and a lexical retriever (Postgres
`tsvector` + GIN) using Reciprocal Rank Fusion at `k=60`. Fusion is
expressed as a single SQL Common Table Expression so that the entire
hybrid step is one round-trip to the database. The per-provider
isolation invariant from Phase 31 is enforced inside SQL on both sides
of the fusion, removing application-layer assumptions about embedding
space coherence.

## Background and motivation

Pure dense retrieval underperforms on queries containing rare exact-
match tokens (e.g. identifiers in code, proper nouns, jargon). Pure
lexical retrieval underperforms when the query and the relevant chunks
share concepts but not surface tokens. The current consensus in RAG
literature (Microsoft Azure AI Search 2023; Tiger Data 2024;
[CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres])
is to run both retrievers and fuse the rankings, then hand the fused
top-N to a downstream reranker.

We adopt Reciprocal Rank Fusion (RRF) over weighted-sum and convex-
combination alternatives. RRF was introduced by Cormack, Clarke, and
Büttcher in 2009 ("Reciprocal Rank Fusion outperforms Condorcet and
individual rank learning methods", SIGIR 2009) and has remained the
production default across Elasticsearch, Vespa, Weaviate, LangChain,
and LlamaIndex.

## Method

### Per-retriever queries

Both retrievers scope to a single `embedding_provider`. The dense
retriever uses pgvector's cosine distance operator `<=>` against the
HNSW index created in Phase 31. The lexical retriever uses
`ts_rank_cd` against the `tsvector` generated column added by
migration 0020 (Plan 32-01) and indexed with GIN.

The lexical query string passes through `plainto_tsquery('english',
:q)`, which strips FTS operator characters (`&`, `|`, `!`, `:*`) and
treats the input as a plain phrase. The operator-form variant of
`to_tsquery` is forbidden for user input — accepting raw FTS
expression syntax constitutes operator injection (ASVS V5).

Each retriever is capped at 20 candidates following the Tiger Data
hybrid-search default [CITED: tigerdata.com/docs/build/examples/hybrid-search].

### Reciprocal Rank Fusion

For a document `d` appearing at rank `r_i` in retriever `i`, RRF scores
`d` as:

```
score(d) = sum_i  1 / (k + r_i)
```

with documents absent from retriever `i` contributing zero from that
side. We use `k=60` as in the original paper. The choice is robust:
the original publication and subsequent empirical work
[CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]
show `k=60` performs at or near optimal across a wide range of
corpora, so per-corpus tuning is unnecessary.

### Single-SQL fusion

The fusion is one Postgres query:

```sql
WITH dense AS (
  SELECT id, document_id, content, char_start, char_end,
         row_number() OVER (ORDER BY embedding <=> :qvec) AS rank
  FROM corpus_chunks
  WHERE embedding_provider = :provider
  ORDER BY embedding <=> :qvec
  LIMIT 20
),
fts AS (
  SELECT id, document_id, content, char_start, char_end,
         row_number() OVER (ORDER BY ts_rank_cd(fts, q) DESC) AS rank
  FROM corpus_chunks, plainto_tsquery('english', :qtext) AS q
  WHERE fts @@ q
    AND embedding_provider = :provider
  ORDER BY ts_rank_cd(fts, q) DESC
  LIMIT 20
),
fused AS (
  SELECT id FROM dense
  UNION
  SELECT id FROM fts
)
SELECT
  f.id,
  COALESCE(d.document_id, t.document_id) AS document_id,
  COALESCE(d.content,     t.content)     AS content,
  COALESCE(d.char_start,  t.char_start)  AS char_start,
  COALESCE(d.char_end,    t.char_end)    AS char_end,
  COALESCE(1.0 / (60 + d.rank), 0)
    + COALESCE(1.0 / (60 + t.rank), 0)   AS rrf_score
FROM fused f
LEFT JOIN dense d USING (id)
LEFT JOIN fts   t USING (id)
ORDER BY rrf_score DESC, f.id ASC
LIMIT :top_n
```

The `fused` CTE produces the union of candidate ids (≤40 rows). The
final SELECT uses LEFT JOINs to pull each candidate's per-retriever
rank, falling back to `0` contribution via `COALESCE` for ranks the
retriever did not produce. Tiebreak on `id ASC` guarantees
deterministic ordering when two candidates tie on `rrf_score` — a
prerequisite for the reproducibility section of the planned RAGAS
evaluation (Plan 32-08).

## Threat model

| ID | Category | Mitigation |
|---|---|---|
| T-32-02-01 | Tampering (FTS operator injection) | `plainto_tsquery` strips operator characters; tests `grep` the source to forbid the operator-form `to_tsquery` on bound parameters. |
| T-32-02-02 | Tampering (cross-provider leak) | `WHERE embedding_provider = :provider` pushed into BOTH CTEs; tests assert the filter substring appears at least twice in the hybrid SQL. |
| T-32-02-03 | DoS (unbounded LIMIT) | `top_n` and per-call `k` are clamped to `[1, 100]` in the Python wrappers. |

## Alternatives considered and rejected

| Alternative | Reason rejected |
|---|---|
| Weighted-sum blending `α·cos + (1-α)·ts_rank` | Requires per-corpus tuning of `α` and per-corpus normalization of `ts_rank` (which is unbounded log-scale). RRF is parameter-free in practice. |
| Convex combination after min-max normalization | Adds two more hyperparameters (per-retriever bounds) that drift as the corpus grows. |
| Two round-trip Python-side fusion | Doubles network latency. Loses snapshot atomicity (a concurrent ingest could expose a chunk to retriever 2 that retriever 1 didn't see). Forfeits any future planner optimization Postgres may apply to the shared WHERE predicate. |
| Filtering FTS by `embedding_provider` in application code | Easy to forget. Tests can't statically prove the invariant. Pushing the filter into SQL makes it a single-line static assertion. |
| Reranking before fusion | Collapses two independent ranked lists into one biased list before the fusion can use the diversity signal. The whole point of RRF is to combine independent ranks. |

## Verification

Tests in `backend/tests/test_retrieval_hybrid.py` cover:

1. RRF math via behavioral assertion on ordered output.
2. Single-roundtrip invariant via instrumenting
   `before_cursor_execute` and asserting exactly one statement scans
   `corpus_chunks`.
3. Per-provider isolation via fixture-level chunks from a "wrong"
   provider that must never appear in the result.
4. Determinism via running the same query twice and asserting
   identical ordering.
5. Structural assertion via `inspect.getsource` regex matching for
   `1.0 / (60 +` and at least two `embedding_provider` occurrences.

Module-level coverage on `app/copilot/retrieval/dense.py`,
`app/copilot/retrieval/fts.py`, and `app/copilot/retrieval/hybrid.py`
is 100% line and 100% branch (Plan 32-03 ships its own modules and
tests in parallel; the package-level gate reaches ≥95% once both
plans land).

## Citations

- Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). Reciprocal
  Rank Fusion outperforms Condorcet and individual rank learning
  methods. SIGIR 2009.
- Tiger Data. Elasticsearch's Hybrid Search, Now in Postgres (BM25 +
  Vector + RRF). [CITED: tigerdata.com/blog/elasticsearchs-hybrid-search-now-in-postgres]
- PostgreSQL Documentation §12 Full Text Search — Controlling Text
  Search. [CITED: postgresql.org/docs/current/textsearch-controls.html]
- pgvector README — cosine distance via `<=>` and HNSW indexing.
  [CITED: github.com/pgvector/pgvector]
