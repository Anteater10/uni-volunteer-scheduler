# Phase 15 — Deferred Items

Out-of-scope discoveries logged during plan execution. Do not fix in the
discovering plan — re-scope into a follow-up plan.

## From 15-03 (EventsBrowsePage + PortalPage polish)

### EventDetailPage.test.jsx — 10 failing tests (pre-existing)

- **Found during:** Task 2 verification (`npm run test -- --run`)
- **Scope:** Failures live entirely in `frontend/src/pages/__tests__/EventDetailPage.test.jsx`,
  which Plan 03 does not touch.
- **Confirmed pre-existing:** Stashing the Plan 03 changes and re-running
  `npm run test -- EventDetailPage --run` reproduces the same 10 failures
  on the worktree base commit `e770ce4` — they are NOT regressions
  introduced by Plan 03.
- **Symptom:** `waitFor` on `screen.getByText(/Period Slots/i)` (and similar
  heading lookups) times out — appears related to mock data shape or query
  hydration timing in EventDetailPage, not to Plan 03's state-branch work.
- **Action:** Defer to a future participant-pillar plan (most likely
  Plan 04 or Plan 05 which polish EventDetailPage / signup confirmation).
  EventDetailPage is in scope for Wave 1 — its dedicated plan should
  rebuild the test suite alongside the page polish.
