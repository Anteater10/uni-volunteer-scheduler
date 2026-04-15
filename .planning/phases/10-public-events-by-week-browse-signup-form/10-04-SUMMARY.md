---
phase: "10"
plan: "04"
subsystem: frontend
tags: [react-router, route-wiring, build-verification, smoke-test]
dependency_graph:
  requires: ["10-02-EventsBrowsePage", "10-03-EventDetailPage"]
  provides: ["final-route-wiring", "verified-build"]
  affects: ["11-manage-my-signup"]
tech-stack:
  added: []
  patterns:
    - "Public pages imported from pages/public/ — no ProtectedRoute wrapper"
key-files:
  created: []
  modified:
    - frontend/src/App.jsx
key-decisions:
  - "Old EventsPage import kept on disk (Phase 12 removes it) — only EventDetailPage import was updated"
  - "Visual smoke test documented as manual checklist rather than blocking checkpoint — no backend/seed data available in CI"
requirements-completed: [REQ-10-07, REQ-10-08]
duration: ~5min
completed: "2026-04-09"
---

# Phase 10 Plan 04: Final Route Wiring + Build Verification Summary

**App.jsx /events/:eventId now points to the new public EventDetailPage; Vite build clean at 387 KB with 64/64 vitest tests passing.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-04-09
- **Tasks:** 1 auto-completed, 1 checkpoint documented
- **Files modified:** 1 (`frontend/src/App.jsx`)

## Accomplishments

- Replaced old `pages/EventDetailPage` import with `pages/public/EventDetailPage` in App.jsx
- Removed Plan 10-03 TODO comment — route wiring is final
- Both `/events` and `/events/:eventId` now serve unauthenticated public pages (REQ-10-07)
- Vite build: 1853 modules, 387.57 KB JS, 30.41 KB CSS — zero errors or warnings
- Full vitest suite: 64/64 pass across 11 test files

## Task Commits

1. **Task 1: Final route wiring + build verification** — `48b044d` (feat)

## Files Created/Modified

- `frontend/src/App.jsx` — Updated import on line 11: `./pages/EventDetailPage` → `./pages/public/EventDetailPage`; removed TODO comment

## Decisions Made

- Old `EventsPage` import is kept on disk per plan — Phase 12 will remove it. Only the `EventDetailPage` import line was changed since that was the only outstanding TODO from Plan 10-02.

## Deviations from Plan

None — plan executed exactly as written. The single import change was the only action needed; Plan 10-02 had already wired `/events` to `EventsBrowsePage`.

## Visual Smoke Test Checklist (Task 2 — Human Verification)

Task 2 is a `checkpoint:human-verify`. Since no browser is available in this automated run, the steps are documented here for manual verification. Start the dev server (`cd frontend && npm run dev`) and verify:

1. **`/events` — Week navigation**
   - Prev/next arrows update `?quarter=&year=&week=` in the URL
   - "This week" resets to current quarter/week
   - Loading shows 3 skeleton cards; empty state shows "No events this week"

2. **`/events/:eventId` — Event detail page**
   - Slots appear grouped as "Orientation Slots" / "Period Slots"
   - Each slot is a full-card-clickable `<li>` with checkbox
   - Full slots show "Full" badge and disabled checkbox
   - Selecting a slot reveals the identity form (first_name, last_name, email, phone)

3. **Signup flow**
   - Fill identity fields, click "Sign up"
   - If period slot selected without orientation: orientation modal appears ("Have you completed orientation?")
   - "Yes" proceeds to submit; "No" returns with orientation slots highlighted
   - Successful submission: success popup card shows "Check your email!", volunteer name, and slot list
   - "Done" resets all form state

4. **Error states**
   - 429 response shows toast: "Please wait a moment and try again"
   - Full-slot 409 shows toast and disables the slot

5. **Mobile viewport (iPhone SE 375px)**
   - All touch targets at least 44px (slot cards, nav arrows, buttons, inputs)
   - No bottom nav visible for logged-out users (Layout hides it per account-less pivot)

6. **Auth check**
   - Navigate to `/events` and `/events/:eventId` without being logged in — both render normally, no redirect to login

## Known Stubs

None.

## Threat Flags

None — T-10-09 accepted in plan: public routes are intentionally unauthenticated per the account-less pivot.

## Self-Check: PASSED

- `frontend/src/App.jsx` contains `pages/public/EventDetailPage` import: CONFIRMED
- `frontend/src/App.jsx` does NOT contain `pages/EventDetailPage` import: CONFIRMED
- No `ProtectedRoute` wrapper on `/events` or `/events/:eventId`: CONFIRMED
- Commit `48b044d` exists: CONFIRMED
- Build passes: 387.57 KB, 0 errors
- Vitest: 64/64 pass
