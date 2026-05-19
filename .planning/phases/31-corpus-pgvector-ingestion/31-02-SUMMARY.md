---
phase: 31
plan: 02
subsystem: corpus-substrate
tags: [pgvector, alembic, schema, orm, config, wave1]
dependency_graph:
  requires:
    - 31-01 (pgvector image + python deps baked into backend)
  provides:
    - "alembic head = 0019_enable_pgvector_corpus_tables"
    - "vector extension enabled on uni_volunteer + test_uvs"
    - "corpus_documents (8 cols), corpus_chunks (13 cols, embedding vector(1024)), ingestion_runs (23 cols)"
    - "ORM classes CorpusDocument / CorpusChunk / IngestionRun importable from app.models"
    - "Settings.corpus_* (8 fields) + jina_api_key + jina_embedding_model + local_embedding_model"
  affects:
    - backend/alembic/versions/
    - backend/app/models.py
    - backend/app/config.py
    - backend/tests/conftest.py (alembic_engine + alembic_command fixtures)
tech_stack:
  added:
    - "pgvector.sqlalchemy.Vector (already in deps from 31-01; first ORM use)"
  patterns:
    - "schema first, code second (mirrors Phase 30: 0018 migration then models then router)"
    - "IF NOT EXISTS / IF EXISTS on extension to avoid CLAUDE.md-flagged enum-style round-trip leak"
    - "HNSW index intentionally deferred — built post-bulk-load via plan 04 --build-index"
key_files:
  created:
    - backend/alembic/versions/0019_enable_pgvector_corpus_tables.py
    - .planning/phases/31-corpus-pgvector-ingestion/31-02-SUMMARY.md
  modified:
    - backend/app/models.py
    - backend/app/config.py
    - backend/tests/conftest.py
    - backend/tests/test_corpus_migration_round_trip.py
decisions:
  - "atttypmod for vector(N) in pgvector 0.8.x is N (not N+4 as the plan asserted) — third migration test asserts format_type == 'vector(1024)' which is dim-encoding-agnostic"
  - "embedding_latency_ms_total uses sa.BigInteger in the migration AND ORM (plan suggested Integer in ORM was fine; using BigInteger keeps types honest end-to-end since a long-running ingest can blow past 2.1B ms)"
  - "alembic_engine fixture wipes the public schema before binding so backend/conftest.py's Base.metadata.create_all from a prior session does not collide with migration CREATE TABLE"
metrics:
  duration_minutes: ~10
  completed: 2026-05-11
  tasks_completed: 2
  files_changed: 5
requirements_completed:
  - REQ-31-01  # 0019 upgrade green on test DB
  - REQ-31-02  # round-trip clean
---

# Phase 31 Plan 02: pgvector Migration + Corpus Schema Summary

**One-liner:** Shipped Alembic 0019 (slug form) — `CREATE EXTENSION IF NOT EXISTS vector` plus the three corpus tables (`ingestion_runs`, `corpus_documents`, `corpus_chunks` with `embedding vector(1024)`), mirrored the ORM classes in `app.models`, locked the 8 `corpus_*` config defaults, and flipped the Wave 0 migration xfails to a 3-test green suite.

## What Shipped

### Task 1 — Alembic 0019 + round-trip tests (commit `5f49845`)

- **`backend/alembic/versions/0019_enable_pgvector_corpus_tables.py`** — slug-form revision, `down_revision = "0018_copilot_sessions_and_messages"`.
  - `upgrade()`: `CREATE EXTENSION IF NOT EXISTS vector` → `ingestion_runs` (created first because it is the FK target) → `corpus_documents` → `corpus_chunks` (with `sa.Column("embedding", Vector(1024), nullable=False)`) → indexes on `corpus_documents.source_path` and `ingestion_runs.started_at DESC`.
  - No HNSW index — deferred to plan 04's `--build-index` flag per RESEARCH D8 / Pitfall 5.
  - `downgrade()`: drops indexes first, then tables in FK-reverse order (`corpus_chunks` → `corpus_documents` → `ingestion_runs`), then `DROP EXTENSION IF EXISTS vector`.
- **`backend/tests/conftest.py`** — added `alembic_engine` + `alembic_command` fixtures. The fixture wipes `public` schema before each test so a prior pytest session's `Base.metadata.create_all` cannot collide with the migration's `CREATE TABLE`. `monkeypatch` patches `app.config.settings.database_url` because `alembic/env.py` reads `settings.database_url`, not the ini file's `sqlalchemy.url`.
- **`backend/tests/test_corpus_migration_round_trip.py`** — removed both `@pytest.mark.xfail` decorators (REQ-31-01, REQ-31-02 flipped to green) and added the third assertion `test_corpus_chunks_has_vector_1024_column` using `format_type(atttypid, atttypmod) == 'vector(1024)'` (see deviations).

### Task 2 — ORM classes + corpus_* config (commit `601f0f3`)

- **`backend/app/models.py`** — added `IngestionRun`, `CorpusDocument`, `CorpusChunk` (classic Declarative, matching existing project style). New imports: `BigInteger`, `CHAR` (from `sqlalchemy`), `Vector` (from `pgvector.sqlalchemy`).
- **`backend/app/config.py`** — added 8 new `Settings` fields under a `# --- Phase 31 (v1.4)` section, defaults locked per RESEARCH §Domain Decisions:
  - `corpus_embedding_primary="jina"`, `corpus_embedding_fallback="local"`, `corpus_embedding_dimensions=1024`
  - `corpus_chunk_size=1024`, `corpus_chunk_overlap=128`, `corpus_chunker_version="v1-recursive-char-1024-128"`
  - `jina_api_key=""`, `jina_embedding_model="jina-embeddings-v3"`, `local_embedding_model="BAAI/bge-small-en-v1.5"`
- Existing `copilot_*`, OpenRouter, CORS, etc. fields untouched.

## Verification Snapshot

```text
$ docker run --rm ... uni-volunteer-scheduler-backend sh -c "alembic upgrade head && alembic current"
INFO  [alembic.runtime.migration] Running upgrade 0018_copilot_sessions_and_messages -> 0019_enable_pgvector_corpus_tables
0019_enable_pgvector_corpus_tables (head)

$ psql -U postgres -d test_uvs -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
 extname | extversion
---------+------------
 vector  | 0.8.2

$ psql -U postgres -d test_uvs -c "SELECT table_name, count(*) AS cols FROM information_schema.columns WHERE table_name IN ('corpus_documents','corpus_chunks','ingestion_runs') GROUP BY table_name ORDER BY table_name;"
    table_name    | cols
------------------+------
 corpus_chunks    |   13
 corpus_documents |    8
 ingestion_runs   |   23

$ pytest -q tests/test_corpus_migration_round_trip.py --no-cov
3 passed, 5 warnings in 1.52s

$ pytest -q tests/test_corpus_*.py --no-cov
6 passed, 1 skipped, 7 xfailed, 5 warnings in 2.04s
# (3 new migration tests pass + 3 unchanged xfails on the migration file's siblings)

$ pytest -q tests/test_copilot_router.py --no-cov
29 passed in 1.36s   # Phase 30 invariant intact

$ python -c "from app.models import CorpusDocument, CorpusChunk, IngestionRun; \
             from app.config import settings; \
             print(settings.corpus_embedding_dimensions, \
                   settings.corpus_chunker_version)"
1024 v1-recursive-char-1024-128
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's `atttypmod == 1028` assertion was wrong**
- **Found during:** Task 1, running the third test.
- **Issue:** The plan claimed pgvector encodes the declared dimension as `atttypmod = dim + 4`. Empirically against pgvector 0.8.2 the encoding is `atttypmod == dim` (i.e. 1024 for `vector(1024)`). Pinning to a specific encoding offset is fragile across pgvector versions anyway.
- **Fix:** Test now asserts `format_type(atttypid, atttypmod) == 'vector(1024)'` (authoritative regardless of how the dim is stored internally) AND `atttypmod == 1024` (current pgvector 0.8.x reality). Either alone would catch a regression; together they document the encoding so a future bump won't silently shift it.
- **Files modified:** `backend/tests/test_corpus_migration_round_trip.py`
- **Commit:** `5f49845`

**2. [Rule 2 - Critical correctness] Schema wipe before each `alembic_command` test**
- **Found during:** Task 1, initial test run.
- **Issue:** The session-scoped `engine` fixture in `backend/conftest.py` calls `Base.metadata.create_all(eng)` against `TEST_DATABASE_URL`, which leaves ORM-created tables sitting in `test_uvs` between sessions. When the migration's `op.create_table("ingestion_runs", ...)` runs against a DB that already has ORM-built tables of the same name (or partial leftovers from a half-finished downgrade), it fails with `DuplicateTable` or `UndefinedTable`. Either flavor is a flaky-test classic.
- **Fix:** The `alembic_command` fixture runs `DROP SCHEMA public CASCADE; CREATE SCHEMA public` before binding Alembic. The fixture also `monkeypatch`es `app.config.settings.database_url` since `alembic/env.py` reads that attribute, not the ini file.
- **Files modified:** `backend/tests/conftest.py`
- **Commit:** `5f49845`

**3. [Rule 2 - Type honesty] `embedding_latency_ms_total` BigInteger in ORM too**
- **Found during:** Task 2 ORM authoring.
- **Issue:** Plan said "BIGINT in DB; Integer in ORM is fine." A long-running ingest (Jina rate-limit retries summed over 2K chunks) can plausibly cross 2.1B ms (~24 days). Unlikely but not impossible. The ORM type should match the DB column or SQLAlchemy will silently overflow on read.
- **Fix:** Used `sa.BigInteger` in both the migration AND the ORM class; added `BigInteger` to the imports.
- **Files modified:** `backend/app/models.py`
- **Commit:** `601f0f3`

### Documentation note (not a code deviation)

- Plan's output spec said "ingestion_runs should have 22 columns." Counting the migration column list gives **23** (id + started_at + completed_at + status + git_commit_sha + git_dirty + source_globs + 4 embedding-meta + chunker_version + 8 counters + 3 error/notes). Likely an arithmetic slip in the plan. Both the migration and the ORM class agree at 23.

## Threat Flags

None. Plan 02 is pure schema + ORM + config plumbing. No new trust boundary; no filesystem reads; no new API surface. The `threat_flag` scan is clean — the only "new surface" is database tables that hold our own ingested docs/code, which is the intended Phase 31 trust boundary and was already enumerated in the plan's threat model.

## Known Stubs

None introduced by this plan. The Wave 0 xfails (`test_corpus_chunker.py`, `test_corpus_walker.py`, `test_corpus_embeddings.py`, `test_corpus_ingest_idempotency.py`) remain xfail-pinned — they belong to plans 03/04 and will flip there.

## Commits

- `5f49845` feat(31-02): alembic 0019 — pgvector extension + corpus tables (round-trip safe)
- `601f0f3` feat(31-02): ORM models (CorpusDocument/CorpusChunk/IngestionRun) + corpus_* settings

## Self-Check: PASSED

- `backend/alembic/versions/0019_enable_pgvector_corpus_tables.py` exists ✓
- File contains `CREATE EXTENSION IF NOT EXISTS vector` and `DROP EXTENSION IF EXISTS vector` ✓
- File contains `Vector(1024)` ✓
- File does NOT contain `hnsw` ✓
- `class CorpusDocument`, `class CorpusChunk`, `class IngestionRun` present in `backend/app/models.py` ✓
- `corpus_embedding_dimensions: int = 1024` and `corpus_chunker_version: str = "v1-recursive-char-1024-128"` in `backend/app/config.py` ✓
- `pytest -q tests/test_corpus_migration_round_trip.py` exits 0, 3 passed, no xfail decorators remain ✓
- `pytest -q tests/test_copilot_router.py` still 29/29 green (Phase 30 invariant) ✓
- Commits `5f49845` and `601f0f3` exist in `git log` ✓
