# Phase 15: Participant role audit + UX polish - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end audit + production-polish of every logged-out participant flow on a fresh DB. In-scope routes: `/events`, `/events/:eventId`, `/signup/confirm`, `/signup/manage`, `/check-in/:signupId`, `/portals/:slug`. Deliverables: fix every bug/layout glitch, hit WCAG 2.1 AA (axe-core in CI), pass 375px mobile audit on every page, add loading/empty/error states everywhere, cross-browser smoke pass, and ship ONE new audit-surfaced participant feature (PART-13).

Scope is FIXED by ROADMAP.md and REQUIREMENTS-v1.2-prod.md (PART-01..PART-14). Discussion clarifies HOW, not WHAT.

</domain>

<decisions>
## Implementation Decisions

### PART-13 feature choice
- **D-01:** Ship **Add-to-Calendar (.ics)** as the one new participant feature.
  - Button on confirmation page and event detail page.
  - Generates a downloadable `.ics` file (iCalendar standard) — works with Google, Apple, Outlook without OAuth.
  - No backend changes required — built entirely in frontend using event data already returned by `/events/:eventId`.
  - Rationale: high real-student value, zero new backend, no auth required (fits accountless model), low complexity.

### Audit methodology
- **D-02:** **Design-first, then audit.** Produce a visual target BEFORE fixing, so polish has a clear bar.
- **D-03:** Design pass runs in two stages:
  1. `gsd-ui-phase` → produce `UI-SPEC.md` locking **design tokens + primitive components** (Skeleton, EmptyState, ErrorState, button/input variants, spacing/typography scale) consistent with current Tailwind look.
  2. `frontend-design` skill → iterate **page-level layouts** for the 4 public pages (EventsBrowsePage, EventDetailPage, ConfirmSignupPage, ManageSignupsPage) plus `/check-in/:signupId` and `/portals/:slug` against the locked tokens.
- **D-04:** After design is approved, audit runs against that target using:
  - axe-core in Playwright CI for WCAG AA.
  - Playwright smoke test crawling every public route for console errors, 404s, broken images.
  - Manual 375px walkthrough using Playwright device emulation + screenshot diff.
- **D-05:** Andy reviews each page visually at least once on an actual phone before sign-off.

### Visual style
- **D-06:** **Keep the current Tailwind look — polish, don't redesign.** Tighten spacing, fix states, hit the audit bar, preserve existing colors/typography.
- **D-07:** No UCSB/SciTrek brand repaint in this phase (deferred idea below).

### Loading / empty / error states (PART-12)
- **D-08:** **Shared primitives** under `frontend/src/components/ui/` — `Skeleton`, `EmptyState`, `ErrorState` — built once, reused across all public pages.
- **D-09:** Skeletons for list and detail loads; spinners only for button/action pending states.
- **D-10:** Every public page and every data-fetch site must have loading + empty + error branches wired — verified by checklist during audit.

### Cross-browser verification (PART-14)
- **D-11:** **Playwright projects in CI** covering chromium (Chrome), webkit (Safari mobile/desktop), firefox. Smoke suite runs on every PR touching `frontend/**`.
- **D-12:** Smoke covers the golden path: browse → event detail → sign up → confirm (magic link) → manage → check-in.
- **D-13:** No BrowserStack / SauceLabs in this phase.

### Scope guardrails
- **D-14:** `frontend/src/lib/api.js` is **read-only** in this phase (per ROADMAP file-ownership rule — coordinate with admin worktree). No new backend endpoints, no Alembic migrations, no FastAPI changes.
- **D-15:** No new public routes beyond the Add-to-Calendar feature.
- **D-16:** No admin/organizer work — stay in participant worktree.
- **D-17:** No auth / account features. Accountless stays accountless.

### Claude's Discretion
- Exact skeleton shape (shimmer vs pulse animation).
- `.ics` file formatting details (VTIMEZONE block, UID generation strategy) as long as output validates.
- Playwright project matrix fine-tuning (e.g., viewport list, retry counts).
- Choice of specific empty-state copy and illustration (or no illustration).
- Whether to use a tiny ICS-generation library or hand-roll the string builder.

</decisions>

<specifics>
## Specific Ideas

- "I just want to make sure the entire participant flow works pretty much and how I like it visually."
- Andy wants to actively USE the frontend-design skill during this phase — the phase is a deliberate testbed for it, not just a bug-fix pass.
- Visual target: current Tailwind aesthetic, just polished — not a redesign, not a rebrand.
- Andy will review on a real phone before sign-off (not just browser devtools).
- .ics feature should Just Work with Apple Calendar on iOS (primary target student device).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Phase boundary + requirements
- `.planning/ROADMAP.md` (Phase 15 section) — goal, success criteria, in-scope routes, touches, requirements list.
- `.planning/REQUIREMENTS-v1.2-prod.md` — PART-01 through PART-14 full acceptance text.
- `.planning/PROJECT.md` — product-level vision and constraints.

### Project conventions
- `CLAUDE.md` (repo root) — stack, test harness invocation, alembic conventions, teaching style, CSV cadence.

### Existing public-flow code (read before modifying)
- `frontend/src/pages/public/EventsBrowsePage.jsx`
- `frontend/src/pages/public/EventDetailPage.jsx`
- `frontend/src/pages/public/ConfirmSignupPage.jsx`
- `frontend/src/pages/public/ManageSignupsPage.jsx`
- `frontend/src/components/OrientationWarningModal.jsx` — orientation warning behavior (success criterion #2).
- `frontend/src/components/SignupSuccessCard.jsx`
- `frontend/src/lib/api.js` — READ-ONLY.
- `frontend/src/App.jsx` — public route wiring.

### Prior phase context (design/decisions that carry forward)
- `.planning/phases/10-public-events-by-week-browse-signup-form/` — browse + signup flow baseline.
- `.planning/phases/11-magic-link-manage-my-signup-flow/` — magic link + manage page baseline.
- `.planning/phases/13-e2e-seed-playwright-coverage/` — existing Playwright scaffolding to extend for cross-browser.

### Tooling / skills to deploy
- `frontend-design` skill (plugin: `frontend-design@claude-code-plugins`) — page-level visual iteration.
- `gsd-ui-phase` skill — produces `UI-SPEC.md` for tokens and primitives.
- `axe-core/playwright` (npm: `@axe-core/playwright`) — CI a11y checks.

### External standards
- WCAG 2.1 AA — https://www.w3.org/WAI/WCAG21/quickref/ (AA level).
- iCalendar RFC 5545 — for `.ics` file format.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Tailwind v4 already configured — use utility classes, no new CSS-in-JS.
- `frontend/src/components/ui/` directory exists — drop shared primitives there.
- `StatusIcon.jsx`, `SignupSuccessCard.jsx`, `OrientationWarningModal.jsx` already in `components/` — reuse where relevant; consider promoting to `ui/` if they become primitives.
- Playwright already set up (Phase 13) — extend config to add webkit/firefox projects rather than starting fresh.
- vitest for component tests.

### Established Patterns
- Public pages live in `frontend/src/pages/public/*`.
- Data fetching pattern is via `frontend/src/lib/api.js` wrappers (read-only this phase).
- Route wiring in `frontend/src/App.jsx`.

### Integration Points
- `.ics` download: new util in `frontend/src/lib/calendar.js` (or similar), called from EventDetail and ConfirmSignup pages. No backend touch.
- Shared loading/empty/error primitives: `frontend/src/components/ui/{Skeleton,EmptyState,ErrorState}.jsx`.
- axe-core CI: new Playwright test spec `frontend/tests/a11y.spec.js` + config update to include webkit/firefox projects.

</code_context>

<deferred>
## Deferred Ideas

- **Week/keyword filter on /events** — considered for PART-13, not chosen. Candidate for a future milestone if audit surfaces strong need.
- **Saved / favorite events** — requires localStorage token plumbing; defer unless it becomes a pillar requirement.
- **Share event link (native share sheet)** — low value, skip.
- **UCSB / SciTrek brand repaint** (navy + gold, warmer palette) — explicitly out of scope here; would be its own design phase.
- **Search across events** — new capability, not polish; belongs in a later milestone.
- **Backend fixes surfaced during audit** — log as issues for a followup backend-fix phase; do NOT fix in this worktree.

</deferred>

---

*Phase: 15-participant-role-audit-ux-polish*
*Context gathered: 2026-04-15*
