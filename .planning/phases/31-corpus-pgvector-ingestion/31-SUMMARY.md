# Phase 31 — Knowledge Corpus + pgvector Ingestion — SUMMARY

**Status:** ✅ Shipped
**Date completed:** 2026-05-13
**Branch:** `feature/v1.4-phase-31-corpus-pgvector-ingestion`
**Milestone:** v1.4 (AI Onboarding Copilot)

## What shipped

The retrieval substrate that Phase 32 (RAG: hybrid + rerank +
citations) will query. Phase 31 ships no API endpoints by design —
the deliverable is that a `SELECT COUNT(*) FROM corpus_chunks` returns
a four-figure number against the running stack and an EXPLAIN proves
the HNSW index is used.

### Backend

- **Alembic revision `0019_enable_pgvector_corpus_tables`** — enables
  the `vector` extension and creates three tables: `corpus_documents`,
  `corpus_chunks` (with `embedding vector(1024)`), and `ingestion_runs`.
  Round-trip-safe (`upgrade → downgrade → upgrade` clean) thanks to
  `IF NOT EXISTS` / `IF EXISTS` everywhere and explicit FK-reverse
  drop order on downgrade.
- **ORM models** in `backend/app/models.py`: `CorpusDocument`,
  `CorpusChunk`, `IngestionRun`. The chunk model carries the
  `embedding_provider` / `embedding_model` / `char_start` / `char_end`
  affordances that Phase 32 will filter on.
- **New settings** in `backend/app/config.py`:
  `corpus_embedding_dimensions=1024` (locked),
  `corpus_chunker_version="v1-recursive-char-1024-128"`,
  `corpus_embedding_primary="jina"|"local"`,
  `jina_api_key`, `jina_embedding_model`, `local_embedding_model`.
- **New package `backend/app/corpus/`:**
  - `chunker.py` — deterministic recursive character splitter
    (1024 chars / 128 overlap), `char_start`/`char_end` invariants
    pinned by a dedicated test.
  - `walker.py` — allow-list source walker producing five source
    kinds (`markdown`, `alembic_migration`, `python_module`,
    `python_function`, `frontend_component`). Opens no DB
    connections; reads no JSON/CSV. PII deny-by-construction.
  - `embeddings.py` — `EmbeddingProvider` protocol +
    `JinaEmbeddingProvider` (httpx, exponential backoff on 429) +
    `LocalBgeEmbeddingProvider` (sentence-transformers, 384 → 1024
    padding). `RateLimitError` raised on Jina 429 so the orchestrator
    can fall back.
  - `ingest.py` — `run_ingestion` (idempotent on
    `(source_path, content_sha256)`, per-document transactions,
    fallback path), `build_hnsw_index` (idempotent
    `CREATE INDEX IF NOT EXISTS … USING hnsw` + ANALYZE).
  - `__main__.py` — CLI shim. Flags: `--source`, `--commit`,
    `--dry-run`, `--provider {jina,local}`, `--rebuild`,
    `--build-index`.
- **Wired into the compose stack** via the pgvector image swap
  (`postgres:16` → `pgvector/pgvector:pg16`) already in place from
  plan 02; backend image rebuilt to include `sentence-transformers`,
  `torch` CPU, and the `pgvector` Python adapter.

### Tests

- Backend: **48 tests** in `backend/tests/test_corpus_*.py`:
  - `test_corpus_chunker.py` (REQ-31-03, REQ-31-04) — determinism +
    char-offset invariants.
  - `test_corpus_walker.py` (REQ-31-05/06/07) — allow-list / deny-list,
    no-DB-connection introspection, deterministic ordering.
  - `test_corpus_embeddings.py` (REQ-31-11) — dim locked to 1024,
    Jina + BGE padding behaviour.
  - `test_corpus_logger.py` — per-run telemetry logging contract.
  - `test_corpus_ingest_idempotency.py` (REQ-31-08/09/10/14) —
    idempotency on unchanged repo, resumable on mid-run provider
    failure, fallback engages on rate-limit, telemetry columns
    populated.
  - `test_corpus_cli.py` — CLI argument surface + JSON output.
  - `test_corpus_migration_round_trip.py` (REQ-31-01/02) — Alembic
    upgrade → downgrade → upgrade clean against test DB.
  - `test_corpus_hnsw_index.py` (REQ-31-12) — EXPLAIN proves the
    planner uses `ix_corpus_chunks_embedding_hnsw`.
- **100% coverage on `app.corpus.*`** (matches the Phase 30 invariant
  for `app.copilot.*`).

### Documentation (two-folder rule, REQ-31-J)

- `docs/learning/31-corpus-pgvector-ingestion/` — 4 lectures:
  - `01-pgvector-foundations.md` (intuition: extension-as-index;
    HNSW vs IVFFlat; dimensionality lock-in; build-after-ingest)
  - `02-embedding-model-choice.md` (Jina v3 primary; local BGE
    fallback; the padding trick; OpenRouter-for-embeddings rejected)
  - `03-chunking-and-walker.md` (recursive splitter walked through;
    char-offset invariant; allow-list philosophy; determinism)
  - `04-ingestion-telemetry.md` (per-run row; 22 columns in four
    groups; idempotency anchor; fallback recorded in `notes`)
- `docs/documentation/31-corpus-pgvector-ingestion/` — 4 publication
  writeups with the same topic split, citation-ready
  (`[CITED: …]` markers).

## Locked decisions (unchanged from PLAN / RESEARCH)

| Decision | Value | Reason |
|---|---|---|
| Postgres image | `pgvector/pgvector:pg16` | plain `postgres:16` lacks the extension |
| Embedding dim | **1024** (locked) | Jina v3 native; BGE padded; portable to Voyage/Cohere |
| Primary provider | Jina Embeddings v3 (free tier) | 1024 native, MRL, current best free-tier general embeddings |
| Fallback provider | `BAAI/bge-small-en-v1.5` (local, padded) | permanently free, no rate limit, offline-capable |
| NOT OpenRouter for embeddings | rejected | sparse/unstable free-tier; couples chat reliability to ingestion |
| Index type | HNSW with `vector_cosine_ops` | best default for <1M rows; high recall at small `ef` |
| Index timing | post-ingest via `--build-index` | bulk-load + post-index faster than per-row tree update |
| Chunker | recursive char, 1024/128, version `v1-recursive-char-1024-128` | deterministic, tokenizer-agnostic, paper reproducibility |
| Idempotency key | `(source_path, content_sha256)` on documents | content-addressed, no-op on unchanged repo |
| Telemetry | one `ingestion_runs` row per CLI invocation, 22 columns | mirrors Phase 30 discipline; no backfill at Phase 35 |
| No retrieval surface | Phase 31 ships 0 API endpoints | all retrieval / citation work is Phase 32 |

## End-to-end smoke (2026-05-13)

Live run against the running compose stack with the local BGE
provider (offline, deterministic):

```
docker compose run --rm -v $PWD:/repo -w /repo -e PYTHONPATH=/app \
  backend python -m app.corpus.ingest --source . --commit --provider local
docker compose run --rm backend python -m app.corpus.ingest --build-index
```

Final row counts in the `uni_volunteer` database:

```
 n_docs | n_chunks | n_runs_succeeded
--------+----------+------------------
    619 |     4731 |                1
```

All chunks: `vector_dims(embedding) = 1024`. Telemetry row from the
run:

```
embedding_provider:  local-bge
embedding_model:     BAAI/bge-small-en-v1.5+pad1024
embedding_dim:       1024
chunker_version:     v1-recursive-char-1024-128
files_scanned:       619
files_ingested:      619
chunks_emitted:      4731
chunks_embedded:     4731
status:              succeeded
completed_at:        not null
```

HNSW index `ix_corpus_chunks_embedding_hnsw` exists on
`corpus_chunks.embedding` and is provably used by the planner
(`test_corpus_hnsw_index.py::test_hnsw_index_used` green).

## Definition of Done

- [x] REQ-31-01 — Alembic `0019` upgrades clean on the test DB
- [x] REQ-31-02 — Round-trip (`upgrade → downgrade → upgrade`) clean
- [x] REQ-31-03 — Chunker deterministic across runs
- [x] REQ-31-04 — `char_start`/`char_end` invariants pinned
- [x] REQ-31-05 — Walker opens no DB connections
- [x] REQ-31-06 — Walker honors deny-list (no test fixtures, no `.env`)
- [x] REQ-31-07 — Walker emits deterministic lexicographic order
- [x] REQ-31-08 — Idempotency: re-run on unchanged repo is a no-op
- [x] REQ-31-09 — Resumable on mid-run provider failure
- [x] REQ-31-10 — Fallback engages on Jina rate-limit;
      `ingestion_runs.notes` records both providers
- [x] REQ-31-11 — Embedding dim locked to 1024 (Jina native, BGE padded)
- [x] REQ-31-12 — HNSW index built and used by the planner
- [x] REQ-31-13 — Real smoke against live stack produced 619 docs /
      4731 chunks
- [x] REQ-31-14 — All paper-grade columns on `ingestion_runs`
      populated
- [x] REQ-31-A through REQ-31-K — phase-level requirements green
- [x] REQ-31-I — 100% coverage on `app.corpus.*`
- [x] REQ-31-J — 4 learning lectures + 4 publication writeups,
      each ≥ 80 lines

## Known limitations / deferred work

- **No retrieval API surface.** Phase 31 ships zero endpoints. The
  retrieval layer, citation chips, hybrid (lexical + dense) search,
  and rerank are Phase 32.
- **Jina key rotation.** `JINA_API_KEY` lives in `backend/.env`; the
  smoke shipped on the local-BGE path. When Jina goes into the loop
  in production, a personal key is in use that must be rotated
  before a public deploy.
- **HNSW parameter tuning deferred.** Current parameters are the
  pgvector defaults (`m=16, ef_construction=64`). The `ef_search`
  query-time knob is not yet exposed; it will be added in Phase 32
  when the retrieval API can measure recall vs latency.
- **Cross-provider cosine isolation enforced at the retrieval layer,
  not at the schema layer.** Phase 31 leaves `embedding_provider`
  on every chunk; Phase 32 must `WHERE embedding_provider = $1`
  in every cosine query.
- **`docs/copilot-journal/**` inclusion.** The walker is configured
  to ingest the journal; the smoke ran against the full repo and
  included whatever journal entries existed at commit time. Future
  contributors editing the journal must understand that ingestion
  will pick up their edits.
- **CLI ergonomics.** The canonical invocation requires
  `-v $PWD:/repo -w /repo -e PYTHONPATH=/app` to walk the full
  repo. A future improvement is to bake the repo mount and
  `PYTHONPATH` into a helper script under `bin/`.
- **Backend image size.** Adding `torch` CPU wheel + sentence-
  transformers added ~200 MB to the backend image. Acceptable for a
  research deployment; gate behind an `[embeddings]` extra if image
  size becomes a CI concern.

## Files changed (commit chain)

- `1710ef0` — plan 03 task 1: deterministic recursive character chunker
- `c100655` — plan 03 task 2: allow-list source walker
- `fc003b1` — plan 03 SUMMARY
- `2df4072` — plan 04 task 1: Jina v3 + local BGE embedding providers
- `198a2ae` — plan 04 task 2: idempotent corpus ingestion orchestrator
- `c786bd9` — plan 04 task 3: corpus ingestion CLI (`__main__.py`)
- `7063a58` — plan 04 SUMMARY
- `601f0f3` — plan 02: ORM models + corpus_* settings
- `d28f000` — plan 02 SUMMARY (pgvector migration + corpus schema)
- `666df49` — plan 05 task 1: HNSW index used by planner (REQ-31-12)
- `<docs-commit>` — plan 05 task 2: 8 docs (learning + documentation)
- `<state-commit>` — plan 05 task 4: STATE.md refresh + phase SUMMARY

## Handoff to Phase 32

Phase 32 ("RAG retrieval: hybrid + rerank + citations") inherits:

- A populated corpus: 619 documents / 4731 chunks at 1024-dim, with
  an HNSW cosine index already built and ANALYZE'd.
- The `embedding_provider` filter affordance: every cosine query
  must include `WHERE embedding_provider = $1` to avoid cross-
  provider noise after a fallback event.
- The `char_start`/`char_end` columns: citation chips quote exact
  source offsets, not paraphrases.
- The `ingestion_run_id` foreign key on every chunk: Phase 32 can
  group retrieval results by run for reproducibility analyses.
- The `--build-index` CLI flag: idempotent, run after any rebuild.
- The four-pillar documentation in `docs/learning/31-…/` and
  `docs/documentation/31-…/` to anchor the paper's "Retrieval
  infrastructure" methodology section.

Phase 32 should NOT touch:

- The corpus schema (additive migrations only).
- The per-provider cosine isolation invariant.
- The 100% coverage gate on `app.copilot.*` AND `app.corpus.*`.
- The deny-list / allow-list contract on the walker.
