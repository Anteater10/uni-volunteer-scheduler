---
phase: "10"
plan: "03"
subsystem: frontend
tags: [public-signup, event-detail, state-machine, orientation-modal, vitest]
dependency_graph:
  requires: ["10-01-api-helpers", "09-public-signup-backend"]
  provides: ["EventDetailPage", "OrientationWarningModal", "SignupSuccessCard"]
  affects: ["10-04-route-wiring"]
tech_stack:
  added: []
  patterns:
    - local-state-machine (browse/form/checking-orientation/orientation-warning/submitting/success)
    - checkbox-slot-selection (full-card-clickable, disabled-for-full-slots)
    - orientation-check-at-submit-only (T-10-07 rate-limit protection)
    - no-pii-logging (T-10-05 compliance)
key_files:
  created:
    - frontend/src/pages/public/EventDetailPage.jsx
    - frontend/src/components/OrientationWarningModal.jsx
    - frontend/src/components/SignupSuccessCard.jsx
    - frontend/src/pages/__tests__/EventDetailPage.test.jsx
    - frontend/src/components/__tests__/OrientationWarningModal.test.jsx
  modified: []
decisions:
  - "Slot checkbox aria-labels use time+date (not location) — tests select by index to avoid TZ sensitivity"
  - "formatTime uses new Date(isoString) without appending Z — treats backend times as local to avoid UTC offset in JSDOM"
  - "Tests 7/8 success card: getByText with function matcher to handle 'Thanks, {name}!' split across spans"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-04-09"
  tasks_completed: 3
  files_changed: 5
---

# Phase 10 Plan 03: Event Detail Page + Signup Form + Orientation Modal + Success Card Summary

**One-liner:** Complete volunteer signup UX with slot checkboxes, identity form, 6-step state machine, orientation soft-warning modal, and success popup card — 14 vitest tests all passing.

## What Was Built

### EventDetailPage.jsx (new — 265 lines)
Full signup page at `/events/:eventId`:
- Fetches event via `api.public.getEvent(eventId)` with React Query
- Slots grouped by type: "Orientation Slots" / "Period Slots" sections
- Each slot is a full-card-clickable `<li>` with a `type="checkbox"` input
- Full slots (filled >= capacity): checkbox disabled, "Full" badge, muted ring
- Orientation slots highlighted with `ring-2 ring-[var(--color-primary)]` when `highlightOrientation=true`
- Identity form (first_name, last_name, email, tel) shown when any slot is selected
- Client-side validation: all fields required, email regex, phone 10+ digits
- 6-step state machine: `browse` → `form` → `checking-orientation` → `orientation-warning` → `submitting` → `success`
- Orientation check: only fires at submit time, only when period selected without orientation slot
- Error handling: 429 toast, 422 field-level errors, capacity-full 409/message toast + query invalidation
- No PII logged or persisted (T-10-05)

### OrientationWarningModal.jsx (new — 40 lines)
Soft-warning modal using existing `Modal` component:
- Props: `{ open, onYes, onNo }`
- Title: "Have you completed orientation?"
- Two stacked buttons: "Yes, I have completed orientation" (primary) + "No — show me orientation slots" (secondary)
- `onClose` wired to `onNo` (backdrop click and Escape = same as No)

### SignupSuccessCard.jsx (new — 66 lines)
Post-signup popup using existing `Modal` component:
- Props: `{ open, volunteerName, slots, onDismiss }`
- Shows "Check your email!" heading, "Thanks, {name}!" subtitle
- Renders each signed-up slot as a formatted list item (date, time range, location)
- "Done" button calls `onDismiss` which resets all form state

### Tests (new — 557 lines total)
- `EventDetailPage.test.jsx`: 10 tests covering full state machine
- `OrientationWarningModal.test.jsx`: 4 tests covering render/callbacks

## Test Results

14/14 pass. Full suite: 64 passed, 0 failed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] formatTime appended Z causing UTC offset in JSDOM**
- **Found during:** Task 3 RED phase — test times showed "2:00 AM" instead of "9:00 AM"
- **Issue:** The component appended `Z` to times without timezone markers, causing JSDOM to format them as UTC (9:00 → 2:00 AM in UTC-7 test env)
- **Fix:** Removed Z-appending in `formatTime` — treat backend times as local time (they represent local school schedule times)
- **Files modified:** `frontend/src/pages/public/EventDetailPage.jsx`
- **Commit:** beb7937 (included in test commit)

**2. [Rule 1 - Bug] Tests using location-based aria-labels that don't match rendered labels**
- **Found during:** Task 3 RED phase — `getByRole("checkbox", { name: /Room 202/i })` failed
- **Issue:** Checkbox aria-labels use `"Select slot at {time} on {date}"` format, not location
- **Fix:** Updated tests to select checkboxes by index (ordered: orientation[0], period[1], full-disabled[2])
- **Files modified:** `frontend/src/pages/__tests__/EventDetailPage.test.jsx`

**3. [Rule 1 - Bug] "Thanks, Alice!" split across DOM elements**
- **Found during:** Task 3 GREEN phase — `getByText(/Thanks, Alice/i)` failed because text is split: `Thanks,` + `<span>Alice</span>` + `!`
- **Fix:** Used RTL function matcher `getByText((_, el) => el.tagName === "P" && el.textContent.includes("Thanks,") && el.textContent.includes("Alice"))`
- **Files modified:** `frontend/src/pages/__tests__/EventDetailPage.test.jsx`

## Known Stubs

None — all data is wired to real API calls. The `successData` displayed in the success card uses the slot objects already held in component state (not stub data).

## Threat Flags

No new trust boundaries. All PII handling confirmed:
- No `console.log` of identity fields
- No `localStorage` or `sessionStorage` writes
- Identity state cleared on `handleDismissSuccess` and on component unmount
- orientationStatus called once at submit time only (T-10-07)

## Self-Check

Files exist:
- frontend/src/pages/public/EventDetailPage.jsx: EXISTS
- frontend/src/components/OrientationWarningModal.jsx: EXISTS
- frontend/src/components/SignupSuccessCard.jsx: EXISTS
- frontend/src/pages/__tests__/EventDetailPage.test.jsx: EXISTS
- frontend/src/components/__tests__/OrientationWarningModal.test.jsx: EXISTS

Commits present:
- 8571c53 feat(10-03): EventDetailPage + OrientationWarningModal + SignupSuccessCard
- beb7937 test(10-03): 14 vitest tests for EventDetailPage + OrientationWarningModal

## Self-Check: PASSED
