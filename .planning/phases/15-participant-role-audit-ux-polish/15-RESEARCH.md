# Phase 15: Participant role audit + UX polish - Research

**Researched:** 2026-04-15
**Domain:** React 19 + Tailwind v4 public-flow polish; axe-core/Playwright CI; cross-browser Playwright; RFC 5545 .ics generation
**Confidence:** HIGH (stack, tooling, code inventory) / MEDIUM (iOS Safari .ics UX) / LOW (exact budget for axe-core violation triage)

## Summary

Phase 15 is an audit-and-polish pass on six public routes, fixing bugs, hitting WCAG 2.1 AA (axe-core in Playwright CI), passing a 375px mobile audit, wiring loading/empty/error states on every data-fetch site, adding cross-browser Playwright projects (webkit + firefox), and shipping one net-new feature (Add-to-Calendar .ics). The UI system, routing, data layer, and E2E infrastructure already exist — this phase composes what's there, adds three small primitives (`ErrorState`, an `Alert`/ARIA-live pattern for loading, and the `.ics` util), and extends the Playwright config. There is NO backend work (`api.js` is read-only per D-14).

All heavy lifting is additive: the existing `frontend/src/components/ui/` primitives (Button, Card, Chip, Modal, Skeleton, EmptyState, Input, Label, FieldError, PageHeader, BottomNav, Toast) already match the UI-SPEC and need NO rebuild. `@axe-core/playwright@4.11.1` and `@playwright/test@1.59.1` are already installed (from phase 13). The Playwright config currently has only `chromium` — webkit/firefox projects are a one-file diff. The one net-new library question is whether to add `ics@3.11.0` (3 transitive deps — nanoid, runes2, yup) or hand-roll ~30 lines of string builder. Recommendation: **hand-roll** (see Don't Hand-Roll table for the nuance).

**Primary recommendation:** Treat this phase as three parallel streams — (A) per-page audit + fix list, (B) CI infrastructure (axe-core spec + webkit/firefox projects), (C) Add-to-Calendar feature — joined by a page-by-page verification pass against the UI-SPEC. Wave 0 sets up the `ErrorState` primitive + the axe-core test harness so later waves can reuse them.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 PART-13 feature choice:** Ship **Add-to-Calendar (.ics)** as the one new participant feature. Button on confirmation page and event detail page. Generates a downloadable `.ics` file (iCalendar standard) — works with Google, Apple, Outlook without OAuth. No backend changes required — built entirely in frontend using event data already returned by `/events/:eventId`. Rationale: high real-student value, zero new backend, no auth required (fits accountless model), low complexity.

**D-02 Audit methodology:** **Design-first, then audit.** Produce a visual target BEFORE fixing, so polish has a clear bar.

**D-03 Design pass — two stages:** (1) `gsd-ui-phase` → `UI-SPEC.md` locking design tokens + primitive components. (2) `frontend-design` skill → iterate page-level layouts for the 4 public pages + `/check-in/:signupId` + `/portals/:slug` against the locked tokens.

**D-04 Post-design audit tools:** axe-core in Playwright CI for WCAG AA. Playwright smoke test crawling every public route for console errors, 404s, broken images. Manual 375px walkthrough using Playwright device emulation + screenshot diff.

**D-05 Andy reviews each page visually at least once on an actual phone before sign-off.**

**D-06 Visual style:** **Keep the current Tailwind look — polish, don't redesign.** Tighten spacing, fix states, hit the audit bar, preserve existing colors/typography.

**D-07 No UCSB/SciTrek brand repaint in this phase.**

**D-08 Loading/empty/error states:** **Shared primitives** under `frontend/src/components/ui/` — `Skeleton`, `EmptyState`, `ErrorState` — built once, reused across all public pages.

**D-09 Skeletons for list and detail loads; spinners only for button/action pending states.**

**D-10 Every public page and every data-fetch site must have loading + empty + error branches wired — verified by checklist during audit.**

**D-11 Cross-browser verification (PART-14):** **Playwright projects in CI** covering chromium (Chrome), webkit (Safari mobile/desktop), firefox. Smoke suite runs on every PR touching `frontend/**`.

**D-12 Smoke covers the golden path:** browse → event detail → sign up → confirm (magic link) → manage → check-in.

**D-13 No BrowserStack / SauceLabs in this phase.**

**D-14 Scope guardrails:** `frontend/src/lib/api.js` is **read-only** in this phase (per ROADMAP file-ownership rule — coordinate with admin worktree). No new backend endpoints, no Alembic migrations, no FastAPI changes.

**D-15 No new public routes beyond the Add-to-Calendar feature.**

**D-16 No admin/organizer work — stay in participant worktree.**

**D-17 No auth / account features. Accountless stays accountless.**

### Claude's Discretion

- Exact skeleton shape (shimmer vs pulse animation).
- `.ics` file formatting details (VTIMEZONE block, UID generation strategy) as long as output validates.
- Playwright project matrix fine-tuning (e.g., viewport list, retry counts).
- Choice of specific empty-state copy and illustration (or no illustration).
- Whether to use a tiny ICS-generation library or hand-roll the string builder.

### Deferred Ideas (OUT OF SCOPE)

- **Week/keyword filter on /events** — considered for PART-13, not chosen. Future milestone candidate.
- **Saved / favorite events** — requires localStorage token plumbing; defer unless pillar requirement.
- **Share event link (native share sheet)** — low value, skip.
- **UCSB / SciTrek brand repaint** (navy + gold, warmer palette) — explicitly out of scope; own design phase.
- **Search across events** — new capability, not polish; later milestone.
- **Backend fixes surfaced during audit** — log as issues for a followup backend-fix phase; do NOT fix in this worktree.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PART-01 | Audit every public flow end-to-end against a fresh dev DB; document in `PART-AUDIT.md`. | Per-page audit checklist (this doc §Audit Methodology). |
| PART-02 | Fix every broken or stubbed participant flow surfaced by PART-01. | Public page inventory + known bug surface (this doc §Public Page Inventory). |
| PART-03 | Browse events by week — clear context, no stuck spinners, no console errors. | `EventsBrowsePage.jsx` already wires week nav + react-query; needs loading state audit. |
| PART-04 | Event detail page — slots grouped by `slot_type` with capacity + filled counts. | `EventDetailPage.jsx` already does this (orientation + period groups). |
| PART-05 | Signup form client-side validation — name, email, phone (E.164). | Existing validator in `EventDetailPage.jsx` needs E.164 tighten; UI-SPEC §Form validation copy is canonical. |
| PART-06 | Orientation-warning modal fires correctly (period-only no-prior case); suppressed when DB confirms prior attendance. | `OrientationWarningModal.jsx` + `handleSubmit()` orientation check in `EventDetailPage.jsx:517-528` — already implemented, needs verification test (e2e already exists at `e2e/orientation-modal.spec.js`). |
| PART-07 | Magic link works on Safari iOS and Chrome Android. | iOS in-app browser issue is the critical risk (see §Magic Link Cross-Browser). |
| PART-08 | Manage-my-signup page — per-row + cancel-all controls. | `ManageSignupsPage.jsx` already has both — needs UI-SPEC copy pass. |
| PART-09 | Self check-in inside window works; outside rejected. | `SelfCheckInPage.jsx` + `api/checkIn.js` — needs copy polish per UI-SPEC §Error states. |
| PART-10 | Every public page meets WCAG 2.1 AA (axe-core in CI passing). | §axe-core + Playwright integration. |
| PART-11 | 375px mobile-first on every public page. | §375px Audit Heuristics. |
| PART-12 | Loading + empty + error states on every public page. | §Loading/Empty/Error primitives. `ErrorState` is the new primitive. |
| PART-13 | Add at least one new audit-surfaced participant feature (locked to .ics per D-01). | §.ics Generation in Browser. |
| PART-14 | Cross-browser smoke pass (Safari mobile, Chrome mobile, Firefox desktop). | §Playwright Project Matrix. |

## Project Constraints (from CLAUDE.md)

- **Branch:** Current branch is `feature/v1.2-participant` (Hung's pillar). Only edit files in the participant pillar.
- **PR-only files (docs/COLLABORATION.md):** `frontend/src/lib/api.js`, `frontend/src/lib/api.public.js`, `frontend/src/App.jsx`, `frontend/src/components/ui/*`, `docker-compose.yml`, `.github/workflows/*`, `.planning/STATE.md`, `CLAUDE.md`. A change to any of these must go through a PR reviewed by both Andy and Hung. **Implication for this phase:** the new `ErrorState.jsx` primitive AND the Playwright config + CI workflow changes are PR-only touches — plan them explicitly.
- **Alembic single-writer:** Andy only. N/A this phase (no backend).
- **Frontend tests:** `cd frontend && npm run test -- --run` (vitest). Backend tests N/A this phase.
- **Playwright tests:** `npx playwright test` at repo root. Requires docker stack up + dev server at :5173 + `EXPOSE_TOKENS_FOR_TESTING=1`.
- **No AI attribution in commits** (global rule). Commit types: feat, fix, refactor, docs, test, chore, perf, ci.
- **Never commit `.planning/` or `.claude/`.**

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Public page rendering (6 routes) | Browser/Client (React 19 SPA) | — | Vite dev server + SPA; no SSR. |
| Data fetching (events, signups, portals) | Browser/Client via react-query | API (read-only this phase) | `api.js` locked per D-14. |
| Form validation (signup identity fields) | Browser/Client | API (server-side Pydantic) | Client validation for UX; server is authoritative. |
| Magic-link token handling | Browser/Client (URL param parsing) | API (validate + return signup list) | Already wired in `ConfirmSignupPage` + `ManageSignupsPage`. |
| Self check-in (4-digit venue code) | Browser/Client + API | — | `SelfCheckInPage.jsx` + `api/checkIn.js`. |
| Accessibility compliance verification | CI (Playwright + axe-core) | Browser runtime | axe-core runs in-browser via Playwright. |
| 375px mobile audit | CI (Playwright devices) + manual real-device review | — | Playwright device emulation + Andy's phone. |
| .ics generation | Browser/Client (new `lib/calendar.js` util) | — | No backend per D-01; use event data already returned by `getEvent`. |
| Loading/empty/error rendering | Browser/Client (primitives under `components/ui/`) | — | Shared across 6 pages. |

## Standard Stack

### Core (already in `frontend/package.json` — verified 2026-04-15)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react | ^19.2.0 | UI framework | Locked by project. |
| react-dom | ^19.2.0 | React renderer | Paired with react. |
| react-router-dom | ^7.11.0 | Routing | Already wiring 6 public routes. |
| @tanstack/react-query | ^5.90.12 | Data fetching + caching | Every public page uses it; handles loading/error states natively. |
| lucide-react | ^1.7.0 | Icon library | UI-SPEC mandates this; already used. |
| tailwindcss | ^4.2.2 | Styling | Tailwind v4 via `@tailwindcss/vite`. `@theme` block in `index.css` declares tokens. |
| @tailwindcss/vite | ^4.2.2 | Vite plugin for Tailwind v4 | Config-as-code; NO `tailwind.config.js` needed. |

### Testing (already installed — verified 2026-04-15)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @playwright/test | ^1.59.1 | E2E testing | Already runs 5 specs; extend projects + add a11y spec. |
| @axe-core/playwright | ^4.11.1 | WCAG a11y scans in Playwright | **Already installed**; official Deque package (MPL-2.0). Bundles `axe-core@~4.11.1`. [VERIFIED: `frontend/node_modules/@axe-core/playwright/package.json`] |
| vitest | ^2.1.2 | Unit/component tests | Used for component + lib tests; JSDOM environment. |
| @testing-library/react | ^16.3.2 | Component testing | Already in use. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ics (npm) | 3.11.0 | iCalendar file generator | **Consider NOT installing** (see Don't Hand-Roll table). Transitive deps: `nanoid`, `runes2`, `yup` — yup is ~40KB gzipped and adds schema validation we don't need. [VERIFIED: `npm view ics` 2026-04-15 — last published 2026-03-25.] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `.ics` string builder | `ics@3.11.0` npm package | Library: ~30KB+ gzipped with yup transitively; handles edge cases (escape, fold, UID gen). Hand-roll: ~30 lines, zero deps, matches UI-SPEC §Add-to-Calendar line-by-line. Recommendation: **hand-roll** (see §.ics Generation). |
| Adding `clsx` + `tailwind-merge` | Existing `frontend/src/lib/cn.js` (one-liner `args.flat().filter(Boolean).join(' ')`) | Current `cn` works; no class-conflict resolution needed for this phase's additive changes. |
| Floating-time DTSTART (no VTIMEZONE) | Full VTIMEZONE block with America/Los_Angeles | Floating time is simpler AND matches expectation ("event starts at 9am Pacific, wherever the viewer is reading"). Calendar apps interpret floating time as "local to event venue". All SciTrek events are PT. **Recommendation: use floating time** (DTSTART:20260422T090000 — no TZID, no Z). [CITED: RFC 5545 §3.3.5; icalendar.org example page] |
| axe-core `wcag22aa` tag | `wcag2a + wcag2aa + wcag21a + wcag21aa` | Project targets WCAG 2.1 AA per CLAUDE.md cross-cutting. 2.2 would add target-size-minimum (SC 2.5.8, 24px floor) — UI-SPEC already mandates 44px via `min-h-11`, so 2.2 would pass anyway. **Safe to include `wcag22aa`** as aspirational tag; not required. |

**Installation:**
```bash
# NOTHING NEEDS INSTALLING — @axe-core/playwright is already in package.json.
# If Claude's-discretion choice goes with the `ics` package:
cd frontend && npm install ics
# (3 transitive deps; not recommended per Don't Hand-Roll table below)
```

**Version verification (run 2026-04-15):**
- `@axe-core/playwright@4.11.1` (published 2026-04-14) — installed
- `@playwright/test@1.59.1` — installed
- `ics@3.11.0` (published 2026-03-25) — NOT installed; optional

## Architecture Patterns

### System Architecture Diagram

```
                         ┌───────────────────────────────────────┐
                         │  Volunteer (phone/laptop browser)     │
                         │  Chrome / Safari iOS / Firefox        │
                         └───────────────┬───────────────────────┘
                                         │
                                         ▼  (HTTP + react-query)
        ┌──────────────────────────────────────────────────────────────┐
        │  Vite + React 19 SPA  (frontend/src — participant pillar)    │
        │                                                              │
        │  Routes (App.jsx):                                           │
        │   /events         → EventsBrowsePage.jsx                     │
        │   /events/:id     → EventDetailPage.jsx                      │
        │   /signup/confirm → ConfirmSignupPage.jsx ─wraps→ ManageSignupsPage.jsx
        │   /signup/manage  → ManageSignupsPage.jsx                    │
        │   /check-in/:id   → SelfCheckInPage.jsx                      │
        │   /portals/:slug  → PortalPage.jsx                           │
        │                                                              │
        │  Shared primitives (components/ui/):                         │
        │   Button · Card · Chip · Input · Label · FieldError          │
        │   Skeleton · EmptyState · [ErrorState ← NEW]                 │
        │   Modal · PageHeader · BottomNav · Toast                     │
        │                                                              │
        │  Domain components (components/):                            │
        │   OrientationWarningModal · SignupSuccessCard · StatusIcon   │
        │                                                              │
        │  New util (lib/calendar.js ← NEW):                           │
        │   buildIcs(event) → string  →  downloadIcs(event, filename)  │
        └────────┬─────────────────────────────────────────────────────┘
                 │
                 │  api.public.* (lib/api.js — READ-ONLY per D-14)
                 ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  FastAPI backend (docker container, port 8000)               │
        │  Endpoints used (no changes):                                │
        │   GET  /public/week                                          │
        │   GET  /public/events?quarter&year&week_number               │
        │   GET  /public/events/:id                                    │
        │   GET  /public/orientation-status?email                      │
        │   POST /public/signups   (returns confirm_token in test mode)│
        │   GET  /public/signups/manage?token                          │
        │   DELETE /public/signups/:id?token                           │
        │   POST /public/signups/confirm?token                         │
        │   GET  /public/signups/:id                (self check-in)    │
        │   POST /public/events/:eid/signups/:sid/check-in (venue code)│
        │   GET  /public/portals/:slug                                 │
        └──────────────────────────────────────────────────────────────┘

CI Pipeline (.github/workflows/ci.yml — PR-only edit):
  ┌──────────────────────────────────────────────────────────────────┐
  │ e2e-tests job                                                    │
  │  ├─ npm ci (root + frontend)                                     │
  │  ├─ docker compose up db + redis + backend + celery              │
  │  ├─ npm run dev (frontend at :5173)                              │
  │  ├─ npx playwright install --with-deps  ← add firefox + webkit   │
  │  └─ npx playwright test                                          │
  │      projects: chromium │ webkit │ firefox │ mobile-chrome │ mobile-safari
  │      specs: public-signup · orientation-modal · organizer-check-in
  │             admin-smoke · a11y (NEW)                             │
  └──────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (additive only — reflect what already exists)

```
frontend/src/
├── components/
│   ├── OrientationWarningModal.jsx        ← existing (PART-06)
│   ├── SignupSuccessCard.jsx              ← existing; hosts "Add to calendar" primary CTA (D-01)
│   ├── StatusIcon.jsx                     ← existing
│   └── ui/
│       ├── Button.jsx · Card.jsx · Chip.jsx
│       ├── Input.jsx · Label.jsx · FieldError.jsx
│       ├── Skeleton.jsx · EmptyState.jsx
│       ├── ErrorState.jsx                 ← NEW primitive (mirrors EmptyState API)
│       ├── Modal.jsx · PageHeader.jsx · BottomNav.jsx · Toast.jsx
│       └── index.js                       ← re-export ErrorState
├── pages/public/
│   ├── EventsBrowsePage.jsx               ← audit + rewire error state
│   ├── EventDetailPage.jsx                ← audit + add "Add to calendar" secondary button
│   ├── ConfirmSignupPage.jsx              ← audit + replace inline spinner with skeleton
│   └── ManageSignupsPage.jsx              ← audit + error state + use UI-SPEC copy
├── pages/
│   ├── SelfCheckInPage.jsx                ← audit + UI-SPEC error copy
│   └── PortalPage.jsx                     ← audit + EmptyState copy + ErrorState
└── lib/
    ├── calendar.js                        ← NEW: buildIcs / downloadIcs util (hand-rolled)
    └── __tests__/
        └── calendar.test.js               ← NEW: unit test for ics string shape

e2e/
├── a11y.spec.js                           ← NEW: axe-core sweep of all 6 routes
├── public-signup.spec.js                  ← existing (may need "webkit" + "firefox" tolerance tweaks)
├── orientation-modal.spec.js              ← existing (verify still green cross-browser)
├── organizer-check-in.spec.js             ← existing
├── admin-smoke.spec.js                    ← existing
└── fixtures.js · global-setup.js          ← existing

playwright.config.js                       ← PR-only: add webkit, firefox, Mobile Chrome, Mobile Safari projects
.github/workflows/ci.yml                   ← PR-only: add `npx playwright install --with-deps` for all browsers
```

### Pattern 1: axe-core in Playwright — scan-per-page spec

**What:** Single `e2e/a11y.spec.js` that iterates every in-scope public route and runs `AxeBuilder` against a configured tag set. Violations array must be empty for CI to pass.

**When to use:** One per milestone. This phase creates it.

**Example:**
```javascript
// Source: https://playwright.dev/docs/accessibility-testing
// Source: https://github.com/dequelabs/axe-core-npm/blob/develop/packages/playwright/README.md
// e2e/a11y.spec.js
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { getSeed } from './fixtures.js';

const PUBLIC_ROUTES_STATIC = [
  { path: '/events', name: 'events browse' },
  { path: '/signup/manage', name: 'manage (no token — error card)' },
];

// Routes needing the seeded event ID / token are parameterized
function dynamicRoutes() {
  const seed = getSeed();
  return [
    { path: `/events/${seed.event_id}`, name: 'event detail' },
    { path: `/signup/confirm?token=${seed.confirm_token}`, name: 'confirm page' },
    { path: `/portals/${seed.portal_slug || 'scitrek'}`, name: 'portal landing' },
    { path: `/check-in/${seed.signup_id}`, name: 'self check-in' },
  ];
}

test.describe('a11y (axe-core WCAG 2.1 AA sweep)', () => {
  for (const r of PUBLIC_ROUTES_STATIC) {
    test(`no violations on ${r.name}`, async ({ page }) => {
      await page.goto(r.path);
      // Let react-query settle before scanning
      await page.waitForLoadState('networkidle');
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        // Exclude third-party widgets if ever added; none today
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }

  for (const r of dynamicRoutes()) {
    test(`no violations on ${r.name}`, async ({ page }) => {
      await page.goto(r.path);
      await page.waitForLoadState('networkidle');
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});
```

**Key points:**
- `withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])` is the exact tag set for **WCAG 2.1 AA** per Deque guidance. [CITED: axe-core/doc/API.md; Deque University rule-descriptions]
- Do NOT include `'best-practice'` in v1 — too noisy for an existing codebase. Add later as a stretch goal.
- `waitForLoadState('networkidle')` avoids scanning a skeleton-only page. For paths with `aria-live` regions that change, call it AFTER the expected content is visible.
- No `disableRules` in v1 — if a violation is intentional (e.g., a legacy pattern not yet fixed), add a `disableRules([ruleId])` with a code-comment justifying why. Don't baseline silently.

### Pattern 2: Cross-browser Playwright projects

**What:** Extend `playwright.config.js` to run each spec against chromium, webkit, firefox, and two mobile viewports.

**Example:**
```javascript
// Source: https://playwright.dev/docs/test-projects
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['html'], ['github']] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium',       use: { ...devices['Desktop Chrome']  } },
    { name: 'firefox',        use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit',         use: { ...devices['Desktop Safari']  } },
    { name: 'Mobile Chrome',  use: { ...devices['Pixel 5']         } }, // viewport 393x851
    { name: 'Mobile Safari',  use: { ...devices['iPhone 12']       } }, // viewport 390x844
    // Optional — 375px exactly (iPhone SE legacy + most aggressive thumb test)
    { name: 'iPhone SE 375',  use: { ...devices['iPhone SE']       } }, // viewport 375x667
  ],
});
```

**Key points:**
- `devices['iPhone 12']` viewport is 390x844, not 375px. The UI-SPEC mandates 375px audit — `devices['iPhone SE']` (375x667) is the tightest standard preset. [VERIFIED: Playwright devices.json]
- For CI time budget: run chromium + webkit + firefox on every PR. Run `iPhone SE 375` only in the a11y spec (it's the one that most exposes mobile gutter bugs).
- `fullyParallel: true` is already set — each project multiplies the worker pool; existing capacity-200 seed trick from v1.1 handles this.
- CI must add `npx playwright install --with-deps` to install all three browser engines + OS libs. [CITED: playwright.dev/docs/ci]

### Pattern 3: Loading / Empty / Error state composition (PART-12)

**What:** Every data-fetch site renders one of four branches: loading → empty / error / success.

**Example:**
```jsx
// Source: UI-SPEC.md §Interaction Contract + React 19 + react-query v5 idiom
// Re-usable pattern for every public page with a useQuery site
import { Skeleton, EmptyState, ErrorState } from '../../components/ui';

function EventsList() {
  const q = useQuery({ queryKey: ['publicEvents'], queryFn: api.public.listEvents });

  if (q.isPending) {
    return (
      // aria-busy on the region so screen readers wait
      <div aria-busy="true" aria-live="polite">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
      </div>
    );
  }
  if (q.isError) {
    return (
      <ErrorState
        title="We couldn't load this page"
        body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
        action={<Button variant="secondary" onClick={() => q.refetch()}>Try again</Button>}
      />
    );
  }
  if (!q.data?.length) {
    return (
      <EmptyState
        title="Nothing scheduled this week"
        body="New events go up on Mondays. Check back then, or browse next week's calendar."
        action={<Button variant="secondary" onClick={nextWeek}>View next week</Button>}
      />
    );
  }
  return <>{q.data.map((e) => <EventCard key={e.id} event={e} />)}</>;
}
```

**Key points:**
- `aria-busy="true"` on the region AND `aria-live="polite"` tell assistive tech to wait before announcing. [CITED: MDN aria-busy; aria-live]
- `Skeleton` already has `aria-hidden="true"` (see `components/ui/Skeleton.jsx:8`) — so the skeleton itself is invisible to screen readers; the outer region is what aria-busy modifies.
- `role="alert"` on `ErrorState` (or `role="status"` for non-critical) ensures the error is announced. `EmptyState` does NOT need a role — it's static content.
- Button pending states (per UI-SPEC §Loading copy): inline spinner inside button, label gerund ("Signing up…"), button stays disabled. Already partially done in `EventDetailPage.jsx` and `ManageSignupsPage.jsx`.

### Pattern 4: `.ics` generation in-browser (hand-rolled)

**What:** A ~30-line util that builds an RFC 5545 VCALENDAR string from an event object and triggers a download.

**Example:**
```javascript
// Source: https://icalendar.org/iCalendar-RFC-5545/4-icalendar-object-examples.html
// Source: UI-SPEC.md §Add-to-Calendar
// frontend/src/lib/calendar.js

/** Escape per RFC 5545 §3.3.11. Newlines, commas, semicolons, backslashes. */
function escapeText(s) {
  if (!s) return '';
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;');
}

/** RFC 5545 DATE-TIME floating form: 20260422T090000 (no Z, no TZID). */
function toFloatingDt(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return (
    d.getFullYear() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    'T' +
    pad(d.getHours()) +
    pad(d.getMinutes()) +
    pad(d.getSeconds())
  );
}

/** UTC DTSTAMP per §3.8.7.2. Required, must be a UTC DATE-TIME. */
function toUtcDtStamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return (
    date.getUTCFullYear() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    'T' +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds()) +
    'Z'
  );
}

/** Build VCALENDAR for one event + one slot. CRLF line endings per §3.1. */
export function buildIcs({ event, slot, origin }) {
  const uid = `scitrek-${event.id}-slot-${slot.id}@scitrek.ucsb.edu`;
  const url = `${origin}/events/${event.id}`;
  const summary = `Sci Trek: ${event.title}`;
  const location = slot.location || event.school || '';
  const description = (event.description || '') + (event.description ? '\n' : '') + url;

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//SciTrek//Volunteer Scheduler//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${toUtcDtStamp()}`,
    `DTSTART:${toFloatingDt(slot.start_time)}`,
    `DTEND:${toFloatingDt(slot.end_time)}`,
    `SUMMARY:${escapeText(summary)}`,
    `LOCATION:${escapeText(location)}`,
    `DESCRIPTION:${escapeText(description)}`,
    `URL:${url}`,
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    'TRIGGER:-PT1H',
    'DESCRIPTION:Sci Trek event reminder',
    'END:VALARM',
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  return lines.join('\r\n') + '\r\n';
}

export function downloadIcs({ event, slot, filename }) {
  const ics = buildIcs({ event, slot, origin: window.location.origin });
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

**Key points:**
- **Floating time** (no Z, no TZID) matches UI-SPEC intent for "event starts 9am local Pacific". Calendar apps show this as the venue's local time. This sidesteps VTIMEZONE blocks entirely. [CITED: RFC 5545 §3.3.5 — DATE-TIME form 3]
- **CRLF line endings** are mandatory per §3.1. A single `\n` bugs out on stricter parsers (some Outlook versions).
- **DTSTAMP (UTC, Z-suffix)** is REQUIRED; DTSTART is required when no METHOD is present (we have none). [CITED: RFC 5545 §3.6.1]
- **VALARM** with `TRIGGER:-PT1H` = 1 hour before event (UI-SPEC directive).
- **UID** must be globally unique. `scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu` satisfies RFC 822-style uniqueness. Stable — re-downloading the same slot produces identical UID, so the target calendar deduplicates rather than creating a second event.
- **Filename** per UI-SPEC: `scitrek-{event-slug}-{yyyy-mm-dd}.ics` lowercase/hyphens.
- **Line folding (§3.1) is NOT needed** as long as no single line exceeds 75 octets. The longest line in our output is `DESCRIPTION:` concatenating event.description + URL — if event.description is long, add line folding (split at 74 chars with CRLF + SPACE continuation) OR truncate description in the download util to keep lines ≤74 bytes.

### Anti-Patterns to Avoid

- **`<div className="animate-spin">` on the whole page for loading.** UI-SPEC §Loading copy bans this. Use `Skeleton` for lists/detail, inline button spinner for actions.
- **Raw `window.confirm()` for cancel.** `ManageSignupsPage.jsx` already uses `Modal` — keep it. UI-SPEC §Destructive confirmations is explicit.
- **Placeholder as label.** Tailwind patterns tempt this; axe-core flags `label-content` rule. UI-SPEC requires visible `<Label>` for every `<Input>`.
- **Color as sole signal.** Status chips today use background+text only ("Confirmed" green, "Pending" yellow). Per UI-SPEC A11y Checklist, status chips MUST carry a text label AND an icon (e.g., `<CheckCircle size={12} />`). This phase adds the icon.
- **`<a onClick>` for buttons.** Use `Button` primitive (or `Button as={Link}` for nav).
- **Opening magic links in a new tab (target="_blank")** — worsens iOS Safari in-app-browser session loss.
- **Baselining axe violations silently.** If a rule must be disabled, wrap the `disableRules` call in a comment explaining why; never edit the spec to "pass".

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Focus trap on Modal | Custom keydown handler | Existing `lib/useFocusTrap.js` | Already handles Tab loop + ESC + restore-focus. Don't reinvent. |
| Toast queue | Your own state | Existing `state/toast.js` + `components/ui/Toast.jsx` | Already used 6+ places. |
| axe-core engine | Write WCAG checks yourself | `@axe-core/playwright` | 120+ rules maintained by Deque; updated for WCAG 2.2. Hand-rolled checks will miss 90%+ of real violations. |
| Cross-browser testing harness | Headless Chrome + wget | Playwright `projects` | Single config, parallel, traces/screenshots built in. |
| Week navigation logic | Raw date math | Existing `lib/weekUtils.js` | Used by EventsBrowsePage. |
| Form validation framework | Yup/zod/formik | Inline `validateIdentity()` already in EventDetailPage | Phase 15 is polish, not re-architecture. 4 fields don't warrant a library. |
| **`.ics` string builder** | **`ics@3.11.0` npm package** | **Hand-rolled 30-line util (see Pattern 4)** | Library pulls in `yup` (~40KB gzipped) for a problem that is 30 lines of string concat. Our eventV shape is FIXED (one event, one slot, floating time, one VALARM), so we don't need the library's generality. UI-SPEC pins filename, SUMMARY, LOCATION, DESCRIPTION, UID shape — a custom builder matches 1:1 without indirection. Counter-example where you WOULD use `ics`: if we needed recurrence rules (RRULE), multi-day VJOURNAL, or timezone conversions. We don't. |

**Key insight:** This phase is composition, not construction. The UI primitives, the data layer, the routing, the E2E scaffold, and the a11y tooling all exist. The only net-new artifact is the `.ics` util + one new primitive (`ErrorState`). Resist the urge to "modernize" anything else.

## Runtime State Inventory

N/A — this phase does not rename, refactor strings, or migrate data. All changes are additive (new primitive, new util, new spec) or in-place polish of JSX. No database columns are touched.

## Common Pitfalls

### Pitfall 1: iOS Safari magic-link in-app-browser session loss
**What goes wrong:** Volunteer opens Gmail on their iPhone, taps the confirmation magic link, it opens in Gmail's in-app browser (WebKit inside Gmail, not Safari). The token is consumed there. Later they try to visit the site in Safari proper — their session is gone and the one-shot token is burned.
**Why it happens:** iOS Gmail/Outlook/Instagram/LinkedIn in-app browsers are separate WKWebView instances with their own cookie jars; tapping a link doesn't hand off to Safari by default. [CITED: daringfireball.net 2025-12; supabase discussion #15708]
**How to avoid:**
1. We already use URL-param tokens (no cookie dependency), so the token is portable across browsers. This phase DOES NOT need to fix this.
2. Add a small interstitial note on `ConfirmSignupPage` when detecting in-app browser: "On iPhone? Long-press the email link and choose 'Open in Safari' for best results." (Claude's discretion — UI-SPEC doesn't require it.)
3. Verify Playwright `webkit` project picks this up — it does emulate Mobile Safari's default browser, not in-app Gmail, so the CI pass tells us "Safari proper works"; the in-app issue is an organic UX note.
**Warning signs:** Reports of "my link stopped working" — nearly always in-app browser, not a real bug.

### Pitfall 2: axe-core scanning before page finishes rendering
**What goes wrong:** Test calls `AxeBuilder({page}).analyze()` while the skeleton is still visible. Axe reports "heading-order" false positive because the real H1 hasn't rendered.
**Why it happens:** Playwright defaults to a short load timeout; react-query fires in a microtask.
**How to avoid:** Always `await page.waitForLoadState('networkidle')` OR `await expect(page.getByRole('heading', {name: ...})).toBeVisible()` before `analyze()`. For pages gated on seeded data (event detail, portal, check-in), also wait for the specific content (e.g., `await page.getByText('E2E Seed Event').first().waitFor()`).
**Warning signs:** Flaky axe tests that fail once in three runs.

### Pitfall 3: 375px horizontal scroll from a single wide element
**What goes wrong:** A table, a code block, or a pre-wrap string (long email address) blows out the page width on 375px. Playwright mobile-safari project catches this as a horizontal scroll.
**Why it happens:** Tailwind's `overflow-x-auto` is often missing from wrappers; long unbroken strings don't wrap unless `break-words` / `overflow-wrap: anywhere` is set.
**How to avoid:**
- `EventDetailPage.jsx` already wraps its slot table in `<div className="overflow-x-auto">`. Verify every page does this for any `<table>`.
- Add a Playwright assertion `expect(await page.evaluate(() => document.body.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)` per route in the a11y spec. Simple, catches 90% of cases.
- Long emails in `SignupSuccessCard` → add `break-words` to the `<li>` text.
**Warning signs:** `scrollWidth > clientWidth` on document.body at 375px.

### Pitfall 4: Tap target spacing under 24px
**What goes wrong:** Two adjacent `Chip` components with 4px gap — each is 44px tall but only 8px apart. WCAG 2.5.8 (target-size-minimum in 2.2) warns that targets <24px need spacing; 44px targets with <8px gap can still cause mis-taps.
**Why it happens:** Tailwind `gap-1` (4px) is seductive for pill groups.
**How to avoid:** UI-SPEC §Spacing Scale token 2 (8px / `gap-2`) is the minimum for Chip groups. Token 4 (16px / `gap-4`) is the default between list rows. Audit every `gap-1` usage — most should be `gap-2`.
**Warning signs:** Fat-finger mis-taps in manual testing; axe-core does NOT flag this (it's a heuristic, not a strict rule at AA level).

### Pitfall 5: `aria-busy` forgotten in the finally branch
**What goes wrong:** A button action sets `aria-busy="true"` on the page region, errors out in catch, and the region stays busy forever — screen reader never announces subsequent updates.
**Why it happens:** Missing `finally` reset.
**How to avoid:** Derive `aria-busy` from react-query's `isFetching` / `isPending`, not from manual state. Never set it imperatively. [CITED: MDN aria-busy]
**Warning signs:** Screen reader goes quiet after an error on any data page.

### Pitfall 6: Playwright `webkit` flakiness on form-submit responses
**What goes wrong:** `public-signup.spec.js` uses `waitForResponse` for POST /public/signups. Webkit's network handling is slightly different from Chromium — races occasionally fail the first run.
**Why it happens:** Webkit fires response events slightly before DOM mutations that Chromium batches.
**How to avoid:** Use `Promise.all([waitForResponse, click])` pattern already in `public-signup.spec.js:64-69` — this is already robust. Set retries: `retries: process.env.CI ? 2 : 0` is already configured. If webkit needs higher retries than chromium, consider `retries` at the project level.
**Warning signs:** Test passes in chromium project, fails first-try in webkit project.

### Pitfall 7: Axe false positive on color-contrast for brand button
**What goes wrong:** `--color-brand` (#0284c7) on `--color-brand-fg` (#ffffff) is 4.87:1 — above 4.5:1 AA for normal text. But on small button text with `font-weight: 500` (not bold), axe might flag it as borderline.
**Why it happens:** Axe uses the computed ratio; UI-SPEC color contrast note says PASS, so this should NOT fire. But `Card` borders overlaid on brand CTAs or chip states can create local contrast issues.
**How to avoid:** Before running the a11y spec in CI, run locally once: `cd frontend && npm run dev` then `cd .. && npx playwright test a11y.spec.js --headed`. Fix every violation surfaced. If a "false positive" appears, justify in a code comment before `disableRules`.
**Warning signs:** `color-contrast` rule in violations array.

### Pitfall 8: Copy drift between code and UI-SPEC
**What goes wrong:** Phase 10/11 shipped UI with copy strings that don't match UI-SPEC §Copywriting Contract. E.g., current `OrientationWarningModal.jsx` says `"Have you completed orientation?"` but UI-SPEC says `"Have you done a Sci Trek orientation?"`. Current `ManageSignupsPage.jsx` says `"Never mind"` and `"Yes, cancel"` but UI-SPEC says `"Keep signup"` and `"Yes, cancel"`.
**Why it happens:** UI-SPEC is new (written this phase).
**How to avoid:** Treat UI-SPEC §Copywriting Contract + §Empty states + §Error states + §Orientation-warning modal + §Add-to-Calendar as a CHECKLIST. Audit every string in the 6 public pages against the spec. Planner should create a per-page "copy diff" task.
**Warning signs:** User confusion; Andy flagging "I said X but the app says Y".

## Code Examples

### Verified patterns from official sources

#### ErrorState primitive (new, mirrors EmptyState API)

```jsx
// frontend/src/components/ui/ErrorState.jsx
// Source: UI-SPEC.md §ErrorState API
import React from 'react'
import { AlertTriangle } from 'lucide-react'
import { cn } from '../../lib/cn'

const ErrorState = React.forwardRef(function ErrorState(
  { title, body, action, icon, className, ...rest },
  ref,
) {
  const Icon = icon || AlertTriangle
  return (
    <div
      ref={ref}
      role="alert"
      className={cn('py-12 text-center', className)}
      {...rest}
    >
      <Icon
        aria-hidden="true"
        className="mx-auto mb-3 h-8 w-8 text-[var(--color-danger)]"
      />
      {title ? <p className="text-lg font-semibold">{title}</p> : null}
      {body ? (
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">{body}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
})

export default ErrorState
export { ErrorState }
```

Register in `frontend/src/components/ui/index.js`:
```javascript
export { default as ErrorState } from './ErrorState'
```

#### Axe-core tag selection (authoritative list)

Tags used for **WCAG 2.1 AA**:
- `wcag2a` — all WCAG 2.0 Level A rules
- `wcag2aa` — all WCAG 2.0 Level AA rules
- `wcag21a` — all WCAG 2.1 Level A rules (adds status-messages, autocomplete-valid, etc.)
- `wcag21aa` — all WCAG 2.1 Level AA rules (adds identical-links-same-purpose, page-has-heading-one, etc.)

Tags explicitly NOT used:
- `best-practice` — noisy for existing codebase; consider enabling in a follow-up milestone
- `wcag22aa` — higher bar than required; would pass anyway per UI-SPEC min-h-11 mandate, but don't gate CI on it
- `experimental` — unstable, never in CI
- `aaa` / `wcag2aaa` / `wcag21aaa` — target is AA, not AAA

[CITED: axe-core/doc/rule-descriptions.md; deque.com/axe/axe-core/]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global CSS full-page spinner | Skeleton screens matched to final layout shape | Industry pivot ~2020; NN/g research | Per UI-SPEC D-09; UX research confirms skeletons reduce perceived wait. |
| Placeholder-only form labels | Visible `<label>` elements via `<Label>` primitive | WCAG 2.1 (2018) + axe-core flagging | Already baked into UI primitives; phase 15 adds CI enforcement. |
| `window.confirm()` destructive dialogs | Styled `Modal` with explicit cancel/confirm buttons | React ecosystem ~2016; reinforced by WCAG 2.1 | Already in use on ManageSignupsPage. |
| Hand-rolled focus-trap on dialogs | Reusable `useFocusTrap` hook | Already in repo (`lib/useFocusTrap.js`) | Don't hand-roll — use the hook. |
| BrowserStack / SauceLabs for cross-browser | Playwright `projects` with bundled engines | Playwright 1.x, 2020+ | D-13 confirms no BrowserStack; extend projects matrix. |
| `ics` npm package for calendar files | Hand-rolled 30-line VCALENDAR builder | Unchanged in 10+ years; RFC 5545 is stable | Our usage is narrow; library cost > benefit. |

**Deprecated/outdated:**
- React 18 patterns using `ReactDOM.render` — we use React 19 `createRoot` (already in `main.jsx`).
- `react-router-dom` v5 `<Switch>` / `<Route exact>` — we use v7 `<Routes>` / `<Route>`.
- Tailwind v3 `tailwind.config.js` + `content: [...]` — we use Tailwind v4 `@theme` block in CSS. **Do not add a `tailwind.config.js`.**
- `tanstack-query` v4 `isLoading`/`useQuery({queryKey, queryFn, enabled}).data` — in v5 the loading state is `isPending` (already migrated in all public pages).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Floating-time DTSTART is acceptable to Apple Calendar, Google Calendar, and Outlook for SciTrek's use case (event starts at venue's local time). | .ics generation | LOW. If a viewer in a different timezone imports and sees a mis-aligned time, they can manually adjust — but floating time is a deliberate spec choice for cross-timezone events. RFC 5545 §3.3.5 documents this as "form 3" floating. Test plan: download the .ics locally, open in Apple Calendar + Google Calendar, verify time shows correctly. [CITED: RFC 5545 §3.3.5; icalendar.org] |
| A2 | `@axe-core/playwright@4.11.1` + axe-core `@~4.11.1` cover all WCAG 2.1 AA rules needed for this codebase (no gaps). | axe-core integration | LOW. Deque is the reference implementation; 120+ rules. Any gaps would also not be covered by other tools. |
| A3 | Andy's phone is iPhone (iOS) and is the primary device for D-05 manual review. | Audit methodology | LOW. UI-SPEC §Add-to-Calendar explicitly targets Apple Calendar. If Andy is on Android, swap to Google Calendar for manual .ics check; logic unchanged. |
| A4 | Adding `webkit` + `firefox` Playwright projects will roughly triple CI time (~6 min → ~18 min). Acceptable. | Playwright matrix | MEDIUM. If CI time becomes painful, shard by project (`--shard`) or run firefox nightly only. Current CI already runs docker + 5 specs; 3x overhead is workable. [CITED: playwright.dev/docs/ci sharding] |
| A5 | All event slot data returned by `/public/events/:id` includes `start_time`, `end_time`, `date`, `location`, `id` fields usable for .ics generation — no backend shape change needed. | .ics generation | VERIFIED in `EventDetailPage.jsx:174-176` and SignupSuccessCard — these fields are already consumed. Confidence HIGH, but validate during Wave 0 by inspecting actual API response shape. |
| A6 | The "one new feature" .ics download does NOT require a route change (no `/calendar/:id` URL). Button handler triggers an in-memory Blob download. | .ics generation | LOW. Matches D-01 "frontend-only, zero new backend". |
| A7 | Existing seed (`seed_e2e.py`) provides enough distinct fixtures for the axe-core spec (seeded event + seeded confirm_token + a seeded signup_id for check-in + a portal slug). | a11y spec dynamic routes | MEDIUM. Inspect `backend/tests/fixtures/seed_e2e.py` in Wave 0. If the seed doesn't expose a `portal_slug` or `signup_id`, add them — this is in-scope for the e2e/ directory (Hung's domain). Backend changes to expose more seed fields would need coordination with Andy. |
| A8 | axe-core 4.11.1 has no known bugs or regressions relative to 4.10.x that would affect our rules. | axe-core integration | LOW. Latest release; CHANGELOG shows no regressions. Verify by running spec locally before CI push. |

## Open Questions (RESOLVED)

1. **Should `/signup/manage?token=expired` return a specific error for axe-core's scan?**
   - What we know: `ManageSignupsPage.jsx:91` renders `<ErrorCard>` (not yet using new `ErrorState`).
   - What's unclear: When the a11y spec hits `/signup/manage` without a token (one of the static routes), it renders the `ErrorCard`. Is that an intentional "no-token" state (PART-08) or should the route redirect?
   - RESOLVED: Treat no-token as an error state — it's a degenerate but valid branch. Include it in the a11y sweep; verify UI-SPEC error-copy matches.

2. **Does the existing magic-link token get burned when the a11y spec hits `/signup/confirm?token=...`?**
   - What we know: `ConfirmSignupPage:useEffect` calls `confirmSignup(token)` on mount. Playwright's a11y spec would trigger this.
   - What's unclear: If the seeded confirm_token is single-use, the spec would consume it and subsequent a11y tests (or re-runs) would see the error branch.
   - RESOLVED: Use a dedicated fresh confirm_token for a11y tests, OR have the a11y spec scan the "already-confirmed" state (which is visually the ManageSignupsPage inline-rendered — also valid). Phase 13's seed_e2e.py already supports ephemeral tokens. Document in plan.

3. **Do we need a separate mobile-only a11y sweep, or does desktop-webkit suffice for WCAG AA?**
   - What we know: WCAG rules are mostly browser-agnostic; contrast, roles, names don't vary by viewport. Only viewport-dependent rule is target-size.
   - What's unclear: Whether to run a11y.spec.js in every Playwright project or just `chromium` + `Mobile Safari 375`.
   - RESOLVED: Run a11y spec in `chromium` (fastest) for every PR. Add a second run in `iPhone SE 375` gated on `frontend/**` changes to catch mobile-only target-spacing issues. Saves CI time.

4. **What's the violations budget for "known legacy issues" during the transition?**
   - What we know: D-04 says "axe-core in CI for WCAG AA passing" — implies zero violations at merge.
   - What's unclear: If Wave 0 finds 20 pre-existing violations, do we block Wave 1 on fixing all, or baseline some as technical debt?
   - RESOLVED: Phase goal is "production-ready", so zero-violations at phase close is the bar. But for mid-phase iteration, allow a per-rule `disableRules` with a code-comment, and require every disabled rule to be re-enabled before phase verify. Track in PART-AUDIT.md.

5. **Should `.ics` downloads track in analytics?**
   - What we know: No analytics are currently wired into the public pages (CONTEXT.md confirms no accounts, no tracking).
   - RESOLVED: NO analytics for v1.2-prod. A toast confirming download is enough user feedback.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Everything frontend | ✓ | v22.22.2 (verified) | — |
| npm | Package install | ✓ | 10.9.7 (verified) | — |
| Playwright CLI | E2E runs | ✓ | @playwright/test 1.59.1 installed | — |
| @axe-core/playwright | a11y spec | ✓ | 4.11.1 installed | — |
| Docker + docker-compose | E2E stack (backend, db, redis) | ✓ (assumed — existing) | existing | — (required for CI parity) |
| Python 3.10 | `seed_e2e.py` globalSetup | ✓ (CI) / ✓ (local — existing backend env) | 3.10+ | — |
| Tailwind v4 CLI | Build | ✓ via @tailwindcss/vite 4.2.2 | — | — |
| `ics` npm package | .ics generation (if chosen) | ✗ | — | Hand-roll (recommended) |
| Real iPhone for manual review | D-05 final sign-off | ✓ (assumed — Andy) | — | iOS Simulator as fallback |
| Webkit browser engine | Playwright webkit project | ✗ (needs `npx playwright install webkit`) | — | Install step must run before tests |
| Firefox browser engine | Playwright firefox project | ✗ (needs `npx playwright install firefox`) | — | Install step must run before tests |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- `ics` npm package — fallback is hand-rolled util (recommended path per Don't Hand-Roll table).
- Webkit/Firefox engines — fallback is installing them. CI already uses `npx playwright install --with-deps chromium`; change to `npx playwright install --with-deps` (no arg) to install all three + Linux OS deps. Local dev uses whatever's already installed; `npm run e2e:install` in `frontend/package.json` currently only installs chromium — consider adding an `e2e:install:all` script. [CITED: playwright.dev/docs/ci]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Frontend unit framework | vitest 2.1.2 + @testing-library/react 16.3.2 |
| Frontend unit config | `frontend/vitest.config.js` (jsdom env + `src/test/setup.js`) |
| E2E framework | @playwright/test 1.59.1 + @axe-core/playwright 4.11.1 |
| E2E config | `playwright.config.js` (root) — needs webkit + firefox projects added |
| E2E global setup | `e2e/global-setup.js` (seeds via `seed_e2e.py`; backend must be up) |
| Unit quick run | `cd frontend && npm run test -- --run` |
| Unit watch mode | `cd frontend && npm run test:watch` |
| E2E full run | `npx playwright test` (repo root) |
| E2E single project | `npx playwright test --project=chromium` (swap for webkit, firefox, etc.) |
| E2E single spec | `npx playwright test e2e/a11y.spec.js` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PART-01 | Audit doc `PART-AUDIT.md` exists and lists per-route findings | manual-only | — (doc review) | ❌ Wave 0 — create doc |
| PART-02 | No console errors / 404s / broken images on any public route | e2e smoke | `npx playwright test e2e/public-signup.spec.js` (extend to assert `page.on('pageerror')` / `page.on('console')` captured zero errors) | ✅ existing; needs console-error assertion added |
| PART-03 | Browse-by-week shows events; week nav works; no stuck spinner | e2e + unit | `npx playwright test e2e/public-signup.spec.js` + `npm run test -- EventsBrowsePage.test.jsx` | ✅ existing |
| PART-04 | Slots grouped by type with capacity + filled counts | unit | `npm run test -- EventDetailPage.test.jsx` | ✅ existing |
| PART-05 | Client validation: name, email, phone E.164 | unit | `npm run test -- EventDetailPage.test.jsx::validation` | ✅ existing; may need E.164 case added |
| PART-06 | Orientation modal fires period-only + no-history; suppressed when history=true | e2e | `npx playwright test e2e/orientation-modal.spec.js` | ✅ existing (2 cases A + B) |
| PART-07 | Magic link works on Safari iOS and Chrome Android | e2e cross-project | `npx playwright test e2e/public-signup.spec.js --project=webkit` + `--project="Mobile Chrome"` | ✅ spec exists; ❌ projects missing |
| PART-08 | Manage page shows signups + per-row cancel + cancel-all | e2e | `npx playwright test e2e/public-signup.spec.js::manage` | ✅ existing |
| PART-09 | Self check-in inside window works, outside rejected | unit | `npm run test -- SelfCheckInPage.test.jsx` | ✅ existing |
| PART-10 | WCAG 2.1 AA — axe-core violations array is empty on every public route | e2e a11y | `npx playwright test e2e/a11y.spec.js` | ❌ Wave 0 — create spec |
| PART-11 | 375px: no horizontal scroll, tap targets ≥44px, thumb-zone CTAs | e2e mobile | `npx playwright test e2e/a11y.spec.js --project="iPhone SE 375"` (adds scrollWidth assertion) | ❌ Wave 0 — new project + spec |
| PART-12 | Every public page renders loading + empty + error branches | unit | `npm run test -- EventsBrowsePage.test.jsx EventDetailPage.test.jsx ConfirmSignupPage.test.jsx ManageSignupsPage.test.jsx` | ✅ partial; ErrorState cases need adding |
| PART-13 | Add-to-Calendar button generates valid .ics matching UI-SPEC filename + UID + VALARM | unit (calendar.js) + manual (open in Apple Calendar) | `npm run test -- calendar.test.js` + manual | ❌ Wave 0 — new file + spec |
| PART-14 | Cross-browser smoke pass: chromium + webkit + firefox | e2e matrix | `npx playwright test` (runs all projects) | ✅ specs exist; ❌ projects config needs update |

### Sampling Rate

- **Per task commit:** Affected unit test only — e.g., `npm run test -- EventsBrowsePage.test.jsx --run`
- **Per wave merge (to role branch):** All frontend unit tests + chromium E2E — `cd frontend && npm run test -- --run && cd .. && npx playwright test --project=chromium`
- **Phase gate (before `/gsd-verify-work`):** Full matrix — `cd frontend && npm run test -- --run && cd .. && npx playwright test` (all projects including webkit, firefox, and Mobile Safari; a11y spec green with zero violations)

### Wave 0 Gaps

- [ ] `frontend/src/components/ui/ErrorState.jsx` — new primitive required before pages can wire error branches (blocks PART-12).
- [ ] `frontend/src/components/ui/index.js` — export `ErrorState`.
- [ ] `frontend/src/lib/calendar.js` — new util (blocks PART-13).
- [ ] `frontend/src/lib/__tests__/calendar.test.js` — unit test verifying VCALENDAR output, escaping, UID shape, CRLF line endings (blocks PART-13).
- [ ] `e2e/a11y.spec.js` — new spec that iterates 6 public routes with `AxeBuilder` (blocks PART-10, PART-11).
- [ ] `playwright.config.js` — add `firefox`, `webkit`, `Mobile Chrome`, `Mobile Safari`, `iPhone SE 375` projects (blocks PART-07, PART-14; PR-only file).
- [ ] `.github/workflows/ci.yml` — change `npx playwright install --with-deps chromium` → `npx playwright install --with-deps` (blocks cross-browser CI; PR-only file).
- [ ] `frontend/package.json` — add `e2e:install:all` script `playwright install chromium webkit firefox` (convenience; local dev).
- [ ] `.planning/phases/15-participant-role-audit-ux-polish/PART-AUDIT.md` — new audit checklist doc (PART-01 deliverable).
- [ ] Shared test fixture for a11y spec — may need seed_e2e.py to expose a `portal_slug` and a dedicated `a11y_confirm_token` so the spec has a route that doesn't clash with public-signup.spec.js's token.

*(Nothing prevents parallel work: Wave 0 can drop ErrorState + calendar.js + a11y spec scaffolding; Wave 1 polishes pages against UI-SPEC; Wave 2 wires .ics buttons + cross-browser projects; Wave 3 verifies.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Accountless per D-17; no changes. |
| V3 Session Management | no | No sessions for participants (magic-link token only). |
| V4 Access Control | partial | Magic-link tokens gate signup management + check-in; already enforced server-side. No frontend changes. |
| V5 Input Validation | yes | Client-side form validation in `EventDetailPage.jsx`; server-side Pydantic remains authoritative. This phase tightens PART-05 error copy per UI-SPEC but doesn't weaken validation. |
| V6 Cryptography | no | No new crypto. Magic-link tokens are server-generated. |
| V11 Business Logic | partial | Orientation soft-warning is business logic; already implemented. This phase verifies behavior, doesn't modify. |
| V12 File / Resource | low | `.ics` file is generated client-side from data the API already returned. No user-supplied file paths. Escape via `escapeText()` per RFC 5545 prevents injection into VCALENDAR fields. |
| V14 Configuration | partial | `EXPOSE_TOKENS_FOR_TESTING=1` is a known test-only escape hatch; documented in CLAUDE.md + ci.yml. Do not enable in production. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via event.description in `.ics` DESCRIPTION field | Tampering | `escapeText()` in `calendar.js` escapes `,`, `;`, `\n`, `\\` per RFC 5545. Calendar apps render DESCRIPTION as text, not HTML — but strict escaping is defense-in-depth. |
| XSS via event.title / slot.location in rendered JSX | Tampering | React escapes children by default; no `dangerouslySetInnerHTML` used anywhere in the public flow (verified: grep). No changes. |
| Open-redirect in URL field of .ics | Tampering | `URL` in .ics points to `${origin}/events/${event.id}` — origin from `window.location.origin`, event.id from API. Safe. |
| CSRF on cancel signup / check-in | Tampering | Magic-link token in URL acts as capability token; single-use server-side. No cookies, no CSRF surface. No change. |
| PII in localStorage / logs | Information Disclosure | Already audited in Phase 10 (`EventDetailPage.jsx:3-9` SECURITY comment). Identity state lives in React component state only; no PII persisted. This phase must not regress. |
| Magic-link token leakage via Referer header | Information Disclosure | Tokens are in URL query string. Browsers may send as Referer to third-party resources (e.g., images). No third-party assets today. If any are added, use `<meta name="referrer" content="no-referrer">`. LOW risk. |
| Magic-link token burned by pre-fetch / email scanner | Denial of Service | Known industry issue; mitigated by token being single-use on confirm only (read operations are idempotent). Not this phase's problem. |
| .ics UID collision across volunteers | Spoofing | UID is `scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu` — per-slot, not per-signup. Two volunteers downloading the same slot get the same UID, which is CORRECT (both events collapse to one in the calendar app). Not a vulnerability. |

## Sources

### Primary (HIGH confidence)
- **Context7** `/dequelabs/axe-core` — `axe.run` API, tag values, `runOnly` by tag, `rules: {id: {enabled: false}}` patterns
- **Context7** `/microsoft/playwright` — `defineConfig({projects: [...]})` with `devices['iPhone 12' | 'iPhone SE' | 'Pixel 5' | 'Desktop Safari' | 'Desktop Firefox']`
- **playwright.dev/docs/accessibility-testing** — canonical `AxeBuilder({page}).withTags([...]).analyze()` + `expect(results.violations).toEqual([])` pattern
- **playwright.dev/docs/ci** — `npx playwright install --with-deps`, no caching of browser binaries, sharding with matrix
- **github.com/dequelabs/axe-core-npm/blob/develop/packages/playwright/README.md** — `AxeBuilder` constructor, `include`, `exclude`, `withTags`
- **RFC 5545** (icalendar.org/iCalendar-RFC-5545/) — VEVENT required fields (UID, DTSTAMP, DTSTART), VALARM, floating-time DTSTART form, text-escaping rules (§3.3.11), CRLF line endings (§3.1)
- **MDN aria-busy / aria-live** — ARIA patterns for loading regions
- **WCAG 2.1 W3C Quickref** — AA success criteria mapping (2.5.5 Target Size, 1.4.3 Contrast)
- **Installed code** — `@axe-core/playwright@4.11.1`, `@playwright/test@1.59.1`, existing `components/ui/*`, `e2e/*.spec.js`, `playwright.config.js`, `.github/workflows/ci.yml`

### Secondary (MEDIUM confidence)
- **npm registry** — `ics@3.11.0` version verified 2026-04-15 (`npm view ics`); dependencies `{nanoid, runes2, yup}` verified
- **github.com/adamgibbons/ics** — API shape + Blob download pattern
- **daringfireball.net 2025-12** — iOS Safari magic-link UX issues (in-app browser session loss)
- **DockYard / DigitalA11Y blog posts** — aria-busy best practices (forget-to-reset anti-pattern)

### Tertiary (LOW confidence — verify in plan)
- Exact iOS Safari .ics download UX details (behavior varies Gmail iOS vs Apple Mail iOS vs Safari-direct; needs real-device smoke during D-05 manual review)
- CI time estimate for adding webkit + firefox — claimed ~3x, but depends on spec count and parallelism; measure after first PR

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against installed node_modules and npm registry 2026-04-15.
- Architecture: HIGH — existing codebase inventoried page-by-page; UI-SPEC is authoritative.
- axe-core / Playwright integration: HIGH — Context7 + official docs cross-verified.
- RFC 5545 .ics format: HIGH — RFC is stable since 2009; floating-time is §3.3.5 form 3.
- .ics UX on iOS Safari: MEDIUM — known friction but workaround pattern (Blob + anchor.download) works for Apple Calendar per multiple sources; real-device validation is D-05.
- 375px audit heuristics: MEDIUM — UI-SPEC enforces 44px + 8-16px spacing; axe-core doesn't flag target-size at AA (only AA in WCAG 2.2), so some manual review is required.
- Pitfalls: MEDIUM — based on project code inventory + industry blogs; new classes may surface during Wave 0 audit.

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 for tooling versions (stable); RFC 5545 content valid indefinitely.

---

*Phase: 15-participant-role-audit-ux-polish*
*Research completed: 2026-04-15*
