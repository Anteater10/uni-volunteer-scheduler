# Phase 15 — Deferred Items

Items discovered during plan execution that fall outside the current task's scope.
Logged here so a future plan can address them; do NOT attempt fixes from the discovering plan.

## From Plans 15-01 and 15-03

### EventDetailPage.test.jsx — 10 pre-existing failing tests

- **Status:** 10 failing tests on base commit `e770ce4` BEFORE any wave-1 changes. Confirmed
  independently by 15-01 (stashed 15-01 changes → identical failures) and 15-03 (stashed
  15-03 changes → identical failures).
- **Symptom:** `waitFor` on `screen.getByText(/Period Slots/i)` times out — the old test
  suite asserted on a checkbox-based UI that no longer exists; heading copy also changed
  in a recent EventDetailPage refactor.
- **Resolution:** Plan 15-04 rewrote the suite as part of its EventDetailPage polish
  (18 passing tests on a button-based UI, includes E.164 + Add-to-Calendar coverage).
  Logged here for traceability only; no further action required.
