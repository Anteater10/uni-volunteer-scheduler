# Phase 32 — RAG retrieval: what we shipped (overview)

**Phase:** 32 — RAG retrieval (hybrid + local rerank + citations)
**Milestone:** v1.4 — AI Onboarding Copilot
**Shipped:** 2026-05-20
**Branch:** `feature/v1.4-phase-32-rag-retrieval`

## TL;DR

Phase 32 turns the Phase-31 corpus (6,054 chunks, 1024-dim
embeddings, local-bge provider) into a grounded answer surface for
the copilot. The shipped pipeline is:

```
question ─► hybrid retrieval (dense + FTS + RRF, one SQL CTE)
        ─► local CrossEncoder rerank (BAAI/bge-reranker-base)
        ─► top-5 citations
        ─► SSE `event: meta` frame BEFORE the first token
        ─► frontend chips + side-panel + click-through endpoint
```

Plus an offline RAGAS rerank-lift harness that drives the pipeline
twice (rerank ON / OFF) and emits the CSV + PNG artifact the v1.4
paper cites as evidence for the rerank claim.

## Documents in this folder

This overview indexes seven topic writeups, each one a reference-
style writeup of a single design surface in Phase 32:

| # | Document | Subsystem | Surface |
|---|---|---|---|
| 01 | [FTS in Postgres](./01-fts-in-postgres.md) | Storage | `corpus_chunks.fts` tsvector GENERATED column + GIN index (Alembic `0020`) |
| 02 | [Hybrid retrieval with RRF](./02-hybrid-retrieval-rrf.md) | Retrieval | `app.copilot.retrieval.hybrid` — dense + FTS fused in one SQL CTE at k=60 |
| 03 | [Cross-encoder rerank](./03-cross-encoder-rerank.md) | Retrieval | `app.copilot.retrieval.rerank` — `BAAI/bge-reranker-base`, local only (constraint C6) |
| 04 | [SSE `event: meta`](./04-sse-meta-event.md) | API | Additive SSE frame carrying the 5-citation payload before the first token |
| 05 | [Citations endpoint](./05-citations-endpoint.md) | API | `GET /api/v1/copilot/citations/{chunk_id}` — read-only click-through with UUID validation |
| 06 | [Citation chips frontend](./06-citation-chips-frontend.md) | Frontend | `CitationChip` + `CitationPanel` + `useCopilotStream` meta-event branch + Playwright spec |
| 07 | [RAGAS methodology](./07-ragas-methodology.md) | Eval | `scripts/eval_rerank_lift.py` — frozen 30-Q testset + rerank-lift CSV/PNG |

Two artifact files live alongside:

- `rerank-lift.csv` — paper-locked column header
  `metric,rerank_off,rerank_on,lift`. Ships with shape-correct
  placeholders pending Andy's offline run.
- `rerank-lift.png` — matplotlib figure rendered from the CSV. Same
  status as the CSV.

## Shipped surfaces (one-line reference)

### Backend

- **Migration** `backend/alembic/versions/0020_add_corpus_chunk_fts_column.py`
  adds `corpus_chunks.fts tsvector GENERATED ALWAYS AS
  (to_tsvector('english', coalesce(content,''))) STORED` and
  `ix_corpus_chunks_fts USING GIN (fts)`. Round-trip safe.
- **Retrieval package** `backend/app/copilot/retrieval/`:
  - `dense.py` — HNSW cosine, top-K, per-provider filter in SQL.
  - `fts.py` — `plainto_tsquery('english', :q)`, top-K, per-provider
    filter in SQL.
  - `hybrid.py` — single SQL CTE fusing both with RRF at k=60.
  - `rerank.py` — `CrossEncoder("BAAI/bge-reranker-base")`, model
    loaded lazily on first call.
  - `citations.py` — `Citation` Pydantic model used by both the SSE
    meta frame and the click-through endpoint.
- **Router wiring** `backend/app/copilot/router.py`:
  - `<retrieved_context>` block appended to the Phase-30 system
    prompt (persona / refusal / role-differentiation scaffolding
    untouched).
  - `event: meta` emitted before the LLM round-trip starts.
  - `GET /api/v1/copilot/citations/{chunk_id}` — UUID-validated
    click-through.
- **LLM helper** `backend/app/copilot/llm.py`:
  - `stream_completion_blocking` added for the RAGAS harness (the
    streaming path is unchanged).

### Frontend

- `frontend/src/components/copilot/CitationChip.jsx` — `[N] filename`
  label, accessible tooltip, keyboard-focusable.
- `frontend/src/components/copilot/CitationPanel.jsx` — side-panel
  modal with "Source consulted" header, exact-quote body, optional
  external link (suppressed when `document_url` is empty).
- `frontend/src/hooks/useCopilotStream.js` — `event: meta` branch
  handled additively; per-message citation snapshot keeps multi-turn
  history coherent.
- `frontend/e2e/copilot-citations.spec.js` — Playwright smoke
  covered by all 6 browser projects via the default `testMatch`
  glob.

### Eval

- `scripts/eval_rerank_lift.py` — drives the pipeline twice (rerank
  ON / OFF) over the frozen testset, emits CSV + PNG.
- `scripts/generate_testset.py` — RAGAS `TestsetGenerator` in
  batches of 5 with sleeps to respect Pitfall 4 in the RAGAS
  research notes.
- `backend/requirements-eval.txt` — `ragas==0.4.3`, `datasets`,
  `matplotlib` pinned in a separate extras file so the request-path
  image stays slim.
- `backend/tests/test_eval_script_smoke.py` — CI smoke guarding
  artifact shape via `pytest.importorskip("ragas")`.

## Operational notes

- `backend/.env` must set `CORPUS_EMBEDDING_PRIMARY=local` on the dev
  box to match the corpus that was ingested at Phase 31.
- The FTS layer lives in core Postgres — no new extension; pgvector
  was already enabled at Phase 31.
- Eval extras (`ragas`, `datasets`, `matplotlib`) are intentionally
  NOT in the request-path image. Install only when running the
  offline harness.

## Measured properties (live smoke 2026-05-20)

| Property | Value |
|---|---|
| Retrieval latency (cold) | 3,305 ms |
| Rerank latency (cold, model load into RAM) | 202,041 ms (one-time) |
| Retrieval latency (warm) | ~50–200 ms |
| Rerank latency (warm) | ~100–500 ms |
| `event: meta` dispatch | < 50 ms (Q1 budget) |
| Citation chips rendered | 5 (per Open Question #2) |
| Coverage: `app.copilot` | 99.38% |
| Coverage: `app.copilot.retrieval` | 100.00% |
| Coverage: `app.corpus` | 98.51% |
| Backend test suite | 538–550 passed |
| Frontend test suite | 243 passed |

## Invariants honored

- **Additive migrations only** — no edits to existing `corpus_*`
  schema. (Phase 31 handoff invariant.)
- **Per-provider cosine isolation pushed into SQL** on every cosine
  AND every FTS query. (Phase 31 invariant extended to lexical.)
- **Local rerank only** — no Jina / Cohere / Voyage / external rerank
  API. (Constraint C6.)
- **Phase-30 SSE taxonomy preserved** — `event: meta` is a strict
  addition to `token` / `done` / `error`.
- **Per-package coverage ≥ 95%** on `app.copilot.*`,
  `app.copilot.retrieval.*`, `app.corpus.*`, line + branch blended,
  pinned by a regression test.
- **Two-folder rule** — every plan ships a paired
  `docs/learning/32-rag-retrieval/NN-…md` +
  `docs/documentation/32-rag-retrieval/NN-…md`.

## Handoff to Phase 33

Phase 33 (Tool calling + ReAct loop — paper contribution #1)
inherits the hybrid retrieval modules under `app.copilot.retrieval`,
the `event: meta` SSE frame, the per-provider invariant in SQL, the
working citation chip UX, and the RAGAS harness scaffold. Phase 33
must NOT touch the corpus schema, the `event: meta` shape, or the
Phase-30 SSE taxonomy. See `.planning/phases/32-rag-retrieval/
32-SUMMARY.md` for the full handoff list.

## Status

Phase 32 shipped 2026-05-20. Live smoke green. Coverage gates green.
Ready for Phase 33.
