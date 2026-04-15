# Phase 14: Collaboration setup — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `14-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 14-collaboration-setup
**Areas discussed:** Role assignment + machine model, Worktree layout + docker stack, File ownership rules, Sync cadence + tie-breaker, Existing COLLABORATION.md fate

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|:---:|
| Role assignment + machine model | Who owns participant / admin / organizer; is Hung a separate human or a parallel Claude session | ✓ |
| Worktree layout + docker stack | Where worktrees live; how docker stacks coexist | ✓ |
| File ownership rules | What's PR-only vs role-branch direct beyond the locked files | ✓ |
| Sync cadence + tie-breaker | Daily rhythm; merge cadence; who breaks ties on shared-file changes | ✓ |

**Result:** All four areas selected for discussion.

---

## Area 1 — Role assignment + machine model

### Q1 — Who is Hung and where does he run Claude Code?

| Option | Description | Selected |
|--------|-------------|:---:|
| Real human, his own machine | Hung is a separate person with his own clone of the repo. Coordination via push/pull/PRs. "Worktree" becomes shorthand for "each dev has their own checkout on their own machine." | ✓ |
| Two Claude sessions, my machine | Hung is a label for a second Claude Code session on Andy's machine. Real `git worktree add` with multiple checkouts. | |
| Both — Hung is real but I also want local parallelism | Hung exists on his own machine AND Andy wants local worktrees too. | |

**User's choice:** Real human, his own machine.
**Notes:** Locks in that the worktree workflow is figurative between devs — coordination is via PRs against shared `main`. Real `git worktree` only matters if either dev wants local parallelism on their own machine.

### Q2 — How should the role pillars split between Andy and Hung?

| Option | Description | Selected |
|--------|-------------|:---:|
| Andy = Admin (16-18), Hung = Participant + Organizer (15, 19) | Andy takes the biggest pillar. Hung takes both frontend-heavy audit pillars. | |
| Andy = Participant + Organizer (15, 19), Hung = Admin (16-18) | Inverted split. | |
| Split admin: Andy = Admin shell + LLM, Hung = Templates + Participant, Organizer shared | Three-way load-balance with more coordination overhead. | |
| Andy owns everything, Hung pairs/reviews | Solo execution with Hung as the second pair of eyes. | |
| **Other (free text)** | Hung does participant + some frontend; Andy does admin + organizer. | ✓ |

**User's choice:** "Hung does participant and some frontend, andy does admin and organiser"
**Notes:** Resolves the admin↔organizer "shared-code surface" sequencing risk in the roadmap — both pillars are now Andy's, so there's no inter-dev conflict. Phase 19 still waits for Phase 18 to land for clean intra-dev sequencing. Integration (Phase 20) stays shared.

### Q3 — How does Hung's "some frontend" help land in admin/organizer?

| Option | Description | Selected |
|--------|-------------|:---:|
| Hung opens PRs against Andy's admin/organizer branches | Hung pushes frontend commits directly to Andy's role branches via PRs. | |
| Hung sends PRs to main only; Andy cherry-picks / rebases | Frontend help lands in main as standalone PRs. | |
| Hung helps inside the participant branch only | Hung stays on his branch; shared-component fixes flow via main when the participant branch merges. | |
| Loose — figure it out per situation | No fixed rule. | |
| **Other (free text)** | Hung mainly fixes participant frontend; Andy then refactors those patterns into admin/organizer with little deviations based on preferences. | ✓ |

**User's choice:** "Hung mainly will fix the frontend for participants and then we can refactor that to be used for admin/organiser with little deviations based on preferences obviously"
**Notes:** Important parallelism refinement — Phases 15 and 16 still **start** in parallel, but Andy's UI polish work intentionally lags Hung's participant polish so Andy can lift Hung's patterns rather than re-invent them. Andy uses the early days of the parallel window for backend admin work (retire Overrides, build Overview/Audit/Users CRUD endpoints).

---

## Area 2 — Worktree layout + docker stack

### Q4 — How should the local worktree + docker setup work for Andy?

| Option | Description | Selected |
|--------|-------------|:---:|
| Single checkout, switch branches | One clone at the existing path. `git checkout feature/v1.2-admin` etc. Docker stack runs from the active checkout. Simplest. | ✓ |
| Local worktrees, one docker stack at a time | Real `git worktree add ../uvs-admin feature/v1.2-admin`. Only one docker stack runs at a time (port collision otherwise). | |
| Local worktrees + per-worktree docker (different ports/projects) | Real worktrees + per-worktree `COMPOSE_PROJECT_NAME` to allow two stacks side-by-side. | |

**User's choice:** Single checkout, switch branches.
**Notes:** Resolves docker question simultaneously — only one stack runs at a time naturally. Means the literal "git worktree" framing in REQUIREMENTS COLLAB-01 has to be reconciled in the rewritten COLLABORATION.md as "role-owned long-lived branches each dev checks out on their own clone", not as a literal `git worktree add` workflow.

---

## Area 3 — File ownership rules

### Q5 — What's the principle for file ownership beyond the locked-in PR-only files?

| Option | Description | Selected |
|--------|-------------|:---:|
| Pillar-domain ownership | Files clearly belonging to one pillar are direct-write on that role branch. Only true cross-cutting files are PR-only. | ✓ |
| Conservative — most things PR-only | Add many more files to the PR-only list (models.py, schemas, all routers, planning docs). Slower but very low conflict risk. | |
| Loose — only the locked files are PR-only | Trust pillar separation to keep edits apart; only the 3 locked files are PR-only. | |
| Andy single-writer for backend + infra, otherwise pillar-domain | Pillar-domain for frontend; backend + infra are Andy-only. | |

**User's choice:** Pillar-domain ownership.
**Notes:** Locks the principle — frontend pillar pages, backend pillar routers, etc. live on each role branch; only cross-cutting files need PR-only treatment.

### Q6 — Can Hung edit backend files for his pillar, or is backend Andy-only?

| Option | Description | Selected |
|--------|-------------|:---:|
| Hung can touch participant-side backend (pillar-domain stays the rule) | Hung can edit `backend/app/routers/signups.py`, `events.py` etc. for public flows on his role branch. Andy single-writer only for `models.py`, `alembic/`, shared services. | |
| Backend = Andy-only, period (matches existing COLLABORATION.md) | Hung never edits backend. | |
| Hung opens PRs against main for backend tweaks | Hung can edit backend but only via PRs to main, not direct on his role branch. | |
| **Other (free text)** | Hung can touch whatever he wants. | ✓ |

**User's choice:** "hung can touch whatever he wants"
**Notes:** Highest-trust variant. The PR-only list still applies to Hung — he can edit anything on his role branch, but operationally-risky files (Alembic, models, planning state) still need PR-only treatment. Captured as D-11 in CONTEXT.md.

---

## Area 4 — Sync cadence + tie-breaker

### Q7 — What sync rhythm do Andy and Hung want?

| Option | Description | Selected |
|--------|-------------|:---:|
| Async-only — commits + PR descriptions are the standup | No scheduled syncs. | |
| Weekly 30-min check-in | One scheduled call per week. | |
| Daily quick async update + weekly call | 3-bullet daily update + weekly call. | |
| Loose — sync only when blocked | No fixed cadence. | |
| **Other (free text)** | Daily 3-hour meeting. | ✓ |

**User's choice:** "We will meet daily for 3 hours"
**Notes:** Unusually long daily sync but explicitly chosen. CONTEXT.md treats this as load-bearing and notes it may relax once the milestone is in flight.

### Q8 — When does a role branch merge back to main?

| Option | Description | Selected |
|--------|-------------|:---:|
| After each phase ships green | Role branch lives until phase success criteria pass + Playwright is green, then PR to main. | ✓ |
| After each plan/sub-plan inside a phase | Smaller chunks. Each `<phase>-PLAN-N` lands in main when green. | |
| Daily — rebase + merge anything green every day | End-of-day push: anything green merges. | |

**User's choice:** After each phase ships green.
**Notes:** Locks in the roadmap's "merge between phases" rule. No mid-phase merges to main.

### Q9 — Who breaks ties when Andy and Hung disagree on a shared-file change?

| Option | Description | Selected |
|--------|-------------|:---:|
| Andy decides (project owner) | Andy holds the casting vote. | |
| Whoever owns the pillar where the change matters most | Domain-owner-decides. | ✓ |
| Defer to existing pattern — don't change shared code unless forced | Avoidance-first. | |

**User's choice:** Whoever owns the pillar where the change matters most.
**Notes:** Pillar-owner-decides. CONTEXT.md adds Andy as the casting vote if both pillars are equally affected — derived from D-16 framing, not a separate choice.

---

## Area 5 — Existing COLLABORATION.md fate

### Q10 — What should happen to the existing `docs/COLLABORATION.md`?

| Option | Description | Selected |
|--------|-------------|:---:|
| Wholesale rewrite — same path, new content | Phase 14 produces a complete rewrite at `docs/COLLABORATION.md` in one commit. The old version is replaced entirely. | ✓ |
| Surgical edit — keep structure, swap stale sections | Keep skeleton, replace stale sections individually. | |
| New file alongside old — archive old as `COLLABORATION-v1.0.md` | Move old to `docs/archive/` and create fresh file. | |

**User's choice:** Wholesale rewrite — same path, new content.
**Notes:** No archive copy. The existing file's role/scope/filename references are all wrong for v1.2-prod, so a clean rewrite avoids leaving stale fragments behind. Skeleton (Roles / Hard ownership / Workflow / Collision prevention / etc.) can be reused but content is replaced.

---

## Claude's Discretion

The following implementation details were deliberately left to the planner / executor:

- **Exact wording and structure** of the rewritten `docs/COLLABORATION.md` — must satisfy decisions D-01 through D-18 but the layout (tables vs lists vs sections) is at the writer's discretion.
- **Exact wording of the `CLAUDE.md` branch-awareness guidance** (D-18) — must tell Claude to check `git branch --show-current` before editing and respect pillar ownership, but the precise wording is open.
- **Whether to add a `docs/weeknotes.md` skeleton** — referenced in the existing stale COLLABORATION.md, not a Phase 14 deliverable, but the planner can choose to include it if the rewrite logically extends to it.
- **Whether to update `.planning/config.json`** to reconcile the `phase_branch_template` (`gsd/phase-{phase}-{slug}`) with the role-branch model. Could be a one-liner config tweak in Phase 14, or a deferred follow-up.

---

## Deferred Ideas

Captured in `14-CONTEXT.md` `<deferred>` section. Highlights:

- Local `git worktree add` setup on Andy's machine (opt-in convenience, not now)
- Per-worktree docker stacks with `COMPOSE_PROJECT_NAME` (only if local worktrees become real)
- `/gsd-workstreams` per-dev workstream dirs (decision deferred to planner; check if harness still recommends them)
- `docs/weeknotes.md` weekly update file (optional process)
- GitHub branch-protection rules on `main` (infra follow-up)
- Hetzner / autonomous remote box (only relevant if the box still exists)
- `.planning/config.json` `phase_branch_template` reconciliation (could be a tiny Phase 14 task or deferred)

---

*End of discussion log.*
