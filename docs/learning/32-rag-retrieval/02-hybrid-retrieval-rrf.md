# Lecture 32-02 — Hybrid retrieval and Reciprocal Rank Fusion

Phase 32, plan 02. Audience: future-Andy who wants to remember WHY we
fused two retrievers in one SQL query instead of either ranking on its
own.

## Why two retrievers, not one

Pure dense retrieval (cosine similarity over embeddings) is great at
*semantic* matches: "How do I sign up for an event?" pulls back chunks
about volunteer registration even if those chunks never literally
contain the word "sign up". Embeddings are trained to put synonyms,
paraphrases, and topically-related sentences near each other in the
1024-dimensional vector space.

But embeddings have a known weakness: rare exact-match terms. A query
like `magic_link_token` (a code identifier in our docstrings) lands
nowhere meaningful in semantic space — there is nothing it is *like*.
Lexical retrievers, on the other hand, light up immediately when the
exact token appears.

The fix everyone in 2024-2026 RAG converged on is **hybrid retrieval**:
run both, fuse the rankings, hand the top-N to a reranker. The fused
list catches everything either retriever alone would have missed.

## RRF in one paragraph

Reciprocal Rank Fusion is a one-line formula:

```
score(doc) = sum over retrievers of 1 / (k + rank_of_doc_in_that_retriever)
```

That's it. If a doc shows up rank-1 in BOTH retrievers, with `k=60`,
its score is `1/61 + 1/61 ≈ 0.0328`. If it shows up rank-1 in one and
not at all in the other, its score is `1/61 ≈ 0.0164`. Rank-2 + rank-2
is `2/62 ≈ 0.0323` — JUST below double-rank-1.

The genius is what RRF leaves out: scores. ts_rank_cd is unbounded
(log-scale), cosine distance is `[0, 2]`. Trying to add them naively is
nonsense — you'd need to normalize, pick weights, and re-tune every
time the corpus changes. RRF skips all that by using only the *ranks*,
which are universally comparable.

## Why k=60

Picked by Cormack/Clarke/Büttcher in the 2009 RRF paper. They tested
across many TREC corpora and `k=60` was robustly the best or
indistinguishable-from-best. Sixteen years later it remains the default
in Elasticsearch, Vespa, Weaviate, LangChain, LlamaIndex, and Tiger
Data's Postgres hybrid demos.

Intuition: `k` damps the tail. Small `k` means rank-1 dominates and
rank-50 is nearly invisible; large `k` flattens the curve so rank-50
matters almost as much as rank-1. `k=60` is the sweet spot where the
top of each ranked list pulls strongly but rare-but-relevant rank-30s
still contribute.

We hard-code `k=60` in the SQL. Tests `grep` for the literal `1.0 / (60`
substring so a future refactor cannot silently change it without
tripping the test suite.

## The per-provider invariant — even on the FTS side

Phase 31 set up `corpus_chunks` to hold embeddings from MULTIPLE
providers — the active Jina v3 provider AND a local-bge fallback for
the offline path. Phase 31's SUMMARY made this an INVARIANT: every
cosine query MUST include `WHERE embedding_provider = :provider`.
Otherwise you cosine-compare across embedding spaces, which produces
nonsense distances.

The non-obvious part is: the FTS side needs the same filter. FTS is
lexical, so the embedding space doesn't matter for the ranking itself —
"orientation" matches "orientation" no matter who embedded the chunk.
But the FUSED result set must be coherent. If FTS returns a `local-bge`
chunk and dense returns only `jina-v3-embeddings` chunks, the reranker
downstream is going to score a chunk that has no peer in the dense
space. Worse: future analyses (rerank-lift, citation traceability)
assume every retrieved chunk has a valid dense score. The cleanest fix
is to push the filter into the FTS SQL too. One SQL line, one
guarantee.

This is RESEARCH §Pattern 3 and §Pitfall 3 in one move.

## Walking the single SQL CTE

```sql
WITH dense AS (
  SELECT id, ..., row_number() OVER (ORDER BY embedding <=> :qvec) AS rank
  FROM corpus_chunks
  WHERE embedding_provider = :provider
  ORDER BY embedding <=> :qvec
  LIMIT 20
),
fts AS (
  SELECT id, ..., row_number() OVER (ORDER BY ts_rank_cd(fts, q) DESC) AS rank
  FROM corpus_chunks, plainto_tsquery('english', :qtext) AS q
  WHERE fts @@ q
    AND embedding_provider = :provider
  ORDER BY ts_rank_cd(fts, q) DESC
  LIMIT 20
),
fused AS (SELECT id FROM dense UNION SELECT id FROM fts)
SELECT f.id, COALESCE(...), 
       COALESCE(1.0/(60+d.rank), 0) + COALESCE(1.0/(60+t.rank), 0) AS rrf_score
FROM fused f LEFT JOIN dense d USING(id) LEFT JOIN fts t USING(id)
ORDER BY rrf_score DESC, f.id ASC
LIMIT :top_n
```

- `dense` CTE: top-20 chunks by cosine, scoped to the active provider.
- `fts` CTE: top-20 chunks by tsvector, also scoped to the active
  provider, using `plainto_tsquery` (operator-escaping form — never
  `to_tsquery` with raw user input).
- `fused` CTE: UNION of the two id sets (deduped). About 20-40 ids.
- Final SELECT: for each fused id, pull its dense rank (or NULL if
  only FTS found it), pull its fts rank (or NULL if only dense found
  it), and compute `1/(60+rank)` for each side. `COALESCE(..., 0)`
  means a missing-side contributes zero. Sum those two terms — that's
  the RRF score.
- Tiebreak by `f.id ASC` so identical scores produce a deterministic
  order. Critical for reproducibility (RESEARCH §Pitfall 6).

The whole thing is one Postgres round-trip. No app-layer python loop
calling dense_search and fts_search and zip-fusing. The test
`test_hybrid_uses_single_sql_roundtrip` instruments SQLAlchemy's
`before_cursor_execute` event and asserts exactly one statement
touches `corpus_chunks` — that's the load-bearing constraint.

## Why fusion in SQL beats fusion in Python

1. Latency. Two round-trips = two TCP exchanges with the DB; one
   round-trip = one. Negligible for one query, real over thousands.
2. Atomicity. Both retrievers see the same snapshot of the table. If
   ingest runs concurrently with retrieval, the Python-side fusion
   could see a chunk in dense that wasn't yet visible to fts.
3. Coverage. The test surface is tighter. Move fusion to Python and
   you have to test fusion math AND mocking the SQL responses; in SQL
   you just test the SQL.
4. Future planner optimization. Postgres MIGHT (in some future version)
   notice the two CTEs share the same `WHERE embedding_provider`
   predicate and fold the index scan. App-side fusion gives the
   planner nothing to fold.

## Check-in question

Suppose a query returns the same chunk at rank 3 from dense and rank
17 from FTS. What is its RRF score with `k=60`?

(Answer: `1/(60+3) + 1/(60+17) = 1/63 + 1/77 ≈ 0.0159 + 0.0130 ≈
0.0289`. A doc at rank 1 from one retriever only would score `1/61 ≈
0.0164` — so being a strong rank-3-then-decent-rank-17 BEATS being a
spectacular rank-1 in only one retriever. That's the whole point.)
