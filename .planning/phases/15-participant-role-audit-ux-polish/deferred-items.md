# Phase 15 — Deferred Items

Items discovered during plan execution that fall outside the current task's scope.
Logged here so a future plan can address them; do NOT attempt fixes from this plan.

## From Plan 15-01 (Wave 0 — ErrorState + Playwright matrix)

### Pre-existing vitest failures: `frontend/src/pages/__tests__/EventDetailPage.test.jsx`

- **Status:** 10 failing tests on base commit `e770ce4` BEFORE any 15-01 changes were applied.
- **Confirmed by:** `git stash` of 15-01 changes → run vitest → identical 10 failures.
- **Symptom:** `waitFor` cannot find `/Period Slots/i` heading; rendered DOM shows event detail
  with slot rows but heading text appears to have changed in a recent EventDetailPage refactor.
- **Out of scope for 15-01** because:
  - Plan 15-01 only touches: `ErrorState.jsx`, `ui/index.js`, `playwright.config.js`,
    `.github/workflows/ci.yml`, `frontend/package.json`. None of these are imported by
    `EventDetailPage.test.jsx`.
  - The failures are pre-existing — not regressed by 15-01.
- **Recommended owner:** Whichever Wave 1 plan touches `EventDetailPage` (likely Plan 15-04
  or 15-05 per the participant pillar polish sweep).
- **Action when fixing:** Re-read the page source for the actual heading copy, update the
  test selector to match (or restore the heading if accidentally removed).
