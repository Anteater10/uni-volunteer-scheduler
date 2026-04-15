# Collaboration Contract

Two developers (Andy and Hung) running Claude Code + GSD on the UCSB Sci Trek volunteer scheduler in parallel for the v1.2-prod milestone (production-ready by role). This doc is the operational contract for that parallel work.

**Status:** v1.1 merged into `main`. Next milestone: v1.2-prod (production-ready by role).

**This is a wholesale rewrite** of a prior collaboration doc that used a role split no longer accurate for v1.2-prod, referenced an outdated requirements filename, and treated Phase 14 as UCSB infra work. None of that applies here. The canonical requirements file is `.planning/REQUIREMENTS-v1.2-prod.md`.

---

## Roles (D-02, D-03, D-04, D-05)

| Pillar | Owner | Phases |
|---|---|---|
| **participant** | Hung | Phase 15 |
| **admin** | Andy | Phases 16, 17, 18 |
| **organizer** | Andy | Phase 19 |
| Integration | Shared | Phase 20 |

**Hung is frontend-leaning.** His participant pillar ships first; the polished frontend patterns he lands (components, layout, loading/empty/error states, Tailwind classes) become the template Andy refactors into admin and organizer with role-appropriate deviations.

**Phases 15 (participant) and 16 (admin) start in parallel** as the roadmap calls for, but Andy's UI polish for admin intentionally lags Hung's participant polish so Andy can lift Hung's patterns rather than reinvent them. Andy uses the early parallel window for backend admin work and retiring the Overrides tab.

**Admin and organizer are both Andy's** — the cross-dev shared-code sequencing risk that would exist if they were split collapses into an intra-Andy scheduling problem. Phase 19 (organizer) still waits for Phase 18 (admin LLM imports) to land for clean serialization, but that is Andy scheduling against himself.

Use the exact pillar names `participant`, `admin`, `organizer` — all grep-friendly.

---

## Machine model and worktree explanation (D-01, D-06, D-07, D-08, D-09)

**Hung is a real second human working on his own machine** with his own clone of the repo. Coordination is via push/pull/PRs against the shared `main` branch. There is no shared filesystem between Andy and Hung.

**Each dev uses single checkout, branch switching on their own machine** — no multiple simultaneous working trees needed. Andy has one clone at his existing repo path and runs `git checkout feature/v1.2-admin` (or `feature/v1.2-organizer`) to switch pillars. Hung does the same on his machine with `feature/v1.2-participant`.

**Reconciling the REQUIREMENTS wording:** COLLAB-01 in `.planning/REQUIREMENTS-v1.2-prod.md` uses "git-worktree" as loose shorthand. The spirit of COLLAB-01 is "role-owned long-lived branches enabling parallel work"; the implementation is one clone per dev with `git checkout` to switch. No additional working tree setup is needed or used.

**One docker stack at a time per machine.** Container names and ports (5173 frontend, 8000 backend) are hardcoded in `docker-compose.yml`. DB and Redis are not exposed to localhost — both devs run pytest via the docker-network pattern documented in `CLAUDE.md`:

```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

This pattern is non-negotiable for both devs. See `CLAUDE.md` for the full setup including first-time `CREATE DATABASE test_uvs`.

---

## The three long-lived role branches (D-06, D-07, D-09)

```
feature/v1.2-participant   # Hung — Phase 15
feature/v1.2-admin         # Andy — Phases 16, 17, 18
feature/v1.2-organizer     # Andy — Phase 19
```

All three are created from `main` once at Phase 14, live for the entire v1.2-prod milestone, and merge back to `main` only after each phase ships green (see Merge Cadence below). Do not create `gsd/phase-15-...` branches that bypass this model — the GSD config `phase_branch_template` is overridden by this collaboration contract.

---

## File ownership rules (D-10, D-11, D-12, D-13)

### PR-only files — both devs must approve any change

These files are cross-cutting or operationally risky. A change touching any of them must go through a PR reviewed by both Andy and Hung before landing on any role branch or `main`.

| File / Glob | Why PR-only |
|---|---|
| `frontend/src/lib/api.js` | Shared API contract — locks both pillars simultaneously |
| `frontend/src/lib/api.public.js` | Public API contract |
| `frontend/src/App.jsx` | Route table — affects every pillar |
| `frontend/src/components/ui/*` | Shared design system components |
| `backend/app/models.py` | Schema — concurrent edits risk migration drift |
| `backend/alembic/versions/*` | Andy is the single Alembic writer (see hard rule below) |
| `.planning/STATE.md` | Single-source-of-truth project state |
| `.planning/ROADMAP.md` | Master phase list |
| `.planning/REQUIREMENTS-v1.2-prod.md` | Joint scope contract |
| `CLAUDE.md` | Both Claude sessions read this |
| `docs/COLLABORATION.md` | This file — joint contract |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | Stack definition |
| `.github/workflows/*` | CI — quality gates |

**Hard rule overriding high trust:** Andy is the single Alembic writer. `backend/alembic/versions/*` is Andy-only regardless of D-11. Multi-head migrations are operationally painful to recover from. If Hung needs a schema change, file a ticket or ping Andy in the daily sync.

### Pillar-direct files — write freely on your role branch

**High trust** — each dev edits any file they need on their own role branch. The PR-only list above is the only enforced wall. Resist formalizing this into a 30-row matrix.

**Hung / participant domain:**
- `frontend/src/pages/public/*`
- Public-facing route components
- `e2e/` Playwright specs touching public flows
- Backend changes Hung needs in participant-facing routers:
  `backend/app/routers/portals.py`, `backend/app/routers/events.py` (read paths), `backend/app/routers/signups.py` (read paths)

**Andy / admin domain:**
- `frontend/src/pages/admin/*`
- `frontend/src/components/admin/*`
- `backend/app/routers/admin.py`
- `backend/app/routers/templates.py`, `backend/app/routers/imports.py`
- `backend/app/services/llm_import.py`
- Admin-related migrations (Andy-only as noted above)

**Andy / organizer domain:**
- `frontend/src/pages/organizer/*`
- `frontend/src/components/organizer/*`
- `backend/app/routers/organizer.py`
- Organizer-side magic-link self-checkin code

Hung may also contribute frontend patterns that land in his participant branch first; Andy refactors them into admin and organizer as needed. This is informal — one sentence is all the formality it needs.

---

## Sync cadence (D-14)

**Daily 3-hour pair/sync session** between Andy and Hung. This is unusual cadence for a software project but explicitly chosen. The 3-hour window is for live alignment, joint review of shared-file changes, and pair work on cross-cutting decisions.

Disagreements that are not tie-breaker calls (see Conflict Resolution below) go to the daily 3-hour sync, not async commit-watching.

Expect this to relax to a lighter cadence once the milestone is well underway. Phase 14 documents the heavy version because that is what is planned now.

---

## Merge cadence (D-15)

Role branches merge to `main` **after each phase ships green**. The three gates are:
1. Phase success criteria pass
2. Playwright suite green
3. Code review done (both devs)

**No mid-phase merges to main.** If a shared-file fix is urgent, open a hotfix PR directly on `main` and rebase both role branches on main within 24 hours.

---

## GSD harness command flow

Both devs use the same GSD commands. Per phase:

| Command | When |
|---|---|
| `/gsd-progress` | Daily session start — reads STATE + gives next action |
| `/gsd-plan-phase <N>` | Before executing a phase |
| `/gsd-execute-phase <N>` | Main work loop — atomic commits per task |
| `/gsd-verify-work <N>` | Goal-backward check against success criteria |
| `/gsd-code-review <N>` | Self-review before opening PR |
| `/gsd-pr-branch` | Strips `.planning/` noise from PR diff |
| `/gsd-ship` | Pushes + opens PR |
| `/gsd-pause-work` | Context switch or end of session — writes `.continue-here.md` |
| `/gsd-resume-work` | Next session — restores full state |

These are documented in the GSD harness. This file references them; it does not redefine them.

**`.planning/STATE.md` is PR-only** (D-12). Changes flow through Andy via `/gsd-progress` rather than direct edits from either dev's role branch. If Hung's GSD session writes to STATE.md from the participant branch, that is a conflict point — pull Andy in at the next sync.

---

## Conflict resolution and tie-breaker (D-16, COLLAB-07)

### Tie-breaker rule

The dev whose pillar is being most affected by a shared-file change wins the call:
- `frontend/src/lib/api.js` change for participant work → Hung decides
- `frontend/src/lib/api.js` change for admin or organizer work → Andy decides
- Tied still tied? **Andy holds the casting vote** as project owner.

### Rebase on main

When shared files change on `main`, role branches rebase (not merge) to keep history clean. Do not let a role branch drift more than ~24 hours behind `main` during the parallel window.

### Daily sync as the escalation path

Disagreements that do not resolve via the tie-breaker rule go to the daily 3-hour sync, not to async comment threads.

---

## Critical files reference

| File | Purpose | Owner |
|---|---|---|
| `docs/COLLABORATION.md` | This file — joint contract | Joint (PR-only) |
| `CLAUDE.md` | Project notes for Claude (stack, test pattern, Alembic conventions, teaching style) | Joint (PR-only) |
| `.planning/ROADMAP.md` | Master phase list (14–20) | Joint (PR-only) |
| `.planning/STATE.md` | Current project status — Andy writes via GSD | Andy via `/gsd-progress` |
| `.planning/REQUIREMENTS-v1.2-prod.md` | Joint scope contract for v1.2-prod | Joint (PR-only) |
| `feature/v1.2-participant` | Hung's long-lived role branch | Hung |
| `feature/v1.2-admin` | Andy's admin role branch | Andy |
| `feature/v1.2-organizer` | Andy's organizer role branch | Andy |
| `docker-compose.yml` | Canonical stack — one stack at a time per machine | Joint (PR-only) |
| `backend/alembic/versions/*` | Migrations — Andy single-writer | Andy only |
| `.github/workflows/*` | CI quality gates | Joint (PR-only) |

---

## Optional

A `docs/weeknotes.md` append-only weekly log is optional. If anyone wants to start one, append three bullets at end of each Friday session: what shipped, what's in flight, what's next. Not a Phase 14 deliverable.
