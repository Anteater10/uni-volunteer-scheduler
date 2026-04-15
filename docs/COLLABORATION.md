# Collaboration Contract

Two developers (Hung, Andy) shipping the UCSB Sci Trek volunteer scheduler to production before June 2026 graduation handoff. Both use Claude Code + GSD. This doc is the operational contract — read once, reference often. Both Claude sessions read this too.

**Status:** v1.0 + v1.1 merged into `main` (tag `v1.1.0`). Next milestone: `v1.2-prod-deploy`.

---

## Roles

- **Andy** — backend, infra, DB, Celery, deployment, CI pipelines.
- **Hung** — frontend, UX, Playwright E2E, accessibility, copy, user-facing docs.

Neither dev should be "blocked" by the other in normal operation. API contract changes are the only coupling point — see "Joint review" below.

---

## Hard ownership rules

### Andy-only writes

- `backend/alembic/versions/*` — **single writer**. Prevents multi-head migrations. Andy runs `alembic heads` before every migration and aborts if >1.
- `backend/app/models.py`, `backend/app/services/*`, `backend/app/routers/*`, `backend/app/celery_app.py`, `backend/app/main.py`, `backend/app/deps.py`
- `docker-compose.yml`, `backend/Dockerfile`, infra scripts
- `.github/workflows/*`
- `.planning/STATE.md` (via `/gsd-progress` or `/gsd-next` — not manual)

### Hung-only writes

- `frontend/src/*` (pages, components, state, lib, styles)
- `e2e/*` Playwright specs
- `docs/*` user-facing docs (`HANDOFF.md`, admin guide, volunteer guide, this file)
- `.planning/ROADMAP.md` edits (after initial GSD generation)

### Joint review (both must approve)

- `frontend/src/lib/api.js`, `frontend/src/lib/api.public.js` — API contract. Changes to this file go in the same PR as the backend change, or in tightly coupled back-to-back PRs.
- `.planning/REQUIREMENTS-v1.2.md` — scope contract. Changed only by explicit joint decision.
- `.github/workflows/ci.yml` quality-gate changes (adding new test suites is OK solo).

---

## Shared source of truth

| File | Purpose | Owner |
|------|---------|-------|
| `.planning/ROADMAP.md` | Master phase list (14-20) with owners, deps, dates | Hung writes, Andy reviews |
| `.planning/STATE.md` | Current project status, last activity, next action | Andy writes via GSD skills |
| `.planning/REQUIREMENTS-v1.2.md` | v1.2 feature scope lock | Joint |
| `.planning/PROJECT.md` | Product thesis + open questions | Joint |
| `docs/COLLABORATION.md` | This file | Hung |
| `docs/OPERATIONS.md` | Deployment runbook (to be written in Phase 16) | Andy |
| `docs/HANDOFF.md` | Post-June maintainer handoff (Phase 20) | Hung |

---

## GSD multi-dev workflow

### Shared setup (runs once, by Andy, after v1.1.0 merge lands)

```
/gsd-new-milestone v1.2-prod-deploy
```

This generates `.planning/ROADMAP.md` with phases 14-20 and `.planning/REQUIREMENTS-v1.2.md`. Scope must be pre-decided in a 30-min joint call before running this — GSD reads REQUIREMENTS to generate the ROADMAP.

### Per-phase workflow (each dev, independently)

```
# Claim the phase
/gsd-workstreams create <phase-slug>        # creates .planning/workstreams/<slug>/

# Plan it
/gsd-plan-phase <N>                         # writes <N>-PLAN.md in your workstream

# Execute
/gsd-execute-phase <N>                      # atomic commits, runs tests per task

# Verify
/gsd-verify-work <N>                        # goal-backward check against phase success criteria

# Review your own code before shipping
/gsd-code-review <N>                        # flags issues; fix them
/gsd-code-review-fix                        # auto-fix trivial findings

# Ship
/gsd-pr-branch                              # strips .planning/ from PR diff
/gsd-ship                                   # pushes + opens PR (but let the reviewer merge)

# After PR merges to main
/gsd-workstreams complete <slug>            # merges workstream STATE back into shared STATE.md
```

### Daily loop

- **Start of session:** `/gsd-progress` reads shared STATE + your workstream; tells you what's unblocked.
- **Mid-work:** your Claude operates only in your workstream dir — never touches the other dev's files (enforced by ownership rules above).
- **Context switch or stop:** `/gsd-pause-work` — writes `.continue-here.md` so tomorrow's session picks up cleanly.
- **Next morning:** `/gsd-resume-work` restores full state.

### Workstream isolation rule

Your workstream is your private workspace. Never commit to `.planning/STATE.md` or `.planning/ROADMAP.md` from inside a workstream — those changes flow through `/gsd-workstreams complete`. If you need a ROADMAP change mid-phase (e.g. dependency discovered), stop, commit a 1-line ROADMAP fix to main as its own PR, then resume the workstream.

---

## PR & merge workflow

1. Work on a feature branch. Name it: `phase-<N>-<slug>` (e.g. `phase-14-infra-staging`).
2. Commit cadence: atomic green commits. No >500 LOC per commit.
3. Run `/gsd-code-review` before opening PR.
4. Use `/gsd-pr-branch` — your PR excludes `.planning/` noise. Reviewers see only code diff.
5. Open PR against `main`. Title format: `feat(<N>-<plan>): <short>` matching commit convention.
6. CI must be green before review requested.
7. Reviewer = the other dev. Review required if PR is >200 LOC **or** touches Alembic, auth, deployment, or API contract.
8. Pure-frontend copy/style PRs <200 LOC can self-merge after CI green.
9. After merge, the author runs `/gsd-workstreams complete <slug>` to sync STATE.md.

### Quality gates (minimum bar)

Every PR merged to main must have:

1. **CI green:** pytest (≥206 baseline), vitest (≥78 baseline), Playwright (16/16 baseline + any new specs).
2. **Alembic round-trip** (CI-enforced on any PR touching `backend/alembic/` or `backend/app/models.py`): `upgrade head → downgrade base → upgrade head`.
3. **One human review** from the other dev per the threshold rule above.
4. **Deployment PRs:** staging URL 200-OK smoke test is a required check.

Two real gates: CI green + one human eyeball on substantive diffs. No approval theater.

### Rollback protocol

If main's Playwright suite goes red after a merge: the merger has **2 hours** to revert or forward-fix. No exceptions. If both devs are away, whoever is online first reverts.

---

## Collision prevention

1. **Alembic multi-head:** Andy-only. PR title must include revision ID (e.g. `feat(19-02): migration 0012_waitlist_table`). Hung never creates a migration; if schema is needed, file a ticket or ping Andy.
2. **API contract drift:** any new backend endpoint or signature change → `frontend/src/lib/api.public.js` updated in the same PR (or the immediate next PR, with cross-links).
3. **`.planning/` conflicts:** solved by workstream isolation above. If you ever see a merge conflict in `.planning/STATE.md`, stop — something bypassed the workflow. Resolve by hand, notify the other dev.
4. **Parallel commits breaking E2E:** rebase feature branches onto main daily; don't let a branch drift more than 24h behind main.
5. **Commit-cadence discipline:** no >500 LOC diffs per commit; each phase checkpoint is an atomic green commit.

---

## Autonomous (Hetzner) execution

There's a Hetzner box that can run `/gsd-autonomous` unattended. Use it for deterministic, test-covered work:

**Safe to run autonomous:**
- Deterministic backend validators / importers (Phase 15 sub-plans).
- Accessibility lint fixes, copy-only PRs (Phase 17 sub-plans).
- Backlog items (`.planning/999.x`).
- Overnight test-baseline runs.

**Never autonomous:**
- Infra decisions (Phase 14).
- Production deployment (Phase 16 — irreversible).
- Handoff docs (Phase 20 — judgment required).
- Any PR touching secrets, schema, or auth.

Schedule via `CronCreate` for nightly backlog passes. Follow `remote-run-instructions.md` at repo root.

---

## Onboarding — your first session

### If you're Hung:
1. `cd ~/Desktop/uni-volunteer-scheduler` (main repo) — wait for `v1.1.0` merge to land.
2. `git pull`.
3. `/gsd-progress` — see current state.
4. Begin Phase 17 discovery in parallel with Andy's Phase 14.

### If you're Andy:
1. `cd <your-repo-path>` on main.
2. `git pull`.
3. **First run:** `/gsd-new-milestone v1.2-prod-deploy` — generates the shared roadmap. Do this only after you and Hung have agreed on 2-3 v1.2 features.
4. `/gsd-workstreams create andy-phase-14-infra`.
5. `/gsd-plan-phase 14`.
6. Phase 14 hard deadline: UCSB infra target chosen by **2026-04-21**. Fallback: DigitalOcean droplet.

### Joint: v1.2 scoping call (30 min, before Andy runs `/gsd-new-milestone`)

Pick 2-3 of these v1.2 features (all must avoid schema changes outside of one Andy-owned Alembic migration):

- **Waitlist + auto-promote** — when a slot is full, collect waitlist; Celery task promotes on cancel.
- **iCal export** — confirmed signups return a `.ics` attachment in the confirmation email + download link on manage page.
- **Bulk signup for school groups** — organizer-facing endpoint to create N signups for a cohort email list.
- **Organizer attendance analytics** — dashboard card with quarter-over-quarter attendance trends per school.

Lock the decision in `.planning/REQUIREMENTS-v1.2.md` before running `/gsd-new-milestone`.

---

## Weekly cadence (zero-meeting)

- **Monday:** each dev runs `/gsd-progress`. 5 min.
- **Throughout week:** daily `git push` of WIP; `/gsd-pause-work` if dropping mid-phase.
- **Friday:** each dev commits a 3-bullet update to a `docs/weeknotes.md` (new file, append-only). What shipped, what's in flight, what's next.
- **Blockers:** `@` mention in commit message or PR description; other dev responds within 24h.

No standups, no story points, no sprint ceremonies. The tests + ROADMAP checkmarks are the status report.

---

## Top 3 risks

1. **v1.2 scope creep blows the deadline.** Mitigation: `REQUIREMENTS-v1.2.md` locked end of week 1. No new features after week 3. Late asks → `.planning/999.x` backlog for post-June handoff.
2. **UCSB infra decision stalls.** Hard deadline 2026-04-21. Fallback = DigitalOcean droplet with documented migration path. Staging on DO is enough for UAT.
3. **AI regenerates the other dev's in-flight code.** Enforced commit cadence, ownership walls, `/gsd-pause-work` before context switches. If PRs start overlapping, fall back to whole-phase ownership until re-synced.

---

## Critical files reference

- `.planning/ROADMAP.md` — master phase list. Generated by GSD after v1.2 scoping.
- `.planning/STATE.md` — Andy-owned via GSD skills.
- `.planning/REQUIREMENTS-v1.2.md` — jointly locked.
- `backend/alembic/versions/` — Andy single-writer. Current head: `0010`.
- `frontend/src/lib/api.public.js` — joint API contract.
- `.github/workflows/ci.yml` — quality gates.
- `remote-run-instructions.md` — Hetzner handoff rules.
- `docs/OPERATIONS.md` — deployment runbook (to be written in Phase 16).
- `docs/HANDOFF.md` — post-June handoff (to be written in Phase 20).
