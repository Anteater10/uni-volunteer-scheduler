# Uni Volunteer Scheduler

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

### Validated (from existing code — brownfield)

- ✓ FastAPI backend with routers for auth, users, portals, events, slots, signups, notifications, admin — existing
- ✓ SQLAlchemy models + Alembic migrations — existing
- ✓ Celery worker wiring + Docker compose + GitHub Actions CI — existing
- ✓ React frontend page skeletons (Login, Register, Portal, Events, EventDetail, MySignups, Notifications, Admin, Organizer, AuditLogs, Users, Portals) — existing
- ✓ `lib/api.js` client stub — existing
- ✓ `test_smoke.py` baseline — existing

### Active (hypotheses until shipped)

**Phase 0 — Backend completion + frontend integration**
- [ ] Every existing backend endpoint audited: working / stubbed / broken, with a punch list
- [ ] Validation + consistent error shapes across all routers
- [ ] Auth / magic-link hardening (token expiry, rate limits, replay protection)
- [ ] Celery + notifications reliability (idempotency, retries, dedup keys)
- [ ] Expanded test coverage beyond smoke tests (unit + integration)
- [ ] Every page wired to real backend via `lib/api.js`
- [ ] E2E flows: student register → confirm → browse → signup → see it in MySignups
- [ ] E2E flows: organizer login → dashboard → roster
- [ ] E2E flows: admin login → CRUD users/portals/events
- [ ] Playwright E2E suite in CI covering each critical flow

**Phase 1 — Mobile-first frontend pass**
- [ ] Tailwind migration (decided: yes, early)
- [ ] All pages designed at 375px first
- [ ] Touch targets ≥ 44px, thumb-zone bottom nav, card-based event list, sticky filter chips, skeleton loaders
- [ ] One-tap signup flow (tap slot → confirm modal → done)
- [ ] ADA / WCAG AA compliance baseline
- [ ] SEO baseline (meta tags, semantic HTML, sitemap)

**Phase 2 — Magic-link confirmation**
- [ ] On registration, send one-time confirmation link via Resend
- [ ] Clicking flips signup `registered → confirmed`
- [ ] Weak identity proof; catches email typos before they break prereq history

**Phase 3 — Check-in state machine + organizer roster**
- [ ] Signup lifecycle: `registered → confirmed → checked_in → attended | no_show`
- [ ] Organizer-driven roster with large tap targets, polling updates
- [ ] Self check-in via time-gated magic link + per-event venue code
- [ ] End-of-event unmarked-attendee prompt

**Phase 4 — Prereq / eligibility enforcement**
- [ ] Prereq SQL query against `checked_in` status
- [ ] **Soft warn** on registration (not hard block) — show "you haven't completed X" with link to next orientation
- [ ] Admin manual override for edge cases (email history broken)

**Phase 5 — Event template + LLM CSV import**
- [ ] `module_templates` table (permanent records: slug, name, prereqs, capacity, duration)
- [ ] Stage 1: single LLM extraction call (Pydantic + response_format) normalizing yearly CSV → canonical JSON
- [ ] Stage 2: deterministic importer with preview UI, atomic commit, rollback on error
- [ ] Few-shot examples from past years; log raw→normalized pairs for eval corpus
- [ ] Explicitly NOT an agent — single-shot extraction

**Phase 6 — Notifications polish**
- [ ] Registration confirmation email (with magic link)
- [ ] 24h reminder
- [ ] 1h reminder (optional)
- [ ] Cancellation email on slot removal/reschedule
- [ ] Celery idempotency + dedup keys

**Phase 7 — Admin dashboard polish**
- [ ] Manual eligibility override UI
- [ ] Bulk module-template CRUD
- [ ] CSV import UI surface (from Phase 5)
- [ ] Audit log viewer polish
- [ ] Analytics reporting (volunteer hours, attendance rates) — nice-to-have

**Phase 8 — Deployment to UCSB infrastructure**
- [ ] Production deploy target identified and configured
- [ ] Secrets management
- [ ] Monitoring / error reporting
- [ ] Handoff-ready docs (README, ops runbook, onboarding)

### Out of Scope

- **AI matching / recommendation engine** — no user profiles to match against
- **Full AI agent for event creation** — single LLM extraction call instead
- **Accounts, passwords, OAuth** — magic links only
- **Storing high school student data** — keeps FERPA/COPPA out of scope
- **Real-time WebSockets in v1** — 5s polling is sufficient
- **Multi-tenant / SaaS features** — single org (Sci Trek) only
- **i18n / Spanish support** — deferred

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
*Last updated: 2026-04-08 after initialization*
