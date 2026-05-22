# Lecture 03 — Cross-encoder rerank, the local-only way

## Why this lecture exists

The hybrid retriever (Plan 32-02) returns the top-20 chunks fused by
RRF from a dense-vector search and a Postgres FTS search. Twenty
chunks is too many to stuff into the LLM prompt, and the ordering at
this point is *coarse* — the dense retriever scores by cosine
similarity in 1024-D embedding space, the FTS retriever scores by
lexical overlap, and RRF combines the two ranks without ever looking
at the *actual semantic relationship* between the user's query and a
chunk's text.

A **reranker** is the second-stage model whose only job is to look at
each (query, chunk) pair and ask: "given the full text of both, how
relevant is this chunk to this query?" That is a different and much
harder model than a bi-encoder retriever, and it is the single piece
of the RAG pipeline that most reliably moves the answer-quality
needle.

This lecture explains what a cross-encoder is, why we run it locally
on CPU instead of calling an API, and the three implementation traps
that the production code in `backend/app/copilot/retrieval/rerank.py`
is designed to step around.

## Bi-encoder vs cross-encoder

A bi-encoder (what we use for dense retrieval) embeds the query and
each chunk **independently**. The score is just the cosine of the two
vectors. This is fast because you can pre-compute and index the chunk
embeddings — at query time you only embed the query and run a vector
search. The downside is that the model never *compares* the two
texts; it just hopes that semantically-similar content lands near
each other in embedding space.

A cross-encoder embeds the **concatenated pair** `[CLS] query [SEP]
chunk [SEP]` and produces a single scalar relevance score. Because
both texts share every transformer layer, the model can do real
token-level attention between query and chunk: a query word that
matches a chunk's pronoun, a negation, a paraphrase, all become
direct attention edges. The downside is that there is no
pre-computation possible — you have to run the model `N` times for
`N` candidates at query time.

The two are not competitors. They are stages: bi-encoder retrieves
fast (~5k chunks down to top-20 in milliseconds), cross-encoder
reranks slowly but precisely (top-20 down to top-5 in ~150-350 ms).

## Why CPU is good enough here

The reranker we chose, `BAAI/bge-reranker-base`, is a 278 MB model
with ~110 M parameters. On the existing backend container's CPU,
`predict()` on a batch of 20 (query, chunk) pairs runs around 150-350
ms p50 according to the published benchmarks
([CITED: medium.com/@xiweizhou/speed-showdown-reranker]). The Phase
30 latency budget is P95 < 12 s for the full streaming chat turn,
dominated by the LLM token stream. Spending ~300 ms on rerank is
nothing.

Could we make it faster with a GPU? Yes. Would we then have to
re-architect the backend container, manage GPU memory, deal with
CUDA driver compatibility, and pay a cloud GPU bill? Also yes. The
honest answer for ~5k chunks and a single-instance deployment is
that CPU rerank is the right operating point.

## The `lru_cache(1)` pattern

The naive implementation looks like this:

```python
def rerank(query, candidates):
    model = CrossEncoder("BAAI/bge-reranker-base")
    return model.predict(...)
```

This is wrong. Every chat turn loads the 278 MB weights from disk and
constructs the transformer object — that's a 2-5 second cold load
*per request*. By the third user message the model has been loaded
and thrown away three times.

The fix is to load it once per worker process and hold it in memory
for the life of the process:

```python
@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    return CrossEncoder("BAAI/bge-reranker-base", max_length=512)
```

`functools.lru_cache(maxsize=1)` is the standard Python pattern for
"compute this expensive thing once, then return the cached copy
forever." Phase 31 used the same trick for the local BGE embedding
model. We deliberately avoid a module-level global because that runs
at *import* time — every pytest collection of every unrelated test
would pay the 278 MB cost. `lru_cache` runs at first *call* time,
which is exactly when we want it.

The singleton property is load-bearing enough that the test suite
asserts it directly. `test_rerank_singleton_model_load` calls
`rerank()` five times with a mocked `CrossEncoder` constructor and
asserts the constructor was invoked **exactly once**. If anyone
refactors `_model` to not be cached, that test fails immediately.

## Why `bge-reranker-base` and not the alternatives

Three reasonable candidates:

| Model                              | Params | Latency  | Quality (English) |
|------------------------------------|--------|----------|-------------------|
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | 22 M  | very fast | mediocre on technical docs |
| `BAAI/bge-reranker-base` (chosen)  | 110 M | ~300 ms   | strong on diverse English |
| `BAAI/bge-reranker-v2-m3`          | 568 M | ~3x slower | strongest, multilingual |

`ms-marco-MiniLM` was trained on web-search queries (TREC MS MARCO).
Our corpus is technical documentation. Domain mismatch hurts.

`bge-reranker-v2-m3` is the strongest model but it's 5x larger and
multilingual — we have an English-only corpus, so we'd pay the cost
of a feature we don't use.

`bge-reranker-base` is the sweet spot: BGE-family training is good on
technical English, the 110 M size fits comfortably in CPU memory next
to the embedding model, and the latency is well within budget.

## Determinism and tiebreaks

Two chunks can score identically — especially with the float16
arithmetic torch uses internally. Without an explicit tiebreak the
order between them depends on Python's sort stability AND the order
the candidates were passed in AND the order the retriever returned
them, none of which are stable across runs.

The fix is a secondary sort key:

```python
scored = sorted(
    zip(candidates, scores),
    key=lambda cs: (-float(cs[1]), str(cs[0]["id"])),
)
```

The negative score gets descending order, and `str(id)` ascending is
the deterministic tiebreaker. The test
`test_rerank_tiebreak_by_id` patches `predict` to return identical
scores for three candidates and asserts the output order matches
sorted-by-id. This is the kind of test that costs ten lines now and
saves you a six-hour "why did the citations change?" investigation
six months from now.

## Quick check

What two stages does the retrieval pipeline have, and which one is
the cross-encoder reranker? What single Python decorator turns a
naive model loader into a process-wide singleton?
