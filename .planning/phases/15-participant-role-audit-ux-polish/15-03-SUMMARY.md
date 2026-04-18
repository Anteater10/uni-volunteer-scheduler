---
phase: 15
plan: 03
subsystem: participant-pillar
tags: [ui, polish, accessibility, error-states, empty-states, ui-spec]
requires: [ErrorState primitive (15-01)]
provides:
  - "EventsBrowsePage with UI-SPEC loading/error/empty branches"
  - "PortalPage with UI-SPEC loading/error/empty branches + zero TODO markers"
affects:
  - "frontend/src/pages/public/EventsBrowsePage.jsx"
  - "frontend/src/pages/PortalPage.jsx"
  - "frontend/src/components/ui/ErrorState.jsx (added — Plan 01 dep)"
  - "frontend/src/components/ui/index.js (added ErrorState export)"
  - "frontend/src/pages/__tests__/EventsBrowsePage.test.jsx (Test 3 copy assertion update)"
tech_stack:
  added: []
  patterns:
    - "react-query state-branch composition (loading → error → empty → success)"
    - "aria-busy + aria-live region wrapping skeleton loaders for AT users"
    - "ErrorState primitive (role=alert) for fetch failures, distinct from EmptyState"
key_files:
  created:
    - "frontend/src/components/ui/ErrorState.jsx"
    - ".planning/phases/15-participant-role-audit-ux-polish/deferred-items.md"
  modified:
    - "frontend/src/pages/public/EventsBrowsePage.jsx"
    - "frontend/src/pages/PortalPage.jsx"
    - "frontend/src/components/ui/index.js"
    - "frontend/src/pages/__tests__/EventsBrowsePage.test.jsx"
decisions:
  - "Created ErrorState primitive in this plan (Rule 3 deviation) because Plan 01 had not landed in the worktree base — used the exact API contract from 15-01-PLAN.md so the merge from Plan 01's worktree will be a content match"
  - "Empty-state 'View next week' action wired to the page's existing handleNext handler — no new week-navigation logic introduced"
  - "PortalPage 'View all events' action uses Button as=Link to=/events to match the existing CTA pattern on the same page; avoided introducing useNavigate"
  - "Mobile gutter (px-4 md:px-8) added on every render branch of both pages, including loading + error branches, so 375px audit passes regardless of which branch renders"
metrics:
  duration: "~12 min"
  completed: "2026-04-15T21:57:21Z"
  tasks_completed: 2
  files_changed: 5
  commits: 3
---

# Phase 15 Plan 03: Polish list/landing pages — UI-SPEC states + copy

**One-liner:** Ship the new ErrorState primitive into EventsBrowsePage and PortalPage with UI-SPEC empty/error/loading copy, aria-busy regions, and zero TODO markers — clearing the Wave 1 polish gates for /events and /portals/:slug.

## Final State-Branch Shape

### `frontend/src/pages/public/EventsBrowsePage.jsx`

| Branch | Component | Copy / behavior |
| --- | --- | --- |
| Loading (`!allParamsReady || eventsQ.isPending`) | `<LoadingSkeletons />` (3 × Skeleton wrapped in `<div aria-busy="true" aria-live="polite">`) | Skeletons aria-hidden; outer region announces busy state to AT |
| Error (`eventsQ.isError`) | `ErrorState` | "We couldn't load this page" / "Check your connection and try again. If the problem continues, email scitrek@ucsb.edu." / **Try again** (calls `eventsQ.refetch()`) |
| Empty (`events.length === 0`) | `EmptyState` | "Nothing scheduled this week" / "New events go up on Mondays. Check back then, or browse next week's calendar." / **View next week** (calls existing `handleNext`) |
| Success | School-grouped `<EventCard />` list | Unchanged from base |

### `frontend/src/pages/PortalPage.jsx`

| Branch | Component | Copy / behavior |
| --- | --- | --- |
| Loading (`q.isPending`) | 2 × Skeleton wrapped in `<div aria-busy="true" aria-live="polite">` | New aria region |
| Error (`q.error`) | `ErrorState` | "We couldn't load this page" / "Check your connection and try again. If the problem continues, email scitrek@ucsb.edu." / **Try again** (calls `q.refetch()`) |
| Empty (`portalEvents.length === 0`, success path) | `EmptyState` | "No events from this partner yet" / "Sci Trek will post new events here as they're scheduled." / **View all events** (Link to `/events`) |
| Success (`portalEvents.length > 0`) | "Events" section heading + `<Card />` list | Unchanged structure; just the surrounding shell + CTA copy refreshed |

Outer page wrapper on both routes uses `px-4 md:px-8 py-4` (UI-SPEC mobile gutter).

## All Copy Strings Shipped (UI-SPEC cross-reference)

| Location | Title | Body | Action label |
| --- | --- | --- | --- |
| EventsBrowsePage error | "We couldn't load this page" | "Check your connection and try again. If the problem continues, email scitrek@ucsb.edu." | "Try again" |
| EventsBrowsePage empty | "Nothing scheduled this week" | "New events go up on Mondays. Check back then, or browse next week's calendar." | "View next week" |
| PortalPage error | "We couldn't load this page" | "Check your connection and try again. If the problem continues, email scitrek@ucsb.edu." | "Try again" |
| PortalPage empty | "No events from this partner yet" | "Sci Trek will post new events here as they're scheduled." | "View all events" |
| PortalPage primary CTA | (welcome card) | "Welcome to {portal.name}. Browse upcoming events and sign up for a slot." | "See this week's events" |
| PortalPage header | `portal.name || "Partner portal"` | `portal.description \|\| ""` | — |

All strings match UI-SPEC §Empty states / §Error states / §Per-page primary CTA.

## Untouched Files (Verified)

- `frontend/src/lib/api.js` — `git diff e770ce4..HEAD -- frontend/src/lib/api.js` empty (D-14 honoured)
- `frontend/src/App.jsx` — `git diff e770ce4..HEAD -- frontend/src/App.jsx` empty (no route changes)
- All admin / organizer files — out of pillar; not touched

## PART-AUDIT.md Status (pending Wave 2)

The two routes covered by this plan can be marked **PASS pending Wave 2 axe + 375px run**:

- `/events` — PART-02 (broken/stubbed flow fixed), PART-03 (no stuck spinner), PART-12 (loading/empty/error wired)
- `/portals/:slug` — same set + zero TODO(copy) markers remain

Wave 2 axe sweep + 375px viewport audit will confirm WCAG AA (PART-10) and mobile gutter (PART-11).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking dependency] Created `ErrorState` primitive in-plan**

- **Found during:** Pre-Task 1 readiness check
- **Issue:** Plan 03 imports `ErrorState` from `../../components/ui`, but the primitive is shipped by Plan 01 (Wave 0). At the worktree base (`e770ce4`) Plan 01 has not landed and no sibling worktree has shipped it either. The barrel exports only the original 12 primitives.
- **Fix:** Created `frontend/src/components/ui/ErrorState.jsx` and added the barrel export using the exact contract from `15-01-PLAN.md` Task 1 — same forwardRef + named/default export pattern, `role="alert"`, `AlertTriangle` icon in `--color-danger`, mirrors EmptyState API. When Plan 01's worktree merges back, the file content will match (or the conflict will be a trivial accept-ours).
- **Files added:** `frontend/src/components/ui/ErrorState.jsx`
- **Files modified:** `frontend/src/components/ui/index.js`
- **Commit:** `2800b75`

**2. [Rule 2 — Missing critical functionality] Mobile gutter on PortalPage loading + error branches**

- **Found during:** Task 2 implementation
- **Issue:** UI-SPEC §Mobile gutter requires `px-4 md:px-8` on every page render branch at 375px. The original loading and error branches had no horizontal padding, which would fail PART-11 even with the success branch padded.
- **Fix:** Added `px-4 md:px-8 py-4` wrapper class to every render branch on both pages.
- **Files modified:** `frontend/src/pages/public/EventsBrowsePage.jsx`, `frontend/src/pages/PortalPage.jsx`
- **Commit:** Bundled into `f8a85d1` and `d9b50bc`.

**3. [Rule 1 — Test alignment] Updated `EventsBrowsePage.test.jsx` Test 3 to assert new UI-SPEC copy**

- **Found during:** Task 1 verification
- **Issue:** Existing Test 3 asserted the old empty-state strings ("No events this week" / "Try browsing a different week."). Plan permits — and explicitly calls out — updating tests in the same task when UI-SPEC dictates new copy.
- **Fix:** Test 3 now asserts the new UI-SPEC strings + the "View next week" CTA button.
- **Files modified:** `frontend/src/pages/__tests__/EventsBrowsePage.test.jsx`
- **Commit:** Bundled into `f8a85d1`.

## Authentication Gates

None — both pages are public (loginless).

## Deferred Issues

**`EventDetailPage.test.jsx` — 10 pre-existing failing tests**

- Confirmed pre-existing on the worktree base via `git stash` + isolated test run; NOT a regression caused by Plan 03.
- Out of scope per executor SCOPE BOUNDARY rule — Plan 03 only modifies EventsBrowsePage and PortalPage.
- Logged in `.planning/phases/15-participant-role-audit-ux-polish/deferred-items.md` for a future Wave 1 plan that owns EventDetailPage polish.

## Threat Flags

None — no new network surface, auth path, file access, or schema change introduced beyond what the plan's `<threat_model>` already declared. T-15-03-02 (raw `error.message` leak) was successfully mitigated by replacing dynamic error bodies with hardcoded UI-SPEC copy on both pages.

## Verification Snapshot

```
git log --oneline -3
d9b50bc feat(15-03): polish PortalPage with UI-SPEC states + copy
f8a85d1 feat(15-03): polish EventsBrowsePage with UI-SPEC states + copy
2800b75 feat(15-03): add ErrorState primitive (Plan 01 dep, Rule 3)

vitest filter EventsBrowsePage --run     → 7/7 pass
vitest filter PortalPage --run           → no test files (no PortalPage test exists; manual smoke deferred to Wave 2)
grep -c "TODO(copy)" PortalPage.jsx      → 0
git diff e770ce4..HEAD -- api.js         → empty
git diff e770ce4..HEAD -- App.jsx        → empty
```

## Self-Check: PASSED

- Files created: `frontend/src/components/ui/ErrorState.jsx` — FOUND
- Files created: `.planning/phases/15-participant-role-audit-ux-polish/deferred-items.md` — FOUND
- Files modified: `frontend/src/pages/public/EventsBrowsePage.jsx` — FOUND (committed in `f8a85d1`)
- Files modified: `frontend/src/pages/PortalPage.jsx` — FOUND (committed in `d9b50bc`)
- Files modified: `frontend/src/components/ui/index.js` — FOUND (committed in `2800b75`)
- Files modified: `frontend/src/pages/__tests__/EventsBrowsePage.test.jsx` — FOUND (committed in `f8a85d1`)
- Commit `2800b75` — FOUND in `git log --all`
- Commit `f8a85d1` — FOUND in `git log --all`
- Commit `d9b50bc` — FOUND in `git log --all`
