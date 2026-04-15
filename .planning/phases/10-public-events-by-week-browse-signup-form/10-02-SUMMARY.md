---
phase: "10"
plan: "02"
subsystem: "frontend/public"
tags: ["react", "react-query", "react-router", "public-browse", "week-nav"]
dependency_graph:
  requires: ["10-01"]
  provides: ["EventsBrowsePage", "App.jsx route wiring for /events"]
  affects: ["frontend/src/App.jsx"]
tech_stack:
  added: []
  patterns:
    - "useSearchParams for URL-synced week navigation"
    - "useQuery with enabled flag for deferred fetch"
    - "events grouped by school via reduce()"
key_files:
  created:
    - frontend/src/pages/public/EventsBrowsePage.jsx
    - frontend/src/pages/__tests__/EventsBrowsePage.test.jsx
  modified:
    - frontend/src/App.jsx
decisions:
  - "Used native button + className for prev/next arrows instead of Button component to avoid size prop clashing with touch-target classes (min-h-11 min-w-11 set directly)"
  - "vi.mock for api + weekUtils placed before component import so vitest hoisting intercepts correctly — require() inside tests caused authStorage resolution failures"
  - "Loading state triggers when EITHER getCurrentWeek OR listEvents is pending, preventing flash of empty state before params are ready"
metrics:
  duration: "~12 min"
  completed: "2026-04-09"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
---

# Phase 10 Plan 02: Events Browse Page with Week Nav + Route Wiring Summary

**One-liner:** Public EventsBrowsePage with prev/next/this-week navigation synced to URL query params (`?quarter=&year=&week=`), events grouped by school, and 7 Vitest tests covering all states.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | EventsBrowsePage component + route wiring | `3f47171` | `pages/public/EventsBrowsePage.jsx`, `App.jsx` |
| 2 | Vitest component tests (TDD GREEN) | `aa81959` | `pages/__tests__/EventsBrowsePage.test.jsx` |

## What Was Built

### EventsBrowsePage (`frontend/src/pages/public/EventsBrowsePage.jsx`)

- **Week navigator:** ChevronLeft/ChevronRight arrows (min-h-11 min-w-11 touch targets) + "This week" Button. All three update `?quarter=&year=&week=` via `useSearchParams`.
- **Data fetching:**
  - `useQuery(["publicCurrentWeek"])` → `api.public.getCurrentWeek()` — provides defaults when no URL params present.
  - `useQuery(["publicEvents", quarter, year, weekNumber])` → `api.public.listEvents()` — only fires when all three params are set (`enabled: allParamsReady`).
  - 429 errors: `toast.error("Please wait a moment and try again")` before re-throwing.
- **Event display:** events grouped by school via `reduce()`, each school gets an `<h2>` heading, each event gets an `<EventCard>` that `Link`s to `/events/{event.id}`.
- **States:** loading (3 Skeleton cards), empty (EmptyState), error (EmptyState + Retry button), populated.
- **No auth dependency:** does not call `useAuth()`, no ProtectedRoute wrapper (REQ-10-07).

### App.jsx changes

- `/events` route now renders `EventsBrowsePage` (imported from `pages/public/EventsBrowsePage`).
- Old `EventsPage` import kept with comment — Phase 12 removes it.
- `/events/:eventId` keeps old `EventDetailPage` with a TODO comment marking it for Plan 10-03 replacement.

### Test file (`frontend/src/pages/__tests__/EventsBrowsePage.test.jsx`)

7 tests, all pass:

1. Renders loading skeletons while data is pending
2. Renders event cards after data loads (2-event mock)
3. Shows EmptyState when no events returned
4. Clicking next week arrow calls `getNextWeek` and updates URL
5. Clicking "This week" resets to `getCurrentWeek` values
6. Events grouped by school with h2 headings
7. Renders without AuthProvider wrapper (no crash, REQ-10-07)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] vitest `require()` in test body caused authStorage resolution failure**
- **Found during:** Task 2
- **Issue:** Original test draft used `const api = require("../../lib/api").default` inside `beforeEach` to access mock fn instances. Vitest's module system tried to resolve `api.js`'s real transitive dependency (`authStorage`) before the mock was applied, producing "Cannot find module authStorage" errors.
- **Fix:** Changed to `import api from "../../lib/api"` at top level (after `vi.mock`). Since `vi.mock` is hoisted, the imported `api` IS the mocked version. All `vi.fn()` references accessed directly.
- **Files modified:** `src/pages/__tests__/EventsBrowsePage.test.jsx`
- **Commit:** `aa81959`

## Verification Results

- `npx vite build` — passes, 383 KB bundle, 0 errors
- `npx vitest run src/pages/__tests__/EventsBrowsePage.test.jsx` — 7/7 pass
- `npm run test -- --run` — 50/50 pass (full suite)
- `/events` route renders `EventsBrowsePage` (confirmed in App.jsx)
- Old `EventsPage` file still on disk (`frontend/src/pages/EventsPage.jsx`)

## Known Stubs

None. EventsBrowsePage calls real API endpoints via `api.public.*` and displays real data.

## Threat Flags

No new trust boundaries or security-relevant surfaces introduced. All data displayed is public (event titles, school names, dates, slot counts). Threat model accepted in plan (T-10-03, T-10-04).

## Self-Check: PASSED

- [x] `frontend/src/pages/public/EventsBrowsePage.jsx` exists (161 lines)
- [x] `frontend/src/pages/__tests__/EventsBrowsePage.test.jsx` exists (266 lines)
- [x] `frontend/src/App.jsx` contains `EventsBrowsePage`
- [x] Commit `3f47171` exists
- [x] Commit `aa81959` exists
- [x] Build passes
- [x] 7/7 tests pass
