---
phase: 12-retirement-pass
plan: 02
subsystem: frontend
tags: [deletion, routing, nav, api-cleanup, role-guards]
completed: 2026-04-10T19:03:11Z
duration_minutes: 25
tasks_completed: 2
files_modified: 17
files_deleted: 13

dependency_graph:
  requires: []
  provides:
    - Clean frontend with no dead imports, routes, or nav entries
    - Role-guarded notifications/profile routes (organizer/admin only)
    - TemplatesSection with no prereq_slugs fields
    - api.js with no dead student-facing functions
  affects:
    - frontend/src/App.jsx
    - frontend/src/components/Layout.jsx
    - frontend/src/lib/api.js
    - frontend/src/pages/LoginPage.jsx
    - frontend/src/pages/admin/TemplatesSection.jsx

tech_stack:
  added: []
  patterns:
    - Role guards via ProtectedRoute roles prop (already supported, now applied to notifications/profile)

key_files:
  created: []
  deleted:
    - frontend/src/pages/RegisterPage.jsx
    - frontend/src/pages/MySignupsPage.jsx
    - frontend/src/pages/EventsPage.jsx
    - frontend/src/pages/SignupConfirmedPage.jsx
    - frontend/src/pages/SignupConfirmFailedPage.jsx
    - frontend/src/pages/SignupConfirmPendingPage.jsx
    - frontend/src/pages/admin/OverridesSection.jsx
    - frontend/src/pages/AdminTemplatesPage.jsx
    - frontend/src/components/PrereqWarningModal.jsx
    - frontend/src/components/ModuleTimeline.jsx
    - frontend/src/components/__tests__/PrereqWarningModal.test.jsx
    - frontend/src/components/__tests__/ModuleTimeline.test.jsx
    - frontend/src/pages/EventDetailPage.jsx (old v1.0, no route, imported deleted PrereqWarningModal)
  modified:
    - frontend/src/App.jsx
    - frontend/src/components/Layout.jsx
    - frontend/src/pages/LoginPage.jsx
    - frontend/src/lib/api.js
    - frontend/src/pages/admin/TemplatesSection.jsx
    - frontend/src/lib/__tests__/api.test.js

decisions:
  - key: D-01 — LoginPage title updated to "Organizer / Admin Login" per research doc locked decision
  - key: D-02 — notifications and profile routes moved to organizer/admin role guard (T-12-03 mitigation)
  - key: D-03 — api.public.createSignup kept; only top-level student createSignup deleted

metrics:
  duration_minutes: 25
  completed: 2026-04-10
  tasks: 2
  files_deleted: 13
  files_modified: 5
  test_count_before: ~78
  test_count_after: 73
---

# Phase 12 Plan 02: Frontend Retirement — Summary

**One-liner:** Deleted 13 dead frontend files (10 pages, 2 test files, 1 old non-routed page), cleaned App.jsx routes and imports, stripped prereq_slugs from TemplatesSection, removed dead API functions from api.js, and added role guards to notifications/profile routes.

## What Was Deleted

| File | Reason |
|------|--------|
| `pages/RegisterPage.jsx` | Student self-registration retired in v1.1 |
| `pages/MySignupsPage.jsx` | Auth'd student signups retired; replaced by magic-link manage |
| `pages/EventsPage.jsx` | Old auth'd events list; EventsBrowsePage was already the live route |
| `pages/SignupConfirmedPage.jsx` | Replaced by ConfirmSignupPage at /signup/confirm |
| `pages/SignupConfirmFailedPage.jsx` | Replaced by error handling in ConfirmSignupPage |
| `pages/SignupConfirmPendingPage.jsx` | Replaced by spinner state in ConfirmSignupPage |
| `pages/admin/OverridesSection.jsx` | Prereq overrides retired; backend endpoints already 501 |
| `pages/AdminTemplatesPage.jsx` | Old standalone templates page; no route, dead import |
| `components/PrereqWarningModal.jsx` | Only used by old EventDetailPage (deleted); not used by new public page |
| `components/ModuleTimeline.jsx` | Only used by MySignupsPage (deleted) |
| `components/__tests__/PrereqWarningModal.test.jsx` | Tests deleted component |
| `components/__tests__/ModuleTimeline.test.jsx` | Tests deleted component |
| `pages/EventDetailPage.jsx` | Old v1.0 page with no route; imported deleted PrereqWarningModal |

## What Was Changed

**App.jsx:**
- Removed 12 dead imports
- Removed routes: `/register`, `/my-signups`, `/signup/confirmed`, `/signup/confirm-failed`, `/signup/confirm-pending`, `/admin/overrides`
- Moved `notifications` and `profile` routes into `<ProtectedRoute roles={["organizer", "admin"]}>` block

**Layout.jsx:**
- Deleted `studentNavItems` array (Events, My Signups, Profile)
- Removed `"participant"` case from `navItemsForRole()`
- Removed unused `ListChecks` import
- Removed `<Link to="/register">Register</Link>` from header

**LoginPage.jsx:**
- Removed "Create an account" Register button and `<Link to="/register">` 
- Updated page title to "Organizer / Admin Login"
- Removed unused `Link` import

**api.js:**
- Deleted functions: `register()`, `createSignup()`, `cancelSignup()` (student), `listMySignups()`, `getModuleTimeline()`
- Removed from exports: `register`, `createSignup`, `cancelSignup`, `listMySignups`, `moduleTimeline`
- Removed nested aliases: `api.signups.create`, `api.signups.cancel`, `api.signups.my`
- Removed `api.admin.overrides.list/create/revoke`
- Kept: `api.public.createSignup`, `api.admin.signups.cancel`, all other surviving functions

**TemplatesSection.jsx:**
- Removed `prereq_slugs` from form state initialization and reset
- Removed prereq_slugs form field from Create Modal
- Removed Prereqs column from desktop table (header and row cells)
- Removed prereq_slugs mobile card display
- Simplified `handleInlineUpdate` (removed CSV-split branch)
- Removed `prereq_slugs` from createMut payload

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] api.test.js tested createSignup which was deleted**
- **Found during:** Task 2 verification (npm run test)
- **Issue:** `src/lib/__tests__/api.test.js` had a single test: `expect(typeof api.createSignup).toBe('function')`. After deleting `createSignup`, this test failed.
- **Fix:** Rewrote test file to verify surviving public API surface (`api.public.createSignup`, `api.login`) and explicitly assert that retired functions are absent (`api.createSignup`, `api.listMySignups`, `api.admin.overrides`)
- **Files modified:** `frontend/src/lib/__tests__/api.test.js`
- **Commit:** 3f01a4f

**2. [Rule 2 - Missing cleanup] Old unreachable EventDetailPage.jsx deleted**
- **Found during:** Post-deletion grep verification (`grep ... RegisterPage|...|PrereqWarningModal`)
- **Issue:** `frontend/src/pages/EventDetailPage.jsx` (the old v1.0 non-public EventDetailPage) had no route in App.jsx (routes only point to `pages/public/EventDetailPage`) but imported `PrereqWarningModal` which we deleted. The research doc listed `EventsPage.jsx` for deletion but not this file — the old `EventDetailPage.jsx` was already dead (no route).
- **Fix:** Deleted the file. The live page at `pages/public/EventDetailPage.jsx` is unaffected.
- **Commit:** b1219b5

## Verification Results

| Check | Result |
|-------|--------|
| `npm run build` | PASS — 0 errors |
| `npm run test -- --run` | PASS — 73 tests, 0 failures |
| grep for dead page names | 0 matches |
| grep for prereq_slugs | 0 matches |
| grep for dead API functions (top-level) | 0 matches |

## Test Count

- Before: ~78 tests (previous baseline included PrereqWarningModal.test + ModuleTimeline.test + old api.test)
- After: 73 tests passing
- Deleted test files reduced count by ~5; new api.test.js added 5 tests replacing 1

## Known Stubs

None. This plan was pure deletion — no new stubs introduced.

## Threat Flags

None. Deletion reduces attack surface. Role guards on notifications/profile tighten existing access (T-12-03 mitigated).

## Self-Check: PASSED

- App.jsx exists: FOUND
- Layout.jsx exists: FOUND
- LoginPage.jsx exists: FOUND
- api.js exists: FOUND
- TemplatesSection.jsx exists: FOUND
- 12-02-SUMMARY.md: CREATED
- Commits: bb7cf11, 59f6f2e, 7aca57f, 3f01a4f, b1219b5 — all verified in git log
- Build: PASS
- Tests: 73 passing
