# Roadmap — Uni Volunteer Scheduler

**Project:** UCSB Sci Trek volunteer scheduler
**Deadline:** Before June 2026 (graduation handoff)
**Granularity:** Standard (5–8 phases)
**Phases:** 9 (Phase 0 through Phase 8)
**Coverage:** 9/9 phases derived from REQUIREMENTS.md

---

## Phases

- [ ] **Phase 0: Backend Completion + Frontend Integration** — Audit, wire, and test every endpoint and page; close the cancel/withdraw gap
- [ ] **Phase 1: Mobile-First Frontend Pass + Tailwind Migration** — Migrate to Tailwind v4; redesign all pages at 375px; WCAG AA baseline
- [ ] **Phase 2: Magic-Link Confirmation** — Email ownership proof via one-time link; `registered → confirmed` signup transition
- [ ] **Phase 3: Check-In State Machine + Organizer Roster** — Full signup lifecycle; organizer tap-to-mark; self check-in with venue code
- [ ] **Phase 4: Prereq / Eligibility Enforcement** — Soft-warn on registration; prereq query against check-in data; admin override
- [ ] **Phase 5: Event Template System + LLM CSV Import** — `module_templates` table; two-stage LLM extraction + deterministic commit
- [ ] **Phase 6: Notifications Polish** — Production-reliable email pipeline; idempotency guards; full Resend integration
- [ ] **Phase 7: Admin Dashboard Polish** — Override UI; bulk template CRUD; CSV import surface; audit log viewer; CCPA review
- [ ] **Phase 8: Deployment to UCSB Infrastructure** — Production deploy; secrets; monitoring; handoff docs

---

## Phase Overview Table

| Phase | Name | Goal | Key Requirements | Depends On | Parallel Opportunity |
|-------|------|------|-----------------|------------|----------------------|
| 0 | Backend Completion + Frontend Integration | Every endpoint working and wired to a real page | Backend audit, validation, auth hardening, Celery reliability, all E2E flows, cancel/withdraw | Nothing (start here) | None — strict prerequisite |
| 1 | Mobile-First Frontend Pass + Tailwind Migration | All pages usable on a 375px phone with WCAG AA color palette | Tailwind migration, 375px redesign, touch targets, one-tap signup, SEO, axe-core CI | Phase 0 | None — unblocks all frontend work |
| 2 | Magic-Link Confirmation | Email ownership proved before any check-in data is recorded | MagicLinkToken table, registered→confirmed transition, Resend, TTL, single-use | Phase 1 | None — strict predecessor to Phase 3 |
| 3 | Check-In State Machine + Organizer Roster | Organizer can run a real event and mark attendance on a phone | Status enum migration, roster UI, self check-in, venue code, end-of-event prompt | Phase 2 | Phase 8 infra prep can start |
| 4 | Prereq / Eligibility Enforcement | Registration page shows missing-prereq soft warning with next-slot link | Prereq SQL query, soft-warn modal, admin override, module timeline in MySignups | Phase 3 | Phase 5 (module_templates) can start; Phase 6 can start |
| 5 | Event Template System + LLM CSV Import | Organizer can import a yearly CSV and review/commit events in one flow | module_templates table+seed, Stage 1 LLM extraction, Stage 2 deterministic importer, preview UI | Phase 4 (module_templates FK), Phase 0 (working API) | Parallel with Phase 6 and Phase 7 after Phase 4 |
| 6 | Notifications Polish | System never double-sends a reminder; every email has a matching Celery idempotency guard | Celery dedup keys, 24h/1h reminders, cancellation email, WCAG email templates | Phase 2 (Resend infra), Phase 4 (stable signup flow) | Parallel with Phase 5 and Phase 7 |
| 7 | Admin Dashboard Polish | Admins can override eligibility, manage templates, view CSV imports, and run the audit log without engineering help | Override UI, bulk CRUD, CSV import surface, audit log filters, CCPA review | Phase 5 (CSV import), Phase 4 (override endpoint) | Parallel with Phase 5 and Phase 6 |
| 8 | Deployment to UCSB Infrastructure | Product runs on UCSB infrastructure (or Fly.io fallback) with monitoring, secrets, and handoff docs | Deploy target, Docker production config, secrets management, Sentry, backup runbook, handoff docs | Phase 0 (IT ticket answered); full feature stability before prod cutover | Infra prep and IT ticket can start at Phase 3; staging deploy can happen at Phase 5 |

---

## Dependency Graph

```
Phase 0 (Backend Audit + Integration)
  └── Phase 1 (Tailwind + Mobile)
        └── Phase 2 (Magic-Link Confirmation)
              └── Phase 3 (Check-In State Machine)
                    └── Phase 4 (Prereq Enforcement)
                          ├── Phase 5 (LLM CSV Import) ──┐
                          ├── Phase 6 (Notifications)    ├── Phase 7 (Admin Polish)
                          └── Phase 8 infra prep ────────┘
                                └── Phase 8 prod cutover (after Phase 5/6/7 stable)

Parallelism windows:
  - Phase 3 complete → begin Phase 8 IT ticket + infra prep (runs alongside Phase 4)
  - Phase 4 complete → Phase 5, Phase 6, Phase 7 all run in parallel
  - Phase 5 + Phase 6 + Phase 7 stable → Phase 8 production cutover
```

---

## Critical Path

The critical path is the longest chain of dependencies that determines the earliest possible completion date.

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 8 (prod cutover)
```

**Critical path logic:**
- Phase 0 is the only true hard gate: nothing else can start without a working, audited backend.
- Phase 1 (Tailwind) must complete before Phase 2 because all future frontend components are built in Tailwind; retrofitting later costs more than doing it once on clean skeletons.
- Phase 2 → Phase 3 → Phase 4 is a strict data-integrity chain: magic-link proves email identity, check-in records use that identity, prereq enforcement queries those records. Reordering produces corrupted data.
- Phase 5 (CSV import) is on the critical path because module_templates must be seeded before a real yearly cycle can be imported; this is required for handoff.
- Phase 8 production cutover requires all features stable. Infra prep can start earlier (Phase 3).

**Schedule risk:** The UCSB infrastructure target is unknown. Phase 0 must open an IT ticket immediately. If no response within 2 weeks, default to Fly.io (Docker-native, confirmed fallback) and migrate to UCSB hardware later.

---

## Parallelization Opportunities

| Window | Parallel Tracks | Gate Condition |
|--------|-----------------|----------------|
| Phase 3 complete | Begin Phase 8 IT ticket + infra environment setup | Phase 3 shipped |
| Phase 4 complete | Phase 5 + Phase 6 + Phase 7 all run simultaneously | Phase 4 shipped |
| Phase 5 stable | Phase 8 staging deploy to UCSB/Fly.io | Phase 5 + Phase 6 passing CI |
| Phase 5 + 6 + 7 stable | Phase 8 production cutover | All feature phases green |

**Single-developer note:** Parallelism here means alternating between tracks within the same work session, not concurrent staffing. The value is that Phase 6 and Phase 7 work does not block waiting for Phase 5 to fully complete — once Phase 4 ships, any of the three can be tackled in any order.

---

## Phase Details

### Phase 0: Backend Completion + Frontend Integration
**Goal**: Every backend endpoint is audited, working, and called from a real frontend page; a student can register, sign up, and cancel entirely through the UI without curl
**Depends on**: Nothing — start here
**Requirements**: All backend audit items, validation, auth hardening, Celery reliability, all E2E flows (student/organizer/admin), cancel/withdraw flow, Playwright CI suite
**Success Criteria** (what must be TRUE):
  1. A written punch list exists for every `lib/api.js` function: URL correct, HTTP method correct, response shape handled — with a linked fix PR for every mismatch found
  2. A student can register, browse events, sign up for a slot, and see it in MySignups entirely through the browser (no curl)
  3. A student can cancel their signup through the browser, freeing the slot capacity, with a confirmation email dispatched
  4. An organizer can log in, view their event dashboard, and see the roster
  5. An admin can log in, create/edit/delete users, portals, and events
  6. Playwright suite passes on every PR and fails the build on regression (covers all 4 E2E flows)
**Plans**: TBD
**UI hint**: yes
**Open-question gate**: Confirm UCSB infrastructure contact via IT ticket before this phase closes (feeds Phase 8 planning). Confirm whether `signups.status` enum currently includes `registered` as initial status or requires Alembic migration.

---

### Phase 1: Mobile-First Frontend Pass + Tailwind Migration
**Goal**: All pages are usable on a 375px phone with WCAG AA contrast, touch targets ≥ 44px, and a Tailwind v4 codebase that all future components will build on
**Depends on**: Phase 0
**Requirements**: Tailwind migration, 375px redesign on all pages, card-based event list, sticky filter chips, skeleton loaders, bottom-tab nav, one-tap signup flow, WCAG AA audit + remediation, SEO pass, axe-core in CI
**Success Criteria** (what must be TRUE):
  1. All pages render correctly at 375px viewport with no horizontal overflow and no elements clipped below the fold
  2. Every interactive element (buttons, slots, nav items) has a tap target ≥ 44px; organizer roster rows are one-tap to check in
  3. axe-core in CI reports zero WCAG AA violations on every PR as a merge gate
  4. Lighthouse SEO score ≥ 90 on the public event list and event detail pages
  5. The signup flow is completable in three taps or fewer: tap slot → confirm modal → done
**Plans**: TBD
**UI hint**: yes

---

### Phase 2: Magic-Link Confirmation
**Goal**: Every registered email address is verified by clicking a one-time link before check-in data is recorded against it
**Depends on**: Phase 1
**Requirements**: MagicLinkToken table, `GET /auth/magic/{token}` handler, registered→confirmed transition, rate limiting, TTL ≤ 15 min, single-use, fallback resend UI, WCAG-friendly email template via Resend
**Success Criteria** (what must be TRUE):
  1. After registering for a slot, the user receives a confirmation email within 60 seconds containing a unique link
  2. Clicking the link flips the signup from `registered` to `confirmed` and shows a success page
  3. Clicking the same link a second time returns an "already confirmed / link expired" page with a resend option
  4. A link older than 15 minutes returns an expired page with a working resend option
  5. Attempting to generate more than N links per email per hour is rate-limited with a clear user-facing message
**Plans**: TBD

---

### Phase 3: Check-In State Machine + Organizer Roster
**Goal**: An organizer can run a real in-person event from their phone and produce accurate attendance records that will drive prereq eligibility
**Depends on**: Phase 2
**Requirements**: Signup status enum extension + Alembic migration, organizer roster page (large tap targets, 5s polling), self-check-in via time-gated magic link + venue code, first-write-wins conflict resolution, end-of-event unmarked-attendee prompt, student timeline status icons, audit log on every transition
**Success Criteria** (what must be TRUE):
  1. The `SignupStatus` enum supports the full lifecycle: `registered → confirmed → checked_in → attended | no_show`; migration applies cleanly without data loss
  2. An organizer can tap a row on the roster page to mark a student checked in; the change persists and is visible to a second organizer's refreshed view within 5 seconds
  3. A student can self-check-in by tapping a time-gated link only within the valid window (15 min before → 30 min after slot start) and only after entering the venue code
  4. If both organizer and student attempt check-in simultaneously, the first write wins and both UIs reflect the same final state (no double-check-in corruption)
  5. At end of event, the organizer is prompted with a count of unmarked attendees and can resolve them in one tap per row
**Plans**: TBD
**UI hint**: yes
**Open-question gate**: Concurrent check-in integration tests must pass before this phase closes. Phase 3 should not ship without `SELECT ... FOR UPDATE` on the Signup row and a test that simulates simultaneous organizer + self-check-in.

---

### Phase 4: Prereq / Eligibility Enforcement
**Goal**: Registration for a module shows a soft warning when the student has not completed its prerequisites, with a direct link to the next available orientation slot
**Depends on**: Phase 3
**Requirements**: `_check_prereqs()` in `signups.py`, HTTP 422 with structured `PREREQ_MISSING` response, soft-warn registration modal with next-slot link, admin manual override endpoint with reason field, override audit log entry, module timeline (locked/unlocked/completed) in MySignupsPage
**Success Criteria** (what must be TRUE):
  1. Signing up for a module with unmet prereqs shows a warning modal naming the missing prereq and linking directly to the next available orientation slot; the student can still proceed with an extra deliberate tap
  2. Signing up for a module with all prereqs satisfied proceeds without any warning
  3. An admin can override prereq eligibility for a specific student with a required reason; the override appears as a distinct indicator on the student's module timeline
  4. The student's MySignups page shows a timeline where each module is labeled: locked, unlocked, or completed — reflecting their actual check-in history
**Plans**: TBD
**UI hint**: yes
**Open-question gate**: Confirm Sci Trek's prereq policy (soft warn confirmed by user; verify with Sci Trek before Phase 4 planning). Confirm `module_templates` prerequisite slug schema is forward-compatible with Phase 5.

---

### Phase 5: Event Template System + LLM-Normalized CSV Import
**Goal**: An organizer can upload a yearly Sci Trek CSV and see a validated preview of events to be created, then commit them atomically in one action
**Depends on**: Phase 4 (module_templates FK on Event), Phase 0 (working API)
**Requirements**: `module_templates` table (slug PK, name, prereq slugs, default capacity, duration, materials), seed with current modules; Stage 1 LLM extraction (instructor + Pydantic structured output, gpt-4o-mini); Stage 2 deterministic importer (schema validation, conflict detection, atomic commit with rollback); preview UI with row-level validation; `_confidence` field; raw→normalized corpus logging; eval dataset
**Success Criteria** (what must be TRUE):
  1. A module template can be created, edited, and deleted through the admin interface; seeded templates are present after a fresh deploy
  2. Uploading a yearly Sci Trek CSV triggers a single-shot LLM extraction that returns a preview within 30 seconds; the preview shows N events to be created and M rows flagged for manual review
  3. Low-confidence rows are highlighted in the preview and cannot be committed without manual resolution
  4. Clicking "commit" inserts all validated events atomically; if any row fails validation, the entire batch is rolled back and the user sees a clear error
  5. Every raw CSV → normalized JSON pair is logged to a corpus file for future eval
**Plans**: TBD
**UI hint**: yes
**Open-question gate**: A real past-year Sci Trek CSV sample is required before the LLM prompt and few-shot examples can be written. Request from Sci Trek before Phase 5 planning begins. Module year-over-year stability assumption (affects template versioning) must be confirmed.

---

### Phase 6: Notifications Polish
**Goal**: The email pipeline is production-reliable — every transactional email is sent exactly once, idempotency guards prevent double-sends under Celery restarts or beat overlap
**Depends on**: Phase 2 (Resend infrastructure), Phase 4 (stable signup lifecycle)
**Requirements**: Registration confirmation email with magic link, 24h reminder, 1h reminder (optional per-event toggle), cancellation email on slot removal/reschedule, Celery dedup keys (`(signup_id, kind)` + `reminder_24h_sent_at` column), WCAG-friendly email templates, Resend free-tier monitoring
**Success Criteria** (what must be TRUE):
  1. A student who signs up receives a confirmation email with their magic link within 60 seconds
  2. A student with a confirmed signup receives exactly one 24h reminder — not zero, not two — even if the Celery beat fires multiple times in that window
  3. A student whose slot is cancelled or rescheduled receives a cancellation email within 5 minutes
  4. Running the reminder task twice against the same set of signups produces no duplicate emails (idempotency test passes in CI)
**Plans**: TBD

---

### Phase 7: Admin Dashboard Polish
**Goal**: Admins and organizers can operate the system day-to-day — override eligibility, manage module templates, trigger CSV imports, and review audit logs — without engineering intervention
**Depends on**: Phase 4 (override endpoint), Phase 5 (CSV import pipeline)
**Requirements**: Manual eligibility override UI, bulk module-template CRUD, CSV import UI surface (Phase 5 pipeline), audit log viewer with user/kind/date filters, attendance CSV export, analytics views (volunteer hours, attendance rates, no-show rates), CCPA compliance review (data retention policy, deletion endpoint)
**Success Criteria** (what must be TRUE):
  1. An admin can search, filter, and view the audit log by user, action type, and date range without scrolling through 2000 unfiltered rows
  2. An admin can trigger the CSV import pipeline from the UI, review the preview, and commit or discard the batch without touching the terminal
  3. An admin can apply a manual eligibility override with a reason and see it reflected immediately on the student's timeline
  4. An admin can bulk-create, edit, or delete module templates from a single table view
  5. A logged-in admin can export volunteer hours and attendance rates as a CSV (covers grant reporting)
  6. A CCPA data-access or deletion request can be fulfilled by an admin using documented UI steps (no direct DB access required)
**Plans**: TBD
**UI hint**: yes

---

### Phase 8: Deployment to UCSB Infrastructure
**Goal**: The application runs on production UCSB infrastructure (or Fly.io fallback) with error monitoring, secrets management, a staging environment, and handoff documentation sufficient for a new maintainer to operate and onboard
**Depends on**: Phase 0 (IT ticket answer); all feature phases stable before prod cutover
**Requirements**: UCSB deploy target identified, production Docker compose or equivalent, secrets management, structured logging + health endpoint, Sentry error tracking, Postgres backup + restore runbook, staging environment, handoff docs (README, ops runbook, onboarding, architecture diagram)
**Success Criteria** (what must be TRUE):
  1. The application is accessible at a stable URL on UCSB infrastructure (or Fly.io fallback); all E2E Playwright tests pass against the staging environment
  2. A simulated error (forced exception) appears in Sentry within 30 seconds; the health endpoint at `/api/v1/health` returns 200 with uptime data
  3. Secrets (database URL, JWT secret, Resend API key, OpenAI key) are loaded from environment variables or a campus vault — no secrets in source code or Docker images
  4. A Postgres backup can be taken and restored following the runbook without data loss (verified by restore test in staging)
  5. A new maintainer with no prior project context can run the application locally and deploy a change to staging by following the README alone — validated by dry-run before June handoff
**Plans**: TBD
**Open-question gate**: UCSB infrastructure target (VPS, campus Kubernetes, or shared host) must be confirmed via IT ticket before Phase 8 planning begins. Staging environment existence (branch-based or main → prod) must be resolved. If no response within 2 weeks of Phase 3 completing, proceed with Fly.io and document migration path.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Backend Completion + Frontend Integration | 0/? | Not started | - |
| 1. Mobile-First Frontend Pass + Tailwind Migration | 0/? | Not started | - |
| 2. Magic-Link Confirmation | 0/? | Not started | - |
| 3. Check-In State Machine + Organizer Roster | 0/? | Not started | - |
| 4. Prereq / Eligibility Enforcement | 0/? | Not started | - |
| 5. Event Template System + LLM CSV Import | 0/? | Not started | - |
| 6. Notifications Polish | 0/? | Not started | - |
| 7. Admin Dashboard Polish | 0/? | Not started | - |
| 8. Deployment to UCSB Infrastructure | 0/? | Not started | - |

---

## Open-Question Resolution Gates

These questions block specific phases. They must be answered before the corresponding phase is planned.

| Question | Blocks | How to Resolve |
|----------|--------|----------------|
| UCSB infrastructure target (VPS, campus K8s, shared host) | Phase 8 planning | Open IT ticket during Phase 0; Fly.io fallback if no response within 2 weeks of Phase 3 |
| `signups.status` enum current values (does `registered` already exist as initial status?) | Phase 0 Alembic migration | Audit `models.py` and live DB on Day 1 of Phase 0 |
| Real Sci Trek CSV sample (needed for few-shot prompt) | Phase 5 LLM prompt design | Request from Sci Trek before Phase 5 planning begins |
| Module year-over-year stability (affects template versioning strategy) | Phase 5 template schema | Confirm with Sci Trek alongside CSV sample request |
| Staging environment: main → prod, or branch-based deploy? | Phase 8 deploy strategy | Resolve with UCSB IT or decide during Phase 8 planning |
| Post-June 2026 maintainer identity | Handoff doc scope | Decide before Phase 8 handoff-docs work begins; optimize for unknown maintainer in the meantime |
| Phone number collection: keep or drop? (Twilio config exists, no SMS planned) | Phase 0 data model + CCPA surface | Decide during Phase 0; dropping reduces CCPA scope |

---

## Cross-Cutting Requirements (apply to every phase)

- **WCAG 2.1 AA:** Keyboard navigation, focus states, semantic HTML, color contrast, screen-reader labels. axe-core runs in CI as merge gate from Phase 1 onward.
- **Mobile-first:** Every UI page at 375px first; touch targets ≥ 44px. No page ships without mobile pass.
- **SEO baseline:** Semantic HTML, meta tags, sitemap, OpenGraph on public pages. Established in Phase 1.
- **California compliance (CCPA):** Data minimization, no HS student data stored, explicit privacy notice, data access/deletion operable by admin. Formally reviewed in Phase 7.
- **No accounts:** Identity = email + name + phone; magic link only. No passwords introduced.
- **Deterministic core:** LLM only in Phase 5 CSV extraction. No LLM in business logic or runtime paths.
- **Handoff-readiness:** README and ops runbook updated at phase transitions. Architecture diagram maintained. Target: new maintainer can onboard from README alone.

---

*Roadmap created: 2026-04-08*
*Next: `/gsd-plan-phase 0` to decompose Phase 0 into executable plans*
