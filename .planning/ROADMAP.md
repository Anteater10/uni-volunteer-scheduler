# Roadmap — v1.2-prod Production-ready by role

**Project:** UCSB Sci Trek volunteer scheduler
**Milestone:** v1.2-prod Production-ready by role
**Opened:** 2026-04-14
**Deadline:** before June 2026 (graduation handoff)
**Source of truth:** `.planning/REQUIREMENTS-v1.2-prod.md`
**Continues from:** v1.0 phases 00–07 (shipped 2026-04-08) and v1.1 phases 08–13 (shipped 2026-04-10). Both prior milestone phase dirs are preserved as reference, not archived.

## Goal

Take the v1.1 base from "works" to "production-ready and handoff-grade" by walking each user role end-to-end — participant, admin, organizer — auditing functionality, polishing UX, filling missing features, then proving the three roles work together. Set up a parallel collaboration workflow so Andy and Hung can both run Claude Code + GSD on the repo without stepping on each other.

Phase numbering continues from v1.1 (which ended at 13); v1.2-prod starts at Phase 14.

## Phases

- [ ] **Phase 14: Collaboration setup** — git-worktree workflow, role-owned long-lived branches, COLLABORATION.md + CLAUDE.md updates, file-ownership conventions, conflict playbook. Must ship before Andy and Hung run parallel pillars.
- [ ] **Phase 15: Participant role audit + UX polish** — end-to-end audit of public flows, fixes, WCAG AA + 375px verification, loading/empty/error states, cross-browser smoke, one new audit-surfaced feature.
- [ ] **Phase 16: Admin shell + retirement + Overview/Audit/Users/Exports** — retire `Overrides`, audit every admin route, polish admin shell, ship live Overview + filtered Audit Log + Users CRUD + Exports + UX polish across all admin pages.
- [ ] **Phase 17: Admin Templates CRUD** — full CRUD on `module_templates` (list, create, edit, delete/archive). Smaller scoped phase that can land independently between admin shell and the LLM import.
- [ ] **Phase 18: Admin LLM CSV Imports (Phase 5.07 unblocked)** — upload UI, single-shot LLM extraction → Pydantic, preview screen, atomic commit, eval-corpus logging, low-confidence flagging.
- [ ] **Phase 19: Organizer role audit + UX polish** — route normalization (`/organize` → `/organizer`), audit, fixes, roster polish, end-of-event prompts, WCAG AA + 375px verification, one new audit-surfaced feature.
- [ ] **Phase 20: Cross-role integration** — cross-role E2E (admin creates → organizer runs → participant signs up → admin sees in audit log), 4+ new Playwright scenarios, manual smoke checklist, doc sweep.

## Dependency Graph

```
                 ┌──────────────────────────────────────────────┐
                 │              14 (collab setup)               │
                 │  worktrees, role branches, CLAUDE.md update  │
                 └───────────────────────┬──────────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              ▼                          ▼                          
   ┌────────────────────┐     ┌──────────────────────┐       
   │ 15 (participant)   │     │ 16 (admin shell +    │   
   │  Andy or Hung      │     │  retire + overview/  │ 
   │  PART-01..14       │     │  audit/users/exports)│
   └─────────┬──────────┘     └──────────┬───────────┘
             │                           │           
             │                           ▼          
             │                ┌──────────────────────┐
             │                │ 17 (admin templates) │
             │                │      CRUD            │
             │                └──────────┬───────────┘
             │                           │
             │                           ▼
             │                ┌──────────────────────┐
             │                │ 18 (admin LLM CSV    │
             │                │  imports — 5.07)     │
             │                └──────────┬───────────┘
             │                           │
             │                           ▼
             │                ┌──────────────────────┐
             │                │ 19 (organizer audit  │
             │                │  + UX polish)        │
             │                └──────────┬───────────┘
             │                           │
             └──────────────┬────────────┘
                            ▼
                ┌────────────────────────┐
                │ 20 (cross-role         │
                │  integration + E2E)    │
                └────────────────────────┘
```

**Parallelism (the whole point of Phase 14):**
- Phase 15 (participant) and Phase 16 (admin shell) run in PARALLEL on different worktrees once Phase 14 ships. Andy and Hung pick a pillar each in COLLAB-02.
- Phases 17 and 18 are admin-pillar continuations and stay on the admin worktree; they are sequential because they share the admin shell from Phase 16.
- Phase 19 (organizer) starts after the admin pillar reaches a stable point (Phase 18 merged) because organizer and admin share event create/edit + magic-link infra (see Notes — sequencing risk).
- Phase 20 (integration) is strictly last; it requires every role pillar shipped.

## Phase Details

### Phase 14: Collaboration setup
**Goal:** Produce the git-worktree + role-branch contract that lets Andy and Hung each run Claude Code + GSD on a different role pillar without stepping on each other. No code changes to the app — this is the workflow ground truth.
**Depends on:** Nothing (first phase of v1.2-prod; starts from current `main`).
**Pillar:** 1 — Collaboration
**Requirements:** COLLAB-01, COLLAB-02, COLLAB-03, COLLAB-04, COLLAB-05, COLLAB-06, COLLAB-07
**Success Criteria** (what must be TRUE):
  1. `COLLABORATION.md` documents the worktree + role-branch workflow with concrete commands and Andy and Hung know which role pillar they own.
  2. Andy and Hung each have a working worktree on a long-lived role branch (`feature/v1.2-participant`, `feature/v1.2-admin`, `feature/v1.2-organizer`) and can each boot the docker stack + run tests independently.
  3. CLAUDE.md tells future Claude Code sessions which branch they should be on for any given pillar.
  4. The file-ownership table (which files require a PR vs which can be edited directly on a role branch) is written and agreed.
  5. Both devs run a one-day parallel test: each opens a Claude Code session on a different pillar branch, completes one trivial change, merges to main without conflict.
**Plans:** TBD
**UI hint:** no
**Touches:** `COLLABORATION.md`, `CLAUDE.md`, `.gitignore` (worktree dirs if needed), no app code.

### Phase 15: Participant role audit + UX polish
**Goal:** Walk every logged-out participant flow end-to-end on a fresh DB, fix everything broken, polish UX to production-grade, hit WCAG AA and 375px mobile-first across every public page, and add one audit-surfaced feature real students would expect.
**Depends on:** Phase 14 (worktree workflow must be in place).
**Pillar:** 2 — Participant
**Runs in parallel with:** Phase 16 (different worktree)
**Requirements:** PART-01, PART-02, PART-03, PART-04, PART-05, PART-06, PART-07, PART-08, PART-09, PART-10, PART-11, PART-12, PART-13, PART-14
**In-scope routes:** `/events`, `/events/:eventId`, `/signup/confirm`, `/signup/manage`, `/check-in/:signupId`, `/portals/:slug`
**Success Criteria** (what must be TRUE):
  1. A new student can open the app on their phone, browse this week's events, open an event, and sign up — without hitting a single bug, layout glitch, or accessibility violation.
  2. The orientation-warning modal fires correctly in the period-only no-prior-attendance case and is suppressed when the DB confirms prior attendance.
  3. The confirmation email arrives reliably and the magic link works on Safari iOS and Chrome Android; the manage-my-signup page lists everything with per-row + cancel-all controls.
  4. Self check-in via `/check-in/:signupId` works inside the time window and is clearly rejected outside it.
  5. axe-core in CI passes on every public page; every page passes a 375px audit (no horizontal scroll, ≥44px touch targets, thumb-zone CTAs); loading/empty/error states present everywhere; one new feature picked from PART-13 is shipped.
**Plans:** TBD
**UI hint:** yes
**Touches:** `frontend/src/pages/public/*`, `frontend/src/components/*`, `frontend/src/lib/api.js` (read-only — coordinate with admin worktree per file-ownership rules), public routes in `frontend/src/App.jsx`, axe-core CI config.

### Phase 16: Admin shell + retirement + Overview/Audit/Users/Exports
**Goal:** Bring the admin shell to production grade — retire the `Overrides` lingering tab, audit every admin route, ship the live Overview + filtered Audit Log + Users CRUD + Exports surfaces, and hold WCAG AA + 375px-or-graceful-mobile across every admin page. Templates and LLM Imports are intentionally split into Phase 17 and 18.
**Depends on:** Phase 14 (worktree workflow).
**Pillar:** 3 — Admin (part A)
**Runs in parallel with:** Phase 15 (different worktree)
**Requirements:** ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07, ADMIN-18, ADMIN-19, ADMIN-20, ADMIN-21, ADMIN-22, ADMIN-23, ADMIN-24, ADMIN-25, ADMIN-26, ADMIN-27
**In-scope routes:** `/admin`, `/admin/events/:eventId`, `/admin/users`, `/admin/portals`, `/admin/audit-logs`, `/admin/exports`
**Success Criteria** (what must be TRUE):
  1. The `Overrides` admin sidebar item, its (any) backend route, and any test references are gone — closing the v1.1 Phase 12 retirement loop. `git grep` returns no live references.
  2. Admin shell layout is consistent across every section (sidebar, breadcrumbs, mobile-responsive collapse), with no mid-stream layout shift; the audit doc `ADMIN-AUDIT.md` lists every route's status.
  3. The Overview page shows live stats (Users, Events, Slots, Signups, Confirmed signups) sourced from the live DB plus a Recent Activity feed of the last N audit entries with clear actor + timestamp formatting.
  4. The Audit Log page paginates every audit entry and supports filters by kind, actor, date range, and free-text search; the Users page supports list/create/edit/deactivate for organizer + admin users (no participant accounts).
  5. Admin can export volunteer hours + attendance + no-show CSVs and the CCPA export flow is polished and tested; every admin page meets WCAG AA, passes a 375px audit (or has a graceful "desktop-only" mobile message), and shows loading/empty/error states.
**Plans:** TBD
**UI hint:** yes
**Touches:** `frontend/src/pages/admin/*`, `frontend/src/components/admin/*`, `frontend/src/lib/api.js` (write — coordinate with participant worktree per ownership rules), `backend/app/routers/admin.py`, `backend/app/routers/users.py`, audit log services, CCPA export router.

### Phase 17: Admin Templates CRUD
**Goal:** Ship full CRUD on `module_templates` from the admin Templates page — list, create, edit, delete/archive — with form validation, optimistic UI, and the Phase 16 polish standards.
**Depends on:** Phase 16 (admin shell + layout patterns).
**Pillar:** 3 — Admin (part B)
**Requirements:** ADMIN-08, ADMIN-09, ADMIN-10, ADMIN-11
**In-scope routes:** `/admin/templates`
**Success Criteria** (what must be TRUE):
  1. Admin lands on `/admin/templates` and sees every module template with slug, name, capacity, and duration in a sortable list.
  2. Admin can create a new module template via a form with client-side validation; the row appears in the list immediately.
  3. Admin can edit an existing module template and see the change reflected in the list and in any downstream consumers.
  4. Admin can delete or soft-archive a module template; the row disappears from the active list and is preserved if soft-archived.
  5. The Templates page meets the Phase 16 standards (WCAG AA, 375px audit or graceful desktop-only message, loading/empty/error states).
**Plans:** TBD
**UI hint:** yes
**Touches:** `frontend/src/pages/admin/AdminTemplatesPage.jsx`, `backend/app/routers/templates.py` (or admin.py), `backend/app/models/module_template.py`, `backend/app/schemas/module_template.py`.

### Phase 18: Admin LLM CSV Imports (Phase 5.07 unblocked)
**Goal:** Finally unblock and ship the LLM CSV extraction surface — Andy holds the Sci Trek CSV. Single-shot LLM call (Haiku default), structured Pydantic output, preview screen, atomic commit, eval-corpus logging, low-confidence flagging. This is the biggest net-new admin feature in v1.2-prod.
**Depends on:** Phase 16 (admin shell), Phase 17 (templates exist before events can be imported against them).
**Pillar:** 3 — Admin (part C)
**Requirements:** ADMIN-12, ADMIN-13, ADMIN-14, ADMIN-15, ADMIN-16, ADMIN-17
**In-scope routes:** `/admin/imports`
**Success Criteria** (what must be TRUE):
  1. Admin uploads a Sci Trek quarterly CSV file via the Imports page and sees a clear progress indicator while the backend processes it.
  2. The backend single-shot LLM extraction (Haiku default, structured Pydantic output) returns canonical normalized JSON; every raw-CSV → normalized-JSON pair is logged for the eval corpus.
  3. The Imports page shows a preview of the parsed events ("N events will be created, M skipped") with a confirm/cancel choice; low-confidence rows are flagged for manual review rather than silently guessed.
  4. Confirming the import is atomic — all rows commit or none do; any error during commit triggers a full rollback and a clear error message.
  5. A real Sci Trek quarterly CSV (the one Andy holds) imports cleanly end-to-end against the docker stack and the resulting events are visible in the public events-by-week browse.
**Plans:** TBD
**UI hint:** yes
**Touches:** `frontend/src/pages/admin/AdminImportsPage.jsx`, new `backend/app/services/llm_import.py`, new `backend/app/routers/imports.py`, Pydantic schemas for canonical event JSON, eval-corpus storage, `module_templates` lookup.

### Phase 19: Organizer role audit + UX polish
**Goal:** Walk every organizer flow end-to-end (login → dashboard → roster → check-in), normalize the `/organize` → `/organizer` typo from v1.0, fix everything broken, polish the roster for venue use on a phone, ship end-of-event prompts, hit WCAG AA + 375px (organizers run events from their phone, this is critical), and add one audit-surfaced feature.
**Depends on:** Phase 18 (admin pillar reaches a stable point — admin and organizer share event create/edit + magic-link infra; admin lands first to keep the shared surface stable).
**Pillar:** 4 — Organizer
**Requirements:** ORG-01, ORG-02, ORG-03, ORG-04, ORG-05, ORG-06, ORG-07, ORG-08, ORG-09, ORG-10, ORG-11, ORG-12, ORG-13, ORG-14
**In-scope routes:** `/login`, `/organizer`, `/organizer/events/:eventId`, `/organizer/events/:eventId/roster` (post-rename)
**Success Criteria** (what must be TRUE):
  1. The organizer route paths are normalized (`/organize` → `/organizer`), every link and test is updated, and `ORG-AUDIT.md` documents what was broken before and after.
  2. An organizer logs in on their phone, lands on a dashboard listing their assigned events, opens an event, and sees the full slot list with current signup counts.
  3. The roster page has large tap-friendly check-in toggles, polls every 5s with a clear polling indicator, supports `checked_in → attended` and `→ no_show` with optimistic UI, and resolves first-write-wins conflicts between organizer and self check-in.
  4. The end-of-event prompt fires for unmarked attendees ("You have N unmarked — mark them now?"), and an organizer can create or edit an event from the organizer surface (or via admin if that ownership decision lands there).
  5. Every organizer page meets WCAG AA, passes a 375px audit, has loading/empty/error states, and one new audit-surfaced feature from ORG-14 ships.
**Plans:** TBD
**UI hint:** yes
**Touches:** `frontend/src/pages/organizer/*`, `frontend/src/App.jsx` (route rename), `frontend/src/lib/api.js`, `backend/app/routers/organizer.py`, `backend/app/routers/events.py`, magic-link self check-in code.

### Phase 20: Cross-role integration
**Goal:** Prove the three roles work together end-to-end with new Playwright scenarios + a manual smoke checklist + a final doc sweep. This is the v1.2-prod acceptance gate — if Phase 20 ships green, the milestone is done.
**Depends on:** Phase 15, Phase 18, Phase 19 (every pillar must be shipped before integration tests can exercise them).
**Pillar:** 5 — Integration
**Requirements:** INTEG-01, INTEG-02, INTEG-03, INTEG-04, INTEG-05, INTEG-06
**Success Criteria** (what must be TRUE):
  1. A cross-role Playwright scenario runs the full loop in CI: admin creates an event → organizer manages the roster → participant signs up via the public flow → admin sees both the signup and the resulting check-in in the audit log.
  2. The Playwright suite has at least 4 new cross-role scenarios on top of the 16 from v1.1, and the full suite is green in CI on every PR.
  3. A manual smoke pass against the docker stack drives all three roles in one sitting following `docs/smoke-checklist.md`, with no manual DB nudges and no failed requests.
  4. Any cross-role bugs surfaced during integration are fixed (or filed as explicit out-of-scope follow-ups) before sign-off.
  5. PROJECT.md, README, CLAUDE.md, and in-app copy reflect the v1.2-prod state — no stale "yearly CSV", "student account", or `/organize` references remain.
**Plans:** TBD
**UI hint:** no
**Touches:** `frontend/tests/e2e/*` (new spec files), `docs/smoke-checklist.md` (new), `README.md`, `PROJECT.md`, `CLAUDE.md`, in-app copy sweep.

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 14. Collaboration setup | 0/? | Not started | - |
| 15. Participant role audit + UX polish | 0/? | Not started | - |
| 16. Admin shell + retirement + Overview/Audit/Users/Exports | 0/? | Not started | - |
| 17. Admin Templates CRUD | 0/? | Not started | - |
| 18. Admin LLM CSV Imports (Phase 5.07 unblocked) | 0/? | Not started | - |
| 19. Organizer role audit + UX polish | 0/? | Not started | - |
| 20. Cross-role integration | 0/? | Not started | - |

## Coverage

All 68 v1.2-prod requirements are mapped to exactly one phase:

| Pillar | Requirements | Count | Phase(s) |
|---|---|---:|---|
| 1. Collaboration | COLLAB-01..07 | 7 | 14 |
| 2. Participant | PART-01..14 | 14 | 15 |
| 3a. Admin shell + retirement | ADMIN-01, 02, 03 | 3 | 16 |
| 3b. Admin Overview | ADMIN-04, 05 | 2 | 16 |
| 3c. Admin Audit Log | ADMIN-06, 07 | 2 | 16 |
| 3d. Admin Templates | ADMIN-08, 09, 10, 11 | 4 | 17 |
| 3e. Admin LLM Imports | ADMIN-12, 13, 14, 15, 16, 17 | 6 | 18 |
| 3f. Admin Users | ADMIN-18, 19, 20, 21 | 4 | 16 |
| 3g. Admin Exports | ADMIN-22, 23, 24 | 3 | 16 |
| 3h. Admin UX polish | ADMIN-25, 26, 27 | 3 | 16 |
| 4. Organizer | ORG-01..14 | 14 | 19 |
| 5. Integration | INTEG-01..06 | 6 | 20 |
| **Total** |  | **68** |  |

No orphaned requirements. No duplicates.

## Out of Scope (explicit)

- **UCSB production deployment** — Phase 8 stays deferred; v1.2-prod is feature-completeness only. Deploy is its own milestone after v1.2-prod.
- **Participant accounts / login / OAuth** — locked out from v1.1.
- **AI matching, recommendation engine, agentic event creation** — locked out from v1.0.
- **Real-time WebSockets** — 5s polling is sufficient.
- **i18n / Spanish support** — deferred.
- **Multi-tenant / SaaS features** — single Sci Trek org only.
- **Net-new product capabilities** beyond what's listed in PART-13 / ORG-14 — this milestone is audit + polish + targeted fills, not a v2 feature push.

## Notes

- **v1.0 + v1.1 phase dirs preserved as reference, not archived.** `.planning/phases/00-*` through `.planning/phases/13-*` stay on disk so v1.2-prod work can grep for prior decisions, schemas, and patterns. Same convention v1.1 used for v1.0.
- **Parallelism is the whole point of Phase 14.** Phases 15 and 16 are designed to run on different worktrees by Andy and Hung. The COLLAB-03 file-ownership table must call out `frontend/src/lib/api.js`, `frontend/src/App.jsx` (routes), and any shared component files as PR-only edits to keep the two worktrees from colliding.
- **Sequencing risk: admin and organizer share code surface.** Both pillars touch event create/edit and magic-link infrastructure (admin manages events; organizer can edit their own; self check-in via magic link spans both). To avoid two worktrees fighting over the same files, organizer (Phase 19) waits until admin has reached a stable point at the end of Phase 18. This is a deliberate sequencing choice — the alternative is more merge conflicts than two devs can absorb in a 6-week window.
- **Phase 18 (LLM CSV import) is the milestone's biggest net-new feature.** Everything else is audit + polish + targeted fills. If Phase 18 slips, plan a focused recovery rather than spreading the LLM work across other phases.
- **Cross-cutting standards** (mobile-first 375px, WCAG AA, docker-network test pattern, atomic commits, PR per phase, loginless for participants) apply to every phase per `REQUIREMENTS-v1.2-prod.md` "Cross-Cutting" section. The success criteria of each phase reference these — they are non-negotiable, not optional polish.
- **PART-13 and ORG-14 deliberately defer their scope to discuss-phase.** "One new audit-surfaced feature" is a known-unknown; the candidate list (e.g. add-to-calendar, roster CSV export, broadcast message) is locked when planning the phase, not when writing the roadmap.
- **`/gsd-plan-phase 14` is the next action.** Phase 14 ships first because everything else depends on the worktree workflow being defined and tested.

---
*Roadmap created: 2026-04-14 — v1.2-prod milestone opened*
*Next: `/gsd-plan-phase 14` to decompose the collaboration setup phase into executable plans*
