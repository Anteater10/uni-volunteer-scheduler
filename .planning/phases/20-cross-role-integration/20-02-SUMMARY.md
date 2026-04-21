---
phase: 20-cross-role-integration
plan: 02
subsystem: docs-smoke
tags: [smoke, manual-qa, integration, docs, v1.2-prod]
requirements: [INTEG-04]
dependency-graph:
  requires:
    - backend/tests/fixtures/seed_e2e.py (seed event + admin + organizer + attended volunteer)
    - docker-compose.yml (db, redis, backend, migrate, celery_worker, celery_beat, mailpit)
    - Mailpit at http://localhost:8025 (magic-link delivery verification)
    - Frontend dev server at http://localhost:5173
  provides:
    - docs/smoke-checklist.md — single-source manual smoke pass across all three roles
    - Regression watchlist for v1.2-prod (quarterly copy, Overrides retirement, /organizer/ route, account-less participants)
  affects:
    - None (new doc, no code change)
tech-stack:
  added: []
  patterns:
    - "Plain-markdown checklist with literal copy-pasteable commands in Preconditions"
    - "Three-window protocol: admin desktop 1280×800, organizer phone 375×812, participant incognito 375×812"
    - "Sign-off block at EOF for reviewer initials + date"
key-files:
  created:
    - docs/smoke-checklist.md
    - .planning/phases/20-cross-role-integration/20-02-SUMMARY.md
  modified: []
decisions:
  - "Plain-markdown format (no scripts, no automation) — the point of INTEG-04 is human eyes on the product to catch UX / visual / copy regressions the Playwright suite misses"
  - "Use seeded event via seed_e2e.py rather than documenting an admin-UI event-create path — mirrors the 20-01 decision, keeps the checklist short enough to run in ~30 minutes"
  - "Explicit orientation-modal dual-check: once with a fresh email (modal fires), once with seeded attended_volunteer_email (modal suppressed) — catches PART-06 regression in one pass"
  - "Cross-role section (§4) notes the 20-01 audit-write finding: only ADMIN-initiated actions and public cancel are audited; participant signup.created and organizer check-in are NOT. Prevents smoke runner chasing a phantom bug"
metrics:
  duration: ~15 minutes (Task 1 only; Task 2 dry-run pending human execution)
  completed: 2026-04-17 (Task 1); Task 2 awaiting human verification
---

# Phase 20 Plan 02: Manual Smoke Checklist Summary

Shipped `docs/smoke-checklist.md` — a 185-line plain-markdown checklist that walks a human operator through all three v1.2-prod roles (admin, organizer, participant) against the local docker stack in ~30 minutes. Covers INTEG-04.

## What Shipped

| Section | Target | Checks |
|---|---|---|
| Preconditions | Stack boot | 6 numbered steps with literal docker/npm commands + three-window setup protocol |
| 1. Participant (phone 375px) | Incognito window | 10 checkboxes: `/events` → detail → orientation modal (both states) → signup → Mailpit → confirm → manage → self check-in → phone-size hygiene |
| 2. Admin (desktop 1280px) | Admin window | 10 checkboxes: Overview / Audit Logs / Users / Portals / Templates / Imports / Exports + Overrides-retirement regression + console-clean sweep |
| 3. Organizer (phone 375px) | Organizer window | 6 checkboxes: `/organizer` dashboard, tab switching, roster, tap-to-check-in, sidebar RBAC (no Users/Audit Logs/Exports) |
| 4. Cross-role loop | All three windows | 6 checkboxes: mirrors `cross-role.spec.js` Scenario 1 by human fingers; includes inline note about narrow audit-write surface finding from 20-01 |
| 5. Regressions to watch | Global sweep | 6 bullets: quarterly copy, no-student-account copy, `/organizer/` consistency, Mailpit delivery, zero failed requests, zero console errors |
| Sign-off | EOF | `Smoke passed by: ____  Date: ____` line |

## Task Status

| Task | Status | Commit |
|---|---|---|
| Task 1 — Author `docs/smoke-checklist.md` | DONE | 7d1af66 |
| Task 2 — Manual smoke-pass dry run | **AWAITING HUMAN** | n/a |

Task 2 is a `checkpoint:human-verify` gate. Per the plan, the subagent does NOT perform the manual smoke pass — Andy drives it outside the subagent. See the checkpoint section below for the exact instructions passed back to the orchestrator.

## Checkpoint Handoff (Task 2)

**What to verify:** that `docs/smoke-checklist.md` can be driven end-to-end, in one sitting, on a fresh docker stack, with every box ticked, zero manual DB nudges, and zero failed network requests.

**Acceptance:**
- Every box in the checklist ticked.
- Zero manual DB nudges required.
- Zero failed network requests across the sweep.
- Zero console errors across the sweep (or, if any, captured in `20-bugs-notes.md` for INTEG-05 triage in Plan 20-03).
- Sign-off block filled in with Andy's initials + date (commit that single-line edit).

**Resume signal:** "smoke passed — sign-off filled" OR list of checklist bugs / cross-role bugs found. Cross-role bugs get filed in `.planning/phases/20-cross-role-integration/20-bugs-notes.md` for INTEG-05 triage in Plan 20-03.

## Deviations from Plan

None for Task 1 — the checklist was authored exactly as specified in the plan's `<action>` block (Preconditions + 5 sections + sign-off). Structure, wording, and scope match the plan and the research-doc §Smoke Checklist Structure skeleton.

Task 2 has not been attempted by the subagent (by design — plan marks it `type="checkpoint:human-verify"` and the orchestrator instructed "do NOT attempt to perform the manual smoke test yourself").

## Known Stubs

None — `docs/smoke-checklist.md` is a pure-prose checklist. No placeholder data, no TODOs, no mocked content.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | 7d1af66 | docs(20-02): add v1.2-prod manual smoke checklist (INTEG-04) |

## Self-Check: PASSED

- [x] `docs/smoke-checklist.md` exists (185 lines)
- [x] Contains `Preconditions` section (1 match)
- [x] Contains `Cross-role` section (1 match)
- [x] Contains `Sign-off` block (1 match)
- [x] Commit 7d1af66 on v1.2-final
- [x] Task 2 NOT attempted (correctly deferred to human verifier per plan + orchestrator instructions)
