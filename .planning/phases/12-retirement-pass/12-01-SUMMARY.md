---
phase: 12-retirement-pass
plan: 01
subsystem: backend
tags: [deletion, analytics, ccpa, tests, retirement]
dependency_graph:
  requires: []
  provides: [clean-backend-no-prereq-refs, working-analytics, working-ccpa-signups, 0-skipped-tests]
  affects: [admin-analytics-ui, ccpa-export, test-suite]
tech_stack:
  added: []
  patterns: [volunteer-email-match-for-ccpa, signup-volunteer-join-for-analytics]
key_files:
  created: []
  modified:
    - backend/app/routers/users.py
    - backend/app/routers/signups.py
    - backend/app/routers/auth.py
    - backend/app/routers/admin.py
    - backend/app/schemas.py
    - backend/tests/test_signups.py
    - backend/tests/test_admin.py
    - backend/tests/test_admin_phase7.py
    - backend/tests/test_auth.py
  deleted:
    - backend/app/services/prereqs.py
decisions:
  - Rewrote test_register_returns_user_record as test_register_endpoint_removed (asserts 404) — test_auth.py still tests the remaining auth surface
  - CCPA links User to Volunteer by email match (no direct FK) — simplest correct approach, email is unique in both tables
  - NoShowRateRow.count is no_show count (not total denominator) — matches what the frontend ExportsSection expects
metrics:
  duration: ~35 minutes
  completed_date: 2026-04-09
  tasks_completed: 3
  files_modified: 9
  files_deleted: 1
---

# Phase 12 Plan 01: Backend Retirement Pass Summary

Deleted all v1.0 prereq surfaces, removed dead signup/auth stubs, reimplemented three analytics 501 endpoints and the CCPA signups stub with volunteer-keyed queries. Test suite: 206 passed, 0 skipped, 0 failed (was 188 passed, 12 skipped).

## What Was Deleted

### Files Deleted
- `backend/app/services/prereqs.py` — PrereqOverride model was dropped in migration 0009; this file had an import guard to prevent collection failure until Phase 12

### Endpoints Deleted
| Endpoint | Reason |
|----------|--------|
| `GET /users/me/module-timeline` | Used Signup.user_id (removed), PrereqOverride model (dropped), prereq_slugs (column removed), check_missing_prereqs (deleted service) |
| `GET /signups/my` | Returned `[]` stub; under v1.1 volunteer self-service is via magic-link manage page |
| `GET /signups/my/upcoming` | Same as above |
| `POST /auth/register` | Student self-registration retired; organizer/admin accounts created via admin UI |
| `GET /admin/prereq-overrides` | Returned 501; PrereqOverride model deleted in Phase 08 |
| `POST /admin/users/{user_id}/prereq-overrides` | Returned 501; same |
| `DELETE /admin/prereq-overrides/{override_id}` | Returned 501; same |

### Schemas Deleted
- `PrereqOverrideCreate` — stub kept since Phase 08 to avoid import failure; now safe to delete
- `PrereqOverrideRead` — same
- `ModuleTimelineItem` — only used by deleted module-timeline endpoint

## What Was Reimplemented

### Analytics Endpoints (was 501, now 200)

**`GET /admin/analytics/volunteer-hours`**
- Query: `Signup -> Slot -> Event -> Volunteer`, filter `status == attended`
- Aggregate: group by `volunteer_id`, sum `(slot.end_time - slot.start_time)` in hours, count distinct events
- Apply `from_date`/`to_date` filters on `Event.start_date`
- Returns `List[VolunteerHoursRow]` with `volunteer_id`, `volunteer_name`, `email`, `hours`, `events`

**`GET /admin/analytics/no-show-rates`**
- Query: same join, filter `status in [attended, no_show]`
- Aggregate: group by volunteer, count attended vs no_show; skip zero-denominator volunteers
- Returns `List[NoShowRateRow]` with `volunteer_id`, `volunteer_name`, `rate`, `count`

**`GET /admin/analytics/volunteer-hours.csv`**
- Same query as JSON endpoint, output via `io.StringIO` + `csv.writer`
- Columns: `volunteer_name, email, hours, events`

**CCPA Export signups** (was `[]` stub)
- Look up `Volunteer` by `user.email` (no direct FK between User and Volunteer)
- If found, collect all `Signup` rows for that volunteer
- Returns signup list with `id, slot_id, status, timestamp` fields
- If no matching volunteer: returns `[]` (correct for admin-only accounts with no volunteer record)

### Schema Updates
- `VolunteerHoursRow`: `user_id → volunteer_id`, `name → volunteer_name`, added `email`
- `NoShowRateRow`: `user_id → volunteer_id`, `name → volunteer_name`

## Test Suite Changes

**Before:** 188 passed, 12 skipped, 0 failed
**After:** 206 passed, 0 skipped, 0 failed

### Category A: test_signups.py (8 tests) — Complete rewrite
Old tests exercised deleted `POST /api/v1/signups/` endpoint. New tests exercise:
- Admin cancel changes status to cancelled
- Admin cancel decrements slot current_count
- Admin cancel promotes oldest waitlisted (FIFO by timestamp)
- Admin cancel promotes by id tiebreaker with equal timestamps
- Already-cancelled signup is idempotent (returns 200)
- Admin cancel enqueues Celery cancellation email
- POST /signups/{id}/cancel returns 403 for participant-role user
- POST /admin/signups/{id}/cancel returns 404 for non-existent signup

### Category B: test_admin.py (1 test)
`test_admin_cancel_signup_promotes_waitlist`: rewrote to use `VolunteerFactory` — creates confirmed A + waitlisted B directly in DB, admin cancels A, asserts B promoted to pending.

### Category C: test_admin_phase7.py (3 tests)
- `test_analytics_volunteer_hours_shape`: seeds attended signup, asserts 200 + correct field names
- `test_ccpa_export_returns_user_data`: seeds Volunteer with matching email + Signup, asserts signups non-empty
- `test_ccpa_delete_preserves_signups`: seeds Volunteer + Signup, CCPA-deletes User, asserts Signup still exists keyed to volunteer_id

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_auth.py::test_register_returns_user_record failing after /auth/register deletion**
- **Found during:** Task 3 test run
- **Issue:** test_register_returns_user_record called `POST /auth/register` which was deleted in Task 1; test got 404 and failed
- **Fix:** Rewrote test as `test_register_endpoint_removed` — asserts 404, verifying the route is correctly absent
- **Files modified:** `backend/tests/test_auth.py`
- **Commit:** 6f7530d

## Known Stubs

None — all stubs removed or reimplemented in this plan.

## Threat Flags

None — no new network endpoints or trust boundaries introduced. Eight endpoints deleted (attack surface reduced). Analytics reimplementation uses same `require_role(admin)` guard as the 501 stubs it replaced.

## Self-Check: PASSED

- `backend/app/services/prereqs.py` — MISSING (correctly deleted)
- Commit bcc8578 — FOUND
- Commit 59b6eee — FOUND
- Commit 951f6ac — FOUND
- Commit f6ac035 — FOUND
- Commit f9024b2 — FOUND
- Commit 6f7530d — FOUND
- Final pytest: 206 passed, 0 skipped, 0 failed
