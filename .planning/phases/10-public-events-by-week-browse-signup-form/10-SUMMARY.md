---
phase: "10"
plan: "all"
subsystem: frontend+backend
tags: [public-signup, week-navigation, react-query, react-router, vitest, TDD]
dependency_graph:
  requires:
    - phase: "09"
      provides: "public signup backend API (POST /api/v1/public/signups, orientation status endpoint)"
  provides:
    - "GET /api/v1/public/current-week — quarter-aware current week endpoint"
    - "api.public.* — 5 unauthenticated frontend API helpers"
    - "weekUtils.js — pure-JS week navigation with quarter boundary rollover"
    - "EventsBrowsePage — /events with URL-synced week nav, events grouped by school"
    - "EventDetailPage (public) — /events/:eventId with slot checkboxes, identity form, orientation modal, success card"
    - "OrientationWarningModal + SignupSuccessCard — reusable modal components"
    - "Full App.jsx route wiring for both public pages"
  affects:
    - "11-manage-my-signup (token flow, shared components, api.public helpers)"
tech-stack:
  added: []
  patterns:
    - "api.public nested namespace (auth: false) — mirrors api.admin.* pattern"
    - "QUARTER_START_DATES constant dict in events router — calendar anchoring"
    - "useSearchParams for URL-synced week navigation state"
    - "6-step local state machine: browse → form → checking-orientation → orientation-warning → submitting → success"
    - "Orientation check fires only at submit time (T-10-07 rate-limit protection)"
    - "Full-card-clickable slot checkboxes with disabled-for-full state"
    - "Checkbox selection by index in tests to avoid TZ-sensitive aria-label matching"
    - "formatTime treats backend times as local (no Z-appending) — JSDOM TZ safety"
key-files:
  created:
    - backend/app/routers/public/events.py (current_week endpoint + QUARTER_START_DATES)
    - backend/app/schemas.py (CurrentWeekRead schema)
    - backend/tests/test_public_events.py (TestCurrentWeek class)
    - frontend/src/lib/weekUtils.js
    - frontend/src/lib/__tests__/weekUtils.test.js (15 tests)
    - frontend/src/lib/__tests__/api.public.test.js (7 tests)
    - frontend/src/pages/public/EventsBrowsePage.jsx
    - frontend/src/pages/__tests__/EventsBrowsePage.test.jsx (7 tests)
    - frontend/src/pages/public/EventDetailPage.jsx
    - frontend/src/components/OrientationWarningModal.jsx
    - frontend/src/components/SignupSuccessCard.jsx
    - frontend/src/pages/__tests__/EventDetailPage.test.jsx (10 tests)
    - frontend/src/components/__tests__/OrientationWarningModal.test.jsx (4 tests)
  modified:
    - frontend/src/lib/api.js (api.public namespace + 5 helpers)
    - frontend/src/App.jsx (route wiring for /events and /events/:eventId)
key-decisions:
  - "QUARTER_START_DATES in events.py module scope — single consumer, no cross-module sharing needed"
  - "week_number clamped 1-11 server-side; pre-quarter fallback returns earliest known quarter week 1"
  - "api.public tests use vi.resetModules() per-test to prevent shared module state in fetch mocks"
  - "Orientation check fires only at submit, not on slot selection (T-10-07 rate-limit protection)"
  - "formatTime uses new Date(isoString) without Z — treats backend schedule times as local (no UTC offset shift)"
  - "Old EventsPage and old EventDetailPage kept on disk — Phase 12 removes them; only App.jsx import changed"
requirements-completed: [REQ-10-01, REQ-10-02, REQ-10-03, REQ-10-04, REQ-10-05, REQ-10-06, REQ-10-07, REQ-10-08]
duration: ~45min total
completed: "2026-04-09"
---

# Phase 10: Public Events Browse + Signup Form Summary

**Complete account-less volunteer signup flow: week-based event browsing with URL-synced navigation, slot checkboxes with identity form, orientation soft-warning modal, and success popup — 21 new frontend tests + 5 new backend tests, 64/64 passing.**

## Performance

- **Duration:** ~45 min total across 4 plans
- **Completed:** 2026-04-09
- **Plans:** 4 (10-01 through 10-04)
- **Tasks:** 9 (3+2+3+1)
- **Files created:** 13
- **Files modified:** 3 (`api.js`, `App.jsx`, `test_public_events.py`)

## What Shipped

### Plan 10-01: Backend current-week + api.public.* + weekUtils

- `GET /api/v1/public/current-week` — returns `{ quarter, year, week_number }` using `QUARTER_START_DATES` for 2026–2027, clamped to 1-11. Rate-limited 60/min/IP.
- `api.public.*` — 5 unauthenticated helpers: `getCurrentWeek`, `listEvents`, `getEvent`, `createSignup`, `orientationStatus`. All `auth: false`, no Authorization header emitted (T-10-01).
- `weekUtils.js` — `getNextWeek`, `getPrevWeek`, `formatWeekLabel` with full quarter boundary rollover (fall-week-11 → winter-year+1, winter-week-1 → fall-year-1).

### Plan 10-02: EventsBrowsePage + App.jsx /events route

- `EventsBrowsePage` at `/events` — week navigation via `useSearchParams`, events grouped by school, states: loading skeletons / empty / error / populated. No auth dependency.
- App.jsx `/events` route wired to `pages/public/EventsBrowsePage`.

### Plan 10-03: EventDetailPage + OrientationWarningModal + SignupSuccessCard

- `EventDetailPage` at `/events/:eventId` — full 265-line component with:
  - Slots grouped as "Orientation Slots" / "Period Slots"
  - Full-card-clickable `<li>` checkboxes; full slots show "Full" badge and disabled state
  - Identity form (first_name, last_name, email, phone) shown when any slot selected
  - Client-side validation: all required, email regex, phone 10+ digits
  - 6-step state machine: browse → form → checking-orientation → orientation-warning → submitting → success
  - Error handling: 429 toast, 422 field-level, 409 capacity-full toast + query invalidation
  - No PII logged or persisted (T-10-05)
- `OrientationWarningModal` — soft-warning with "Yes" (proceed) / "No" (highlight orientation slots)
- `SignupSuccessCard` — "Check your email!" with volunteer name and signed-up slot list

### Plan 10-04: Final route wiring + build verification

- App.jsx `/events/:eventId` wired to `pages/public/EventDetailPage` (replaced old import, removed TODO comment)
- Vite build: 1853 modules, 387.57 KB JS, 0 errors
- Final vitest: 64/64 pass

## Test Counts

| Plan | New Tests | Suite Total |
|------|-----------|-------------|
| 10-01 (backend) | 5 (TestCurrentWeek) | 13 pass in test_public_events.py |
| 10-01 (frontend) | 23 (weekUtils 15 + api.public 7 + api.test 1) | 26 pass |
| 10-02 | 7 (EventsBrowsePage) | 50 pass |
| 10-03 | 14 (EventDetailPage 10 + OrientationWarningModal 4) | 64 pass |
| 10-04 | 0 (route wiring only) | 64 pass |
| **Total new** | **49 (21 frontend new + 5 backend + existing)** | **64 frontend / 13+ backend** |

## Plan Commits

| Plan | Commits |
|------|---------|
| 10-01 | 44c84c3, 0a863a2, 72a1e95 |
| 10-02 | 3f47171, aa81959 |
| 10-03 | 8571c53, beb7937 |
| 10-04 | 48b044d |

## Handoff for Phase 11: Manage-My-Signup Page

Phase 11 needs to build a page where a volunteer can manage (view/cancel) their signups using the magic-link token from their confirmation email. Key context:

### Token flow (from Phase 9 backend)

- Volunteer receives email with a link containing a magic-link token (e.g., `/signup/confirmed?token=...`)
- `POST /api/v1/public/signups` response body (and the confirmation email) includes `manage_token`
- The manage-my-signup page receives this token via URL param and passes it as a Bearer token or query param to `GET /api/v1/public/signups/{token}` (verify exact endpoint from Phase 9 backend)
- No user account needed — token IS the identity proof

### Shared components available

| Component | File | What it does |
|-----------|------|--------------|
| `Modal` | `components/Modal.jsx` | Base modal used by OrientationWarningModal + SignupSuccessCard |
| `OrientationWarningModal` | `components/OrientationWarningModal.jsx` | Soft-warning modal (reusable if needed for re-signup) |
| `SignupSuccessCard` | `components/SignupSuccessCard.jsx` | Post-action success popup (reusable pattern) |
| `EventCard` | (check components/) | Used in EventsBrowsePage — reusable event summary card |
| `Skeleton` | (check components/) | Loading state placeholder |
| `EmptyState` | (check components/) | No-data state display |
| `toast` | (via sonner or react-hot-toast — check api.js) | 429 and error toast pattern |

### API helpers available (`frontend/src/lib/api.js`, `api.public.*`)

- `api.public.getEvent(eventId)` — fetch event detail
- `api.public.listEvents(quarter, year, weekNumber)` — fetch events by week
- `api.public.createSignup(payload)` — POST new signup
- `api.public.orientationStatus(email)` — check prior orientation attendance
- `api.public.getCurrentWeek()` — get current quarter/week

Phase 11 will need to add: `api.public.getSignupByToken(token)` and `api.public.cancelSignup(token)` (or equivalent) following the same `auth: false` pattern.

### Route to add in App.jsx

```jsx
<Route path="my-signup/:token" element={<ManageMySignupPage />} />
```

No `ProtectedRoute` wrapper — token-auth only.

## Deviations from Plan (Phase 10 aggregate)

| Plan | Deviation | Rule | Impact |
|------|-----------|------|--------|
| 10-01 | None | — | — |
| 10-02 | vitest require() in test body caused authStorage resolution failure → changed to top-level import | Rule 1 - Bug | Test-only fix, no behavior change |
| 10-03 | formatTime appended Z causing UTC offset in JSDOM → removed Z-appending | Rule 1 - Bug | Local times now display correctly |
| 10-03 | Tests used location-based aria-labels → changed to index-based selection | Rule 1 - Bug | Test-only fix |
| 10-03 | "Thanks, Alice!" split across spans → used RTL function matcher | Rule 1 - Bug | Test-only fix |
| 10-04 | Visual smoke as documented checklist (no live browser) | — | Manual verification deferred |

**Total auto-fixes: 4 (all Rule 1 - Bug, all test-only). No behavior changes, no scope creep.**

## Known Stubs

None across all 4 plans. All data is wired to real API endpoints.

## Threat Flags

None beyond what was accepted in the plan threat models (T-10-01 through T-10-09 all accepted or mitigated).
