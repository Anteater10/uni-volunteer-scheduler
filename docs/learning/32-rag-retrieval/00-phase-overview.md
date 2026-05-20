# Phase 32 — RAG retrieval: what we learned (overview)

## Why this overview exists

Phase 32 is the seam where the corpus from Phase 31 stops being "a
table full of vectors" and starts being "a thing the model actually
reads from when it answers a question." Seven topic lectures live
under this folder, each focused on one well-bounded concept. This
overview is the map that ties them together — read it first if you
are coming to the phase cold, then dive into whichever lecture
matches the question you walked in with.

The mental model worth holding the whole time you read these lectures
is this: **retrieval is a pipeline of cheap stages followed by
expensive ones, and the only way that math works is if each stage
throws out enough candidates to make the next stage's cost bearable.**
Dense ANN throws out the global corpus and gives you ~50 candidates.
FTS does the same from the lexical angle. RRF picks the ~15-30 best
across both. The cross-encoder rerank reads all 30 in full and reorders
them. The model only ever sees the top 5. Every stage exists because
the next one would be too expensive to run on what came before.

## The seven lectures

1. **[01 — Full-text search in Postgres, the boring-but-correct way](./01-fts-in-postgres.md)** —
   what `tsvector` actually is, why `english` and not `simple`, why
   `GENERATED ALWAYS AS … STORED` beats a trigger, why GIN and not
   GiST for an append-mostly corpus. The substrate for everything that
   follows.
2. **[02 — Hybrid retrieval with Reciprocal Rank Fusion](./02-hybrid-retrieval-rrf.md)** —
   why dense search and lexical search disagree productively, why RRF
   at k=60 is the right fusion default, and why we do it in one SQL
   CTE instead of two round-trips with application-layer merging.
3. **[03 — Cross-encoder rerank: the second pass that earns its keep](./03-cross-encoder-rerank.md)** —
   what a cross-encoder actually computes that a bi-encoder cannot,
   why we run it locally (`BAAI/bge-reranker-base`) instead of calling
   a rerank API, and what the cold-start cost looks like in practice.
4. **[04 — The `event: meta` SSE frame](./04-sse-meta-event.md)** —
   how to add a new SSE event type without breaking an existing
   stream consumer, why we ship the meta frame before the first
   token, and what the latency budget on it looks like.
5. **[05 — Citations endpoint](./05-citations-endpoint.md)** — what
   the click-through endpoint returns, why UUID validation lives at
   the route layer, why an empty `document_url` is allowed (and what
   the frontend does with it), and why this endpoint is read-only.
6. **[06 — Citation chips in the frontend](./06-citation-chips-frontend.md)** —
   what a `CitationChip` is, why the side-panel is keyboard-navigable,
   why the per-message snapshot matters for multi-turn coherence, and
   how to test the chips in Playwright across all six browser
   projects.
7. **[07 — RAGAS rerank-lift methodology](./07-ragas-methodology.md)** —
   what RAGAS is, what `context_precision` and `context_recall`
   actually measure, why we froze a 30-question testset, and how the
   `metric,rerank_off,rerank_on,lift` CSV becomes the figure that
   substantiates the paper's rerank claim.

## What ties them together

If you read the lectures in order you walk through the request lifecycle:

```
user types question
        │
        ▼
Lecture 02 — hybrid retrieval issues ONE SQL query
        │   ├── Lecture 01: FTS branch (tsvector @@ to_tsquery)
        │   └── (existing) HNSW branch (vector <=> embedding)
        │        ── fused with RRF at k=60 ──
        ▼
Lecture 03 — cross-encoder rerank reorders the top ~30 → top 5
        │
        ▼
Lecture 04 — SSE `event: meta` ships the 5 citations BEFORE the first token
        │
        ▼
Lecture 06 — frontend renders 5 chips above the answer
        │
        ▼
user clicks a chip
        │
        ▼
Lecture 05 — citations endpoint returns the exact quote + optional URL
```

And separately, on a once-a-paper cadence:

```
Lecture 07 — RAGAS harness replays the pipeline twice (rerank ON / OFF)
        ──────────────► CSV + PNG that lives in docs/documentation/32-…
```

## The five lessons we keep relearning

These showed up across multiple lectures. They are worth memorising
because they cost real hours when we forgot them.

1. **Filter in SQL, not in Python.** Every cosine and every FTS query
   carries `WHERE embedding_provider = $1`. If a fallback ever
   happens, chunks from the old provider must not pollute results
   from the new provider. The cleanest place to enforce that is the
   SQL string itself — application-layer filters get forgotten on the
   second function that needs them.
2. **Additive beats invasive.** The `event: meta` frame is a new
   event type, not a change to the existing `token` / `done` /
   `error` shapes. The `corpus_chunks.fts` column is a GENERATED
   ADD COLUMN, not a backfill script. Both choices mean a rollback
   is a drop, not a state-reconstruction job.
3. **Local cheap models beat remote expensive ones for this layer.**
   `BAAI/bge-reranker-base` is ~110 MB and reranks 30 candidates in
   ~100-500ms warm. A rerank API call is two network hops, a key
   rotation surface, and a billing line. The local model wins on
   every dimension that matters at our scale.
4. **Cold start is a one-time event, not a per-request cost.** The
   first request after backend boot loads the cross-encoder weights
   into RAM (~200s on our dev box). Every subsequent request is sub-
   second. Treat cold start as a deploy concern, not a latency
   regression.
5. **Per-message snapshots, not shared state.** When the user asks a
   second question, the citation chips for the first answer have to
   stay attached to that first answer. A naive shared "current
   citations" piece of state will scrub the history. We snapshot the
   chips into the message object the moment `event: meta` arrives.

## What to read next after this folder

- The companion **publication writeups** in
  `docs/documentation/32-rag-retrieval/`. Same seven topics, but
  written for a paper-grade audience instead of a teaching tone, with
  inline `[CITED: …]` markers ready to slot into the v1.4 paper.
- The phase **SUMMARY** at
  `.planning/phases/32-rag-retrieval/32-SUMMARY.md` for the shipped
  scope, REQ ticks, measured latencies, and the handoff to Phase 33.
- The **rerank-lift CSV/PNG** under
  `docs/documentation/32-rag-retrieval/` once Andy's offline run
  populates real numbers.

## Status

Phase 32 shipped 2026-05-20. Live smoke green. Coverage gates green.
Next phase is 33 (tool calling + ReAct loop — paper contribution #1).
