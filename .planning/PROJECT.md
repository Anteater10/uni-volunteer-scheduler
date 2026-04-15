# Uni Volunteer Scheduler

## Current Milestone: v1.2-prod Production-ready by role

**Goal:** Take the v1.1 base from "works" to "production-ready and handoff-grade" by walking each user role end-to-end — participant, admin, organizer — auditing functionality, polishing UX, filling missing features, then proving the three roles work together. Set up a parallel collaboration workflow so Andy and Hung can both run Claude Code + GSD on the repo without stepping on each other.

**Target pillars (in order):**
1. **Collaboration setup** — git-worktree parallel workflow, role-owned branches, COLLABORATION.md updates, role assignments for Andy and Hung
2. **Participant role (logged-out)** — audit + UX polish + missing features for browse → signup → confirm → manage flows; 375px mobile-first; WCAG AA
3. **Admin role** — every admin sidebar page built/polished: Overview, Audit Log, Templates, Imports, Users, Exports; LLM CSV import (Phase 5.07 unblocked — Andy has the file); retire **Overrides** for real (Phase 12 cleanup left it lingering)
4. **Organizer role** — audit + UX polish + missing features for organizer login → dashboard → roster → check-in flows
5. **Cross-role integration** — admin creates event → organizer runs it → participant signs up → admin sees it in audit log; extend Playwright suite

**Locked decisions:**
1. Phase 8 deployment to UCSB infrastructure stays deferred — this milestone is feature-complete only
2. LLM CSV import (Phase 5.07) IS in scope, owned under the admin pillar — Andy holds the CSV file
3. Parallel collab uses git worktrees + role-owned branches (not separate workspaces, not strict phase handoffs)
4. The "Overrides" admin tab is fully retired — closes the Phase 12 loop
5. Phase numbering continues from v1.1 (which ended at 13) — v1.2-prod starts at Phase 14

**Not in this milestone:** UCSB production deployment (next milestone), any new product features beyond audit / polish / role-completeness gaps.

## What This Is

A mobile-first, loginless volunteer scheduler rebuilding SignupGenius for UCSB Sci Trek. UCSB students sign up to teach NGSS science modules to high schoolers; organizers run events and track attendance; admins manage everything. The product's thesis: **check-in is the source of truth**, **deterministic core with AI only where it earns its keep**, and **no accounts** — identity is just email + name + phone verified via magic link.

Brownfield: backend is production-shaped (FastAPI + SQLAlchemy + Alembic + Celery + Docker + CI) but incomplete. Frontend is page skeletons, largely not wired to the backend. The highest-leverage work is completing the backend audit + wiring every page end-to-end before layering new features.

## Core Value

**Volunteers can register for science-teaching slots on their phone in under 30 seconds, and organizers can run real events from their phone with accurate attendance that drives prereq eligibility.**

Everything else (CSV import, notifications, admin polish) serves that loop.

## Context

- **Users:** UCSB undergraduates (volunteers), Sci Trek organizers, Sci Trek admins. No high school student data stored (FERPA/COPPA out of scope).
- **Deployment:** University infrastructure (UCSB-hosted). Not yet deployed; deploy is in scope.
- **Timeline:** Usable before June 2026 (graduation handoff deadline).
- **Handoff:** Post-June 2026 maintainer is undecided — treat as open question; optimize for onboarding-friendly code and docs.
- **Scale:** Sci Trek-scale (tens to low hundreds of volunteers per cycle), not a SaaS product.
- **Compliance:** ADA / WCAG AA accessibility, SEO basics, California regulations (privacy-forward, data minimization).
- **Tech posture:** Deterministic where possible. LLM only for genuinely fuzzy work (yearly CSV normalization). No agents, no AI runtime features beyond that.

## Requirements

### Validated (shipped through v1.1)

**Brownfield baseline (pre-v1.0):**
- ✓ FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery + Redis stack
- ✓ Docker compose orchestration + GitHub Actions CI
- ✓ React 19 + Vite 7 + Tailwind v4 frontend baseline

**v1.0 shipped (phases 0–7, 2026-04-08):**
- ✓ Backend routers wired: auth, users, portals, events, slots, signups, notifications, admin
- ✓ Magic-link confirmation infrastructure
- ✓ Check-in state machine + organizer roster (polling-based)
- ✓ Event template scaffold (`module_templates` table)
- ✓ Notifications pipeline (registration, reminders, cancellation) via Celery + Resend
- ✓ Admin dashboard shell (audit log viewer, CCPA export, analytics)

**v1.1 shipped (phases 08–13, 2026-04-10):**
- ✓ Email-keyed `Volunteer` data model (no login/register for participants)
- ✓ Public signup API + magic-link email confirmation
- ✓ Public events-by-week browse page (structured quarter/year/week_number/module/school)
- ✓ Signup form with orientation-warning modal (DB-checked, soft warn only)
- ✓ Magic-link "manage my signup" page (view + per-row + cancel-all)
- ✓ Retirement of student Register/Login/MySignups pages, Phase 4 prereq enforcement, most of Phase 7 override UI (Overrides admin tab still lingering)
- ✓ Stage 0 latent bug cleanup (enum downgrades, Playwright seed data script)
- ✓ E2E coverage: 16/16 Playwright tests passing (public signup, orientation modal, organizer check-in, admin smoke)

### Active (v1.2-prod pillars — hypotheses until shipped)

**Pillar 1 — Collaboration setup**
- [ ] Git-worktree parallel workflow documented and tested
- [ ] Role-owned long-lived branches with merge cadence agreed
- [ ] COLLABORATION.md updated for v1.2-prod (role assignments Andy ↔ Hung)
- [ ] Conflict-avoidance strategy (file ownership, lock conventions)

**Pillar 2 — Participant role (logged-out flows)**
- [ ] End-to-end audit of browse → signup → confirm → manage at 375px
- [ ] UX polish: spacing, typography, loading/empty/error states, skeleton loaders, card design
- [ ] Missing-feature pass: anything a real student would expect that isn't there
- [ ] WCAG 2.1 AA verification on every public page (axe-core in CI if not already)
- [ ] SEO baseline polish (meta tags, semantic landmarks, sitemap)
- [ ] Cross-browser smoke: Safari mobile, Chrome mobile, Firefox

**Pillar 3 — Admin role (every sidebar tab functional + polished)**
- [ ] Overview: live stats (Users, Events, Slots, Signups, recent activity)
- [ ] Audit Log: filtered view with pagination, search, kind filter
- [ ] Templates: full CRUD on `module_templates` (slug, name, prereqs, capacity, duration)
- [ ] Imports: LLM CSV extraction (Phase 5.07) — Andy holds the CSV file; single-shot extraction → preview → atomic commit
- [ ] Users: organizer + admin user CRUD (no participant accounts)
- [ ] Exports: CCPA export polish + reporting exports (volunteer hours, attendance, no-shows)
- [ ] **Retire Overrides tab for real** — close the Phase 12 loop (delete UI + backend route)
- [ ] Admin shell UX polish (consistent layout, breadcrumbs, mobile-responsive)

**Pillar 4 — Organizer role**
- [ ] End-to-end audit of organizer login → dashboard → event roster → check-in
- [ ] Roster UX polish: large tap targets, polling indicator, conflict resolution
- [ ] Self check-in via time-gated magic link + per-event venue code (verify shipped or build)
- [ ] End-of-event prompt for unmarked attendees
- [ ] Missing-feature pass: anything organizers need at the venue that isn't there

**Pillar 5 — Cross-role integration**
- [ ] Cross-role E2E: admin creates event → organizer runs roster → participant signs up → admin sees in audit log
- [ ] Extend Playwright suite to cover the integration scenarios
- [ ] Run the full suite green in CI on every PR
- [ ] Manual smoke pass against the docker stack covering all three roles in one sitting

### Out of Scope

- **AI matching / recommendation engine** — no user profiles to match against
- **Full AI agent for event creation** — single LLM extraction call instead
- **Accounts, passwords, OAuth (for participants)** — magic links only; organizer/admin still authenticate
- **Storing high school student data** — keeps FERPA/COPPA out of scope
- **Real-time WebSockets in v1** — 5s polling is sufficient
- **Multi-tenant / SaaS features** — single org (Sci Trek) only
- **i18n / Spanish support** — deferred
- **UCSB production deployment** — deferred to next milestone after v1.2-prod (feature-completeness comes first; deploy is its own surface area)
- **New product features beyond audit/polish** in v1.2-prod — this milestone is finishing the existing roles, not adding new capabilities

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Brownfield, full backlog (#0–#8) | IDEAS.md is already a mature PRD; no need to narrow | Pending |
| Migrate to Tailwind early | User confirmed; pays off across all future frontend work | Pending |
| Soft warn on missing prereq | User preference; organizer discretion at venue | Pending |
| Deploy target = UCSB infrastructure | User constraint | Pending |
| Deadline = before June 2026 | Graduation handoff | Pending |
| ADA/WCAG AA + SEO + CA compliance = cross-cutting requirements | Legal/accessibility baseline | Pending |
| LLM CSV import is extraction, not agent | Single-shot, debuggable, reversible | Pending |
| Check-in is source of truth for prereqs | Cleaner than a separate attendance system | Pending |
| No accounts — magic link only | Loginless thesis; matches user base (one-cycle volunteers) | Pending |
| Handoff maintainer undecided | Treat as open question; optimize for onboarding-friendliness | Open |
| v1.0 drifted from no-accounts thesis → v1.1 realigns | Autonomous run introduced student accounts and complex prereq system not in original spec; easier to realign now than maintain two conflicting mental models | ✓ Shipped 2026-04-10 |
| Volunteers identified by email (Q1, Stage 1) | Lets orientation warning do a real DB check instead of a dumb modal | ✓ Shipped 2026-04-10 |
| One Signup row per slot (Q2, Stage 1) | Matches SignUpGenius; simpler capacity logic; cancel-all is just UI | ✓ Shipped 2026-04-10 |
| Event has structured quarter/year/week_number/module/school columns (Q3, Stage 1) | Week-view browse is one WHERE clause; preserves multi-day date range via start_date/end_date | ✓ Shipped 2026-04-10 |
| Slot has single capacity; no role on Signup (Q4, Stage 1) | Leads-vs-mentors is organizer-side knowledge, kept out of DB entirely | ✓ Shipped 2026-04-10 |
| v1.2-prod organized by user role, not feature phases | Walking each role end-to-end surfaces UX gaps that feature-phase slicing misses; also enables clean parallel work between Andy and Hung | Locked 2026-04-14 |
| v1.2-prod = feature-complete only, deploy deferred | Deploy is its own surface (UCSB infra, secrets, monitoring) and shouldn't gate the role-completeness work | Locked 2026-04-14 |
| LLM CSV import (Phase 5.07) unblocked — Andy holds the file | Earlier notes saying "blocked on CSV from Hung" are wrong; Andy has the file and CSV import ships under the v1.2-prod admin pillar | Locked 2026-04-14 |
| Overrides admin tab fully retired in v1.2-prod | Phase 12 left it lingering; no orientation-override workflow in the loginless model | Locked 2026-04-14 |
| Parallel collab via git worktrees + role-owned branches | Lets Andy and Hung run Claude Code + GSD on different role pillars without stepping on each other; merge to main between phases | Locked 2026-04-14 |

## Open Questions

- Does `signups.status` enum already include `checked_in` / `attended`? (audit in Phase 0)
- Does Sci Trek turn people away for missing prereqs, or soft-warn? → Decision: soft warn; confirm with Sci Trek
- Real sample of yearly CSV from Sci Trek (needed as few-shot for Phase 5)
- Are module descriptions/capacities stable year-over-year? (affects template versioning)
- Who owns the code post-June 2026?
- Is there a staging environment, or main → prod?
- Which UCSB infrastructure target exactly (VPS, campus Kubernetes, shared host)?

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 — v1.2-prod milestone opened (production-ready by role: participant → admin → organizer → integration)*
