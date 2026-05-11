---
phase: 31
plan: 01
subsystem: corpus-substrate
tags: [pgvector, embeddings, wave0, test-stubs]
dependency_graph:
  requires: []
  provides:
    - pgvector-enabled Postgres image (db service)
    - backend image with pgvector + sentence-transformers + torch CPU
    - Wave 0 pytest stubs pinning REQ-31-01..11
  affects:
    - docker-compose.yml (db service image)
    - backend/requirements.txt
    - backend/tests/ (new conftest + 5 test files)
tech_stack:
  added:
    - pgvector (Python adapter, >=0.3,<1.0)
    - sentence-transformers (3.4.1 installed)
    - torch (2.11.0+cpu via download.pytorch.org/whl/cpu extra index)
    - numpy (>=1.26,<2)
  patterns:
    - strict-xfail test stubs pinning future-wave contracts
    - drop-in Postgres image swap reusing pgdata volume (PG16 page-format compat)
key_files:
  created:
    - backend/tests/conftest.py
    - backend/tests/test_corpus_chunker.py
    - backend/tests/test_corpus_walker.py
    - backend/tests/test_corpus_ingest_idempotency.py
    - backend/tests/test_corpus_migration_round_trip.py
    - backend/tests/test_corpus_embeddings.py
    - .planning/phases/31-corpus-pgvector-ingestion/31-01-SUMMARY.md
  modified:
    - docker-compose.yml (db image swap)
    - backend/requirements.txt (4 new deps + torch CPU index URL)
decisions:
  - "Pin torch to CPU wheel via --extra-index-url in requirements.txt (plan said default linux/amd64 torch is CPU; in reality it pulls CUDA + nvidia-* ~2GB)"
  - "Do not enable CREATE EXTENSION vector in Wave 0; that lands in plan 02 migration 0019"
  - "Place corpus fixtures in backend/tests/conftest.py (root backend/conftest.py provides db_session, client, engine; pytest merges both)"
metrics:
  duration_minutes: ~12
  completed: 2026-05-11
  tasks_completed: 2
  files_changed: 8
requirements_completed:
  - REQ-31-01  # pinned (xfail) - migration lands plan 02
  - REQ-31-02  # pinned (xfail)
  - REQ-31-03  # pinned (xfail) - chunker lands plan 03
  - REQ-31-05  # pinned (xfail)
  - REQ-31-08  # pinned (xfail) - idempotency lands plan 04
  - REQ-31-11  # pinned (xfail) - embedding dim lock
---

# Phase 31 Plan 01: Corpus + pgvector Wave 0 Substrate Summary

**One-liner:** Swapped Postgres to `pgvector/pgvector:pg16`, baked `pgvector` + `sentence-transformers` + CPU-only `torch 2.11.0` into the backend image, and pinned every Phase 31 requirement (REQ-31-01..11) with strict-xfail pytest stubs so later waves get a green-or-red signal on every commit.

## What Shipped

### Task 1 — Image swap + dep bake (commit `3b5f36a`)
- `docker-compose.yml`: `db.image: postgres:16` → `pgvector/pgvector:pg16`
- `backend/requirements.txt`: appended `pgvector`, `sentence-transformers`, `torch`, `numpy` and added `--extra-index-url https://download.pytorch.org/whl/cpu` at top.
- Verified:
  - `docker compose ps`: `db` container running `pgvector/pgvector:pg16`, healthy.
  - `pg_available_extensions WHERE name='vector'` → `vector | 0.8.2`.
  - `docker compose exec backend python -c "import pgvector, sentence_transformers, torch"` → exit 0; `sentence-transformers 3.4.1`, `torch 2.11.0+cpu`.

### Task 2 — Wave 0 test stubs (commit `7945e48`)
- Created `backend/tests/conftest.py` with `tiny_markdown_corpus` fixture + placeholder `fake_embedding_provider` (lands in plan 04).
- Created 5 test files with **10 total tests**: 9 strict-xfail + 1 skipped (the ingest test, because its placeholder fixture calls `pytest.skip`).
- `pytest -q tests/test_corpus_*.py --no-cov` → `1 skipped, 9 xfailed in 0.62s`, exit 0.

## Verification Snapshot

```
$ docker compose -p uni-volunteer-scheduler ps db
NAME                           IMAGE                    STATUS
uni-volunteer-scheduler-db-1   pgvector/pgvector:pg16   Up (healthy)

$ docker compose exec db psql -U postgres -d uni_volunteer -c "\dx"
                 List of installed extensions
  Name   | Version |   Schema   |         Description
---------+---------+------------+------------------------------
 plpgsql | 1.0     | pg_catalog | PL/pgSQL procedural language
(1 row)

# vector extension is AVAILABLE (pg_available_extensions) but not yet
# INSTALLED. CREATE EXTENSION vector lands in plan 02 migration 0019.

$ docker compose exec backend python -c \
    "import pgvector, sentence_transformers, torch; \
     print(sentence_transformers.__version__, torch.__version__)"
3.4.1 2.11.0+cpu

$ pytest -q tests/test_corpus_*.py --no-cov
1 skipped, 9 xfailed in 0.62s    # exit 0

Backend image digest: sha256:908bc6d042e18d9761870129e7697550e1b0821f02f1c49c7734b8b615a4a352
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] torch CUDA wheel exhausts disk + bloats image**
- **Found during:** Task 1, first `docker compose build backend` attempt.
- **Issue:** Plan said "default `torch` wheel on Linux/amd64 is CPU build". This is wrong — pip's default `torch>=2.2,<3` resolves to the CUDA wheel which drags in `cuda-toolkit`, `triton`, `nvidia-cublas`, `nvidia-cudnn-cu13`, `nvidia-cusolver`, `nvidia-cusparse`, etc. — well over 2GB. First build failed with `OSError: [Errno 5] Input/output error` after consuming the host's ~10GB of free disk. After `docker builder prune`, host had 23GB free.
- **Fix:** Added `--extra-index-url https://download.pytorch.org/whl/cpu` as the first non-comment line of `backend/requirements.txt`. Plan explicitly forbade modifying `backend/Dockerfile`, so the redirect goes in requirements (pip honors it). Resulting wheel: `torch-2.11.0+cpu` (~250MB), no nvidia-* packages.
- **Files modified:** `backend/requirements.txt`
- **Commit:** `3b5f36a`

No other deviations. No auth gates. No checkpoints (autonomous plan).

## Stub Inventory

All Wave 0 stubs are intentional and strict-xfail-pinned. Each will flip RED in the named later-wave plan:

| Test | Pins | Flips in plan |
| --- | --- | --- |
| `test_chunker_deterministic` | REQ-31-03 | 03 |
| `test_chunker_offsets_consistent` | REQ-31-04 | 03 |
| `test_chunker_version_constant` | REQ-31-03 | 03 |
| `test_walker_deterministic_order` | REQ-31-07 | 03 |
| `test_walker_respects_deny_list` | REQ-31-06 | 03 |
| `test_walker_opens_no_db_connection` | REQ-31-05 | 03 |
| `test_ingest_idempotent_on_unchanged_repo` | REQ-31-08 | 04 |
| `test_upgrade_creates_extension_and_tables` | REQ-31-01 | 02 |
| `test_round_trip_clean` | REQ-31-02 | 02 |
| `test_embedding_dim_locked_to_1024` | REQ-31-11 | 04 |

`fake_embedding_provider` fixture is a `pytest.skip` placeholder; plan 04 will replace it with a deterministic in-memory provider.

## Known Caveats

- Postgres logs a benign `collation version mismatch` warning on the existing `uni_volunteer` db (created with glibc 2.41, container now uses 2.36). Resolution is `ALTER DATABASE uni_volunteer REFRESH COLLATION VERSION;`. Not done here — does not affect Wave 0; can be cleaned up in plan 02 alongside the `CREATE EXTENSION` migration if desired.
- Backend image bloated by ~700MB from the CPU torch + sentence-transformers + scikit-learn deps. Acceptable for v1.4; revisit during deployment phase.

## Commits

- `3b5f36a` feat(31-01): pgvector image + embedding deps (Wave 0 substrate)
- `7945e48` test(31-01): Wave 0 corpus test stubs pinning REQ-31-01..11

## Self-Check: PASSED

- docker-compose.yml contains `pgvector/pgvector:pg16` ✓
- backend/requirements.txt contains all 4 new deps ✓
- All 5 test files exist at `backend/tests/test_corpus_*.py` ✓
- `pytest -q backend/tests/test_corpus_*.py --no-cov` exits 0 with 9 xfailed + 1 skipped, 0 errors ✓
- Both task commits present in `git log` ✓
