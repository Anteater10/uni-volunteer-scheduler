---
phase: 31
slug: corpus-pgvector-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-10
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
- **Before `/gsd-verify-work`:** Full suite green AND `app.corpus.*` coverage ≥ 95%
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

> Filled in by `gsd-planner` during step 8. Required: every task in PLAN.md has either an `<automated>` verify block or a Wave 0 dependency on a Phase 31 test file. Sampling continuity: no 3 consecutive tasks without automated verify.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled by planner_ | | | | | | | | | |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_corpus_chunker.py` — chunker determinism + boundary tests (stubs for REQ-31 chunker contract)
- [ ] `backend/tests/test_corpus_walker.py` — allow-list walker stubs (verifies no DB connections opened, gitignore-style excludes honored)
- [ ] `backend/tests/test_corpus_ingest_idempotency.py` — content-hash idempotency stubs (re-running ingest with same input creates 0 new rows)
- [ ] `backend/tests/test_corpus_migration_round_trip.py` — Alembic upgrade → downgrade → upgrade gate for `0019_enable_pgvector_corpus_tables`
- [ ] `backend/tests/conftest.py` — extend with corpus fixtures (sample markdown fixture dir, mock embedding provider)

*pgvector image swap (Wave 0 task in PLAN) is a prerequisite — without `pgvector/pgvector:pg16`, the migration cannot run and these tests cannot pass.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| First real ingestion run against project docs produces non-empty `corpus_chunks` rows with 1024-dim embeddings | RESEARCH §Recommended Approach | Real network call to Jina API + real model invocation; not safe to assert exact embedding values | Run `docker compose run --rm backend python -m app.corpus.ingest --source docs --commit`, then `SELECT COUNT(*), vector_dims(embedding) FROM corpus_chunks` — expect > 0 rows, 1024 dims |
| HNSW index build completes against seeded corpus | RESEARCH §Index Strategy | Index creation cost depends on row count; assertion would be flaky in CI | Run `docker compose run --rm backend python -m app.corpus.ingest --build-index`, then `\d corpus_chunks` in psql shows HNSW index on `embedding` |
| Jina v3 → BGE-small fallback path triggers on Jina rate-limit | RESEARCH §Embeddings | Requires inducing a 429 response from the real API, or extensive mocking that duplicates the unit tests | Set `CORPUS_EMBEDDING_PRIMARY_RATE_LIMIT=1` env var (test hook) and run ingestion twice in quick succession — second run should log `fallback_provider=bge-small` in `ingestion_runs.notes` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (filled by planner)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (chunker, walker, idempotency, migration round-trip)
- [ ] No watch-mode flags in any task command
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter once planner fills the per-task table

**Approval:** pending
