---
phase: 12-retirement-pass
plan: 03
subsystem: full-stack
tags: [deletion, verification, retirement, cleanup, phase-complete]
completed: 2026-04-09
duration_minutes: ~75
tasks_completed: 3
files_modified: 14
files_deleted: 14

dependency_graph:
  requires: ["12-01", "12-02"]
  provides:
    - Phase 12 verified clean: zero dead references, zero skipped tests, zero 501 stubs
    - Final test baselines: backend 206/0/0, frontend 73/0
    - Clean handoff state for Phase 13 E2E + Playwright
  affects:
    - backend/app/ (all routers, schemas, services)
    - frontend/src/ (pages, components, lib/api.js)

tech_stack:
  added: []
  patterns:
    - Volunteer-email-match for CCPA (no direct FK between User and Volunteer)
    - Signup->Slot->Event->Volunteer join for analytics queries
    - Role guards via ProtectedRoute roles prop

key_files:
  created:
    - .planning/phases/12-retirement-pass/12-SUMMARY.md
  deleted:
    - backend/app/services/prereqs.py
    - frontend/src/pages/RegisterPage.jsx
    - frontend/src/pages/MySignupsPage.jsx
    - frontend/src/pages/EventsPage.jsx
    - frontend/src/pages/SignupConfirmedPage.jsx
    - frontend/src/pages/SignupConfirmFailedPage.jsx
    - frontend/src/pages/SignupConfirmPendingPage.jsx
    - frontend/src/pages/admin/OverridesSection.jsx
    - frontend/src/pages/AdminTemplatesPage.jsx
    - frontend/src/pages/EventDetailPage.jsx (old v1.0 unreachable)
    - frontend/src/components/PrereqWarningModal.jsx
    - frontend/src/components/ModuleTimeline.jsx
    - frontend/src/components/__tests__/PrereqWarningModal.test.jsx
    - frontend/src/components/__tests__/ModuleTimeline.test.jsx
  modified:
    - backend/app/routers/admin.py
    - backend/app/routers/users.py
    - backend/app/routers/signups.py
    - backend/app/routers/auth.py
    - backend/app/schemas.py
    - backend/tests/test_signups.py
    - backend/tests/test_admin.py
    - backend/tests/test_admin_phase7.py
    - backend/tests/test_auth.py
    - frontend/src/App.jsx
    - frontend/src/components/Layout.jsx
    - frontend/src/pages/LoginPage.jsx
    - frontend/src/lib/api.js
    - frontend/src/lib/__tests__/api.test.js
    - frontend/src/pages/admin/TemplatesSection.jsx

decisions:
  - key: D-01 — RewriteSignupTests — old test_signups.py tested a deleted POST /signups/ endpoint; rewrote 8 tests covering admin cancel, FIFO waitlist promotion, idempotency, Celery email enqueue
  - key: D-02 — CCPAEmailMatch — User linked to Volunteer by email (no FK); simplest correct approach given schema, email unique in both tables
  - key: D-03 — NoShowRateCount — NoShowRateRow.count is no_show count (not total denominator); matches ExportsSection expectations
  - key: D-04 — KeepPublicCreateSignup — api.public.createSignup retained; only top-level student createSignup deleted
  - key: D-05 — RegisterEndpointTest — test_register_returns_user_record rewritten as test_register_endpoint_removed (asserts 404)

metrics:
  duration_minutes: ~75
  completed_date: 2026-04-09
  plans: 3
  files_deleted: 14
  files_modified: 14
  backend_tests_before: "188 passed, 12 skipped, 0 failed"
  backend_tests_after: "206 passed, 0 skipped, 0 failed"
  frontend_tests_before: "~78 passed"
  frontend_tests_after: "73 passed, 0 failed"
---

# Phase 12: Retirement Pass — Complete Summary

**One-liner:** Deleted all v1.0 dead code (14 files: 1 backend service, 13 frontend pages/components/tests), removed 7 dead endpoints, reimplemented 3 analytics 501s and the CCPA signups stub with volunteer-keyed queries, rewrote 12 skipped backend tests, cleaned all frontend routes/nav/api — codebase now has a single mental model.

## What Was Deleted

### Backend (Plan 12-01)

| Item | Reason |
|------|--------|
| `backend/app/services/prereqs.py` | `PrereqOverride` model dropped in migration 0009; import guard was the only thing keeping this alive |
| `GET /users/me/module-timeline` | Used deleted `Signup.user_id`, `PrereqOverride` model, `prereq_slugs` column, `check_missing_prereqs` service |
| `GET /signups/my` | Stub returning `[]`; v1.1 volunteers use magic-link manage page |
| `GET /signups/my/upcoming` | Same |
| `POST /auth/register` | Student self-registration retired; organizer/admin accounts created via admin UI |
| `GET /admin/prereq-overrides` | Was 501; `PrereqOverride` model deleted in Phase 08 |
| `POST /admin/users/{user_id}/prereq-overrides` | Was 501; same |
| `DELETE /admin/prereq-overrides/{override_id}` | Was 501; same |
| Schemas: `PrereqOverrideCreate`, `PrereqOverrideRead`, `ModuleTimelineItem` | Used only by deleted endpoints |

### Frontend (Plan 12-02)

| File | Reason |
|------|--------|
| `pages/RegisterPage.jsx` | Student self-registration retired in v1.1 |
| `pages/MySignupsPage.jsx` | Auth'd student signups retired; replaced by magic-link manage |
| `pages/EventsPage.jsx` | Old auth'd events list; `EventsBrowsePage` was already the live route |
| `pages/SignupConfirmedPage.jsx` | Replaced by `ConfirmSignupPage` at `/signup/confirm` |
| `pages/SignupConfirmFailedPage.jsx` | Replaced by error handling in `ConfirmSignupPage` |
| `pages/SignupConfirmPendingPage.jsx` | Replaced by spinner state in `ConfirmSignupPage` |
| `pages/admin/OverridesSection.jsx` | Prereq overrides retired; backend endpoints already 501 |
| `pages/AdminTemplatesPage.jsx` | Old standalone templates page; no route, dead import |
| `components/PrereqWarningModal.jsx` | Only used by old EventDetailPage (deleted) |
| `components/ModuleTimeline.jsx` | Only used by MySignupsPage (deleted) |
| `pages/EventDetailPage.jsx` (old v1.0) | No route in App.jsx; imported deleted `PrereqWarningModal` |
| `__tests__/PrereqWarningModal.test.jsx` | Tests deleted component |
| `__tests__/ModuleTimeline.test.jsx` | Tests deleted component |

## What Was Reimplemented

### Analytics Endpoints (was 501, now live)

**`GET /admin/analytics/volunteer-hours`**
Joins `Signup -> Slot -> Event -> Volunteer`, filters `status == attended`, groups by `volunteer_id`, sums `(slot.end_time - slot.start_time)` in hours. Applies optional `from_date`/`to_date` filters on `Event.start_date`.

**`GET /admin/analytics/no-show-rates`**
Same join, filters `status in [attended, no_show]`, groups by volunteer, computes per-volunteer no-show rate. Skips zero-denominator volunteers.

**`GET /admin/analytics/volunteer-hours.csv`**
Same query as JSON endpoint, streamed via `StreamingResponse` with `csv.writer`. Columns: `volunteer_name, email, hours, events`.

**CCPA Export signups** (was `[]` stub, now live)
Looks up `Volunteer` by `user.email` match (no FK between `User` and `Volunteer`). Collects all `Signup` rows for that volunteer. Returns `[]` for admin-only accounts with no volunteer record (correct behavior).

### Schema Updates
- `VolunteerHoursRow`: `user_id -> volunteer_id`, `name -> volunteer_name`, added `email` field
- `NoShowRateRow`: `user_id -> volunteer_id`, `name -> volunteer_name`

## Test Suite Changes

### Backend

| Metric | Before | After |
|--------|--------|-------|
| Passed | 188 | 206 |
| Skipped | 12 | 0 |
| Failed | 0 | 0 |

12 tests moved from skipped to passing:
- **test_signups.py (8):** Rewrote — new tests cover admin cancel, FIFO waitlist promotion, idempotency, Celery email enqueue, 403/404 edge cases
- **test_admin.py (1):** Rewrote `test_admin_cancel_signup_promotes_waitlist` to use `VolunteerFactory`
- **test_admin_phase7.py (3):** New tests for analytics shape, CCPA signups non-empty, CCPA delete preserves signup
- **test_auth.py (bonus):** `test_register_returns_user_record` rewritten as `test_register_endpoint_removed` (asserts 404)

### Frontend

| Metric | Before | After |
|--------|--------|-------|
| Tests | ~78 | 73 |
| Failed | 0 | 0 |

Net -5: deleted 2 test files (~6 tests), rewrote api.test.js (1 old test → 5 new tests covering surviving API surface).

## Final Verification Results (Plan 12-03)

| Check | Command | Result |
|-------|---------|--------|
| Backend boot | `python -c "from app.main import app; print('OK')"` | OK |
| Backend pytest | `pytest -q --no-cov` | **206 passed, 0 skipped, 0 failed** |
| Frontend build | `npm run build` | **0 errors**, 1.91s |
| Frontend tests | `npm run test -- --run` | **73 passed, 11 files** |
| Dead-reference grep (full) | multi-pattern grep on `backend/app/` + `frontend/src/` | **0 live code matches** |
| Dead API functions | grep for `listMySignups`, `getModuleTimeline`, `admin.overrides.*` in api.js | **0 matches** |
| Dead backend routes | grep for `signups/my`, `auth/register`, `prereq-overrides`, `users/me/module-timeline` | **0 matches** |
| 501 stubs | grep for `status_code=501` | **0 matches** |

Note: Two documentary comments in `backend/app/models.py` mention `prereq_slugs` and `PrereqOverride` — these are intentional migration notes, not live code references.

## Manual Verification Checklist for Phase 13

Start the stack with `docker compose up -d`, then verify:

1. `http://localhost:5173/events` — public browse page loads without login
2. `http://localhost:5173/login` — shows "Organizer / Admin Login" with NO "Register" link
3. Navigate to `/register` — should show 404 or redirect (route removed)
4. Navigate to `/my-signups` — should redirect to login or show 404 (route removed)
5. Log in as admin — admin dashboard loads, Analytics section returns data (no 501 errors)
6. Admin nav — Overrides tab is absent
7. Admin Templates section — no "prereq_slugs" column visible
8. Admin Analytics CSV download — downloads a CSV with correct columns

## Handoff for Phase 13: E2E Seed + Playwright

The codebase is now a single mental model: account-less volunteers + authenticated organizer/admin.

**Phase 13 should test these flows:**

### Public (unauthenticated) flows
| Flow | Route | Key assertions |
|------|-------|----------------|
| Browse events | `/events` | Events list loads, week selector works |
| View event detail | `/events/:id` | Slots visible, signup form present |
| Sign up for slot | `/events/:id` (form submit) | Confirmation email sent, slot count incremented |
| Confirm signup | `/signup/confirm?token=...` | Status → confirmed |
| Manage signups | `/manage?token=...` | Shows confirmed/pending signups |
| Cancel signup | `/manage?token=...` (cancel) | Status → cancelled, slot count decremented |

### Organizer/Admin flows
| Flow | Route | Key assertions |
|------|-------|----------------|
| Login | `/login` | JWT stored, redirect to dashboard |
| Organizer check-in | `/organizer` | Mark attendee/no-show, slot list visible |
| Admin analytics | `/admin` → Analytics tab | Volunteer hours table populated, CSV downloads |
| Admin CCPA export | `/admin` → Exports tab | User data exports, delete request works |
| Admin Templates | `/admin` → Templates tab | No prereq_slugs column, create/edit works |

### Live backend endpoints to cover in E2E
```
GET  /api/v1/public/current-week
GET  /api/v1/public/events
GET  /api/v1/public/events/:id
POST /api/v1/public/signups
POST /api/v1/public/signups/confirm
GET  /api/v1/public/signups/manage
POST /api/v1/public/signups/:id/cancel
POST /api/v1/auth/login
GET  /api/v1/organizer/...
GET  /api/v1/admin/analytics/volunteer-hours
GET  /api/v1/admin/analytics/volunteer-hours.csv
GET  /api/v1/admin/analytics/no-show-rates
GET  /api/v1/admin/users/:id/export
DELETE /api/v1/admin/users/:id
GET  /api/v1/admin/module-templates
POST /api/v1/admin/module-templates
PATCH /api/v1/admin/module-templates/:slug
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_auth.py::test_register_returns_user_record failed after /auth/register deletion (Plan 12-01)**
- **Found during:** Task 3 test run
- **Fix:** Rewrote as `test_register_endpoint_removed` — asserts 404

**2. [Rule 1 - Bug] api.test.js tested createSignup which was deleted (Plan 12-02)**
- **Found during:** Task 2 verification (`npm run test`)
- **Fix:** Rewrote api.test.js to verify surviving public API surface and assert retired functions are absent

**3. [Rule 2 - Missing cleanup] Old unreachable EventDetailPage.jsx deleted (Plan 12-02)**
- **Found during:** Post-deletion grep in Plan 12-02
- **Fix:** Deleted the file (no route in App.jsx, imported deleted PrereqWarningModal)

## Known Stubs

None. All 501 stubs replaced with real implementations. All empty-list stubs (`[]`) replaced or removed.

## Threat Flags

None. Phase 12 reduced attack surface (8 backend endpoints deleted, 6 frontend routes removed). No new trust boundaries introduced.

## Self-Check: PASSED

- `12-SUMMARY.md`: CREATED at `.planning/phases/12-retirement-pass/12-SUMMARY.md`
- Backend: 206 passed, 0 skipped, 0 failed (confirmed in this run)
- Frontend: 73 passed, 0 failed (confirmed in this run)
- Dead-reference grep: 0 live code matches (confirmed in this run)
- 501 stubs: 0 (confirmed in this run)
- Backend boot: OK (confirmed in this run)
- Frontend build: clean (confirmed in this run)
