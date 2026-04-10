# Remote Autonomous Run — Rules for the Hetzner Claude Instance

You are Claude Code running **unattended on a headless Hetzner server** as user `kael`, with `--dangerously-skip-permissions` on. A human (Hung) will review your work periodically from his laptop by pulling git. You must follow these rules exactly.

## Hard Rules — Never Violate

1. **Never touch any branch that isn't ours.**
   - ❌ NO `git checkout main`, `git checkout master`, `git merge main`, `git push origin main`
   - ❌ NO touching `slice6-my-signups`, `slice7-organizer-operations`, `slice8-admin-tooling`, `fix-time-slot-creation`, or any branch you didn't create
   - ✅ Stay on `gsd/phase-0-backend-completion` or create new branches under the `gsd/*` namespace only
2. **Never merge anything into `main`.** Not via CLI, not via PR, not at all. Humans do merges on the laptop.
3. **Never force-push.** Regular `git push origin gsd/<branch>` only.
4. **Never push secrets.** If you generate `.env` files, add them to `.gitignore` — do not commit.
5. **Never delete Hung's existing work.** If a file conflict comes up during a GSD phase, stop and log it.

## Frontend Visual Work — Authorized with Placeholders (updated 2026-04-08)

**Override:** Hung has authorized frontend-visual work for this run. Proceed on phases that touch frontend.
- For brand colors, logos, identity, imagery, or copy tone: **use clearly-marked placeholders** (e.g. `/* TODO(brand): replace */`, `bg-slate-900` as neutral stand-in, `Lorem` copy). Hung will replace these tomorrow on the laptop.
- For layout, spacing, responsive breakpoints, touch targets, Tailwind class structure, component composition: **make your best call** — those are reviewable in a diff.
- Do **not** pause just because a phase touches `frontend/`. Pause only if you hit an ambiguous decision that can't be resolved by "use a neutral placeholder and move on" (e.g. a structural choice that would be costly to undo).
- Mark any placeholder you leave with a `TODO(brand)` or `TODO(copy)` comment so Hung can grep for them.
- API contract / schema work that touches `frontend/` for type definitions is fine as before.

## Verification Gates

- At any `VERIFICATION.md` `human_verification` gate: commit current state, append to `.planning/remote-run.log`, and **stop** if the items require visual/UAT checks. Continue only if every item is automatable (tests, linting, type checks).
- Never mark a verification phase as "passed" on your own if it has human-facing acceptance criteria.

## Context Management

- Use `/gsd-autonomous --interactive` so plan/execute dispatch as background agents → keeps main context lean across phases.
- Between phases, if your main-window context feels heavy, run `/compact` preserving: current phase, rules from this file, `.planning/remote-run.log` contents.

## Logging

After every phase or significant action, append one line to `.planning/remote-run.log` in this format:
```
[YYYY-MM-DD HH:MM] <STATUS> phase <N> plan <M>: <one-line description>
```
Statuses: `STARTED`, `COMPLETED`, `BLOCKED`, `PAUSED`, `SKIPPED`.

## Git Workflow per Plan

1. Confirm current branch is `gsd/phase-0-backend-completion` (or an approved `gsd/*` child)
2. Run the plan
3. Commit each atomic change — commit messages follow repo convention (look at `git log`)
4. **Push after every completed plan** so the laptop can pull and review
5. Continue to next plan

## Current State (as of 2026-04-08)

- Phase 00 (backend completion) plans 00-01 through 00-04 are **complete**
- Plans **00-05 (refactor-extractions), 00-06 (pytest-integration-suite), 00-07 (playwright-e2e-ci)** are the remaining work
- Phase 1 (Mobile-first + Tailwind migration) is **frontend — skip, do not run**
- Phase 2+ (Magic-link confirmation, etc.) have no plans yet — you may plan them but pause before execution if they touch frontend

## Startup Command

On a fresh attach, the human will tell you:
> Follow `.planning/remote-run-instructions.md`. Run `/gsd-autonomous --from 0 --to 0 --interactive` to finish phase 0 plans 05–07. Log everything to `.planning/remote-run.log`. Stop at the first frontend-visual requirement.
