# Project State

**Project:** Uni Volunteer Scheduler (UCSB Sci Trek)
**Initialized:** 2026-04-08
**Mode:** YOLO · Standard granularity · Parallel execution · Research/Plan-Check/Verifier all ON
**Deadline:** Before June 2026

## Current Position

**Milestone:** v1.1 Account-less realignment
**Phase:** Not started (defining phase structure)
**Plan:** —
**Status:** Milestone opened 2026-04-09; gsd-roadmapper about to run against REQUIREMENTS-v1.1-accountless.md
**Last activity:** 2026-04-09 — Stage 0 (baseline stabilization) committed as `d74e708`; Stage 1 (requirements lock) wrote `.planning/REQUIREMENTS-v1.1-accountless.md`; Stage 2 (milestone + roadmap) kicking off.

## Current Status

- ✓ v1.0 phases 0–7 code-complete (but drifted from no-accounts thesis — see PROJECT.md milestone v1.1)
- ✓ Stage 0 baseline stabilization merged into `gsd/phase-0-backend-completion`
- ✓ REQUIREMENTS-v1.1-accountless.md — Stage 1 locked decisions
- ⏳ ROADMAP.md — pending gsd-roadmapper run
- ⏳ v1.1 phase planning — not started

## Next Action

Run gsd-roadmapper against `.planning/REQUIREMENTS-v1.1-accountless.md` to produce a phase breakdown, then `/gsd-plan-phase <first-phase>` once the roadmap is approved.

## Accumulated Context

### Stage 0 findings (still relevant for v1.1 phases)
- Alembic chain uses slug-style revision IDs; `alembic/env.py` pre-widens `version_num` to VARCHAR(128). Do not regress.
- Known latent bug: `downgrade()` functions leak postgres enum types (`privacymode` confirmed, others likely). Fold cleanup into v1.1 schema migration phase.
- Docker stack quirk: db/redis not exposed to host. Tests run via one-off container on `uni-volunteer-scheduler_default` network. See CLAUDE.md.
- Phase 5.07 LLM CSV extraction still blocked on real Sci Trek CSV from Hung.

### v1.0 surface map
- **Retiring:** Phase 2 account-confirmation flow (repurposing magic-link infra), Phase 4 prereq enforcement, Phase 7 override UI, student login/register frontend pages.
- **Keeping:** Phase 0 schema scaffolding, Phase 1 Tailwind design system + components, Phase 3 check-in state machine + organizer roster, Phase 5 CSV template import (deterministic parts), Phase 6 notifications, Phase 7 audit log / analytics / CCPA export.

## Key Decisions Log

See `.planning/PROJECT.md` → Key Decisions.

## Open Questions

See `.planning/PROJECT.md` → Open Questions and `.planning/REQUIREMENTS-v1.1-accountless.md` → Open items for Stage 2.

---
*Last updated: 2026-04-09 — v1.1 milestone opened*
