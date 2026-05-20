---
phase: 32-rag-retrieval
plan: 08
subsystem: ci/coverage-gates
tags: [ci, coverage, regression-test, infrastructure]
requires: [32-01, 32-02, 32-03, 32-04, 32-05, 32-06]
provides: [per-package coverage gates locked in CI + regression guard]
affects: [.github/workflows/ci.yml, backend/tests/]
tech-stack:
  added: []
  patterns: [per-package --cov-fail-under (Phase 31-followup pattern), addopts override via pytest -o]
key-files:
  created:
    - backend/tests/test_coverage_gates.py
  modified:
    - .github/workflows/ci.yml
decisions:
  - "Per-package gates expressed as three standalone pytest --cov-fail-under steps (mirrors Phase 31-followup 75f1145) AND extended into the existing JSON-reading per-package script to keep the line-ratio discipline visible in two places."
  - "backend/pytest.ini already sets --cov=app in addopts; gate steps use 'pytest -o addopts=\"\"' to override so each invocation measures only its target namespace."
  - "Regression test discovers ci.yml path heuristically and skips gracefully when only backend/ is mounted (docker test image). CI checks the full repo so all 10 assertions run there."
  - "Coverage gate threshold = 95 (line+branch blended). The actual numbers are 99.38 / 100.00 / 98.51, but the gate sits at 95 — a follow-up could raise it to 98 once the harness lands."
metrics:
  duration: ~15 min
  tasks_completed: 3
  files_created: 1
  files_modified: 1
  completed: 2026-05-20
---

# Phase 32 Plan 08: Coverage Gate Lock Summary

Three standalone per-package `pytest --cov-fail-under=95` gates added to CI for
`app.copilot`, `app.copilot.retrieval`, `app.corpus`, plus a metadata-only
regression test that fails loudly if any future PR loosens the gate below 95.

## Coverage Numbers (verified locally, docker test container)

| Package                 | Stmts | Miss | Branch | BrPart | Coverage |
|-------------------------|-------|------|--------|--------|----------|
| `app.copilot`           | 414   | 1    | 68     | 2      | **99.38%** |
| `app.copilot.retrieval` | 99    | 0    | 10     | 0      | **100.00%** |
| `app.corpus`            | 464   | 0    | 142    | 9      | **98.51%** |

All three gates exit 0 against the floor of 95.

## Tasks Completed

### Task 1 — CI workflow + .coveragerc

- **`backend/.coveragerc`:** verified, no edit needed. Already has
  `branch = True` and `source = app` (wildcard covers
  `app/copilot/retrieval/*`).
- **`.github/workflows/ci.yml`:** added three named steps after the existing
  "Critical-path + per-package coverage gates" step:
  ```yaml
  - name: Coverage gate — app.copilot
    run: |
      cd backend
      pytest -o addopts="" --cov=app.copilot --cov-branch --cov-fail-under=95 …
  - name: Coverage gate — app.copilot.retrieval
    run: |
      cd backend
      pytest -o addopts="" --cov=app.copilot.retrieval --cov-branch --cov-fail-under=95 …
  - name: Coverage gate — app.corpus
    run: |
      cd backend
      pytest -o addopts="" --cov=app.corpus --cov-branch --cov-fail-under=95 …
  ```
  Also extended the inline JSON-reading per-package script (Phase 31-followup
  pattern from commit `75f1145`) to include `app/copilot/retrieval` alongside
  `app/copilot` and `app/corpus`.

**Deviation note (Rule 3 — blocking fix):** `backend/pytest.ini` injects
`--cov=app` into `addopts`. Without `-o addopts=""`, the CLI `--cov=app.copilot`
was being merged additively, so each gate command measured the entire `app/`
tree (giving 73%, tripping the gate). Adding `-o addopts=""` to each gate step
restores per-package scoping. Documented in the workflow comment block.

Commit: `26af7dc` — `feat(32-08): add per-package coverage gates …`

### Task 2 — Regression test

- **`backend/tests/test_coverage_gates.py`** (142 lines, 10 assertions):
  - Parses ci.yml with `yaml.safe_load`.
  - Asserts each of `--cov=app.copilot`, `--cov=app.copilot.retrieval`,
    `--cov=app.corpus` is present with `--cov-fail-under >= 95`.
  - Uses a non-capturing lookahead `(?![.\w])` so `--cov=app.copilot` is not
    matched against `--cov=app.copilot.retrieval`.
  - Asserts `.coveragerc` has `branch = True`.
  - Asserts at least one test file matches each namespace glob.
  - Runs in **~0.12s** (no DB, no fixtures, metadata-only).
  - Skips gracefully when only `backend/` is mounted (the docker test image's
    default layout). CI runs the full repo checkout and exercises all 10
    assertions.

Commit: `9db8c96` — `test(32-08): regression test pinning per-package …`

### Task 3 — Full-suite regression

Backend pytest (full repo mount): **550 passed, 1 skipped** (the lone skip is
the RAGAS `pytest.importorskip` — intentional). Global coverage gate
(`--cov-fail-under=55` from pytest.ini): 73.06%, well above floor.

Regression test alone: **10/10 passed in 0.12s** with full repo mount.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `pytest.ini` addopts pollution forced `-o addopts=""`**
- **Found during:** Task 1 — first run of `pytest --cov=app.copilot …` measured 73% of the full `app/` tree, not 99% of `app.copilot/`.
- **Root cause:** `backend/pytest.ini` has `addopts = -ra --strict-markers --tb=short --cov=app --cov-report=term-missing --cov-fail-under=55`. pytest-cov treats CLI `--cov=X` as additive to config, not replacing.
- **Fix:** Each gate step uses `pytest -o addopts="" --cov=<pkg> …` to override the config-level addopts and scope coverage to exactly one package.
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** `26af7dc`

**2. [Rule 3 — Blocking] Regression test path discovery must survive partial mount**
- **Found during:** Task 2 — initial heuristic `Path(__file__).resolve().parents[2]` resolved to `/` inside the docker test image (only `backend/` mounted).
- **Fix:** `_discover_paths()` checks three plausible roots (dev checkout `backend/..`, `/repo`, `/workspace`) and the `ci_workflow` fixture `pytest.skip()`s with a clear message if none reach ci.yml. CI runs against the full checkout and all 10 assertions execute there.
- **Files modified:** `backend/tests/test_coverage_gates.py`
- **Commit:** `9db8c96`

### Paired Docs Skipped (per plan)

Plan body explicitly designates 32-08 as a CI/infra plan; no `docs/learning/`
or `docs/documentation/` writeup required. Verified — plan tasks 1–3 contain
no docs deliverable, only the SUMMARY in `<output>`.

## ci.yml Structural Notes

No structural deviation from the existing job layout. The three new steps slot
into the `phase0-backend-tests` job after the existing "Critical-path +
per-package coverage gates" step and before the job ends. Each step
re-declares `TEST_DATABASE_URL` (consistent with the surrounding pattern; the
DB is only needed because pytest collection imports modules that touch DB
metadata).

## Self-Check: PASSED

- ✅ `.github/workflows/ci.yml` — three new gate steps present, `app/copilot/retrieval` added to JSON gate dict.
- ✅ `backend/tests/test_coverage_gates.py` — exists, 10 tests, all green under full repo mount.
- ✅ Commit `26af7dc` — `feat(32-08): add per-package coverage gates …`
- ✅ Commit `9db8c96` — `test(32-08): regression test pinning …`
- ✅ Full backend suite: 550 passed / 1 skipped.
- ✅ Three coverage gates measured locally: 99.38% / 100.00% / 98.51%.
