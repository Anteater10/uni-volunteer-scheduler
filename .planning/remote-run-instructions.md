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

## No Frontend Visual Work

You are headless — no browser, no visual verification. Rules:
- If a phase / plan is purely backend / infra / migrations / tests / API work → **run it**
- If a phase touches `frontend/` directories for visual/UX/styling/layout work → **STOP**, append a note to `.planning/remote-run.log`:
  ```
  [YYYY-MM-DD HH:MM] PAUSED at phase <N>: frontend visual work — awaiting laptop verification
  ```
  Then exit the autonomous run cleanly.
- API contract / schema work that happens to touch `frontend/` for type definitions **is fine** — use your judgment.

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
