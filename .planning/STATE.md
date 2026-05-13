---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: milestone
status: in-progress
last_updated: "2026-05-13T21:34:55.457Z"
last_activity: 2026-05-08 — Phase 30 shipped end-to-end. Backend (29 tests, 100% coverage on `app.copilot`), frontend (16 tests, FAB + drawer + streaming hook), 8 docs (lectures + publication writeups), live OpenRouter smoke test passed via both curl and browser. Telemetry rows landing in `copilot_messages` with full paper-relevant columns populated.
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 6
  completed_plans: 5
  percent: 83
---

# Project State

**Project:** Uni Volunteer Scheduler (UCSB Sci Trek)
**Initialized:** 2026-04-08
**Mode:** Autonomous · Standard granularity · Sequential execution · Research/Plan-Check/Verifier all ON
**Deadline:** Phase 30 before graduation; full milestone + paper by week 16.

## Current Position

Milestone: **v1.4 AI Onboarding Copilot** — in progress
Phase: 30 (streaming chat MVP) — ✅ shipped
Branch: `feature/v1.4-phase-30-streaming-chat` — ready to merge
**Last activity:** 2026-05-08 — Phase 30 shipped end-to-end. Backend (29 tests, 100% coverage on `app.copilot`), frontend (16 tests, FAB + drawer + streaming hook), 8 docs (lectures + publication writeups), live OpenRouter smoke test passed via both curl and browser. Telemetry rows landing in `copilot_messages` with full paper-relevant columns populated.

## Current Status

- ✓ v1.0 phases 0–7 shipped (2026-04-08) — drifted from no-accounts thesis, then realigned in v1.1
- ✓ v1.1 phases 08–13 shipped (2026-04-10) — account-less realignment + admin shell + 16/16 Playwright E2E green
- ✓ v1.2-prod phases 14–20 shipped (2026-04-16) — production-ready by role (participant, admin, organizer) + cross-role integration
- ✓ v1.3 phases 21, 22, 23, 24, 25, 26, 28, 29 shipped (2026-04-17) — feature expansion complete
- ⏸ Phase 27 (SMS reminders + no-show nudges, AWS SNS) — **deferred** to a later milestone (TCPA + flag-gated; not a blocker)
- ▶ v1.4 (AI Onboarding Copilot) — Phase 30 shipped 2026-05-08; phases 31–38 ahead

**v1.3 phase outcomes (9 phases, 21–29):**

- ✓ Phase 21: Orientation credit engine — `(volunteer, module_family)` credit table + organizer override + admin grant/revoke
- ✓ Phase 22: Custom form fields — organizer-editable signup questions with module-template defaults; CSV export
- ✓ Phase 23: Recurring event duplication — admin "Duplicate to weeks N…M" with atomic commit + conflict warning
- ✓ Phase 24: Scheduled reminder emails — Celery Beat kickoff + 24h + 2h with idempotency, opt-out, quiet hours
- ✓ Phase 25: Waitlist + auto-promote — public, organizer, admin surfaces; cancel-triggers-promote atomic path
- ✓ Phase 26: Broadcast messages — organizer/admin → email all signups, rate-limited + audited + dedup
- ⏸ Phase 27: SMS reminders + no-show nudges — **deferred** (AWS SNS, TCPA-gated; revisit post-v1.4)
- ✓ Phase 28: QR check-in — **shipped with deviation:** organizer-displayed event-QR + volunteer self-check-in by email (PLAN/SUMMARY written retroactively 2026-05-08; see `.planning/phases/28-qr-check-in/`)
- ✓ Phase 29: Slot swap + signup locking + past-event hiding + cross-feature integration

**Out of scope (carryover for later milestones):** UCSB production deployment, payments/donations, SSO, multi-tenant, branding, bulk QR sticker sheets.

## Next Action

Merge Phase 30 to `main`, then start Phase 31 (conversation history +
session list UI). Phase 31 inherits the working session abstraction
from Phase 30 (`GET /sessions` endpoint exists; only the UI surface
needs to be built). Locked invariants for Phase 31: do not change the
SSE wire format, do not narrow the telemetry column set, keep 100%
coverage on `app.copilot.*`.

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
*Last updated: 2026-05-08 — v1.3 marked code-complete (8/9 phases shipped, Phase 27 SMS deferred); Phase 28 PLAN + SUMMARY written retroactively to document the event-QR deviation; next action is the Stage 0 lock-in for v1.4.*
