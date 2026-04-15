# Requirements — v1.2-prod (Production-ready by role)

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.2-prod
**Opened:** 2026-04-14
**Deadline:** before June 2026 (graduation handoff)
**Source of truth for the v1.2-prod ROADMAP**

## Goal

Take the v1.1 base from "works" to "production-ready and handoff-grade" by walking each user role end-to-end — participant, admin, organizer — auditing functionality, polishing UX, filling missing features, then proving the three roles work together. Set up a parallel collaboration workflow so Andy and Hung can both run Claude Code + GSD on the repo without stepping on each other.

## Cross-Cutting (applies to every pillar)

These are NOT requirements themselves but standards every requirement must meet:

- **Mobile-first:** Every UI verified at 375px; touch targets ≥ 44px; thumb-zone navigation
- **Accessibility:** WCAG 2.1 AA on every shipped surface (keyboard nav, focus states, semantic HTML, contrast, screen-reader labels)
- **No new product capabilities** beyond what's listed here — this milestone is finishing what exists, not adding new things
- **Docker-network test pattern** (CLAUDE.md) for every backend test run
- **Atomic commits** per fix; PR per phase; merge to `main` between pillars
- **Loginless for participants** is a hard rule — any "missing feature" that would require participant accounts is out of scope

---

## Pillar 1 — Collaboration Setup

**Why first:** Andy and Hung both run Claude Code + GSD on the same repo. Without an explicit workflow they will collide. This pillar produces the contract before either pillar 2/3/4 starts.

- [ ] **COLLAB-01**: Document the git-worktree workflow in `COLLABORATION.md` (one worktree per role pillar; long-lived `feature/v1.2-participant`, `feature/v1.2-admin`, `feature/v1.2-organizer` branches; merge to `main` between phases)
- [ ] **COLLAB-02**: Assign role pillars to Andy and Hung (who owns participant, who owns admin, who owns organizer; integration is shared)
- [ ] **COLLAB-03**: Define file-ownership conventions to prevent merge conflicts (e.g. `lib/api.js` is shared and edited only via PR, not direct push to a role branch)
- [ ] **COLLAB-04**: Document the daily sync cadence and the rules for when to merge a role branch back to `main`
- [ ] **COLLAB-05**: Set up a worktree for each role pillar against the current `main` and verify both Andy and Hung can run their stack independently
- [ ] **COLLAB-06**: Update CLAUDE.md so future Claude Code sessions know which branch they should be working on for each pillar
- [ ] **COLLAB-07**: Document conflict-resolution playbook (who breaks ties, how to rebase a role branch on main when shared files change)

**Acceptance:** Andy and Hung can each open a Claude Code session on a different role pillar and work without blocking each other for at least one full day.

---

## Pillar 2 — Participant Role (logged-out flows)

**In-scope routes:** `/events`, `/events/:eventId`, `/signup/confirm`, `/signup/manage`, `/check-in/:signupId`, `/portals/:slug`

- [ ] **PART-01**: Audit every public flow end-to-end against a fresh dev DB; document what works, what's broken, and what's missing in `PART-AUDIT.md`
- [ ] **PART-02**: Fix every broken or stubbed participant flow surfaced by PART-01
- [ ] **PART-03**: User can browse events by week with clear date/quarter context, no spinners stuck on screen, no console errors
- [ ] **PART-04**: User can open an event detail page and see all slots grouped by `slot_type` (orientation / period) with capacity + filled counts
- [ ] **PART-05**: Signup form has client-side validation with clear error messages (name, email, phone — E.164)
- [ ] **PART-06**: Orientation-warning modal fires correctly in the period-only / no-prior-attendance case and is suppressed when DB confirms prior attendance
- [ ] **PART-07**: Confirmation email arrives reliably and the magic link works on mobile (Safari iOS, Chrome Android)
- [ ] **PART-08**: Manage-my-signup page shows all signups for the volunteer + event, with per-row cancel and a cancel-all button
- [ ] **PART-09**: Self check-in via magic link (`/check-in/:signupId`) works inside the time window and is rejected outside it with a clear error
- [ ] **PART-10**: Every public page meets WCAG 2.1 AA (axe-core in CI passing)
- [ ] **PART-11**: 375px mobile-first verification on every public page (no horizontal scroll, all touch targets ≥ 44px, thumb-zone CTAs)
- [ ] **PART-12**: Loading + empty + error states present and styled on every public page
- [ ] **PART-13**: Add at least one new participant-side feature surfaced by the audit that real students would expect (e.g. "add to calendar", filtered views, search) — to be picked during the discuss-phase step
- [ ] **PART-14**: Cross-browser smoke pass on Safari mobile, Chrome mobile, Firefox desktop

**Acceptance:** A new student can open the app on their phone, find this week's events, sign up, confirm, and manage their signups — without hitting a single bug, layout glitch, or accessibility violation.

---

## Pillar 3 — Admin Role (every sidebar tab functional + polished)

**In-scope routes:** `/admin`, `/admin/events/:eventId`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/templates`, `/admin/imports`, `/admin/exports`

**Note on existing state:** AdminLayout has 7 sidebar items but only 6 routes registered in App.jsx. `Overrides` is a dead nav link with no route — removing it closes the v1.1 Phase 12 retirement loop.

### 3a. Admin shell + retirement
- [ ] **ADMIN-01**: Retire the `Overrides` admin sidebar nav item, the corresponding backend route (if any still exists), and any test references — closes the v1.1 Phase 12 loop
- [ ] **ADMIN-02**: Audit every admin route end-to-end and document what works, what's broken, and what's missing in `ADMIN-AUDIT.md`
- [ ] **ADMIN-03**: Admin shell layout is consistent across every section (sidebar, breadcrumbs, mobile-responsive collapse), no mid-stream layout shift

### 3b. Overview
- [ ] **ADMIN-04**: Overview page shows live stats (Users, Events, Slots, Signups, Confirmed signups) sourced from the live DB
- [ ] **ADMIN-05**: Recent Activity feed shows the last N audit-log entries with clear actor + timestamp formatting

### 3c. Audit Log
- [ ] **ADMIN-06**: Audit Log page lists every audit entry with pagination
- [ ] **ADMIN-07**: Audit Log filters by kind, actor, date range, free-text search

### 3d. Templates (`module_templates`)
- [ ] **ADMIN-08**: Admin can list every module template (slug, name, capacity, duration)
- [ ] **ADMIN-09**: Admin can create a new module template via form
- [ ] **ADMIN-10**: Admin can edit a module template
- [ ] **ADMIN-11**: Admin can delete (or soft-archive) a module template

### 3e. Imports (LLM CSV — Phase 5.07, finally unblocked)
- [ ] **ADMIN-12**: Admin can upload a Sci Trek quarterly CSV file via the Imports page
- [ ] **ADMIN-13**: Backend single-shot LLM extraction normalizes the CSV → canonical JSON (Pydantic + structured output, Haiku default)
- [ ] **ADMIN-14**: Imports page shows a preview of the parsed events ("N events will be created, M skipped") with a confirm/cancel choice
- [ ] **ADMIN-15**: Confirming the import is atomic: all rows commit or none do; rollback on any error
- [ ] **ADMIN-16**: Every raw-CSV → normalized-JSON pair is logged for the eval corpus
- [ ] **ADMIN-17**: Low-confidence rows are flagged for manual review rather than silently guessed

### 3f. Users (organizers + admins only — no participant accounts)
- [ ] **ADMIN-18**: Admin can list every user (organizer / admin)
- [ ] **ADMIN-19**: Admin can create a new organizer or admin user
- [ ] **ADMIN-20**: Admin can edit a user (name, role)
- [ ] **ADMIN-21**: Admin can deactivate a user

### 3g. Exports
- [ ] **ADMIN-22**: Admin can export volunteer hours per quarter as CSV
- [ ] **ADMIN-23**: Admin can export attendance + no-show rates as CSV
- [ ] **ADMIN-24**: CCPA data-export flow polished and tested

### 3h. UX polish
- [ ] **ADMIN-25**: Every admin page meets WCAG 2.1 AA
- [ ] **ADMIN-26**: Every admin page passes a 375px mobile-first audit (or has an explicit "desktop-only" pattern with a graceful mobile message)
- [ ] **ADMIN-27**: Loading / empty / error states present on every admin page

**Acceptance:** A SciTrek admin can run a full quarter cycle from the admin dashboard alone — import templates from CSV, see live stats, drill into the audit log, manage users, and export reports — with zero bugs or layout glitches.

---

## Pillar 4 — Organizer Role

**In-scope routes:** `/login`, `/organizer`, `/organizer/events/:eventId`, `/organize/events/:eventId/roster`

**Note on existing state:** the roster route uses the path `/organize/...` (not `/organizer/...`) — a typo from v1.0 that should be normalized.

- [ ] **ORG-01**: Audit every organizer flow end-to-end and document what works, what's broken, and what's missing in `ORG-AUDIT.md`
- [ ] **ORG-02**: Normalize the organizer route paths (`/organize` → `/organizer`) and update every link
- [ ] **ORG-03**: Organizer can log in and land on a dashboard listing their assigned events
- [ ] **ORG-04**: Organizer can open an event and see its full slot list with current signup counts
- [ ] **ORG-05**: Organizer roster page shows every confirmed signup with large, tap-friendly check-in toggles
- [ ] **ORG-06**: Organizer can mark a signup `checked_in → attended` and `→ no_show`, with optimistic UI
- [ ] **ORG-07**: Roster polls for live updates (5s) and shows a clear polling indicator
- [ ] **ORG-08**: First-write-wins conflict resolution between organizer and self check-in
- [ ] **ORG-09**: End-of-event prompt for unmarked attendees ("You have N unmarked — mark them now?")
- [ ] **ORG-10**: Organizer can create or edit an event (if not already supported via admin pillar)
- [ ] **ORG-11**: Every organizer page meets WCAG 2.1 AA
- [ ] **ORG-12**: Every organizer page passes a 375px mobile-first audit (organizers run events from their phone — this is critical)
- [ ] **ORG-13**: Loading / empty / error states present on every organizer page
- [ ] **ORG-14**: Add at least one missing organizer-side feature surfaced by the audit (e.g. roster CSV export, last-minute slot reassignment, broadcast a message to confirmed signups)

**Acceptance:** A SciTrek organizer can land at a school venue, log in on their phone, run the entire roster, and leave with accurate attendance data — without needing a laptop, without bugs, without layout glitches.

---

## Pillar 5 — Cross-Role Integration

- [ ] **INTEG-01**: Cross-role E2E test: admin creates an event → organizer manages the roster → participant signs up → admin sees both the signup and the check-in in the audit log
- [ ] **INTEG-02**: Extend the Playwright suite (currently 16 tests) with at least 4 cross-role scenarios
- [ ] **INTEG-03**: Full Playwright suite green in CI on every PR
- [ ] **INTEG-04**: Manual smoke pass against the docker stack covering all three roles in one sitting (script: `docs/smoke-checklist.md`)
- [ ] **INTEG-05**: Document any cross-role bugs surfaced and fix them
- [ ] **INTEG-06**: Final PROJECT.md / README sweep: every doc reflects the v1.2-prod state, no stale "yearly CSV" or "student account" copy remains

**Acceptance:** Three browsers open side-by-side — admin, organizer, participant — driving the same event from creation to attendance, no manual DB nudges, no failed requests.

---

## Out of Scope (explicit)

- **UCSB production deployment** — Phase 8 stays deferred; v1.2-prod is feature-completeness only. Deploy is its own milestone.
- **Participant accounts / login / OAuth** — magic links only; this is locked from v1.1
- **AI matching, recommendation engine, agentic event creation** — locked from v1.0
- **Real-time WebSockets** — 5s polling is sufficient
- **i18n / Spanish** — deferred
- **Multi-tenant / SaaS features** — single Sci Trek org only
- **Net-new product capabilities beyond what's listed in PART-13 / ORG-14** — this milestone is audit + polish + targeted fills, not a v2 feature push

## Open Questions (to resolve during planning)

- Which role pillar does Andy own, which does Hung own? (resolved in COLLAB-02)
- What's the one missing participant-side feature (PART-13)? (resolved in discuss-phase)
- What's the one missing organizer-side feature (ORG-14)? (resolved in discuss-phase)
- Does Sci Trek need analytics/dashboards beyond the CSV exports in ADMIN-22 / ADMIN-23? (defer to admin pillar discuss-phase)
- Where does event create/edit live — admin pillar, organizer pillar, or both? (likely both: admin can do it, organizer can edit their own events) — resolve before Pillar 3 vs Pillar 4 conflict
- LLM CSV import: does Andy want it as one phase or split (UI plumbing → LLM extraction → preview/commit)?

## Traceability

Every requirement is mapped to exactly one phase. 68/68 requirements covered. No orphans.

| REQ-ID | Phase | Pillar |
|---|---|---|
| COLLAB-01 | 14 | 1 |
| COLLAB-02 | 14 | 1 |
| COLLAB-03 | 14 | 1 |
| COLLAB-04 | 14 | 1 |
| COLLAB-05 | 14 | 1 |
| COLLAB-06 | 14 | 1 |
| COLLAB-07 | 14 | 1 |
| PART-01 | 15 | 2 |
| PART-02 | 15 | 2 |
| PART-03 | 15 | 2 |
| PART-04 | 15 | 2 |
| PART-05 | 15 | 2 |
| PART-06 | 15 | 2 |
| PART-07 | 15 | 2 |
| PART-08 | 15 | 2 |
| PART-09 | 15 | 2 |
| PART-10 | 15 | 2 |
| PART-11 | 15 | 2 |
| PART-12 | 15 | 2 |
| PART-13 | 15 | 2 |
| PART-14 | 15 | 2 |
| ADMIN-01 | 16 | 3 |
| ADMIN-02 | 16 | 3 |
| ADMIN-03 | 16 | 3 |
| ADMIN-04 | 16 | 3 |
| ADMIN-05 | 16 | 3 |
| ADMIN-06 | 16 | 3 |
| ADMIN-07 | 16 | 3 |
| ADMIN-08 | 17 | 3 |
| ADMIN-09 | 17 | 3 |
| ADMIN-10 | 17 | 3 |
| ADMIN-11 | 17 | 3 |
| ADMIN-12 | 18 | 3 |
| ADMIN-13 | 18 | 3 |
| ADMIN-14 | 18 | 3 |
| ADMIN-15 | 18 | 3 |
| ADMIN-16 | 18 | 3 |
| ADMIN-17 | 18 | 3 |
| ADMIN-18 | 16 | 3 |
| ADMIN-19 | 16 | 3 |
| ADMIN-20 | 16 | 3 |
| ADMIN-21 | 16 | 3 |
| ADMIN-22 | 16 | 3 |
| ADMIN-23 | 16 | 3 |
| ADMIN-24 | 16 | 3 |
| ADMIN-25 | 16 | 3 |
| ADMIN-26 | 16 | 3 |
| ADMIN-27 | 16 | 3 |
| ORG-01 | 19 | 4 |
| ORG-02 | 19 | 4 |
| ORG-03 | 19 | 4 |
| ORG-04 | 19 | 4 |
| ORG-05 | 19 | 4 |
| ORG-06 | 19 | 4 |
| ORG-07 | 19 | 4 |
| ORG-08 | 19 | 4 |
| ORG-09 | 19 | 4 |
| ORG-10 | 19 | 4 |
| ORG-11 | 19 | 4 |
| ORG-12 | 19 | 4 |
| ORG-13 | 19 | 4 |
| ORG-14 | 19 | 4 |
| INTEG-01 | 20 | 5 |
| INTEG-02 | 20 | 5 |
| INTEG-03 | 20 | 5 |
| INTEG-04 | 20 | 5 |
| INTEG-05 | 20 | 5 |
| INTEG-06 | 20 | 5 |

**Counts by phase:**

| Phase | Pillar | Reqs | Count |
|---|---|---|---:|
| 14 | 1 — Collaboration | COLLAB-01..07 | 7 |
| 15 | 2 — Participant | PART-01..14 | 14 |
| 16 | 3 — Admin shell + Overview/Audit/Users/Exports + UX polish | ADMIN-01..07, 18..27 | 17 |
| 17 | 3 — Admin Templates CRUD | ADMIN-08..11 | 4 |
| 18 | 3 — Admin LLM CSV Imports | ADMIN-12..17 | 6 |
| 19 | 4 — Organizer | ORG-01..14 | 14 |
| 20 | 5 — Integration | INTEG-01..06 | 6 |
| **Total** | | | **68** |

---
*Created: 2026-04-14*
*Traceability filled by roadmapper: 2026-04-14*
