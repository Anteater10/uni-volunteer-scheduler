---
phase: "11-magic-link-manage-my-signup-flow"
plan: "01"
subsystem: "frontend/public"
tags: [magic-link, volunteer-signup, cancel, react, fastapi, audit-log]
dependency_graph:
  requires: [09-public-signup-backend, 10-public-events-by-week-browse-signup-form]
  provides: [magic-link-confirm-flow, manage-signups-ui, cancel-signup-ui]
  affects: [volunteer-signup-lifecycle]
tech_stack:
  added: []
  patterns: [useQuery-v5-no-onSuccess, tokenOverride-prop-pattern, sequential-cancel-all-loop]
key_files:
  created:
    - frontend/src/pages/public/ManageSignupsPage.jsx
    - frontend/src/pages/public/ConfirmSignupPage.jsx
    - frontend/src/pages/__tests__/ManageSignupsPage.test.jsx
    - frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx
  modified:
    - frontend/src/lib/api.js
    - frontend/src/lib/__tests__/api.public.test.js
    - frontend/src/App.jsx
    - backend/app/routers/public/signups.py
    - backend/tests/test_public_signups.py
decisions:
  - "Inline render: ConfirmSignupPage renders ManageSignupsPage inline after confirm (no redirect) — token stays in URL for bookmarking"
  - "tokenOverride prop: ManageSignupsPage accepts optional tokenOverride prop so ConfirmSignupPage can embed it without router"
  - "Cancel-all sequential loop: frontend iterates non-cancelled signups one-by-one, stops on first error (no new backend endpoint)"
  - "Audit log via extra field: actor_id=None, volunteer_email stored in extra JSON (AuditLog.actor_id is FK to users, not volunteers)"
  - "React Query v5: useEffect for data sync instead of deprecated onSuccess callback"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-09"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 5
---

# Phase 11 Plan 01: Magic-Link Manage-My-Signup Flow Summary

**One-liner:** Token-gated confirm + manage UI for account-less volunteers using magic-link token as sole auth credential.

## What Was Built

Complete account-less signup lifecycle: a volunteer clicks the confirm link from their email, sees a spinner, gets their signups confirmed, then sees a manage view where they can cancel individual signups or all at once using only the magic-link token.

### Files Created

- **`frontend/src/pages/public/ManageSignupsPage.jsx`** (235 lines) — Token-gated manage page. Accepts optional `tokenOverride` prop for inline embedding. Shows signup cards with slot type badge, date, time, location, status. Cancel single via modal + optimistic remove. Cancel all via sequential loop with stop-on-first-error. Token error card with no retry button. Loading skeleton (3 cards). Empty state.

- **`frontend/src/pages/public/ConfirmSignupPage.jsx`** (70 lines) — Email link entry point at `/signup/confirm?token=`. State machine: confirming (spinner) → confirmed (success banner + inline ManageSignupsPage) → error (error card). Idempotent confirm (already-used token) still transitions to confirmed state.

- **`frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`** (7 tests) — Renders signup list, cancel single modal flow, cancel-all sequential loop, token error card, loading skeleton, empty state, 403 permission error toast.

- **`frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx`** (4 tests) — Confirm success → manage view, error card on 400, idempotent confirm → manage view, no-token → immediate error.

### Files Modified

- **`frontend/src/lib/api.js`** — Added `publicConfirmSignup`, `publicGetManageSignups`, `publicCancelSignup` helpers exposed as `api.public.confirmSignup`, `api.public.getManageSignups`, `api.public.cancelSignup`.

- **`frontend/src/lib/__tests__/api.public.test.js`** — Added 3 tests for new helpers (POST /confirm with token, GET /manage with token, DELETE /{id} with token). All use no-auth pattern.

- **`frontend/src/App.jsx`** — Added imports and routes: `signup/confirm` → `ConfirmSignupPage`, `signup/manage` → `ManageSignupsPage`. Neither wrapped in ProtectedRoute.

- **`backend/app/routers/public/signups.py`** — Imported `log_action` from deps. Added `log_action(db, actor=None, action="signup_cancelled", entity_type="signup", entity_id=..., extra={"volunteer_email": ..., "signup_id": ...})` before `db.commit()` in `cancel_signup`.

- **`backend/tests/test_public_signups.py`** — Added `TestCancelSignup.test_cancel_creates_audit_log_entry` which verifies AuditLog row with `action="signup_cancelled"` and correct `volunteer_email` in `extra`.

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| api.public helpers (frontend) | 10 (3 new) | PASS |
| ManageSignupsPage (frontend) | 7 | PASS |
| ConfirmSignupPage (frontend) | 4 | PASS |
| Full frontend suite | 78 | PASS |
| Backend test_public_signups.py | 16 (1 new) | PASS |
| Vite build | — | PASS (0 errors, 1855 modules) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] React Query v5 onSuccess removed**
- **Found during:** Task 2 implementation
- **Issue:** The plan specified using `onSuccess` callback in `useQuery`, but React Query v5 (^5.90.12 in use) removed the `onSuccess` option entirely.
- **Fix:** Used `useEffect(() => { if (data?.signups) setSignups(data.signups); }, [data])` pattern to sync query data to local state.
- **Files modified:** `frontend/src/pages/public/ManageSignupsPage.jsx`

**2. [Rule 1 - Bug] Empty state test — ambiguous text match**
- **Found during:** Task 2 test run
- **Issue:** Test used `/no upcoming signups/i` regex which matched both the `title` and `body` of EmptyState, causing `getByText` to find multiple elements.
- **Fix:** Used exact string match `"No upcoming signups found for this event."` targeting the body text.
- **Files modified:** `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`

## Known Stubs

None — all API calls are wired to real endpoints. No placeholder data.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All token validation is backend-enforced (Phase 09). Frontend handles 400/403 error responses per T-11-02 and T-11-03 dispositions.

## Self-Check: PASSED

- `frontend/src/pages/public/ManageSignupsPage.jsx` — FOUND
- `frontend/src/pages/public/ConfirmSignupPage.jsx` — FOUND
- `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` — FOUND
- `frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx` — FOUND
- Commit e2076cd — FOUND (api helpers + backend audit log)
- Commit 5057de0 — FOUND (ManageSignupsPage)
- Commit 78143cb — FOUND (ConfirmSignupPage + routes)
