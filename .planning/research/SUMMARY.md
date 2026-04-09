# Project Research Summary

**Project:** uni-volunteer-scheduler (UCSB Sci Trek)
**Domain:** Mobile-first loginless volunteer scheduler — brownfield FastAPI + React
**Researched:** 2026-04-08
**Confidence:** HIGH (stack, architecture, pitfalls from direct codebase analysis); MEDIUM (features from competitor analysis; deploy target unknown)

## Executive Summary

This is a brownfield completion project, not a greenfield build. The FastAPI + SQLAlchemy + Celery + React stack is already in place and production-shaped; the highest-leverage work is auditing and wiring what exists before any new feature is added. The recommended approach is a strict phase gate: Phase 0 completes backend integration and frontend wiring across all existing pages, and every subsequent phase builds on a provably working foundation. Skipping Phase 0 — building new features on unverified page skeletons — is the single largest risk to the June 2026 handoff deadline.

The product's competitive thesis is narrow and clear: volunteers register on a phone in under 30 seconds, and check-in becomes the source of truth that drives prerequisite eligibility. No other comparable tool (SignUpGenius, VolunteerHub, SignUp.com) links attendance history to future access in a loginless, mobile-first interface. That loop — register, attend, unlock next module — is the entire product. Everything else (LLM CSV import, notification polish, admin tooling) is supporting infrastructure for that loop.

The critical risks are technical and sequenced: magic-link token replay must be hardened before check-in ships (Pitfall 1); check-in state machine locking must be correct before prereq enforcement ships (Pitfall 3); and the UCSB infrastructure question must be answered before Phase 8 begins (Pitfall 11). A secondary risk — volunteer cancel/withdraw flow — is missing from the current backlog entirely despite being table stakes; it must be added to the Phase 0 punch list.

## Key Findings

### Recommended Stack

The existing stack requires no replacement — only targeted additions. For the frontend: migrate to Tailwind CSS v4 (stable since Jan 2025, Vite-native plugin, no PostCSS config) and add Playwright 1.59+ for E2E testing with `@axe-core/playwright` for WCAG AA scanning in CI. For the backend: replace SendGrid with the Resend Python SDK (already decided; free tier covers Sci Trek scale), add `instructor` 1.15.1 for Phase 5 LLM extraction (provider-agnostic, Pydantic-validated, automatic retry), and add `sentry-sdk[fastapi]` before first production deploy. Magic-link tokens require no external library — Python `secrets.token_urlsafe(32)` plus a `MagicLinkToken` table is sufficient and correct.

**Core technologies (additions only — existing stack unchanged):**
- `tailwindcss` 4.x + `@tailwindcss/vite`: Vite-native CSS migration — faster builds, no PostCSS
- `@playwright/test` 1.59.x: E2E test runner — native SPA selectors, trace viewer, CI-ready
- `@axe-core/playwright` 4.10.x: WCAG AA scanning in E2E suite — catches ~57% of violations automatically
- `eslint-plugin-jsx-a11y` 6.x: static JSX accessibility linting — catches violations at dev time
- `resend` 2.27.x: transactional email (replaces SendGrid) — simpler SDK, free tier fits scale
- `instructor` 1.15.1: structured LLM extraction for Phase 5 — provider-agnostic, retry on validation failure
- `sentry-sdk[fastapi]` 2.57.x: error tracking + performance — zero-config FastAPI integration
- Deploy fallback: Fly.io (Docker-native, free tier) if UCSB infra contact is delayed; migrate later

### Expected Features

The brownfield codebase already has routing and skeletons for all core flows. The work is wiring and completing, not inventing. Competitor analysis confirms the expected table-stakes set is well-understood; the differentiators (prereq gating from check-in data, module timeline UX, LLM CSV import) are genuinely novel — no competitor offers them.

**Must have (table stakes — needed before June 2026 handoff):**
- Backend + frontend fully integrated, every page wired to real API
- Cancel / withdraw from a slot — **gap in current backlog; must be added to Phase 0** (every competitor provides this; without it coordinators receive manual cancellation requests and capacity is permanently locked)
- Slot capacity limits with "slot full" feedback
- Automated confirmation email on signup
- Automated 24h reminder emails
- Organizer roster view with tap-to-mark attendance
- Admin CRUD for users, portals, events
- Mobile-first layout at 375px, touch targets >= 44px
- Magic-link email confirmation on signup (unblocks prereq integrity)
- Cancellation email when slot is removed
- UCSB deployment (local-only has zero operational value)

**Should have (differentiators — flagship features):**
- Check-in state machine: `registered -> confirmed -> checked_in -> attended | no_show`
- Prereq soft-warn on registration with module timeline in MySignupsPage
- Self check-in via time-gated magic link + per-event venue code (organizer-driven is primary)
- LLM CSV import (Stage 1 normalize + Stage 2 deterministic commit with preview UI)

**Defer (v2+):**
- Real-time WebSockets — 5s polling is imperceptible at Sci Trek scale
- Detailed analytics dashboard — CSV export covers grant reporting at lower cost
- i18n / Spanish support — deferred until specific user evidence
- AI matching / recommendation engine — no user profiles to match against

### Architecture Approach

The architecture is a conventional REST SPA: React pages fetch from FastAPI routers via a single `lib/api.js` wrapper, with TanStack Query managing server-state cache, SQLAlchemy + Alembic managing the Postgres schema, and Celery + Redis handling async email delivery. The key structural insight from codebase analysis is that all business rules (capacity, prereq, signup window, duplicate check) live at the application layer in router handlers — not in DB constraints — and this pattern must be continued consistently. Two major additions are purely additive: a `MagicLinkToken` table (new model, new auth handler) and a `ModuleTemplate` table (new model, new router, FK on `Event`). The LLM CSV import is isolated as a two-stage pipeline behind a dedicated `import_csv` router, keeping LLM non-determinism out of the main signup flow entirely.

**Major components:**
1. `lib/api.js` — single fetch wrapper; currently has known URL/method mismatches against the backend (Phase 0 punch list item)
2. FastAPI routers — HTTP entry, auth enforcement, business rules, task dispatch, audit logging; `signups.py` is the critical path for prereq logic
3. `SignupStatus` enum (models.py) — currently `confirmed | waitlisted | cancelled`; must be extended to `registered | confirmed | checked_in | attended | no_show` (breaking change requiring Alembic migration)
4. `MagicLinkToken` table — new; stores hashed one-time tokens with purpose + expiry + used_at
5. `ModuleTemplate` table — new; permanent records (slug, name, prereq_slugs, default_capacity); `Event` gets a nullable FK to this table
6. `csv_extractor.py` service + `import_csv` router — two-stage pipeline: LLM extraction (Stage 1) produces Pydantic-validated preview; deterministic importer (Stage 2) does atomic DB commit
7. Celery tasks — existing `send_email_notification`; needs idempotency guards (`reminder_24h_sent_at` column, Redis dedup key) before scaling
8. `AuthContext` + `authStorage.js` — frontend session; refresh token flow currently unimplemented (tokens discarded at line 30); must be completed alongside magic-link rollout

### Critical Pitfalls

1. **Brownfield "looks wired" pages with silent backend failures (Pitfall 12)** — Phase 0 must produce a written URL/method punch list for every `lib/api.js` function; add a global 4xx/5xx console logger in development so invisible 404s become visible. This is the highest-priority pitfall and the primary purpose of Phase 0.

2. **Magic-link token replay (Pitfall 1)** — Store token as `sha256(token)` in DB; set `used_at` atomically in the same transaction that issues the session JWT; hard-expire at 15 minutes; rate-limit generation per email. Frontend must implement the refresh token flow in `authStorage.js`.

3. **Check-in race condition corrupts attendance (Pitfall 3)** — Lock the Signup row with `SELECT ... FOR UPDATE` (not the Slot row) before reading status; establish canonical lock order (Slot then Signup); return 200 idempotent success if already `checked_in`. Do not ship Phase 3 without concurrent check-in integration tests.

4. **Celery beat firing twice — duplicate reminders (Pitfall 7)** — Add `reminder_24h_sent_at` timestamp column on signups; atomic UPDATE with null-check guard in task; Redis dedup key per signup/kind; run beat as dedicated process, never with `--beat` flag in multi-replica deploys.

5. **UCSB infrastructure deploy surprises (Pitfall 11)** — Open an IT ticket before writing Phase 8 code to determine Docker support, outbound email constraints, Redis availability, and TLS process. Phase 0 must capture the infrastructure answer. Fly.io is the validated fallback if UCSB infra is delayed.

6. **WCAG AA failures hidden by Tailwind defaults (Pitfall 9)** — Define a custom AA-verified color palette before Tailwind migration; configure `eslint-plugin-jsx-a11y` to error (not warn); never use `outline-none` without a `focus-visible` replacement; run axe-core in CI as a merge gate.

## Implications for Roadmap

Based on research, the phase structure in PROJECT.md is well-sequenced. The key additions and clarifications from research:

### Phase 0: Backend Completion + Frontend Integration
**Rationale:** Every feature below this phase depends on a working API contract. Building on unverified page skeletons means testing against stubs, not real behavior. The `lib/api.js` mismatches documented in CONCERNS.md (wrong URLs, wrong HTTP methods) will silently corrupt any feature built on top of them.
**Delivers:** Written punch list of every endpoint status; all pages wired to real backend; E2E Playwright suite passing in CI; auth hardening (token replay, rate limits, refresh flow); Celery reliability audit; cancel/withdraw flow added and wired (gap closure).
**Addresses:** All table-stakes features require this foundation. Cancel/withdraw gap must be closed here.
**Avoids:** Pitfall 12 (silent backend failures), Pitfall 1 (magic-link replay — auth hardening), Pitfall 7 (Celery beat — reliability audit), Pitfall 10 (CCPA — deletion endpoint stub).

### Phase 1: Mobile-First Frontend Pass
**Rationale:** The stated reason for the rebuild is SignUpGenius's poor mobile UX. If the product ships without a 375px-first layout, it fails its primary thesis regardless of backend correctness. Tailwind migration must happen early because every future frontend component will be built in it — retrofitting later costs more than migrating once on a clean slate of page skeletons.
**Delivers:** Tailwind v4 migration (run upgrade tool first), all pages at 375px, touch targets >= 44px, one-tap signup flow, WCAG AA color palette + focus indicators, SEO baseline, axe-core in CI.
**Uses:** `tailwindcss` 4.x + `@tailwindcss/vite`, `eslint-plugin-jsx-a11y`, `@axe-core/playwright`.
**Avoids:** Pitfall 9 (WCAG AA failures from Tailwind defaults — must establish AA palette during migration, not after).

### Phase 2: Magic-Link Confirmation
**Rationale:** Magic-link confirmation is the prerequisite for prereq integrity. Without proving email ownership, `checked_in` records can be corrupted by typos — two different email strings for the same person produce split identity that breaks the prereq query permanently (Pitfall 2).
**Delivers:** `MagicLinkToken` table, `GET /auth/magic/{token}` handler, `registered -> confirmed` signup transition, "check your inbox" interstitial, case-insensitive email match on confirmation, Resend integration.
**Implements:** MagicLinkToken architecture component; replaces SendGrid with Resend SDK.
**Avoids:** Pitfall 2 (email typo breaks prereq history), Pitfall 1 (replay protection enforced here).

### Phase 3: Check-In State Machine + Organizer Roster
**Rationale:** Check-in is the source of truth for prereqs. The state machine must ship and be proven correct (with concurrent access tests) before Phase 4 prereq enforcement is built on top of it. Organizer roster is the primary interface for running real events and is required for any live deployment.
**Delivers:** Full `SignupStatus` enum extension + Alembic migration; organizer tap-to-mark roster with per-row save confirmation; self-check-in via time-gated magic link + venue code (primary: organizer-driven); end-of-event unmarked-attendee prompt; prereq-missing badge on roster; self-check-in audit trail.
**Avoids:** Pitfall 3 (race condition — Signup row locking, idempotent 200), Pitfall 4 (offline mid-event — per-row save confirmation + end-of-event prompt), Pitfall 5 (venue code bypass — rate limiting, organizer-driven as primary), Pitfall 8 (soft-warn UX — prereq badge on roster).

### Phase 4: Prereq / Eligibility Enforcement
**Rationale:** Depends entirely on Phase 3 check-in data and Phase 2 magic-link identity proof. Must not ship before both are stable. The prereq SQL query is simple once data is clean; the complexity is in the UX (soft warn with next-slot link, admin override) and the state integrity requirements.
**Delivers:** `_check_prereqs()` query in `signups.py`; HTTP 422 with structured `{"detail": "PREREQ_MISSING", "missing": [...], "next_slots": [...]}` response; soft-warn registration modal with direct prereq-signup link; admin manual override endpoint; module timeline (locked/unlocked/completed) in MySignupsPage.
**Avoids:** Pitfall 8 (soft-warn regret — warning must include direct link to next orientation and require deliberate extra tap to skip).

### Phase 5: Event Template + LLM CSV Import
**Rationale:** `module_templates` table is the prerequisite for LLM import (Stage 1 maps CSV rows to template slugs; the table must exist and be seeded manually first). The two-stage pipeline (LLM extraction -> human preview -> deterministic commit) keeps LLM non-determinism isolated and reversible. High operational leverage for yearly cycle setup.
**Delivers:** `ModuleTemplate` table + CRUD router; `POST /import/extract` (Stage 1 LLM, instructor + openai gpt-4o-mini); `POST /import/commit` (Stage 2 deterministic, atomic with rollback); preview UI with row-level validation highlighting; `_confidence` field per extracted row; raw->normalized corpus logging.
**Uses:** `instructor` 1.15.1, `openai` 2.31.x.
**Avoids:** Pitfall 6 (LLM hallucinated dates/capacities — Stage 2 must validate date validity, capacity range +/- 2x template default, duplicate event detection; preview UI must highlight failing rows in red).

### Phase 6: Notifications Polish
**Rationale:** Email pipeline exists in skeleton form; this phase makes it production-reliable. Idempotency guards (reminder sent-at columns, Redis dedup) must be in place before any volume of events runs through the system.
**Delivers:** Registration confirmation email with magic link; 24h reminder; cancellation email on slot removal; Celery idempotency (`reminder_24h_sent_at` column + Redis dedup key); `celery-redbeat` for distributed beat locking if multi-container.
**Avoids:** Pitfall 7 (duplicate reminders — idempotency guards are this phase's primary deliverable).

### Phase 7: Admin Dashboard Polish
**Rationale:** Admin tooling is needed for organizers to operate without engineering help, but it is not on the critical path for the core volunteer loop. Polish after the core features are stable.
**Delivers:** Manual eligibility override UI; bulk module-template CRUD; CSV import UI surface; audit log viewer; attendance CSV export; privacy/CCPA compliance review (data retention policy, deletion endpoint polish).
**Avoids:** Pitfall 10 (California privacy — data retention policy and deletion endpoint must be documented and operable before handoff).

### Phase 8: Deployment to UCSB Infrastructure
**Rationale:** Deploy target must be identified before writing any deployment code. Phase 0 must capture the infrastructure answer; Phase 8 executes against it. 4 weeks minimum before the June deadline for a staging run on actual UCSB hardware.
**Delivers:** Production deploy (UCSB L&S Cloud VM or Fly.io fallback); secrets management; Sentry error tracking; CORS origin configuration; handoff-ready README, ops runbook, onboarding docs.
**Uses:** `sentry-sdk[fastapi]` 2.57.x.
**Avoids:** Pitfall 11 (UCSB infrastructure surprises — IT ticket before Phase 8 starts; Docker support, outbound email constraints, Redis availability, TLS process all confirmed in advance).

### Phase Ordering Rationale

- Phase 0 is the non-negotiable prerequisite for all subsequent phases. Feature development on unverified skeletons produces features that appear to work but silently fail.
- Phase 1 (mobile-first) must happen before any user-facing feature UX is designed, because retrofitting 375px layout onto desktop-first markup costs more than building it correctly once. The Tailwind migration also enables Phase 2+ frontend work to use the correct toolchain from the start.
- Phases 2 -> 3 -> 4 are a strict dependency chain: magic-link confirmation proves email identity, check-in state machine uses that identity to populate attendance records, prereq enforcement queries those records. Swapping this order produces corrupted data that is difficult to clean up.
- Phase 5 (LLM import) is independent of Phases 2-4 at the data model level but requires `module_templates` to exist, which can be built in parallel with Phase 4 if staffing allows.
- Phases 6 and 7 are polish phases and can overlap with earlier phases for parts that do not block core flow.
- Phase 8 (deploy) requires all features to be stable and the infrastructure question answered from Phase 0.

### Research Flags

Phases likely needing `/gsd-research-phase` during planning:
- **Phase 3 (check-in state machine):** Concurrent access patterns under mobile organizer load require careful lock ordering. The race condition between organizer-driven and self-check-in paths needs integration tests before implementation.
- **Phase 5 (LLM CSV import):** Real Sci Trek CSV samples are needed before the LLM extraction prompt can be written. The prompt design, few-shot examples, and `_confidence` schema fields depend on seeing actual data. This is a hard dependency on getting a sample CSV from Sci Trek.
- **Phase 8 (UCSB deploy):** Deploy approach is fully unknown until the IT ticket is answered. The entire phase plan depends on the infrastructure answer.

Phases with standard patterns (skip research-phase):
- **Phase 0 (backend audit):** Mechanical audit — URL matching, HTTP method verification. No novel patterns needed; the work is inspection and fixing.
- **Phase 1 (Tailwind migration):** The `npx @tailwindcss/upgrade` tool handles ~90% mechanically. Tailwind v4 docs are complete and official.
- **Phase 2 (magic-link):** Implementation is ~30 lines of FastAPI using Python stdlib. Pattern is well-documented.
- **Phase 6 (notifications):** Resend SDK is simple; Celery idempotency pattern is documented in PITFALLS.md with exact column names and Redis key pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified on PyPI/npm; version compatibility matrix confirmed; UCSB deploy target is the only MEDIUM confidence area |
| Features | MEDIUM | Table-stakes and differentiators derived from live competitor docs (HIGH); prioritization based on IDEAS.md and PROJECT.md (HIGH); cancel/withdraw gap identified from first-party research |
| Architecture | HIGH | Based on direct codebase analysis, not speculation; all component boundaries and insertion points map to actual files with line references |
| Pitfalls | HIGH | All 12 pitfalls grounded in CONCERNS.md codebase findings and domain verification; not theoretical — each maps to a specific existing gap |

**Overall confidence:** HIGH for technical approach; MEDIUM for deploy target and LLM prompt design (both require external input).

### Gaps to Address

- **UCSB infrastructure target:** Open question from PROJECT.md; must be answered in Phase 0 via IT ticket. Until answered, Phase 8 plan is notional. Fly.io is the validated fallback.
- **Real Sci Trek CSV sample:** Phase 5 LLM extraction prompt cannot be finalized without seeing actual yearly CSV format. Request from Sci Trek before Phase 5 planning begins.
- **`signups.status` enum current values:** Phase 0 audit must confirm whether any live data uses the current `confirmed` default as initial status before the breaking change to `registered` as initial status is applied.
- **Phone number retention decision:** CONCERNS.md notes Twilio config exists but no SMS is planned. If SMS is not in scope, consider removing phone number collection to reduce CCPA surface area. Decision needed before Phase 0 data model work.
- **Cancel/withdraw gap:** Not in current IDEAS.md backlog. Confirmed as table stakes by competitor analysis. Must be added to Phase 0 punch list explicitly — backend endpoint + frontend button in MySignupsPage.

## Sources

### Primary (HIGH confidence)
- `CONCERNS.md`, `backend/`, `frontend/` (codebase) — direct architecture and pitfall analysis
- https://tailwindcss.com/blog/tailwindcss-v4 — v4 stable release, Vite setup
- https://playwright.dev/docs/ci-intro — recommended GH Actions config
- https://playwright.dev/docs/accessibility-testing — @axe-core/playwright
- https://pypi.org/project/instructor/ — instructor 1.15.1
- https://pypi.org/project/resend/ — resend 2.27.0
- https://pypi.org/project/sentry-sdk/ — sentry-sdk 2.57.0
- https://www.signupgenius.com/features — SignUpGenius feature set
- https://volunteerhub.com/platform/volunteer-scheduling — VolunteerHub feature set
- IDEAS.md, PROJECT.md — primary product context

### Secondary (MEDIUM confidence)
- https://it.ucsb.edu/servers-and-large-data-storage/application-hosting — UCSB ITS hosting options
- https://cloud.lsit.ucsb.edu/ — LSIT L&S Cloud VM options
- https://worldmetrics.org/best/volunteer-shift-scheduling-software/ — competitor ecosystem overview
- https://www.capterra.com/p/135392/SignUpGenius/reviews/ — SignUpGenius mobile UX complaints

---
*Research completed: 2026-04-08*
*Ready for roadmap: yes*
