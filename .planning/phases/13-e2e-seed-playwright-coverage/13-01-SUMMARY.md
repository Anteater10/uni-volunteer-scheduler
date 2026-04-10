---
phase: 13-e2e-seed-playwright-coverage
plan: 01
subsystem: e2e-testing
tags: [playwright, e2e, seed, ci, v1.1]
dependency_graph:
  requires:
    - 09-public-signup-backend
    - 10-public-signup-ui
    - 11-orientation-modal
    - 12-frontend-retirement
  provides:
    - e2e-coverage-v1.1
    - ci-e2e-gate
  affects:
    - all future PRs (CI gate)
tech_stack:
  added:
    - backend/app/routers/test_helpers.py (test-only cleanup endpoints)
  patterns:
    - EXPOSE_TOKENS_FOR_TESTING=1 for E2E token exposure + rate-limit bypass
    - Idempotent seed via cancel+cleanup+recreate pattern
    - test.describe.serial for ordered mutation tests
key_files:
  created:
    - backend/app/routers/test_helpers.py
    - e2e/public-signup.spec.js
    - e2e/orientation-modal.spec.js
    - e2e/organizer-check-in.spec.js
    - e2e/admin-smoke.spec.js
  modified:
    - backend/app/schemas.py (confirm_token field, v1.1 fields on EventCreate/SlotCreate/SlotRead)
    - backend/app/services/public_signup_service.py (EXPOSE_TOKENS_FOR_TESTING gate)
    - backend/app/services/orientation_service.py (count checked_in as attended)
    - backend/app/models.py (values_callable on all SqlEnum columns)
    - backend/app/routers/events.py (persist v1.1 event/slot fields)
    - backend/app/routers/slots.py (persist slot_type, date, location)
    - backend/app/deps.py (rate limit bypass for EXPOSE_TOKENS_FOR_TESTING)
    - backend/app/main.py (test_helpers router registration)
    - backend/tests/fixtures/seed_e2e.py (full rewrite for v1.1)
    - e2e/fixtures.js (v1.1 credentials, VOLUNTEER_IDENTITY, ephemeralEmail)
    - e2e/global-setup.js (minor log line fix)
    - .github/workflows/ci.yml (EXPOSE_TOKENS_FOR_TESTING, renamed job)
    - .gitignore (add test-results/, playwright-report/)
decisions:
  - "Added test-helper backend endpoints (seed-cleanup, event-signups-cleanup) to work around UNIQUE(volunteer_id, slot_id) constraint for idempotent seed re-runs"
  - "Rate limit bypass when EXPOSE_TOKENS_FOR_TESTING=1 — all parallel Playwright tests come from same localhost IP and exhausted 10/min limit"
  - "Slot capacity 200 for E2E event to prevent exhaustion across parallel test workers"
  - "orientation_service counts both checked_in and attended as having attended (D-03 fix)"
  - "SqlEnum values_callable fix across all 8 enum columns — PostgreSQL native enum uses lowercase values but Python enum .name is uppercase"
  - "email-validator 2.3.0 rejects .test TLD; all seed/fixture emails use @e2e.example.com"
metrics:
  duration: "131 minutes"
  completed_date: "2026-04-10"
  tasks_completed: 8
  files_changed: 17
---

# Phase 13 Plan 01: E2E Seed + Playwright Coverage Summary

Full Playwright E2E suite for v1.1 account-less volunteer scheduling, with idempotent seed and CI gate.

## What Was Built

16 Playwright tests across 4 spec files covering every major user flow of the v1.1 account-less pivot:

| Spec | Tests | Coverage |
|------|-------|----------|
| public-signup.spec.js | 7 | Browse → signup → confirm → manage → cancel one → cancel all |
| orientation-modal.spec.js | 2 | Modal fires (period-only, no history); modal skipped (has orientation) |
| organizer-check-in.spec.js | 1 | API signup → UI check-in via roster row click |
| admin-smoke.spec.js | 5 | Login, overview, audit logs, templates, exports |

All 16 tests pass in 4 consecutive runs (~10-17s each).

## Key Backend Changes

**`EXPOSE_TOKENS_FOR_TESTING=1` pattern**: The public signup API returns the raw magic-link `confirm_token` only when this env var is set. This allows Playwright tests to confirm signups without intercepting email. The same flag bypasses the `/public/signups` rate limit (10/min) that would otherwise throttle parallel test workers (all from localhost).

**`SqlEnum values_callable` fix**: All 8 `SqlEnum` columns in `models.py` were missing `values_callable=lambda x: [e.value for e in x]`. Without it, SQLAlchemy serialized Python enum `.name` (uppercase: `SPRING`) but PostgreSQL stored lowercase (`spring`). This caused every query involving enums to fail silently. Fixed across: UserRole, Quarter, SlotType, SignupStatus, NotificationType, PrivacyMode, MagicLinkPurpose, CsvImportStatus.

**Orientation service**: Changed to count both `checked_in` AND `attended` as having attended orientation. Previously only counted `attended`, but `checked_in` is the final state set by organizers before event resolution runs.

**v1.1 schema fields**: Added `quarter`, `year`, `week_number`, `school`, `module_slug` to `EventCreate`; added `slot_type`, `date`, `location` to `SlotCreate`/`SlotRead`. Updated routers to persist these fields.

## Seed Design

`seed_e2e.py` runs on every Playwright session start via `global-setup.js`. It:
1. Logs in as admin, ensures organizer user exists
2. Gets or creates the "E2E Seed Event" for the current quarter/week
3. Sets slot capacity to 200 (prevents exhaustion)
4. Cancels all non-seed-volunteer signups (resets capacity for next run)
5. Ensures `attended-vol@e2e.example.com` has a `checked_in` orientation signup
6. Creates/recreates `seeded-pending@e2e.example.com` with a fresh `confirm_token`
7. Outputs a JSON blob consumed by all specs via `process.env.E2E_SEED`

Idempotency is handled via two test-helper endpoints (`DELETE /api/v1/test/seed-cleanup` and `DELETE /api/v1/test/event-signups-cleanup`) that are only mounted when `EXPOSE_TOKENS_FOR_TESTING=1`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SqlEnum values_callable missing on all 8 enum columns**
- Found during: Task 1 (event creation with quarter field failed silently)
- Issue: `SqlEnum` without `values_callable` serializes Python enum `.name` (uppercase) but PostgreSQL native enums have lowercase values from migrations
- Fix: Added `values_callable=lambda x: [e.value for e in x]` to all 8 `SqlEnum` columns
- Files modified: `backend/app/models.py`
- Commit: e6d478b (part of task 1)

**2. [Rule 2 - Missing functionality] orientation_service only counted `attended` not `checked_in`**
- Found during: Task 7 (Test B failed — orientation modal appeared when it shouldn't)
- Issue: Orientation service returned `has_attended_orientation: false` for volunteers in `checked_in` state (event resolution hadn't run yet to advance to `attended`)
- Fix: Changed query to `Signup.status.in_([SignupStatus.attended, SignupStatus.checked_in])`
- Files modified: `backend/app/services/orientation_service.py`
- Commit: 6af9618

**3. [Rule 3 - Blocking issue] Rate limit 429 exhausted during parallel test runs**
- Found during: Task 7 (intermittent test failures after 10+ signups in 60s)
- Issue: All Playwright workers hit the `/public/signups` 10/min rate limit from same localhost IP
- Fix: Added bypass in `deps.py` when `EXPOSE_TOKENS_FOR_TESTING=1`
- Files modified: `backend/app/deps.py`
- Commit: 6af9618

**4. [Rule 3 - Blocking issue] UNIQUE(volunteer_id, slot_id) blocks seed re-runs**
- Found during: Task 7 (seed 409 failures on 2nd+ run)
- Issue: Once cancelled, the UNIQUE constraint prevents re-signup for same volunteer+slot
- Fix: Added `DELETE /api/v1/test/seed-cleanup` and `DELETE /api/v1/test/event-signups-cleanup` endpoints, only mounted when testing flag is on
- Files modified: `backend/app/routers/test_helpers.py`, `backend/app/main.py`
- Commit: 6af9618

**5. [Rule 1 - Bug] Admin smoke spec strict mode violations**
- Found during: Task 7 (audit logs + organizer check-in failures)
- Issue: AdminLayout renders both mobile and desktop DOM; `#al-q` appears twice. `getByText(/checked in/i)` matched 2 elements (header + chip)
- Fix: Added `.first()` to both selectors
- Files modified: `e2e/admin-smoke.spec.js`, `e2e/organizer-check-in.spec.js`
- Commit: 6af9618

**6. [Rule 1 - Bug] email-validator 2.3.0 rejects `.test` TLD**
- Found during: Task 2 (seed failed on email validation)
- Issue: email-validator 2.3.0 treats `.test` as a special-use domain and rejects it
- Fix: Changed all seed/fixture emails from `@e2e.test` to `@e2e.example.com`
- Files modified: `backend/tests/fixtures/seed_e2e.py`, `e2e/fixtures.js`
- Commit: 8fdbbba

**7. [Rule 1 - Bug] Confirm token required before check-in (pending → confirmed → checked_in)**
- Found during: Task 7 (attended volunteer stuck in pending state)
- Issue: `check_in_signup` requires `confirmed` status; seed was trying to check-in from `pending`
- Fix: Added confirm step via `POST /public/signups/confirm?token=<raw_token>` before check-in
- Files modified: `backend/tests/fixtures/seed_e2e.py`
- Commit: 6af9618

### Deleted Files (as planned)
7 stale v1.0 spec files removed: `student-signup.spec.js`, `student-cancel.spec.js`, `magic-link.spec.js`, `signup-three-tap.spec.js`, `a11y.spec.js`, `admin-crud.spec.js`, `organizer-roster.spec.js`

## Test Results

| Suite | Pass | Fail | Skip |
|-------|------|------|------|
| Playwright (16 tests) | 16 | 0 | 0 |
| Backend pytest | 206 | 0 | 0 |
| Frontend vitest | 73 | 0 | 0 |

## Self-Check: PASSED
