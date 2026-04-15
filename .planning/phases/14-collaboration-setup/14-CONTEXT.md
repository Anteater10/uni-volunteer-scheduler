# Phase 14: Collaboration setup — Context

**Gathered:** 2026-04-14
**Status:** Ready for planning
**Milestone:** v1.2-prod (production-ready by role)

<domain>
## Phase Boundary

Produce the workflow contract that lets Andy and Hung both run Claude Code + GSD on the v1.2-prod milestone in parallel without colliding. **Docs only — no app code.** Deliverables:

1. A wholesale rewrite of `docs/COLLABORATION.md` reflecting the new role-pillar split.
2. An updated `CLAUDE.md` that tells future Claude Code sessions which branch to be on for each pillar.
3. The three long-lived role branches created from `main`: `feature/v1.2-participant`, `feature/v1.2-admin`, `feature/v1.2-organizer`.
4. A verified one-day parallel test where each dev makes a trivial change on their branch and merges to main without conflict.

What this phase does **not** do: change any application code, set up CI, build any UI, or deploy anything.

</domain>

<decisions>
## Implementation Decisions

### Role assignment + machine model
- **D-01:** Hung is a real second human working on his own machine with his own clone of the repo. "Worktree" between Andy and Hung is figurative — coordination is via push/pull/PRs against shared `main`.
- **D-02:** Andy owns **Admin pillar** (Phases 16, 17, 18) **and Organizer pillar** (Phase 19). Hung owns **Participant pillar** (Phase 15). Integration (Phase 20) is shared.
- **D-03:** Hung's role is "frontend-leaning". His participant work ships first; the polished frontend patterns Hung lands (components, layout, loading/empty/error states, tailwind classes) become the template Andy then refactors into the admin and organizer pillars with small role-appropriate deviations.
- **D-04:** Phases 15 and 16 still **start in parallel** as the roadmap calls for, but Andy's UI polish for the admin pillar intentionally lags Hung's participant polish so Andy can lift Hung's patterns rather than re-invent them. Andy uses the early days of the parallel window for backend admin work + retiring the Overrides tab.
- **D-05:** Because admin and organizer are now both owned by Andy, the roadmap's "admin↔organizer shared-code-surface sequencing risk" dissolves into an intra-dev sequencing problem. Phase 19 still waits for Phase 18 to land for clean serialization, but it's now Andy scheduling against himself, not avoiding cross-dev conflict.

### Worktree layout + docker stack
- **D-06:** Andy uses **single checkout, branch switching** on his machine — no local `git worktree add` setup. One clone at the existing path, `git checkout feature/v1.2-admin` etc. when switching pillars.
- **D-07:** Hung uses the same model on his own machine — single clone, single checkout, branch switching.
- **D-08:** One docker stack at a time. Container names and ports (5173, 8000) are hardcoded in `docker-compose.yml`, and DB/Redis aren't exposed to localhost (CLAUDE.md docker-network test pattern stays unchanged).
- **D-09:** The "git-worktree" framing in REQUIREMENTS COLLAB-01 is loose — the real workflow is "role-owned long-lived branches each dev checks out on their own clone". Phase 14's COLLABORATION.md must call this out explicitly so future readers don't expect a literal `git worktree add` flow.

### File ownership rules
- **D-10:** **Pillar-domain ownership with high trust.** Each dev edits any file they need on their own role branch. The PR-only list is reserved for files where concurrent edits cause hard-to-reverse damage, not for per-pillar walls.
- **D-11:** Hung is allowed to touch anything — backend, frontend, infra — on his role branch. The PR-only list still applies to him equally; high trust does not mean ignoring the operational constraints below.
- **D-12:** **PR-only files (cross-cutting / operationally risky, both devs must approve a change):**
  - `frontend/src/lib/api.js` (shared API contract — already locked in roadmap notes)
  - `frontend/src/lib/api.public.js` (public API contract)
  - `frontend/src/App.jsx` route table (already locked in roadmap notes)
  - Shared frontend components in `frontend/src/components/ui/*` (already locked in roadmap notes)
  - `backend/app/models.py` (schema — concurrent edits risk migration drift)
  - `backend/alembic/versions/*` (Andy is single-writer; multi-head migrations are a PITA to recover from)
  - `.planning/STATE.md` (single-source-of-truth project state)
  - `.planning/ROADMAP.md` (master phase list)
  - `.planning/REQUIREMENTS-v1.2-prod.md` (joint scope contract)
  - `CLAUDE.md` (both Claude sessions read this)
  - `docs/COLLABORATION.md` (this file — joint contract)
  - `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` (stack)
  - `.github/workflows/*` (CI)
- **D-13:** **Pillar-direct files (write freely on your role branch, no PR required):**
  - **Hung / participant:** `frontend/src/pages/public/*`, public-facing route components, `e2e/` Playwright specs touching public flows, plus any backend changes Hung needs in participant-facing routers (`backend/app/routers/portals.py`, `events.py`, `signups.py` for public read paths).
  - **Andy / admin:** `frontend/src/pages/admin/*`, `frontend/src/components/admin/*`, `backend/app/routers/admin.py`, `backend/app/routers/templates.py`, `backend/app/routers/imports.py`, `backend/app/services/llm_import.py`, admin-related migrations.
  - **Andy / organizer:** `frontend/src/pages/organizer/*`, `frontend/src/components/organizer/*`, `backend/app/routers/organizer.py`, organizer-side magic-link self-checkin code.

### Sync cadence + tie-breaker
- **D-14:** **Daily 3-hour pair/sync session** between Andy and Hung. This replaces async-only commit-watching. The 3-hour window is for live alignment, joint review of shared-file changes, and pair work on cross-cutting decisions. Expect this to drop to lighter cadence once the milestone is well underway, but Phase 14 documents the heavy version because that's what's planned now.
- **D-15:** **Merge cadence:** role branches merge to `main` after each phase ships green — phase success criteria pass + Playwright is green + code review done. No mid-phase merges to main. This locks in the roadmap's "merge between phases" rule.
- **D-16:** **Tie-breaker for shared-file disagreements:** the dev whose pillar is being most affected by the change wins the call. If a `frontend/src/lib/api.js` change is being made for participant work, Hung decides; for admin or organizer, Andy decides. Tie still tied? Andy holds the casting vote as project owner.

### Existing doc handling
- **D-17:** **Wholesale rewrite** of `docs/COLLABORATION.md` at the same path. The existing file is from a prior pass and contradicts the v1.2-prod role-pillar reality (wrong roles — uses backend/frontend split; wrong scope — references waitlist/iCal features; wrong filenames — `REQUIREMENTS-v1.2.md` instead of `-v1.2-prod.md`; treats Phase 14 as UCSB infra rather than collaboration setup). One commit replaces it entirely. No archive copy.

### CLAUDE.md updates required
- **D-18:** `CLAUDE.md` currently says "Sole developer: Andy. First-time Claude Code user". This must be updated for v1.2-prod to:
  1. Acknowledge two devs (Andy + Hung).
  2. List the role pillars and their owners.
  3. Tell future Claude sessions: "Before working, run `git branch --show-current` and check the role pillar — only edit files in the pillar that owns the current branch, plus the PR-only list with explicit user permission."
  4. Keep the existing teaching-style note (Andy preference for one concept per turn), the docker-network test pattern, and the Alembic slug-revision-ID convention untouched.

### Claude's Discretion
- The exact wording / structure of the rewritten `docs/COLLABORATION.md` — must include all D-01..D-18 decisions, but layout (tables vs lists vs sections) is at the writer's discretion as long as the file is short, scannable, and self-contained.
- The exact wording of the `CLAUDE.md` branch-awareness guidance, as long as it satisfies D-18.
- Whether to add a tiny `docs/weeknotes.md` skeleton or leave it for whoever wants to start it — not a Phase 14 requirement.
- Whether to add a "GSD config sanity check" command to the daily routine doc — nice-to-have, not a hard requirement.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing Phase 14.**

### Milestone source-of-truth
- `.planning/PROJECT.md` — v1.2-prod vision + locked decisions table; the "Locked decisions 1–5" list and the "Parallel collab via git worktrees + role-owned branches" entry under Key Decisions.
- `.planning/REQUIREMENTS-v1.2-prod.md` § "Pillar 1 — Collaboration Setup" — the seven `COLLAB-01..07` requirements that Phase 14 must satisfy.
- `.planning/ROADMAP.md` § "Phase 14: Collaboration setup" — goal, dependencies, success criteria, touches list.
- `.planning/STATE.md` — current milestone status; Phase 14 is the "Next Action".

### Existing files this phase rewrites or updates
- `docs/COLLABORATION.md` — **stale, to be wholesale rewritten** (D-17). Keep it open while drafting the replacement so nothing useful gets lost. Note: existing version uses Andy=backend / Hung=frontend split, references `REQUIREMENTS-v1.2.md`, and treats Phase 14 as UCSB infra — all wrong for v1.2-prod.
- `CLAUDE.md` — root project notes. Phase 14 updates the "Sole developer" framing per D-18 but leaves the docker-network test pattern, Alembic conventions, and teaching style note intact.
- `.gitignore` — verify no role-branch artifacts need ignoring (e.g. local docker volumes, `.continue-here.md` files from `/gsd-pause-work`).

### Project conventions that Phase 14 must respect
- `CLAUDE.md` § "Running tests" — the docker-network test pattern; Hung must follow the same pattern on his clone.
- `CLAUDE.md` § "Alembic conventions" — Alembic slug-style revision IDs and the `alembic/env.py` `version_num` widening; both stay in force regardless of which dev runs migrations.
- `docker-compose.yml` — the canonical stack definition; one stack at a time per machine (D-08).

### GSD harness commands referenced in COLLABORATION.md
- `/gsd-progress` — daily session start
- `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-code-review`
- `/gsd-pr-branch`, `/gsd-ship` (PR open + push)
- `/gsd-pause-work`, `/gsd-resume-work` (context switching)
- `/gsd-workstreams create|complete` (per-dev workstreams; if not used, document why)

### Out-of-tree references (no specs to read; all in-tree)
No external ADRs, RFCs, or third-party specs are referenced for this phase. Everything Phase 14 needs lives in `.planning/`, `docs/`, `CLAUDE.md`, and the roadmap.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`docs/COLLABORATION.md` skeleton** — even though it's stale, the document structure (Roles / Hard ownership / GSD multi-dev workflow / PR & merge / Collision prevention / Onboarding / Weekly cadence / Risks / Critical files reference) is a good shape for the rewrite. Adapt the skeleton; replace the content.
- **GSD harness commands** — `/gsd-pause-work`, `/gsd-resume-work`, `/gsd-workstreams`, `/gsd-progress` are already documented in the harness. The new COLLABORATION.md just references them, doesn't redefine them.
- **CLAUDE.md teaching style + conventions sections** — preserved as-is in the update; only the "Sole developer" framing is touched.

### Established Patterns
- **Atomic green commits, no >500 LOC per commit** — already a project convention in the existing COLLABORATION.md and the v1.1 phase summaries. Carry forward.
- **Phase-branch naming `gsd/phase-N-slug`** — the GSD config has `phase_branch_template: "gsd/phase-{phase}-{slug}"`. v1.2-prod overrides this convention with `feature/v1.2-{pillar}` long-lived role branches per REQUIREMENTS COLLAB-01. Phase 14's COLLABORATION.md must explain the difference so future Claude sessions don't auto-create `gsd/phase-15-...` branches and bypass the role-branch model.
- **Docker-network test pattern** — non-negotiable. Both devs run pytest the same way (one-off container on the `uni-volunteer-scheduler_default` network with `TEST_DATABASE_URL` set). Documented in CLAUDE.md, repeated in COLLABORATION.md.
- **Alembic single-writer (Andy)** — operational constraint, not a politeness rule. Multi-head migrations require manual recovery. Keep Andy as the sole Alembic writer even though D-11 says Hung "can touch whatever he wants" — hard rule overrides high trust on this one.

### Integration Points
- **`.gitignore`** — may need entries for any per-dev local files (`.continue-here.md` if not already ignored, `node_modules`, `.venv`, etc.). Quick check during planning.
- **GSD config (`.planning/config.json`)** — `branching_strategy: "none"` and `phase_branch_template: "gsd/phase-{phase}-{slug}"` should be reconciled with the role-branch model. Possible Phase 14 task: update the config to set `branching_strategy: "feature"` or document the override in COLLABORATION.md.
- **`.planning/STATE.md`** — single source of truth for milestone state. Both devs read it; Andy writes it via GSD skills (D-12 PR-only). If Hung's GSD session writes to STATE.md from the participant branch, that's a conflict point — COLLABORATION.md must say "STATE.md flows through Andy after `/gsd-progress` runs" or similar.

</code_context>

<specifics>
## Specific Ideas

- **Daily 3-hour meetings (D-14)** are unusual for software projects but explicitly chosen by Andy. Treat as a load-bearing decision; document it as the planned cadence rather than recommending lighter alternatives. Phase 14's COLLABORATION.md should mention "expect this to relax once the milestone is in flight" so future-Andy reading the doc doesn't feel locked in.
- **"Hung's frontend patterns ship first, Andy refactors them" (D-03/D-04)** is the key parallelism refinement. The roadmap claims Phases 15 and 16 run "in parallel" — Phase 14's COLLABORATION.md must clarify that they start in parallel but Andy's UI polish lags. Otherwise downstream readers will assume both pillars race independently.
- **Single checkout + branch switching (D-06/D-07)** contradicts the literal "git worktree" wording in REQUIREMENTS COLLAB-01. The rewritten COLLABORATION.md must reconcile this gracefully — explain that the *spirit* of the requirement is "role-owned long-lived branches enabling parallel work", and the *implementation* is single checkout per dev with branch switching. Don't invent fake `git worktree add` instructions just because the requirement uses the word.
- **Hung's "some frontend" help (D-03)** is informal. COLLABORATION.md doesn't need to over-specify it; one sentence saying "Hung may also contribute frontend patterns to admin/organizer via his participant branch landing first; Andy refactors as needed" is enough.
- **High-trust pillar-domain (D-10/D-11)** is deliberately loose. The rewrite should resist the temptation to formalize it into a 30-row matrix. The PR-only list (D-12) is the only enforced wall; everything else is "use judgment, talk in the daily 3-hour sync".

</specifics>

<deferred>
## Deferred Ideas

- **Local `git worktree add` setup on Andy's machine** — opt-in convenience for later if branch switching feels too coarse. Not part of Phase 14. Andy can add it himself via `git worktree add ../uvs-organizer feature/v1.2-organizer` whenever he wants without changing the COLLABORATION.md contract.
- **Per-worktree docker stacks (different ports + `COMPOSE_PROJECT_NAME`)** — only relevant if the local-worktree opt-in above ever happens AND Andy wants two stacks side-by-side. Defer until that's a real need; needs a `docker-compose.override.yml` pattern.
- **`/gsd-workstreams` per-dev workstream dirs** — the existing stale COLLABORATION.md mentions `.planning/workstreams/<slug>/`. Phase 14 doesn't decide whether to use them or not; planner should check if the GSD harness still recommends them and either adopt or document the override.
- **`docs/weeknotes.md` append-only weekly update file** — the existing stale COLLABORATION.md describes this. Worth keeping in the rewrite but it's optional process, not a Phase 14 deliverable.
- **CI badge / role-branch protection rules on GitHub** — would be nice to set up branch protection on `main` so role branches can only land via PR. Not part of Phase 14 docs work; could be a follow-up infra task.
- **Hetzner / autonomous remote box** — the existing COLLABORATION.md mentions a Hetzner machine running `/gsd-autonomous` overnight. Not in scope for Phase 14; if it still exists, document briefly in the rewrite, otherwise drop it.
- **Reconciling `.planning/config.json` `phase_branch_template`** — the GSD config still says `gsd/phase-{phase}-{slug}` which conflicts with the role-branch model. Could be a tiny tweak in Phase 14 or deferred to whichever phase first hits the conflict. Note for the planner.

### Reviewed Todos (not folded)
None — `gsd-tools todo match-phase 14` returned zero matches.

</deferred>

---

*Phase: 14-collaboration-setup*
*Context gathered: 2026-04-14*
