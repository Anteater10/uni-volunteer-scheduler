---
phase: 14-collaboration-setup
plan: "01"
subsystem: docs
tags: [collaboration, v1.2-prod, documentation, collab-contract]
dependency_graph:
  requires: []
  provides: [docs/COLLABORATION.md v1.2-prod contract]
  affects: [.planning/REQUIREMENTS-v1.2-prod.md, CLAUDE.md]
tech_stack:
  added: []
  patterns: [wholesale-doc-rewrite, D-series-decision-encoding]
key_files:
  created: []
  modified:
    - docs/COLLABORATION.md
decisions:
  - "Wholesale rewrite at same path — no archive copy per D-17"
  - "Phrase 'git worktree add' removed to avoid false instruction signal; 'single checkout, branch switching' used instead"
  - "Self-referential entry in PR-only table so future readers recognize this file as joint-owned"
metrics:
  duration_minutes: 3
  completed: "2026-04-15"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 14 Plan 01: Collaboration Contract Rewrite Summary

Wholesale rewrite of `docs/COLLABORATION.md` encoding all 18 locked decisions (D-01..D-18) from `14-CONTEXT.md` for the v1.2-prod milestone: role-pillar model with three named long-lived branches, PR-only file list, daily 3-hour sync cadence, and pillar-most-affected tie-breaker with Andy's casting vote.

## What Was Done

**Task 1:** Replaced the entire contents of `docs/COLLABORATION.md`. The prior file used an Andy=backend / Hung=frontend role split, referenced `REQUIREMENTS-v1.2.md` (wrong filename), described waitlist/iCal features (old scope), and had a Hetzner autonomous execution section (not in v1.2-prod scope). All of that was discarded.

The new file is 200 lines of markdown organized into sections:
- Header / status block with reference to `.planning/REQUIREMENTS-v1.2-prod.md`
- Role assignment table (participant → Hung, admin → Andy, organizer → Andy, integration → shared)
- Machine model explanation (single checkout + branch switching per dev, one docker stack at a time)
- Three long-lived role branches named verbatim
- PR-only file list with 13 canonical entries from D-12
- Pillar-direct domain examples for both devs
- Daily 3-hour sync cadence
- Merge cadence (after each phase ships green, no mid-phase merges)
- GSD command reference table
- Conflict resolution + tie-breaker rule (casting vote)
- Critical files reference table

**Task 2:** Cross-decision verification of D-01..D-17. Found one issue: the phrase `git worktree add` appeared in explanatory sentences (saying "not literal `git worktree add`"), which triggered the D-06 negative grep check. Fixed by rewording those sentences to convey the same meaning without the phrase. All 17 decision checks now pass.

## Decisions Encoded

| Decision | Where in file |
|---|---|
| D-01 — Hung is real second human on own machine | Machine model section |
| D-02 — Andy owns admin + organizer; Hung owns participant | Role table |
| D-03 — Hung frontend-leaning, patterns ship first | Role section prose |
| D-04 — Phases 15 and 16 start in parallel; Andy's UI lags | Role section prose |
| D-05 — admin/organizer is intra-Andy | Role section prose |
| D-06 — single checkout, branch switching (no literal worktree) | Machine model section |
| D-07 — Hung uses same model on his machine | Machine model section |
| D-08 — one docker stack at a time, ports 5173/8000 | Machine model section + code block |
| D-09 — reconcile COLLAB-01 'git-worktree' wording | Machine model section (Reconciling paragraph) |
| D-10 — high-trust pillar-domain ownership | File ownership section |
| D-11 — Hung allowed to touch anything (PR-only still applies) | File ownership section |
| D-12 — PR-only file list (13 canonical entries) | PR-only table |
| D-13 — pillar-direct domain examples | Pillar-direct section |
| D-14 — daily 3-hour sync | Sync cadence section |
| D-15 — merge after phase ships green, no mid-phase | Merge cadence section |
| D-16 — pillar-most-affected wins, Andy casting vote | Conflict resolution section |
| D-17 — wholesale rewrite (verified by file's new content) | Entire file |
| D-18 — CLAUDE.md updates | Out of scope for Plan 01 (Plan 02) |

## Acceptance Criteria Results

All checks pass:
- `feature/v1.2-participant` present
- `feature/v1.2-admin` present
- `feature/v1.2-organizer` present
- `single checkout` / `branch switching` present
- `daily 3-hour` present
- `REQUIREMENTS-v1.2-prod.md` present (correct filename)
- `REQUIREMENTS-v1.2.md` (wrong filename) absent
- `casting vote` present
- `ships green` present
- `Hetzner`, `waitlist`, `iCal`, `v1.2-prod-deploy` all absent
- All D-12 PR-only filenames present
- `ALL_CHECKS_PASS` from Task 2 verify block

## Diff Stats

Prior file: 225 lines
New file: 200 lines
Net change: 137 insertions, 161 deletions (from git log)

## Deviations from Plan

**1. [Rule 1 - Bug] Removed 'git worktree add' phrase during Task 2 verification**
- **Found during:** Task 2 D-06 negative grep check
- **Issue:** Explanatory sentences mentioning "NOT literal `git worktree add`" caused `! grep -q "git worktree add"` to fail
- **Fix:** Rewrote two sentences to say "no multiple simultaneous working trees needed" and "no additional working tree setup is needed or used"
- **Files modified:** `docs/COLLABORATION.md`
- **Commit:** `8fc923e`

## Known Stubs

None — all sections are fully written and self-contained.

## Commits

| Hash | Message |
|---|---|
| `662c04a` | feat(14-01): wholesale rewrite of docs/COLLABORATION.md for v1.2-prod |
| `8fc923e` | fix(14-01): remove 'git worktree add' phrase from COLLABORATION.md |

## Self-Check: PASSED

- `docs/COLLABORATION.md` exists: FOUND
- Commit `662c04a` exists: FOUND
- Commit `8fc923e` exists: FOUND
- All required tokens present: `feature/v1.2-participant`, `feature/v1.2-admin`, `feature/v1.2-organizer`, `REQUIREMENTS-v1.2-prod.md`, `CLAUDE.md`
