# STATE

**Updated:** 2026-09-08
**Branch:** main @ `89556b8` (PR #93)
**Roadmap:** `.planning/ROADMAP.md` — the single source of truth

> The previous STATE.md was dated 2026-05-23 and said "next action: merge Phase
> 35-01". It was 3.5 months stale and any `/gsd-*` command was acting on May's
> picture. Archived to `.planning/archive/superseded-2026-09-04/STATE.md`.

## Current milestone

**L — Launch.** Target: live, verified, handed over to Rafael.
Estimated 4–6 weeks from Gate 0 being answered.

## Current phase

**Phase L2 — Land what's already built. Complete 2026-09-08.** L0 complete the
same day. Gate 0 before both: 11 of 12 decided as of 2026-09-07. Only #12 (write real
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

1. **Phase L3 — auth and abuse hardening** is the next real phase: move tokens
   out of `localStorage` to an HttpOnly cookie + in-memory access token with
   CSRF (~21 files), plus the missing throttles and the `aud`/`iss` claims.
   Gate 0 #2 committed to this, and L2 deliberately shipped only the
   compensating 2-day window, not the fix.
2. **L1 is ~90% already done and partly throwaway.** DKIM CNAMEs are live on
   `sci-trek.org` (`s1`/`s2._domainkey` → `u113425370.wl121.sendgrid.net`,
   resolving to a real key), so mail is domain-authenticated today. What is
   left: confirm the third SendGrid CNAME in the dashboard, and optionally add
   a DMARC `rua=`. Since the plan is to move SendGrid → SES, polish here gets
   redone. Recommend skipping until the SES port.
3. Decide whether to turn `copilot_profile_extraction_enabled` on — its
   recorded reason for being off (tiny request budget) expired when Gate 0 #9
   funded ~1,000 requests. One line.
2. Answer Gate 0 #12 (write real copilot corpus test questions) — Andy's own
   task, not blocking anything else
3. New Phase P6 (added 2026-09-07) — copilot production hardening: corpus
   refresh, CSV-upload-via-copilot tool, production-grade RAG audit,
   concurrency testing, guardrails. See `.planning/ROADMAP.md` items 133–142.

## Phase L2 outcome (completed 2026-09-08)

Roadmap items #20–#25 plus a new #26.1. Six PRs, five merged and one closed:
**#91** `be0dbde` (2-day refresh window + the security review, salvaged from
#79), **#92** `27bf2e3` (frontend container non-root), **#78** `5f54bce`
(copilot mail transport, which also carried item #24), **#80** `5cbbab7` (CI
security net), **#93** `89556b8` (react-router 7.14.0 → 7.18.3), **#94**
(organizer check-in QR). **#79 closed** per Gate 0 #2. Jira SCRUM-8/9/10/70/71/72
all Done; SCRUM-45 updated.

**Three roadmap errors this phase exposed — worth knowing about, because the
pattern repeats:**

1. **Item #22's description was stale.** The mass-mail bug it warns about was
   already fixed on the branch. The real blocker was two coverage gates.
2. **Item #24 was not a separate task.** The commit lived inside PR #78.
3. **Gate 0 #3 was half wrong.** "Dockerfiles already run non-root" held for
   the backend only; the frontend ran PID 1 as root. And item #23's F3 dep
   bump was outstanding — `react-router-dom` at 7.14.0 with nine high
   advisories, three of which apply to a Vite SPA.

**Method note, recorded because I got it wrong twice before getting it right.**
`git diff main...branch` totals do **not** tell you whether a branch holds
unmerged work — on a stale branch most "differences" are `main` having moved
on. The reliable test is *which files does this branch add that `main` does not
have*, plus a direction check on shared files. On that test
`feat/deploy-baseline` is **fully landed** (all 12 added files present, four
byte-identical including migration `0009`) — not the 1,837 lines of missing
security work an earlier reading of the diff suggested. Same for
`organizer-audit`.

**Two L9 deploy notes**, on top of the existing Celery-worker one:

- **#78 makes `VITE_COPILOT_ENABLED` required** at `docker compose up`.
  Forgetting it previously produced a fully healthy stack with the copilot
  compiled out of the bundle and nothing saying so. The next deploy must export
  it or it fails fast — intended.
- **#92 changed the frontend's internal port** (80 → 8080, with Caddy updated
  to match). Not exercised end-to-end through Caddy locally; confirm the site
  loads on the next deploy, and check that port first if it does not.

**Branches:** one deleted (`fix/confirmation-email-silent-failure`, whose only
unique lines would have reverted PRs #83/#84). `v1.3` and
`fix/imports-templates` kept deliberately — sole copies of the SMS work and the
bulk-add UI respectively. `feat/deploy-baseline` and `organizer-audit` proven
landed and safe to delete. ~52 further remote branches are fully-merged
clutter, not yet cleared.

## Phase L0 outcome (completed 2026-09-08)

Roadmap items #13–#17, all five closed. The docs and `architecture-site` work
went through PR #89, squash-merged to `main` on 2026-09-08 as `3af0c15` (all
three checks green; branch deleted on merge).

Jira: **SCRUM-64/65/66/67/68** all Done. Separately, **SCRUM-146** (X1 #120 —
merge the two eval branches and resolve ~60 PRs of drift) remains open: L0
preserved those branches, it did not integrate them.

- **#13 eval branches pushed.** `feature/v1.4-phase-35-02-multimodel-eval`
  (37 commits, `8fb1a54`) and `feature/v1.4-phase-35-03-grounded-eval`
  (45 commits, `b0f2914`) now have upstreams on `origin` and match it exactly.
  82 commits of copilot eval work — the paper's evidence base — are no longer
  single-laptop. Pushed as archival branches only: no PR, no merge into `main`.
  Pre-push secret scan was clean (no `.env`/`*.pem`/`*.key`/credential-shaped
  filenames; no `sk-or-v1-*`, `sk-ant-*`, `AKIA…`, private-key headers, bearer
  tokens or `postgres://user:pass@` in either diff), which mattered because the
  repo is public.
- **#14/#15 docs and `architecture-site` shipped.** Two commits on
  `chore/L0-housekeeping`, reviewed as PR #89 and squash-merged to `main` as
  `3af0c15`. Covers `.planning/ROADMAP.md`, `.planning/STATE.md`,
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

## Verified test status (2026-09-08, main @ `89556b8`)

- Frontend: **629/629 passing**, 74 files (+3 tests, +1 file — the organizer
  check-in QR, PR #94)
- Backend: **2,097 passing** in CI on PR #78's final run, 1 skipped
- CI green on every merge this phase — #91, #92, #78, #80, #93 — including the
  full Playwright e2e suite, and on #80 also Semgrep, Semgrep OSS and pip-audit,
  which are new gates as of that merge

Locally the backend reads **2,072 passing, 13 skipped** with
`tests/test_corpus_embeddings.py` excluded — it needs the `/opt/hf-cache` mount
the one-off container lacks, so `transformers` tries to fetch BGE and 404s. Not
a code defect; ROADMAP #43. **Note this understates package coverage by ~0.5%**,
because that excluded file is what exercises the embedding paths — which is why
`app.copilot` measures 94.5% locally while passing its 95% gate in CI. Do not
chase that gap locally.

Previous readings: 2026-09-07 frontend 626/626 over 73 files, backend 2,066
passing with 3 environmental failures; 2026-09-03 frontend 609/609 over 72
files, backend 2,044 passing, 88.22% coverage (gate 55).

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

**None outstanding from before this phase.** All three that had been sitting
open are resolved: **#80** merged `5cbbab7`, **#78** merged `5f54bce`, **#79**
closed with its useful half salvaged into **#91** `be0dbde`.

Opened and merged during L2: **#91**, **#92** `27bf2e3`, **#93** `89556b8`.
**#94** (organizer check-in QR) was the last one in flight.

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
