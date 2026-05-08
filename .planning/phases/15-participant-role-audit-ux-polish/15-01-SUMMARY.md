---
phase: 15-participant-role-audit-ux-polish
plan: 01
subsystem: ui
tags: [react, lucide-react, playwright, vitest, ci, accessibility, components]

# Dependency graph
requires:
  - phase: 14-collaboration-setup
    provides: feature/v1.2-participant branch + COLLABORATION.md PR-only conventions
provides:
  - Shared ErrorState primitive (role=alert, AlertTriangle icon, danger color, EmptyState-mirrored API)
  - components/ui barrel re-export of ErrorState alongside the existing 12 primitives
  - Six-project Playwright matrix (chromium + firefox + webkit + Mobile Chrome + Mobile Safari + iPhone SE 375)
  - CI install of all browser engines (no chromium-only arg)
  - frontend/package.json e2e:install:all script for local CI parity
affects:
  - Phase 15 Wave 1 (Plans 02-07) — every page polish can now `import { ErrorState } from '../../components/ui'`
  - Phase 15 Wave 2 — cross-browser smoke tests can now run against all 6 projects without manual setup

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ErrorState mirrors EmptyState API 1:1 (forwardRef + default + named export) plus icon prop and role=alert"
    - "Lucide AlertTriangle as default error icon; consumers can override via icon prop"
    - "Playwright project matrix uses built-in devices presets (no extra dependency); iPhone SE preset (375x667) is the tightest standard mobile viewport"

key-files:
  created:
    - frontend/src/components/ui/ErrorState.jsx
    - .planning/phases/15-participant-role-audit-ux-polish/deferred-items.md
    - .planning/phases/15-participant-role-audit-ux-polish/15-01-SUMMARY.md
  modified:
    - frontend/src/components/ui/index.js
    - playwright.config.js
    - .github/workflows/ci.yml
    - frontend/package.json

key-decisions:
  - "ErrorState API mirrors EmptyState exactly (title/body/action) plus icon override — keeps caller mental model consistent"
  - "AlertTriangle hardcoded as default icon (rather than required prop) — most consumers want it, and overriding stays cheap via icon prop"
  - "Local e2e:install kept as chromium-only for fast iteration; new e2e:install:all is opt-in for CI parity"
  - "Did not introduce sharding strategy on CI — RESEARCH.md A4 flagged it as future optimization"

patterns-established:
  - "Wave 1 pages can `import { ErrorState } from '../../components/ui'` without per-page boilerplate"
  - "Cross-browser projects share the global `use` block (baseURL, trace, video) — only the device preset differs"

requirements-completed: [PART-07, PART-10, PART-11, PART-12, PART-14]

# Metrics
duration: ~7 min
completed: 2026-04-15
---

# Phase 15 Plan 01: Wave 0 PR-only foundation Summary

**Shared ErrorState primitive (role=alert + AlertTriangle in danger color) plus six-project Playwright matrix and CI install of all browser engines — unblocks every Wave 1 page polish and Wave 2 cross-browser smoke.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-15T21:47Z
- **Completed:** 2026-04-15T21:54Z
- **Tasks:** 2 / 2
- **Files modified:** 4 (1 created, 3 edited)
- **Files created:** 1 source primitive + 1 deferred-items log + 1 SUMMARY

## Accomplishments

- Shipped `frontend/src/components/ui/ErrorState.jsx` — a forwardRef component with `role="alert"`, default `AlertTriangle` icon in `var(--color-danger)`, and the same title/body/action API as `EmptyState`. Wave 1 plans can import it via `import { ErrorState } from '../../components/ui'`.
- Added `ErrorState` to the ui barrel between `EmptyState` and `Skeleton`. All 12 pre-existing barrel exports preserved.
- Expanded `playwright.config.js` from a single chromium project to six: `chromium`, `firefox`, `webkit`, `Mobile Chrome` (Pixel 5), `Mobile Safari` (iPhone 12), and `iPhone SE 375` (iPhone SE preset, 375x667).
- Updated `.github/workflows/ci.yml` to install all browser engines via `npx playwright install --with-deps` (dropped the `chromium`-only arg). Step renamed from "browser" to "browsers".
- Added `e2e:install:all` script to `frontend/package.json` — `playwright install chromium webkit firefox` — so local devs can match CI without memorizing the command.

## Task Commits

Each task was committed atomically:

1. **Task 1: ErrorState primitive + barrel export** — `d10d15a` (feat)
2. **Task 2: Playwright matrix + CI install + package.json script** — `5ea089e` (feat)

_Plan metadata commit will be appended after this SUMMARY is staged (worktree mode)._

## ErrorState API surface

| Prop | Type | Default | Description |
| --- | --- | --- | --- |
| `title` | string | — | Top heading text rendered as `<p class="text-lg font-semibold">`. Optional. |
| `body` | string | — | Secondary copy in muted color. Optional. |
| `action` | ReactNode | — | Action area (e.g. `<Button>Retry</Button>`) centered below body. Optional. |
| `icon` | ComponentType | `AlertTriangle` | Lucide-style icon component. Rendered with `aria-hidden="true"` and `mx-auto mb-3 h-8 w-8 text-[var(--color-danger)]`. |
| `className` | string | — | Merged via `cn()` helper onto the container. Container default is `py-12 text-center`. |
| `...rest` | — | — | Spread onto the root `<div>` (which already carries `role="alert"`). |

The component is exported both as `default` and as named `ErrorState`, matching the EmptyState pattern. Consumers can use either form.

## Playwright project list

| Project name | Device preset | Viewport | Engine |
| --- | --- | --- | --- |
| `chromium` | Desktop Chrome | 1280x720 | Chromium |
| `firefox` | Desktop Firefox | 1280x720 | Firefox |
| `webkit` | Desktop Safari | 1280x720 | WebKit |
| `Mobile Chrome` | Pixel 5 | 393x851 | Chromium (mobile UA) |
| `Mobile Safari` | iPhone 12 | 390x664 | WebKit (mobile UA) |
| `iPhone SE 375` | iPhone SE | 375x667 | WebKit (mobile UA) |

Verified: `npx playwright test --list --project="iPhone SE 375"` returns 16 tests across all four spec files — projects register correctly with no "Project not found" error.

## CI install command shipped

```yaml
- name: Install root playwright deps + browsers
  run: |
    npm ci
    npx playwright install --with-deps
```

The bare `playwright install --with-deps` form fetches every engine the config registers (chromium + firefox + webkit). Per RESEARCH.md A4 this triples install time vs chromium-only — accepted trade-off for PART-14 cross-browser coverage.

## Files Created/Modified

- `frontend/src/components/ui/ErrorState.jsx` — created. New primitive (32 lines including imports + named/default exports).
- `frontend/src/components/ui/index.js` — modified. One line added: `export { default as ErrorState } from './ErrorState'` between EmptyState and Skeleton.
- `playwright.config.js` — modified. Single-project array replaced by six-project array; rest of config unchanged.
- `.github/workflows/ci.yml` — modified. Step name updated and `chromium` arg dropped from the `playwright install` line.
- `frontend/package.json` — modified. New `e2e:install:all` script appended to scripts block. Existing `e2e:install` left as chromium-only.
- `.planning/phases/15-participant-role-audit-ux-polish/deferred-items.md` — created. Pre-existing EventDetailPage.test.jsx failures logged for a Wave 1 plan to address.

## Decisions Made

- **Mirrored EmptyState API exactly** rather than designing a fresh signature — keeps the mental model uniform across both states (caller writes `<ErrorState title=... body=... action=...>` vs `<EmptyState title=... body=... action=...>`). Adds only the `icon` prop and the alert semantics.
- **AlertTriangle as the default icon** so consumers that just want an error state get sensible visuals without an extra import. Override stays cheap via the `icon` prop.
- **Did not consume ErrorState in any page yet** — plan scope is the primitive + barrel; Wave 1 plans wire the consumers. This keeps the PR review surface tight and avoids merge conflicts with parallel admin pillar work.
- **iPhone SE preset chosen as the 375 viewport** because it is Playwright's built-in 375x667 device and matches PART-11's "tightest thumb-test viewport" requirement without a custom viewport definition.
- **Kept `e2e:install` as chromium-only for fast local iteration** — most local Playwright runs only need Chromium. Devs opt into the slower full install via `npm run e2e:install:all` when they need to mirror CI.

## Deviations from Plan

None — plan executed exactly as written. All 8 verification checks pass.

## Issues Encountered

- **Frontend `node_modules` and root `node_modules` were absent in the fresh worktree.** Ran `npm ci` in `frontend/` and `npm install` at the repo root before the verification commands could resolve `vitest` and `playwright`. This is expected for a parallel worktree agent and not a code change.
- **Pre-existing vitest failures in `EventDetailPage.test.jsx` (10 failures).** Confirmed they reproduce on the unmodified base commit `e770ce4` via `git stash`; they are not regressed by 15-01 because nothing in 15-01 imports `EventDetailPage`. Logged to `deferred-items.md` for a Wave 1 plan to fix when it touches that page.

## User Setup Required

None — no external service configuration required. Wave 0 ships only frontend/CI scaffolding.

## Confirmation: Wave 1 plans can import `ErrorState`

```jsx
// In any Wave 1 page (Plans 02–07):
import { ErrorState } from '../../components/ui'

<ErrorState
  title="Something went wrong"
  body="We couldn't load the events list. Please try again."
  action={<Button onClick={refetch}>Retry</Button>}
/>
```

This works today on `feature/v1.2-participant`. The barrel export is in place and the primitive is committed (`d10d15a`).

## Next Phase Readiness

- Wave 1 (Plans 02–07) is unblocked: every page polish plan can consume `ErrorState` and rely on the cross-browser Playwright matrix being live in CI.
- Wave 2 verification can run `npx playwright test` across all six projects without further setup. CI will install the browsers automatically; local devs run `npm run e2e:install:all`.
- Pre-existing `EventDetailPage.test.jsx` failures are logged in `deferred-items.md` and should be picked up by whichever Wave 1 plan touches `EventDetailPage` (likely 15-04 or 15-05).

## Self-Check: PASSED

- FOUND: `frontend/src/components/ui/ErrorState.jsx`
- FOUND: barrel export line `export { default as ErrorState } from './ErrorState'` in `frontend/src/components/ui/index.js`
- FOUND: 6 Playwright projects in `playwright.config.js` (chromium, firefox, webkit, Mobile Chrome, Mobile Safari, iPhone SE 375)
- FOUND: `playwright install --with-deps` (no trailing arg) in `.github/workflows/ci.yml`
- FOUND: `e2e:install:all` script in `frontend/package.json`
- FOUND: commit `d10d15a` (Task 1) in git log
- FOUND: commit `5ea089e` (Task 2) in git log
- FOUND: `iPhone SE 375` project lists 16 tests via `npx playwright test --list`

---
*Phase: 15-participant-role-audit-ux-polish*
*Completed: 2026-04-15*
