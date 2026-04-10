---
phase: "10"
plan: "01"
subsystem: backend+frontend
tags: [public-api, week-navigation, current-week, api-helpers, TDD]
dependency_graph:
  requires: ["09-public-signup-backend"]
  provides: ["current-week-endpoint", "api.public-namespace", "weekUtils"]
  affects: ["10-02-browse-ui", "10-03-signup-form", "10-04-confirmation"]
tech_stack:
  added: []
  patterns:
    - QUARTER_START_DATES constant dict (backend calendar anchoring)
    - api.public nested namespace (auth:false helpers)
    - pure-function week math with quarter boundary rollover
key_files:
  created:
    - frontend/src/lib/weekUtils.js
    - frontend/src/lib/__tests__/weekUtils.test.js
    - frontend/src/lib/__tests__/api.public.test.js
  modified:
    - backend/app/routers/public/events.py (added current_week endpoint + QUARTER_START_DATES)
    - backend/app/schemas.py (added CurrentWeekRead schema)
    - backend/tests/test_public_events.py (added TestCurrentWeek class)
    - frontend/src/lib/api.js (added api.public namespace + 5 helper functions)
decisions:
  - "QUARTER_START_DATES placed in events.py module scope (not a separate constants file) — single consumer, no cross-module sharing needed yet"
  - "week_number clamped to 1-11 server-side; pre-quarter fallback returns earliest known quarter week 1"
  - "api.public tests use vi.resetModules() per-test to avoid shared module state between fetch mocks"
  - "weekUtils.test.js writes 15 tests (plan asked for 7+) to cover all 4 quarter rollover permutations bidirectionally"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-10"
  tasks_completed: 3
  files_changed: 7
---

# Phase 10 Plan 01: Backend current-week endpoint + api.public.* helpers + weekUtils.js Summary

**One-liner:** GET /public/current-week with UCSB 2026 quarter dates, api.public 5-helper namespace (auth:false), and pure-JS week navigation with full quarter boundary rollover.

## What Was Built

### Task 1 — Backend GET /api/v1/public/current-week

- Added `QUARTER_START_DATES` constant dict to `backend/app/routers/public/events.py` mapping `(year, quarter)` tuples to `datetime.date` objects for 2026 (winter/spring/summer/fall) and 2027 winter.
- `current_week()` endpoint: finds the latest start date <= today, computes `week_number = ((today - start).days // 7) + 1`, clamps to 1-11.
- Added `CurrentWeekRead(quarter: str, year: int, week_number: int)` Pydantic schema to `schemas.py`.
- Rate-limited at 60/min/IP (same dependency as events list).
- 5 new tests in `TestCurrentWeek` including a mock-date spring 2026 boundary test.

### Task 2 — Frontend api.public.* namespace

- 5 standalone async helpers in `api.js`: `publicGetCurrentWeek`, `publicListEvents`, `publicGetEvent`, `publicCreateSignup`, `publicOrientationStatus`. All use `auth: false`.
- Wired into `api.public` nested namespace following `api.admin.*` pattern.
- 7 tests: URL assertions, no Authorization header (T-10-01), query param serialisation, POST body, 429 and 409 error status propagation.

### Task 3 — weekUtils.js

- `getNextWeek(quarter, year, weekNumber)` — increments or rolls to next quarter; fall week 11 → winter (year+1).
- `getPrevWeek(quarter, year, weekNumber)` — decrements or rolls to prev quarter; winter week 1 → fall (year-1).
- `formatWeekLabel(quarter, year, weekNumber)` — returns "Spring 2026 - Week 3" format.
- 15 tests covering all 4 quarter rollover permutations in both directions.

## Test Results

Backend: **13 passed** (test_public_events.py — all pre-existing + 5 new current-week tests)
Frontend: **26 passed** (4 test files — api.test.js 1, refreshOn401.test.js 3, api.public.test.js 7, weekUtils.test.js 15)

## Deviations from Plan

None — plan executed exactly as written. 

The plan suggested 7+ weekUtils tests; 15 were written to cover every quarter-rollover permutation explicitly. This is additive, not a deviation.

## Known Stubs

None — this plan is pure data-layer and math. No UI rendering, no placeholders.

## Threat Flags

None — no new trust boundaries introduced:
- `GET /public/current-week`: read-only calendar metadata, no PII, rate-limited (T-10-02 mitigated)
- `api.public.*` helpers: all `auth: false`, no Authorization header emitted (T-10-01 mitigated)

## Self-Check: PASSED

Files exist:
- backend/app/routers/public/events.py: current_week function present
- backend/app/schemas.py: CurrentWeekRead class present
- backend/tests/test_public_events.py: TestCurrentWeek class present
- frontend/src/lib/api.js: api.public namespace present
- frontend/src/lib/__tests__/api.public.test.js: 7 tests
- frontend/src/lib/weekUtils.js: getNextWeek/getPrevWeek/formatWeekLabel exports
- frontend/src/lib/__tests__/weekUtils.test.js: 15 tests

Commits present:
- 44c84c3: feat(10-01): GET /public/current-week endpoint with UCSB 2026 quarter dates
- 0a863a2: feat(10-01): api.public.* namespace with 5 unauthenticated helpers
- 72a1e95: feat(10-01): weekUtils.js with quarter boundary rollover navigation
