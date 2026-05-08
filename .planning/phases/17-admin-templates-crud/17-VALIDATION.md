---
phase: 17
slug: admin-templates-crud
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-16
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (frontend), pytest (backend via docker) |
| **Config file** | `frontend/vitest.config.js`, `backend/pytest.ini` |
| **Quick run command** | `cd frontend && npx vitest run --reporter=verbose` |
| **Full suite command** | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q"` |
| **Estimated runtime** | ~5 seconds (vitest), ~15 seconds (pytest in docker) |

---

## Sampling Rate

- **After every task commit:** Run quick frontend tests for changed files
- **After backend changes:** Run pytest in docker for template-related tests
- **After migration:** Verify alembic head matches expected revision

---

## Per-Task Verification Map

| Task | Sampling Method | Pass Criteria |
|------|----------------|---------------|
| TBD | TBD | TBD |

---

## Validation Architecture

Matches Phase 16 pattern: vitest for frontend component tests, pytest-in-docker for backend API tests, grep-based acceptance gates for structural checks (file existence, import presence, schema shape).
