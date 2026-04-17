---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: feature-expansion
status: executing
last_updated: "2026-04-17T00:00:00.000Z"
last_activity: 2026-04-17
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

**Project:** Uni Volunteer Scheduler (UCSB Sci Trek)
**Initialized:** 2026-04-08
**Mode:** Autonomous · Standard granularity · Sequential execution · Research/Plan-Check/Verifier all ON
**Deadline:** Before June 2026

## Current Position

Phase: 21 (orientation-credit-engine) — NEXT
Plan: Not started
**Milestone:** v1.3 feature expansion (SciTrek parity)
Status: Ready to plan Phase 21; v1.3 branch active, roadmap written 2026-04-17
**Last activity:** 2026-04-17

## Current Status

- ✓ v1.0 phases 0–7 shipped (2026-04-08) — drifted from no-accounts thesis, then realigned in v1.1
- ✓ v1.1 phases 08–13 shipped (2026-04-10) — account-less realignment + admin shell + 16/16 Playwright E2E green
- ✓ v1.2-prod phases 14–20 shipped (2026-04-16) — production-ready by role (participant, admin, organizer) + cross-role integration
- ▶ v1.3 feature expansion milestone seeded + roadmap written 2026-04-17 (Phase 21 next)

**v1.3 phase plan (9 phases, 21–29):**

- Phase 21: Orientation credit engine — cross-week/cross-module tracked by (volunteer, module_family)
- Phase 22: Custom form fields — organizer-editable signup questions with template defaults
- Phase 23: Recurring event duplication — admin "Duplicate to weeks N…M"
- Phase 24: Scheduled reminder emails — Celery Beat kickoff + 24h + 2h with idempotency
- Phase 25: Waitlist + auto-promote — wire up waitlisted enum end-to-end
- Phase 26: Broadcast messages — organizer/admin → email all signups
- Phase 27: SMS reminders + no-show nudges — AWS SNS behind feature flag
- Phase 28: QR check-in — per-signup QR on confirmation email
- Phase 29: Slot swap + signup locking + past-event hiding + integration gate

**Out of scope:** UCSB production deployment (next milestone), payments/donations, SSO, multi-tenant, branding.

## Next Action

`/gsd-plan-phase 21` — start Phase 21 (Orientation credit engine). This phase MUST ship first because it reshapes the domain model (module family, credit table) that every later phase either touches or assumes.

**v1.1 closing notes (still relevant for v1.2-prod handoff):**

- Test-helper backend endpoints (`seed-cleanup`, `event-signups-cleanup`) gated by `EXPOSE_TOKENS_FOR_TESTING=1` enable idempotent Playwright reruns despite UNIQUE(volunteer_id, slot_id) constraint
- Rate-limit bypass when `EXPOSE_TOKENS_FOR_TESTING=1` is required so parallel Playwright workers (sharing localhost IP) don't exhaust the 10/min limit
- Slot capacity 200 for E2E events prevents exhaustion across 4 parallel workers

## Accumulated Context

### v1.2-prod sequencing risks (flagged in ROADMAP.md notes)

- **Admin and organizer share code surface** — both pillars touch event create/edit and magic-link infrastructure. Phase 19 (organizer) waits until Phase 18 (admin LLM imports) lands so the two worktrees don't fight over shared files. Deliberate sequencing choice; alternative is more merge conflicts than two devs can absorb in a 6-week window.
- **`frontend/src/lib/api.js`, `frontend/src/App.jsx` (routes), and shared component files are PR-only edits** — must be called out in COLLAB-03 file-ownership table to keep the participant + admin worktrees from colliding during the parallel Phase 15 + 16 window.
- **Phase 18 (LLM CSV import) is the milestone's biggest net-new feature.** Everything else is audit + polish + targeted fills. If Phase 18 slips, plan a focused recovery rather than spreading the LLM work across other phases.

### Stage 0 findings (still relevant for v1.2-prod phases)

- Alembic chain uses slug-style revision IDs; `alembic/env.py` pre-widens `version_num` to VARCHAR(128). Do not regress.
- ~~Enum downgrade leak~~ RESOLVED in Phase 08 — `2465a60b9dbc_initial_schema.py` now drops `signupstatus`, `userrole`, `notificationtype`, `privacymode`. Round-trip gate passes.
- Docker stack quirk: db/redis not exposed to host. Tests run via one-off container on `uni-volunteer-scheduler_default` network. See CLAUDE.md.
- Phase 5.07 LLM CSV extraction: **NO LONGER BLOCKED** — Andy holds the CSV file. Ships in Phase 18.

### Phase 08 handoff for Phase 09 / 12 (historical, still relevant for context)

- App does **not boot** cleanly until Phase 09 wires the new volunteer-keyed code paths.
- Test baseline: 76 passed / 74 skipped / 0 failed (was 185/185). The 74 skips are runtime breakages at `signup.user` sites, marked with "Phase 09" reasons.
- `backend/app/schemas.py` keeps `PrereqOverrideRead` as stubs for `admin.py` compatibility — Phase 12 removes both.
- `backend/app/services/prereqs.py` has a try/except import guard for the same reason.
- `SlotFactory.slot_type` defaults to `SlotType.PERIOD`; Slot model has no `server_default` on `slot_type` (migration handles it).
- See `08-SUMMARY.md` + `08-VERIFICATION.md` for the full handoff list.

### v1.0 surface map

- **Retired in v1.1:** Phase 2 account-confirmation flow (repurposed magic-link infra), Phase 4 prereq enforcement, Phase 7 override UI, student login/register frontend pages.
- **Lingering for v1.2-prod cleanup:** `Overrides` admin sidebar nav item — closes the v1.1 Phase 12 retirement loop. ADMIN-01 in Phase 16.
- **Keeping:** Phase 0 schema scaffolding, Phase 1 Tailwind design system + components, Phase 3 check-in state machine + organizer roster, Phase 5 CSV template import (deterministic parts), Phase 6 notifications, Phase 7 audit log / analytics / CCPA export.

## Key Decisions Log

See `.planning/PROJECT.md` → Key Decisions.

## Open Questions

See `.planning/PROJECT.md` → Open Questions and `.planning/REQUIREMENTS-v1.2-prod.md` → Open Questions (to resolve during planning).

---
*Last updated: 2026-04-14 — v1.2-prod ROADMAP.md written; 7 phases (14–20); 68/68 requirements mapped; next action is `/gsd-plan-phase 14`*
