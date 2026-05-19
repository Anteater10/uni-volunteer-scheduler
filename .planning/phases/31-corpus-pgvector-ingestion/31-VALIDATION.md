---
phase: 31
slug: corpus-pgvector-ingestion
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-10
updated: 2026-05-10
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing backend stack) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q backend/tests/test_corpus_*"` |
| **Full suite command** | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q --cov=app.corpus --cov-report=term-missing"` |
| **Estimated runtime** | ~20-40 seconds (includes one real Postgres migration round-trip + chunker fuzz) |

---

## Sampling Rate

- **After every task commit:** Run quick command (corpus tests only)
- **After every plan wave:** Run full suite with `--cov=app.corpus`
- **Before `/gsd-verify-work`:** Full suite green AND `app.corpus.*` coverage == 100%
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 31-01-T1 | 01 | 0 | REQ-31-01 (substrate) | n/a | pgvector image in compose; deps in backend | smoke | `grep -q pgvector/pgvector:pg16 docker-compose.yml && docker compose exec -T backend python -c "import pgvector, sentence_transformers, torch"` | docker-compose.yml, backend/requirements.txt | ⬜ |
| 31-01-T2 | 01 | 0 | REQ-31-03/04/05/06/07/08/11 (stubs) | T-31-03/04 | xfail stubs pin every contract | unit (xfail) | `pytest -q backend/tests/test_corpus_*.py` returns 10 xfailed | 5 new test files | ⬜ |
| 31-02-T1 | 02 | 1 | REQ-31-01, REQ-31-02 | T-31-01 | round-trip safe migration | migration | `pytest -q backend/tests/test_corpus_migration_round_trip.py` | backend/alembic/versions/0019_*.py | ⬜ |
| 31-02-T2 | 02 | 1 | REQ-31-A/B/E (schema + config) | T-31-02 | ORM mirrors schema; settings locked | unit | `python -c "from app.models import CorpusChunk; from app.config import settings; assert settings.corpus_embedding_dimensions == 1024"` | backend/app/models.py, backend/app/config.py | ⬜ |
| 31-03-T1 | 03 | 2 | REQ-31-03, REQ-31-04 | T-31-04 | deterministic chunker, offset invariant | unit | `pytest -q backend/tests/test_corpus_chunker.py --cov=app.corpus.chunker --cov-fail-under=100` | backend/app/corpus/chunker.py | ⬜ |
| 31-03-T2 | 03 | 2 | REQ-31-05, REQ-31-06, REQ-31-07 | T-31-03 | walker opens no DB; deny-list honored | unit | `pytest -q backend/tests/test_corpus_walker.py --cov=app.corpus.walker --cov-fail-under=100` | backend/app/corpus/walker.py | ⬜ |
| 31-04-T1 | 04 | 3 | REQ-31-11 | T-31-05 | dim locked to 1024, BGE padded | unit | `pytest -q backend/tests/test_corpus_embeddings.py --cov=app.corpus.embeddings --cov-fail-under=100` | backend/app/corpus/embeddings.py | ⬜ |
| 31-04-T2 | 04 | 3 | REQ-31-08, REQ-31-09, REQ-31-10, REQ-31-14 | T-31-06/07/08 | idempotent, resumable, fallback-capable, telemetry-complete | integration | `pytest -q backend/tests/test_corpus_ingest_idempotency.py --cov=app.corpus.ingest --cov-fail-under=100` | backend/app/corpus/ingest.py | ⬜ |
| 31-04-T3 | 04 | 3 | REQ-31-F (CLI surface) | n/a | CLI flag surface complete | smoke | `docker compose exec -T backend python -m app.corpus.ingest --source docs --dry-run --provider local` exits 0 with JSON output | backend/app/corpus/__main__.py | ⬜ |
| 31-05-T1 | 05 | 4 | REQ-31-12, REQ-31-13 | T-31-09 | HNSW index used; real ingest populates rows | integration + smoke | `pytest -q backend/tests/test_corpus_hnsw_index.py` AND `SELECT COUNT(*) FROM corpus_chunks >= 20` | backend/tests/test_corpus_hnsw_index.py | ⬜ |
| 31-05-T2 | 05 | 4 | REQ-31-J (two-folder docs) | T-31-10 | 4+4 docs written | manual + grep | `test $(find docs/learning/31-corpus-pgvector-ingestion -name "*.md" | wc -l) -eq 4` AND same for documentation | 8 doc files | ⬜ |
| 31-05-T3 | 05 | 4 | checkpoint:human-verify | n/a | human signoff on row counts + docs | manual | n/a (checkpoint) | n/a | ⬜ |
| 31-05-T4 | 05 | 4 | STATE.md hygiene (RESEARCH §Open Q 6) | n/a | stale "session list UI" line removed | smoke | `! grep -q "conversation history + session list UI" .planning/STATE.md` | .planning/STATE.md | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity:** Max 1 consecutive task without automated verify (31-05-T3 is the lone checkpoint and is bracketed by automated tasks on both sides). ✅

---

## Wave 0 Requirements

- [x] `backend/tests/test_corpus_chunker.py` — chunker determinism + boundary tests — stubs land in 31-01-T2
- [x] `backend/tests/test_corpus_walker.py` — allow-list walker stubs — stubs land in 31-01-T2
- [x] `backend/tests/test_corpus_ingest_idempotency.py` — content-hash idempotency stubs — stubs land in 31-01-T2
- [x] `backend/tests/test_corpus_migration_round_trip.py` — Alembic round-trip gate — stubs land in 31-01-T2
- [x] `backend/tests/conftest.py` — corpus fixtures (`tiny_markdown_corpus`, `fake_embedding_provider` placeholder) — lands in 31-01-T2
- [x] `backend/tests/test_corpus_embeddings.py` — added beyond original Wave 0 list to pin REQ-31-11 — stubs land in 31-01-T2

*pgvector image swap and backend image rebuild also land in 31-01-T1, prerequisite to any other Phase 31 test.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| First real ingestion run against project docs produces non-empty `corpus_chunks` rows with 1024-dim embeddings | REQ-31-13 | Real model invocation; embedding values not byte-asserted | `docker compose run --rm backend python -m app.corpus.ingest --source docs --commit --provider local`, then `SELECT COUNT(*), vector_dims(embedding) FROM corpus_chunks` — expect > 20 rows, 1024 dims |
| HNSW index build completes against seeded corpus | REQ-31-12 | Index creation cost depends on row count | `docker compose run --rm backend python -m app.corpus.ingest --build-index`, then `\d corpus_chunks` in psql shows HNSW index on `embedding`. Automated complement: `test_corpus_hnsw_index.py::test_hnsw_index_used` |
| Jina v3 → BGE-small fallback path triggers on Jina rate-limit | REQ-31-10 | Inducing real 429 is brittle | Automated via `test_ingest_fallback_provider_engages` with a mock provider that raises `RateLimitError`. Manual real-API check optional |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are explicit checkpoints (31-05-T3)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (chunker, walker, idempotency, migration round-trip, embeddings)
- [x] No watch-mode flags in any task command
- [x] Feedback latency < 40s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved by planner; pending execution start
