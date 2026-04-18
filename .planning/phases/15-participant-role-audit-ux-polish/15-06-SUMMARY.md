---
phase: 15-participant-role-audit-ux-polish
plan: 06
subsystem: frontend/participant
tags: [participant, ux-polish, a11y, error-states, modal, copy]
requires:
  - components/ui/ErrorState (from parallel plan 15-01 — imported pre-merge)
  - components/ui/{Input, Label, FieldError, Skeleton, Modal, Button, PageHeader}
  - lib/useFocusTrap
  - api/checkIn (read-only, untouched)
provides:
  - frontend/src/pages/SelfCheckInPage.jsx (UI-SPEC-aligned check-in flow with PART-09 window-aware errors)
  - frontend/src/components/OrientationWarningModal.jsx (UI-SPEC-aligned soft-warning modal)
affects:
  - frontend/tests/SelfCheckInPage.test.jsx (button-name matcher updated)
  - frontend/src/components/__tests__/OrientationWarningModal.test.jsx (copy matchers updated)
  - e2e/orientation-modal.spec.js (copy assertions updated)
tech-stack:
  added: []
  patterns:
    - "Page-level ErrorState for blocking failure modes (load error, OUTSIDE_WINDOW, INVALID_TRANSITION)"
    - "Inline FieldError + aria-describedby/aria-invalid for form-recoverable errors (WRONG_VENUE_CODE)"
    - "aria-busy=true skeleton stacks for loading state"
    - "Client-side time heuristic for OUTSIDE_WINDOW before/after discrimination (backend gap noted)"
key-files:
  created: []
  modified:
    - frontend/src/pages/SelfCheckInPage.jsx
    - frontend/src/components/OrientationWarningModal.jsx
    - frontend/tests/SelfCheckInPage.test.jsx
    - frontend/src/components/__tests__/OrientationWarningModal.test.jsx
    - e2e/orientation-modal.spec.js
decisions:
  - "Used client-side slot-start comparison to split OUTSIDE_WINDOW into 'isn't open yet' vs 'has closed' since backend does not currently return a before/after discriminator. Documented as backend-bounded gap."
  - "Imported ErrorState from components/ui barrel even though primitive lives in parallel plan 15-01 (per orchestrator note: 'Import from the final path — do not create the primitive yourself. Post-merge test gate catches integration issues.')"
metrics:
  duration: ~25min
  tasks: 2
  files_modified: 5
  completed: 2026-04-15
---

# Phase 15 Plan 06: SelfCheckInPage + OrientationWarningModal Polish — Summary

Polish the two remaining participant surfaces — `/check-in/:signupId` and the orientation
soft-warning modal — to UI-SPEC copy + a11y + PART-09 time-window UX. Both use existing
api.js endpoints; no new data wiring (D-14).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | SelfCheckInPage — ErrorState + primitive Input/Label + UI-SPEC copy + window-aware errors | `d068efb` | frontend/src/pages/SelfCheckInPage.jsx, frontend/tests/SelfCheckInPage.test.jsx |
| 2 | OrientationWarningModal — UI-SPEC copy alignment + a11y verification | `7eb825c` | frontend/src/components/OrientationWarningModal.jsx, frontend/src/components/__tests__/OrientationWarningModal.test.jsx, e2e/orientation-modal.spec.js |

## Error-Kind → UI-Treatment Mapping (SelfCheckInPage)

| Server error kind | UI treatment | Copy (title / body / action) |
|-------------------|--------------|------------------------------|
| _(no error)_ load failure | Page-level `ErrorState` | "We couldn't load this check-in" / "Check your connection and try again." / "Try again" (refetch) |
| `OUTSIDE_WINDOW` (before slot start) | Page-level `ErrorState` | "Check-in isn't open yet" / "Check-in opens 15 minutes before the event starts" / "View event details" |
| `OUTSIDE_WINDOW` (after slot start) | Page-level `ErrorState` | "Check-in has closed" / "Check-in closed when the event ended. Talk to the organizer on-site." / "View event details" |
| `WRONG_VENUE_CODE` | Inline `FieldError` (form preserved) | "That's not the right code. Ask an organizer." (wired via `aria-describedby="venue-code-error"` + `aria-invalid="true"`) |
| `INVALID_TRANSITION` | Page-level `ErrorState` | "Already checked in" / "Our records show you're already marked as attended. No action needed." / "View event details" |

All four `TODO(copy)` markers resolved per UI-SPEC Copywriting Contract:
- Page title `"Check in"` (sentence case, not "Check In")
- Venue code label `"4-digit venue code"`
- Primary CTA `"Check me in"` with `size="lg"` (UI-SPEC §Per-page primary CTA)
- Checked-in success heading `"You're checked in"`

Loading state replaced with `aria-busy="true" aria-live="polite"` Skeleton stack.
Bespoke `<input>` replaced with `Input` + `Label` primitives (44px tap target via `min-h-11`,
proper `label[htmlFor]↔input[id]` association — fixes axe-core placeholder-only warning).

## OrientationWarningModal Copy Changes (Before / After)

| Element | Before | After (UI-SPEC) |
|---------|--------|-----------------|
| Title | `"Have you completed orientation?"` | `"Have you done a Sci Trek orientation?"` |
| Body | `"You selected a period slot but no orientation slot. Have you already attended orientation for this module?"` | `"This event has period slots but no orientation slot. New volunteers need to complete an orientation with Sci Trek before working a period slot."` |
| Primary | `"Yes, I have completed orientation"` | `"I've done orientation — continue"` |
| Secondary | `"No — show me orientation slots"` | `"I haven't — show me orientation events"` |

Modal primitive (already used) provides:
- `role="dialog"` + `aria-modal="true"`
- Focus trap via `useFocusTrap` (existing, not re-implemented)
- ESC key close + restore focus to trigger on close

PART-06 behavior preserved: `onYes` callback proceeds with signup submission;
`onNo` navigates away. Parent (EventDetailPage) wiring untouched.

## Test Updates

### `frontend/tests/SelfCheckInPage.test.jsx`
- Updated 3 button-name matchers from `/check in/i` → `/check me in/i` (label changed
  per UI-SPEC).

### `frontend/src/components/__tests__/OrientationWarningModal.test.jsx` (4 tests)
- Title matcher: `/have you completed orientation/i` → `/have you done a sci trek orientation/i`
- Primary button matcher: `/yes, i have completed orientation/i` → `/i've done orientation/i`
- Secondary button matcher: `/no.*show me orientation/i` → `/i haven't.*show me orientation events/i`
- All 4 tests pass: `cd frontend && npm run test -- OrientationWarningModal --run` → `4 passed`.

### `e2e/orientation-modal.spec.js`
- 3 occurrences of title literal updated to UI-SPEC.
- Primary button matcher updated to `/i've done orientation/i`.
- Header comment block updated to reflect new copy.

## Backend-Bounded Gaps Surfaced (for PART-AUDIT.md)

1. **`OUTSIDE_WINDOW` discriminator** — Backend currently returns only `code: "OUTSIDE_WINDOW"`
   without a `before`/`after` flag. We use a client-side fallback heuristic
   (`new Date() < new Date(slot.start_time)` → "isn't open yet"; else "has closed"). This is
   correct for the common case but races at the exact slot-start boundary. Recommend backend
   add `reason: "before_window" | "after_window"` to the error payload in a future plan.
   No api.js changes here per D-14.

2. **OrientationWarningModal secondary navigation filter** — UI-SPEC suggests the
   "show me orientation events" CTA should land on a filtered events list. Per D-01, no new
   filter route is added in this phase; the parent page's `onNo` callback owns navigation
   target. Plain `/events` is acceptable until a dedicated filter is built (future plan).

## Acceptance Criteria

### Task 1 — SelfCheckInPage (all met)
- [x] `grep -c "ErrorState"` returns 5 (≥3 required)
- [x] `grep -c "Check me in"` returns 1
- [x] `grep -c "4-digit venue code"` returns 1
- [x] `grep -c "You're checked in"` returns 1
- [x] `grep -c "Check-in isn't open yet"` returns 1
- [x] `grep -c "Check-in has closed"` returns 1
- [x] `grep -c "Check-in opens 15 minutes before"` returns 1
- [x] `grep -c "View event details"` returns 3 (≥2 required)
- [x] `grep -c "We couldn't load this check-in"` returns 1
- [x] `grep -c "Try again"` returns 1
- [x] `grep -c "TODO(copy)"` returns 0 (all resolved)
- [x] `grep -c "Could not load signup details"` returns 0 (old copy gone)
- [x] `grep -c "<Input"` returns 1 (primitive used)
- [x] `grep -c "<Label"` returns 1 (primitive used)
- [x] `grep -c 'size="lg"'` returns 1 (primary CTA sizing)
- [x] `grep -c 'aria-busy="true"'` returns 1
- [x] `grep -c 'aria-describedby'` returns 1 (FieldError association)
- [x] `git diff frontend/src/lib/api.js` empty (D-14 honored)

### Task 2 — OrientationWarningModal (all met)
- [x] `grep -c "Have you done a Sci Trek orientation?"` returns 1
- [x] `grep -c "Have you completed orientation?"` returns 0 (old copy gone)
- [x] `grep -c "This event has period slots but no orientation slot"` returns 1
- [x] `grep -c "I've done orientation — continue"` returns 1
- [x] `grep -c "I haven't — show me orientation events"` returns 1
- [x] `grep -cE "<Modal|role=\"dialog\""` returns 2
- [x] `e2e/orientation-modal.spec.js` updated with new copy (3 occurrences) and zero old copy
- [x] `cd frontend && npm run test -- OrientationWarningModal --run` exits 0 (4 passed)
- [x] `git diff frontend/src/lib/api.js` empty (D-14 honored)

## PART-AUDIT.md status

| Requirement | Status (pending Wave 2) |
|-------------|--------------------------|
| PART-02 (fix stubbed flows) | PASS — bare `<p>` error swap, primitive inputs |
| PART-06 (orientation modal behavior + copy) | PASS — UI-SPEC-aligned copy + Modal a11y |
| PART-09 (check-in window UX) | PASS — page-level ErrorState branches + window-aware copy |
| PART-10 (axe AA: dialog roles, label/input association) | PASS — Modal primitive + Label/Input primitives |
| PART-11 (375px: primitives enforce min-h-11) | PASS — Input has `min-h-11`, Button `size="lg"` is `min-h-[52px]` |
| PART-12 (loading/empty/error states) | PASS — Skeleton stack + ErrorState wired |

All six requirements PASS pending Wave 2 cross-browser + axe-core run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Pre-existing `frontend/tests/SelfCheckInPage.test.jsx` referenced old button copy**
- **Found during:** Task 1 verification (npm test failed)
- **Issue:** 3 test cases used `screen.getByRole("button", { name: /check in/i })` which no longer matches the new "Check me in" label.
- **Fix:** Updated all three matchers to `/check me in/i`. No structural test changes.
- **Files modified:** `frontend/tests/SelfCheckInPage.test.jsx`
- **Commit:** `d068efb`

**2. [Rule 1 — Bug] OrientationWarningModal unit test asserted old copy**
- **Found during:** Task 2 verification
- **Issue:** Existing 4 tests in `frontend/src/components/__tests__/OrientationWarningModal.test.jsx`
  matched on the old title/button copy.
- **Fix:** Updated title matcher to `/have you done a sci trek orientation/i`; primary button
  matcher to `/i've done orientation/i`; secondary button matcher to
  `/i haven't.*show me orientation events/i`.
- **Files modified:** `frontend/src/components/__tests__/OrientationWarningModal.test.jsx`
- **Commit:** `7eb825c`

These align with plan instructions ("update unit tests if they assert old copy") — they are
mandatory test maintenance, not architectural deviations.

### Unfixed (deferred to integration)

**Pre-merge cross-plan dependency: `ErrorState` import**
- `frontend/src/pages/SelfCheckInPage.jsx` imports `ErrorState` from `../components/ui` barrel,
  but the primitive itself is shipped by parallel plan 15-01. In the worktree base
  (commit `e770ce4`) the barrel does NOT yet export `ErrorState`, so `npm run test -- SelfCheckInPage`
  fails on tests that exercise the OUTSIDE_WINDOW branch (`Element type is invalid: ... ErrorState ... undefined`).
- **Disposition:** Per orchestrator note ("Import from the final path — do not create the primitive
  yourself. Post-merge test gate catches integration issues.") — this is the expected pre-merge
  state. After plan 15-01 merges into the same target branch, the import resolves and tests pass.
- **Verification scope:** 3 of 4 unit tests still pass (form, success, wrong-code, already-checked-in).
  Only the OUTSIDE_WINDOW test path triggers the missing-component render error.

## Self-Check: PASSED

- [x] `frontend/src/pages/SelfCheckInPage.jsx` modified at `d068efb`
- [x] `frontend/tests/SelfCheckInPage.test.jsx` updated at `d068efb`
- [x] `frontend/src/components/OrientationWarningModal.jsx` modified at `7eb825c`
- [x] `frontend/src/components/__tests__/OrientationWarningModal.test.jsx` updated at `7eb825c`
- [x] `e2e/orientation-modal.spec.js` updated at `7eb825c`
- [x] Both commits present in `git log --oneline -5`
- [x] `frontend/src/lib/api.js` and `frontend/src/App.jsx` untouched
