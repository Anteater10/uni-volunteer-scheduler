# STATE

**Updated:** 2026-09-07
**Branch:** main @ `fe05585` (PR #88)
**Roadmap:** `.planning/ROADMAP.md` — the single source of truth

> The previous STATE.md was dated 2026-05-23 and said "next action: merge Phase
> 35-01". It was 3.5 months stale and any `/gsd-*` command was acting on May's
> picture. Archived to `.planning/archive/superseded-2026-09-04/STATE.md`.

## Current milestone

**L — Launch.** Target: live, verified, handed over to Rafael.
Estimated 4–6 weeks from Gate 0 being answered.

## Current phase

**Phase L0 — Protect what's fragile. Complete 2026-09-07.** See the L0 outcome
block below. Gate 0 before it: 11 of 12 decided as of 2026-09-07. Only #12 (write real
corpus test questions) remains, and it's just Andy's to-do, not a blocking call.

Decided: #1 Cloudflare Free — yes. #2 Fix tokens properly, close PR #79. #3
already implemented in code, no action needed. #4 Soft tracking for no-shows.
#5 Drop PR #50 for good. #6 Hard block confirmed correct as implemented, credit
now expires after 1 year (new: SCRUM-151). #7 Audit log retention: 3 months.
#8 Delete the 8 dormant `/admin/imports` endpoints. #9 OpenRouter funded, $10 /
~1,000 requests. #10 Moot — `sci-trek.org` is self-registered by SciTrek, not
UCSB-owned; no IT approval needed, already sending real email from AWS. #11
Switched to Tableau (not Power BI) — dev team is Mac-only, Power BI Desktop has
no native Mac build, no license held anyway.

Also discovered: the app **is already deployed** — a Render test instance (AI
copilot disabled, out of disk) and a full AWS instance (everything working,
including real email from `no-reply@sci-trek.org`). This changes several
Phase L9 "deploy" assumptions — needs reconciling when L9 is planned.

## Next actions

1. Review and merge the open L0 PR (see the L0 outcome block below) — it carries
   the planning-doc archive move and the `architecture-site` rework. Deliberately
   left unmerged for Andy's review; `main` is still at `fe05585`.
2. Pick the next phase — either **L1** (add CNAME records at the `sci-trek.org`
   registrar; optional deliverability upgrade, no external approval wait) or
   **L2** (land the three open PRs: #80 CI safety net, #79 close per Gate 0 #2,
   #78 after fixing the recipient query). L2 is the larger unblock.
3. Answer Gate 0 #12 (write real copilot corpus test questions) — Andy's own
   task, not blocking anything else
4. New Phase P6 (added 2026-09-07) — copilot production hardening: corpus
   refresh, CSV-upload-via-copilot tool, production-grade RAG audit,
   concurrency testing, guardrails. See `.planning/ROADMAP.md` items 133–142.

## Phase L0 outcome (2026-09-07)

Roadmap items #13–#17. Executed on `main @ fe05585`; `main` itself was **not
committed to** — everything landed either on `origin` as a branch or on an open
PR.

Jira: **SCRUM-64** (#13), **SCRUM-67** (#16), **SCRUM-68** (#17) → Done.
**SCRUM-65** (#14) and **SCRUM-66** (#15) → Testing, moving to Done when PR #89
merges. Separately, **SCRUM-146** (X1 #120 — merge the two eval branches and
resolve ~60 PRs of drift) remains open: L0 preserved those branches, it did not
integrate them.

- **#13 eval branches pushed.** `feature/v1.4-phase-35-02-multimodel-eval`
  (37 commits, `8fb1a54`) and `feature/v1.4-phase-35-03-grounded-eval`
  (45 commits, `b0f2914`) now have upstreams on `origin` and match it exactly.
  82 commits of copilot eval work — the paper's evidence base — are no longer
  single-laptop. Pushed as archival branches only: no PR, no merge into `main`.
  Pre-push secret scan was clean (no `.env`/`*.pem`/`*.key`/credential-shaped
  filenames; no `sk-or-v1-*`, `sk-ant-*`, `AKIA…`, private-key headers, bearer
  tokens or `postgres://user:pass@` in either diff), which mattered because the
  repo is public.
- **#14/#15 docs and `architecture-site` committed.** Landed on branch
  `chore/L0-housekeeping` as two commits and opened as a **PR left unmerged for
  review** (Andy's call). Covers `.planning/ROADMAP.md`, `.planning/STATE.md`,
  the `.planning/archive/superseded-2026-09-04/` move (7 files),
  `PRODUCT-BRIEF.md`, `WORK-INVENTORY.md`, and the 5-file `architecture-site`
  rework (+399/−110). `npm run build` in `architecture-site` verified clean
  before committing (vite 7.3.3, 36 modules, no errors).
- **#16 `BioApp/` deleted.** It was a nested standalone repo (1 commit, license
  plus an empty readme) already pushed to `github.com/Anteater10/BioApp`, so the
  local folder was redundant. Deleted rather than gitignored.
- **#17 stashes and worktrees cleared.** All 4 stashes were 2026-04-15
  mid-execution snapshots from the parallel worktree agents running Phase 16,
  which shipped in v1.2-prod on 2026-04-17 — superseded WIP of work that landed,
  and unappliable anyway (3 of 4 bases gone, tree ~500 commits ahead). Dropped
  via `git stash clear`; `/private/tmp/uvs-event-form` and
  `/private/tmp/uvs-render-main` pruned.

## What shipped since the last STATE update

Roughly 60 PRs, #23 → #85, none of which appeared in any planning document:
first-class quarters, permanent orientation credits, slot-scoped broadcasts,
quarter retrospective, pick-your-shift QR check-in, orientation-required-on-
first-signup, calendar invites + organizer role, the Phase K knowledge-base
rebuild (39 files), waitlist promotion via email confirmation, corpus refresh,
read-only volunteer signups, multiple sessions per shift, module catalog
seeding, destructive-action guards, the W4–W6 security work, the Phase B full
agent, and PRs #81–#85 (SCRUM-13/48/49/50).

**2026-09-07 — three reported fixes shipped, PRs #86–#88 (SCRUM-154/155/156).**
All merged to `main`, all three verified in a browser against the running stack
rather than on unit tests alone:

- **#86 SCRUM-154** — the public browse page grouped events by school; it now
  groups and orders by `week_number` ("Week N" headers, ascending), with school
  kept as a per-card label and week-less events in a trailing "Unscheduled"
  group. The `Week N - Module - School` naming rule is now *enforced* in both
  write paths: a regex check that blocks Save on the manual form, and the
  copilot's agent prompt plus tool-layer rejection in
  `create_event_with_schedule` / `update_event`. The regex lives in one place
  per stack (`backend/app/event_title.py`, `frontend/src/lib/eventTitle.js`).
  Legacy titles were deliberately **not** backfilled, so the form only enforces
  on a title actually being written — otherwise every pre-existing event would
  have become uneditable until renamed.
- **#87 SCRUM-155** — admins can reverse a cancellation.
  `POST /admin/signups/{id}/uncancel` and its shift twin, surfaced as an
  Uncancel action on cancelled roster rows, re-checking capacity first and
  emailing the volunteer via a new `resignup` kind. See the deploy caveat under
  "Operational notes" below.
- **#88 SCRUM-156** — Cancel on the event form now routes through the discard
  prompt `FormModal` already owned, instead of silently binning a filled-in
  form. Also wired `dirty` into `EventSettingsModal` and `DuplicateEventModal`,
  which had never passed it, so their prompt could not fire from any route.

These were reported directly by Andy from the live app, not drawn from the
ROADMAP register — the same "SCRUM stream not in any planning doc" gap that
PRs #81–#85 had. Worth folding into ROADMAP if the stream continues.

## Verified test status (2026-09-07, main @ `fe05585`)

- Frontend: **626/626 passing**, 73 files
- Backend: **2,066 passing**, 3 failing, 13 skipped
- CI green on all three of #86/#87/#88 including the full Playwright e2e suite

The 3 failures are environmental and unchanged — no `/opt/hf-cache` mount in
the one-off test container, so `transformers` tries to fetch BGE and 404s. Not
a code defect. Tracked as ROADMAP #43.

Previous reading (2026-09-03): frontend 609/609 over 72 files; backend 2,044
passing, 88.22% coverage (gate 55).

## Operational notes

**The Celery worker must be deployed together with the backend.** Found while
testing SCRUM-155 on 2026-09-07: with the API on new code and the worker still
on the old image, the worker threw
`ValueError: Unknown notification kind: resignup` and the email was lost. The
admin still saw a 200 — nothing surfaced the failure to staff. This was a stale
local container rather than a code defect, but the same hazard applies to any
deploy that updates the API ahead of the worker, and to every future new email
kind. Carry into the L9 deploy runbook and the Rafael handover.

## Open PRs

- **#80** CI safety net — built, never merged
- **#79** F1 accept localStorage — **close if reversing F1** (Gate 0 #2)
- **#78** copilot mail transport — fix the recipient query first (ROADMAP #22)

## Accumulated Context

### Roadmap Evolution

- Phase P6 added 2026-09-07: Copilot production hardening — corpus quality,
  CSV-upload-via-copilot tool (intentional reversal of PR #51's CSV removal,
  confirmed by Andy), production-grade RAG audit, concurrency testing,
  guardrails (prompt injection, scope limiting, PII, rate limits, cost
  monitoring). Directory: `.planning/phases/P6-copilot-production-hardening/`.
  Kept separate from existing Phase P4 (Copilot completion) by Andy's choice.

## Known-stale documents

`FINAL-ROADMAP.md` is retained for the K-register detail only; its W4–W7
sections are self-marked superseded. `PROJECT.md`, `REQUIREMENTS*.md`,
`codebase/*` and `research/*` are historical inventories, not status.
`CLAUDE.md` still describes a v1.2-prod two-developer pillar model that no
longer reflects how this repo is worked — flagged as ROADMAP #75.
