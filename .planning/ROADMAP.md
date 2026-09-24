# ROADMAP — single source of truth

**Written:** 2026-09-04
**Supersedes:** everything in `.planning/archive/superseded-2026-09-04/` (13 docs)
**Still authoritative elsewhere:** `FINAL-ROADMAP.md` for the K-register detail only

## Why this exists

Before this file there were three parallel tracks and nothing reconciled them:

1. The deploy track (W0–W7), driven by `ROADMAP-2026-08-28.md`
2. The v1.4 copilot/paper phases 30–38, frozen since 2026-05-23
3. An undocumented SCRUM/Jira product stream (PRs #81–#85) that appeared in no
   planning document at all — now tracked in "Shipped — SCRUM product stream"
   below, and extended by #86–#88 on 2026-09-07

Plus a Power BI seed (`seeds/v1.4-data-pipeline.md`) whose phases were numbered
30–35 and collided head-on with the copilot's 30–38.

This is one track. Phase IDs are `L` (launch), `P` (product), `D` (data), `X`
(paper) so nothing collides with the historical 0–38 numbering.

Assembled from a full audit on 2026-09-03/04: Jira, all 492 markdown files, the
paper track, and a DB → endpoint → feature → frontend map (30 tables, 160
endpoints, 46 features, 39 routes). Source register: 506 numbered findings.

## Four structural rules

These are why the ordering differs from the old plan.

1. **All user-facing code lands before verification.** The old plan verified the
   app in W6, then would have changed the login path afterwards. Verification is
   the most expensive item here — pay for it once.
2. **Infra decisions come before DNS.** Cloudflare changes where the SendGrid
   CNAMEs live and whether they are proxied. Deciding after filing means filing
   twice.
3. **Nothing is "done" on a branch.** Three items the old roadmap marked ✅ are
   sitting unmerged (PR #80, K31's `569c3ff`, F1's acceptance on PR #79).
   Merged to `main` or it is not done.
4. **A phase is done only when every row is.** Every row ✅ with a merged PR,
   its Jira ticket moved to Done, and STATE.md updated — all three, in the PR
   that lands the last row. A session reports "N of M rows done", never "phase
   done". Added 2026-09-21 after L3 was reported done at 2 of 6 rows and the
   trackers drifted from there (see Phase S).

---

# Shipped — SCRUM product stream

The gap named in "Why this exists" above: work arriving as Jira SCRUM tickets
rather than from this register, shipping straight to `main`, and appearing in no
planning document. Rather than keep re-discovering it, record it here as it
lands. **Merged to `main` only** — per structural rule 3.

| Ticket | PR | What shipped | Merged |
|---|---|---|---|
| SCRUM-13 | #81 | Signup QR generator | 2026-08-28 |
| *(none)* | #82 | School-branch signup notifications; modules and admins classed High/Middle/Both, one summary per matching admin, migration `0042` backfills to Both. Also hardened email config so missing transport credentials cannot fail silently | 2026-09-01 |
| SCRUM-50 | #83 | Disabled SendGrid click tracking — the rewrite was breaking email links with a cert error | 2026-09-02 |
| SCRUM-49 | #84 | Signup emails now reach `pending` volunteers, not just `confirmed` (reminders, broadcasts, reschedules) | 2026-09-02 |
| SCRUM-48 | #85 | Browse by quarter × school level instead of one week at a time | 2026-09-02 |
| SCRUM-154 | #86 | Browse page groups/orders by `week_number`; `Week N - Module - School` title format enforced on the manual form **and** in the copilot (agent prompt + tool-layer rejection). Legacy titles deliberately not backfilled | 2026-09-07 |
| SCRUM-155 | #87 | Admin can reverse a cancellation — `POST /admin/signups/{id}/uncancel` + shift twin, capacity re-checked, volunteer emailed via a new `resignup` kind | 2026-09-07 |
| SCRUM-156 | #88 | Cancel on the event form prompts before discarding unsaved work; `dirty` finally wired into the Settings and Duplicate modals | 2026-09-07 |

Two things this table is meant to make visible:

- **#82 carries no ticket at all.** It is a real, migration-bearing change that
  exists in neither Jira nor this register — the failure mode is not just "SCRUM
  isn't in the roadmap", it is that some shipped work is in no tracker anywhere.
- **#86–#88 came from Andy using the live app**, not from the 506-item audit.
  The register is good at finding structural debt and blind to what breaks in
  daily use, so expect this row-type to keep arriving and leave room for it.

Related open register items: **#106** (K15 focus trap — partly addressed by
SCRUM-156), **#94/#95/#96** (SCRUM-27/28/32, still open under Phase P3).

---

# Gate 0 — Decisions (your time only; blocks all code)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 1 | No CDN/WAF anywhere; Caddy only | Deferred in Phase 09 to "Phase 15+", never picked up | Adopt Cloudflare | L1, L5, all DNS | ✅ **Decided 2026-09-07: Yes, Cloudflare Free plan** [SCRUM-56] |
| 2 | Both tokens in `localStorage` | PR #79 exists to *accept* this, not fix it | Reverse it — fix properly | L2, L3 | ✅ **Decided 2026-09-07: Fix properly — close PR #79** [SCRUM-57] |
| 3 | F2/F3 headers unapproved | F1's acceptance is void without the CSP | Approve | L2 | ✅ **Resolved 2026-09-07: Already implemented in code (CSP live in `frontend/nginx.conf` + `backend/app/main.py:158`, Dockerfile already runs non-root). No action needed — roadmap was stale.** [SCRUM-58] |
| 4 | No consequence for no-show | K21 needs a policy, not code | Pick a rule | L4 | ✅ **Decided 2026-09-07: Soft tracking only — record no-shows on the volunteer's record, visible to organizers, no automatic block/penalty** |
| 5 | PR #50 closed unmerged | Its branch is the only impl of issue #25 | Abandon | L6 scope | ✅ **Decided 2026-09-07: Drop for good — delete the branch, close issue #25 as won't-do** |
| 6 | Orientation = hard 422 | PR #48 had a revert cycle; docs disagree | Confirm final | L11 | ✅ **Decided 2026-09-07: Confirmed correct as implemented (verified in `backend/app/services/public_signup_service.py:264-291` + `orientation_service.py`) — hard block when orientation+module both present and no credit; skip if credited; soft warning when no orientation on event. ONE CHANGE: orientation credit currently never expires — must now expire after 1 year (currently permanent/no-expiry per `has_orientation_credit`). Needs a code change (add expiry check), not yet built. `PRODUCT-BRIEF.md` (K39) still stale and needs fixing to match — queued under L11.** [SCRUM-59] |
| 7 | `audit_logs` grows forever | Retention never decided | 12 months | L5 | ✅ **Decided 2026-09-07: 3 months — auto-delete audit_logs entries older than 3 months** [SCRUM-60] |
| 8 | 8 dormant `/admin/imports` endpoints | Pipeline deleted PR #51, endpoints remain | Delete | P5 | ✅ **Decided 2026-09-07: Confirmed — delete all 8 dead endpoints** |
| 9 | OpenRouter unfunded, ~50 req/day | Can't load-test or demo the copilot | Fund it | L6 | ✅ **Decided/already done 2026-09-07: $10 credit already added, giving ~1,000 requests — no longer blocked** [SCRUM-61] |
| 10 | SendGrid CNAMEs not requested | UCSB IT may refuse | Single-sender fallback | L1 | ✅ **Resolved 2026-09-07: Moot — `sci-trek.org` is self-registered by SciTrek, not a UCSB domain. No UCSB IT approval needed; whoever holds the registrar login can add the CNAME records directly. AWS deployment already sending real confirmation emails from `no-reply@sci-trek.org` successfully.** [SCRUM-62] |
| 11 | Power BI seed unpromoted | Licenses/owner/warehouse unknown | Answer all three | D1 | ✅ **Decided 2026-09-07: Switched from Power BI to Tableau — no Power BI license exists yet, no stakeholder mandate for it specifically (only general post-launch analytics need), and dev team is Mac-only (Power BI Desktop is Windows-only; Tableau has a native Mac app). Build analytics on Tableau instead once Milestone D starts post-launch. Owner/warehouse-sizing questions deferred until D1 planning.** **Superseded in part 2026-09-10: after a full codebase scan, the BI tool is downgraded from an architecture decision to a client choice — the seam is a read-only Postgres role over `warehouse.*`, so Metabase, Tableau and Power BI are all ordinary clients. Metabase is the primary ($0, open source, native Mac, self-serve for non-technical staff); Tableau stays available and, if wanted, should come from UCSB Data Services' existing institutional deployment rather than a new purchase — note Tableau for Teaching licences explicitly exclude administrative use. Warehouse sizing is also now answered: the existing Postgres 16 instance, indefinitely.** [SCRUM-63] |
| 12 | Copilot corpus has no real questions | Only you know SciTrek policy | Write them | P6 | ✅ **Decided 2026-09-07: Moved into Phase P6 (item #133) — Andy will write these as part of the copilot hardening phase, not standalone** |

**Action status, audited 2026-09-08.** All 12 rows are decided; Jira is now
level with that (SCRUM-51 umbrella plus 56/57/58/59/60/61/62/63 all Done). Four
rows never had tickets — #4, #5, #8, #12 — and none was created just to be
closed. Of the rows that carried a *code or admin action* rather than a bare
decision:

- **#5 complete.** GitHub issue #25 closed as not-planned. Deviation, confirmed
  by Andy: the branch `fix/imports-templates` is **kept**, not deleted — it is
  the only copy of the in-app bulk event builder (`BulkAddSection.jsx` + tests,
  `test_bulk_events.py`), which is input to P6 #135. Its
  `0029_seed_scitrek_modules` migration did land separately as `0038`.
- **#8 complete, and it was already done** — verified rather than assumed: no
  `/admin/imports` endpoints in any router, no `csv_imports` in
  `backend/app/models.py`, no `services/import_service.py`. PR #51 had removed
  them; this row's premise ("8 dormant endpoints remain") was stale.
- **#6** created new work — orientation credit must expire after 1 year —
  tracked as SCRUM-151, still open, queued under L11.
- **#12** was moved into Phase P6 as item #133 rather than done standalone.

Two rows proved partly wrong when acted on, recorded so the pattern is visible:
**#3** claimed the Dockerfiles already ran non-root — true of the backend, not
the frontend, whose stock nginx ran PID 1 as root (fixed, PR #92) — and its F3
dependency bump was outstanding despite reading as resolved (fixed, PR #93).

**On #2:** PR #79 exists to accept localStorage tokens, reasoning "don't do
surgery on the login path right before handing off to a developer who has never
deployed this." But Rafael does deployment only, the backlog is entirely yours,
and handoff is weeks away. The reason has expired. Fix it — and fix it in L3,
before verification, or you pay for L6 twice.

---

# Milestone L — Launch (4–6 weeks)

## Phase L0 — Protect what's fragile (0.5 day) — ✅ COMPLETE 2026-09-07

Executed on `main @ fe05585`. Items #14/#15 landed via PR #89, squash-merged to
`main` on 2026-09-08 as `3af0c15` with all three checks green (frontend vitest,
backend tests + coverage, playwright e2e); branch `chore/L0-housekeeping`
deleted on merge. Jira: SCRUM-64/65/66/67/68 all Done.

| # | Current situation | What's wrong | Recommendation | Blocks | Status |
|---|---|---|---|---|---|
| 13 | 2 eval branches, 82 commits, local only | No remote ref — one laptop holds the paper's evidence | Push both today | X1 | **✅ Done 2026-09-07** — both pushed to `origin`, refs verified identical: `…35-02-multimodel-eval` @ `8fb1a54` (37 commits), `…35-03-grounded-eval` @ `b0f2914` (45). Archival only — no PR, no merge. Pre-push secret scan clean (repo is public). Merging them is still open as X1 #120 / SCRUM-146. [SCRUM-64] |
| 14 | 6 planning files untracked | One is the only record of F6 | Commit | Nothing | **✅ Done — `3e2cab5`, merged in PR #89 (`3af0c15`)** — scope widened to the whole tree: 7 superseded docs moved into `.planning/archive/superseded-2026-09-04/` (recorded as **renames**, history preserved), the 2026-08-20/28 snapshots, ROADMAP + STATE updates, `PRODUCT-BRIEF.md`, `WORK-INVENTORY.md`. `PLAN-2026-08-20.md` — the only record of F6 / item #32 — is now in version control. [SCRUM-65] |
| 15 | `architecture-site` rework uncommitted on `main` | Done and builds clean, just sitting there | Commit on a branch | Nothing | **✅ Done — `2a22a64`, merged in PR #89 (`3af0c15`)** — 5 files, +399/−110. "Builds clean" verified, not assumed: `npm run build` → vite 7.3.3, 36 modules, no errors. **Two follow-ups from the register were NOT folded in** — the dead `onNodeHover`/`onLeave` props on `FlowDiagram`, and `wrapSvgText` rendering the literal `"undefined"` for a subtitle-less node. Still outstanding. [SCRUM-66] |
| 16 | `BioApp/` nested untracked git repo | Shows as untracked forever | Gitignore or move out | Nothing | **✅ Done 2026-09-07** — deleted outright rather than gitignored. It was a standalone repo (1 commit, `LICENSE` + empty readme, clean tree) already pushed to `github.com/Anteater10/BioApp`, so nothing was lost. [SCRUM-67] |
| 17 | 4 stashes from April, 2 dead worktrees | Bases deleted; won't apply | Drop and prune | Nothing | **✅ Done 2026-09-07** — `git stash clear` + `git worktree prune`; dropped without patch export after review. All four were 2026-04-15 snapshots of Phase 16, which shipped in v1.2-prod on 2026-04-17 (all seven `16-0N-SUMMARY.md` + `16-VERIFICATION.md` on `main`; `scripts/verify-overrides-retired.sh` still present). Unappliable anyway — 3 of 4 bases gone. [SCRUM-68] |

## Phase L1 — File the DNS request (0.5 day) — ✅ COMPLETE 2026-09-08 (done by circumstance)

Closed with **no DNS work performed**: domain authentication was already live and
nobody had recorded it. The phase's founding premise — "UCSB IT may refuse the
CNAMEs" — never applied, per Gate 0 #10. Remaining polish is deferred to the
SendGrid → SES port, where it would be redone anyway. Jira: SCRUM-69 Done.

| # | Current situation | What's wrong | Recommendation | Blocks | Status |
|---|---|---|---|---|---|
| 18 | No verified sender domain | Premise was wrong twice over | Nothing to do | L9, all email | **✅ Moot — verified from public DNS 2026-09-08.** DKIM is live: `s1._domainkey` and `s2._domainkey` → `s1`/`s2.domainkey.u113425370.wl121.sendgrid.net`, both resolving to a real RSA key. So SendGrid domain auth was configured at some point and never written down — which is why real mail from `no-reply@sci-trek.org` has been arriving. No UCSB IT step was ever needed (Gate 0 #10 — the domain is SciTrek's own, at IONOS). Rest of the zone: apex A `52.35.73.159`, MX `mx00`/`mx01.ionos.com` (inbound stays IONOS), SPF `v=spf1 include:_spf-us.ionos.com ~all` — which does **not** name SendGrid, and that is correct under CNAME-based domain auth because the return path is a SendGrid-hosted subdomain with its own SPF. **Deferred to the SES port:** confirming the third CNAME (the `emNNNN` return-path subdomain, not resolvable from outside without the number — it is in SendGrid → Sender Authentication), and adding a DMARC `rua=` (currently `p=none` with no reporting address, so nobody receives reports). No ticket ever existed for this row; recorded here instead. |
| 19 | Cloudflare not decided | CNAMEs must be DNS-only, not proxied | Decide #1 before filing | L9 | **✅ Decided (Gate 0 #1: Cloudflare Free) — and the constraint outlives this phase.** When Cloudflare is adopted, the DKIM CNAMEs and MX must be **DNS-only, never proxied**: an orange-clouded `_domainkey` resolves to a Cloudflare IP instead of SendGrid's value and breaks DKIM silently, with the records still looking correct in the dashboard. Only the web A record should be proxied. Carried onto SCRUM-56, since adopting Cloudflare is a nameserver migration off IONOS and the whole zone has to be re-created there. Sequencing it **after** the SES port avoids doing the sender records twice. [SCRUM-69] |

## Phase L2 — Land what's already built (1–2 days) — ✅ COMPLETE 2026-09-08

Merged in order: **#91** `be0dbde`, **#92** `27bf2e3`, **#78** `5f54bce`,
**#80** `5cbbab7`, **#93** `89556b8` — plus **#94** for the organizer
check-in QR (see #26.1 below). PR **#79 closed**. Jira: SCRUM-8/9/10/70/71/72
all Done. Order mattered once: #91 had to precede #80, see #20.

| # | Current situation | What's wrong | Recommendation | Blocks | Status |
|---|---|---|---|---|---|
| 20 | PR #80 open (CI net) | Built but never merged; roadmap said done | Merge | L8 | **✅ Merged `5cbbab7`.** Refreshed onto current `main` first — its green checks were 10 days old and it was 9 behind. That refresh made its own pip-audit gate fail on **its first real finding**: `CVE-2026-9856` against `transformers 4.57.6`, published after the baseline was written. Baselined with reasoning inline (the fix is a **major** jump on the library the copilot's embedding + reranker use); triage → SCRUM-45, now 35 advisories. **Also carried #21's `REFRESH_TOKEN_EXPIRES_DAYS: 14→2` in `ci.yml`** — merging it before #91 would have left CI testing 2 days against an app shipping 14. Now agree: `ci.yml:51`/`:236` and `config.py:54` all say 2. |
| 21 | PR #79 open (accept localStorage) | Contradicts #2 if you're fixing tokens | Close it | L3 | **✅ Closed, salvaged into #91 `be0dbde`.** #79 bundled three things; only the acceptance document was reversed. Kept: the 14→2 refresh-window narrowing (a compensating control until L3, not a substitute) and `docs/security-review-frontend-infra.md` — which *recommends* the HttpOnly-cookie fix, so it never conflicted with Gate 0 #2. Landed with a status note so a 2026-08-20 snapshot isn't read as current state. Volunteer magic links untouched at 14 days, deliberately. [SCRUM-70] |
| 22 | PR #78 open (copilot mail transport) | `nudge_understaffed_module:50-59` targets the **whole volunteer table** | Fix recipients, then merge | P4 | **✅ Merged `5f54bce`. This description was already out of date** — the mass-mail policy was fixed on the branch: 120-day window either side of the module, in scope, minus those already signed up, opt-outs skipped, hard cap 200 above which it **refuses** rather than mailing a prefix. Sending still defaults **off**. What actually blocked it was coverage, in **two** gates: `app/celery_app.py` at 100% (ci.yml:110) and `app.copilot` at 95% line+branch (ci.yml:160-165). Nine tests added; both files now 100%. |
| 23 | `Caddyfile:36` HSTS-only; Dockerfile has no `USER` | F2/F3/F4 never shipped | Ship all three | L8 | **✅ Done — but Gate 0 #3 was half wrong.** F2/F3 headers were already live (`frontend/nginx.conf:30-40`, `backend/app/main.py:157-169`); `Caddyfile:36` HSTS-only is correct, not a gap. **F4 was not done:** Gate 0 #3 recorded "Dockerfile already non-root", true of `backend/Dockerfile:54` but not the frontend, whose stock nginx runs PID 1 as root (verified by running both images). Fixed in **#92 `27bf2e3`** via `nginx-unprivileged` (uid 101), forcing `listen 8080` and a matching Caddy change. **F3 was also not done** and I first closed it wrongly: `react-router-dom` was pinned at 7.14.0 with **nine** high advisories — fixed in **#93 `89556b8`** (→7.18.3). |
| 24 | K31 commit `569c3ff` on a branch | Roadmap marked it "✅ pushed" | Merge to `main` | Nothing | **✅ Not a separate task — landed inside #78.** `569c3ff` was the middle of that branch's three commits, never a loose commit needing a cherry-pick. Verified on `main`: the retry policy is in `backend/app/tasks/extract_profile.py` with its 212-line test. **Open question this raised:** `copilot_profile_extraction_enabled` is still `False`, and its recorded reason ("off until the request budget is large enough") has partly expired now Gate 0 #9 funded ~1,000 requests. One-line change, Andy's call. [SCRUM-71] |
| 25 | 9 branches with unmerged work | Includes 39-commit `origin/v1.3` | Merge or delete each | Nothing | **✅ Every branch dispositioned.** Method matters: `git diff` totals are useless here because they don't say which side is newer — the reliable test is *which files does this branch add that `main` lacks*. Deleted `fix/confirmation-email-silent-failure` (its only unique lines would have **reverted** PRs #83 and #84). **`feat/deploy-baseline` is fully landed** — all 12 files it adds are on `main`, four are byte-identical including migration `0009`, and `main` leads every other file; my earlier "1,837 lines missing" was the diff trap. **`organizer-audit` likewise superseded** — `main`'s form-schema endpoints already admit organizers via `require_staff` with no owner filter, which is what the 2026-09-08 ruling wants. **Keep `v1.3`** — sole copy of ~837 lines of SMS work (someone else owns SMS). **Keep `fix/imports-templates`** — sole copy of the bulk-add UI, input to P6 #135. ~52 further remote branches are fully-merged clutter, not yet cleared. [SCRUM-72] |
| 26.1 | Check-in QR unreachable on a phone | `CheckInQRModal` rendered only by `AdminEventPage`, and `AdminLayout` swaps every `/admin/*` page for `DesktopOnlyBanner` below the desktop breakpoint | Surface it on the organizer roster | Nothing | **✅ #94 — added 2026-09-08 on Andy's requirement that organizers use both phone and laptop.** The desktop half was already correct (no `isAdmin` gate on the button; the route admits both roles) — this was a missing surface, not a permission bug. Reuses the existing modal, reading `venue_code` off the roster query the page already runs. A slice of P1 #80/#81, pulled forward because check-in is a live daily flow. |

## Phase S — Stabilization (1–2 days) — *added 2026-09-21* — **✅ COMPLETE 2026-09-21 (10 of 10)**

Before more feature or hardening work: make every tracker agree with `main`, and
remove the known false signals from CI and dev tooling. Why it exists: L3 was
reported done at 2 of 6 rows (see L3), so STATE.md, Jira and the next session all
moved on; Jira never recorded work being finished (16 done items still open,
all 12 L4 tickets "Idea"); roadmap updates sat in unmerged PRs; two kanban
boards disagreed; 53 Jira tickets and 13 GitHub issues were on no plan.

Exit criteria: every row below ✅, and the tracker audit shows no ❌ for any
done row. Then L3 completion, then L5.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 164 | Roadmap and STATE.md lag `main` | Done work unrecorded (L3 #26/#30, L5 #47, P4 #99–#102, P6 #141); open work on no plan | Record it; add rows #153–#163; add structural rule 4 | L3 | **✅ Done — PR #134** (2026-09-21). [SCRUM-176] |
| 165 | Milestone D rescope sits in draft PR #118 | `main` says D1–D5 and Tableau; Jira and #118 say D0–D7 and Metabase | Review, rebase, merge #118 | D | **✅ Done — this PR (#118)**, reviewed and approved by Andy 2026-09-21, rebased on `main`. Also adds the DE / DA / DS work breakdown to Milestone D. [SCRUM-177] |
| 166 | Jira lags `main` | 16 done items still open; #38 not closed; unlinked and missing tickets | Close with PR comments; label drops `wont-do` (no Won't Do status exists); ticket every open row | L3 | **✅ Done 2026-09-21** (no PR; Jira only). 18 tickets moved to Done with PR comments, #38 labelled `wont-do`, about 17 renamed to carry row numbers, 29 created (SCRUM-176–204), so every open row has a ticket. [SCRUM-178] |
| 167 | Two kanban boards disagree | Project #1 duplicates #2; closed issues #24/#27 show "In review"; duplicate issues #12/#34, #10/#35 | Keep "KanBan Board" (#2), close #1, fix cards | — | **✅ Done 2026-09-21** (no PR; GitHub only). #24 and #27 moved to Done on board #2; all 22 cards match their issues; board #1, which held the same 22, is closed (not deleted). [SCRUM-179] |
| 168 | Coverage gate is rounded and floors are stale | #152: 94.5% passes a 95% gate while printing FAIL | `--cov-precision=2`, floors = current measured values, only ever raised; delete confirmed-dead code | L3 | **✅ Done — PRs #135 (`80787ea`) and #143 (`4792a27`).** `--cov-precision=2` on all four gates. Copilot really at 95.23% after `quarters.py` tests. Whole-app floor 55 → 89.5 (measured 89.94%). Tripwire test covers both. Dead code deleted in #143 after Andy approved the re-checked list; the ICS download race it hid was fixed with one joined query; every touched file at 100%; whole-app floor 90.5 (measured 90.61%). Three more unused pieces (`seats_left`, the `bypass` option, the admin-count "no exclusion" mode) are tested and wait on Andy. [SCRUM-180] |
| 169 | Dependabot's pip update crashes | Rewrites the `torch 2.13.0+cpu` pin into one pip rejects; no backend update PRs open | Ignore torch in `dependabot.yml`; bump by hand | — | **✅ Done — PR #135** (`80787ea`). torch ignored at every level. [SCRUM-181] |
| 170 | E2E seed fails on an existing dev DB | `seed_e2e.py::_ensure_quarters` 409s on overlapping quarters | Reuse a covering quarter | — | **✅ Done — PR #136** (`cff7119`). There were three bugs, not one: quarter overlap (incl. archived rows), roster `shift_signup_id` read as `signup_id` (cancelled "None" → null confirm token → confirm e2e silently skipped), and `/test/seed-cleanup` returning before deleting cancelled shift commitments. Three reruns clean. [SCRUM-182] |
| 171 | Three e2e specs flake in parallel | Named: admin-a11y Exports, cross-role 1B and 6. **Wrong diagnosis:** they passed 6 of 6 full runs at normal load. Their failures were `loginAs` timeouts at load average 40+. The real flake was the logout test reading the csrf cookie while the boot refresh rotated it (403, 1 run in 3) | Wait for the boot refresh before logout | L6 | **✅ Done — PR #136** (`cff7119`). 120/120 across six browsers; full chromium suite 3 runs green in a row [SCRUM-183] |
| 172 | CLAUDE.md describes a dead workflow | v1.2 two-developer branch table; tells sessions on `main` to switch to `feature/v1.2-*` | Current one-developer workflow + rule 4 | — | **✅ Done — PR #137.** Rewritten for the current workflow: short-lived branches off `main`, one PR per piece, three trackers in step, rule 4. [SCRUM-184] |
| 173 | ~60 stale branches | Merged branches never deleted | Delete merged ones; list unmerged for Andy | — | **✅ Done 2026-09-21** (no PR). Deleted 61 GitHub and 50 local branches, each with a merged PR or fully in `main`, plus three Andy approved (PR #79, PR #50, `integration/w2-verify`). Six unmerged branches saved first as `archive/*` tags: both v1.4 eval branches, `fix/copilot-outbound-mail-coverage`, Hung's `v1.3` and `organizer-audit`, Jasmine's `jt-simulate-quarter`. Restore with `git switch -c <name> archive/<name>`. [SCRUM-185] |

**Jira audit, 2026-09-24.** Jira was read directly and compared with `main`.
SCRUM-16 was reopened (it was Done, but the runbook, K39 and the walkthrough are
open as #73, #78 and #79). SCRUM-33 was closed as a duplicate of SCRUM-23.
Twelve partly built tickets got a comment saying what remains, and ten went to In
Progress. Five tickets were filed after the fact for work that shipped without
one: SCRUM-207 (PR #125), 208 (#127), 209 (#143), 210 (#144) and 211 (three
deploy commits pushed to `main` with no PR: `ba33587a`, `7a0f39ea`, `491edd72`).
Every open ticket now has a parent epic.

## Phase L3 — Auth and abuse hardening (3–4 days) — **2 of 7 done · reopened 2026-09-21**

PR #117 (2026-09-10) shipped the auth half, #26 and #30, and the session that
merged it reported "L3 is done". It was not: #27, #28, #29 and #31 were never
built. The 2026-09-21 audit verified each against the code on `main`. L3 is
reopened and finishes before L5; see Phase S for how the trackers drifted.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 26 | Access + refresh in `localStorage` | One XSS takes the account | Cookie + in-memory + CSRF; ~21 files | L6 | **✅ Done — PR #117** (2026-09-10). Refresh token in an `HttpOnly` cookie, access token in memory, CSRF on cookie-authenticated routes, throttles on `/auth/refresh` and `/auth/logout` [SCRUM-73] |
| 27 | 3 endpoint groups have zero throttle | `magic/{token}`, `slots/{id}/resolve`, 5 organizer routes | Add limits | L6 | **⬜ Open — never built.** Verified on `main` 2026-09-21: the 5 `@router.post` routes in `organizer.py`, `POST /slots/{id}/resolve` in `check_in.py` and `GET /auth/magic/{token}` have no `rate_limit`. (#117 throttled only `/auth/refresh` and `/auth/logout`) [SCRUM-74] |
| 28 | Every throttle fails **open** on Redis error | Fine for uptime, useless for cost control | Fail closed on the expensive ones | L5 | **⬜ Open — decided 2026-09-21: split** (Andy). Fail closed on email fan-out, admin exports, the copilot, and the unauthenticated venue-code check-in routes; fail open on signup, login and staff roster check-in, so a Redis outage never stops volunteers or staff. Not built yet. [SCRUM-75] |
| 29 | 4 query paths unbounded | `CONFIG-24` = ~20,000 SELECTs in one request | Row-cap + paginate | L5 | **⬜ Open — never built.** The four unbounded query paths (`CONFIG-24`) are still uncapped [SCRUM-76] |
| 30 | No `aud`/`iss` claims minted or verified | `SEC-36` | Add both | L8 | **✅ Done — PR #117** (2026-09-10). `aud`/`iss` minted and verified on access tokens [SCRUM-77] |
| 31 | `refresh_tokens` grows unbounded | No reaper, no cap, can't list sessions | Reaper + cap — see #149, `magic_link_tokens` has the same problem and should share the job | L8 | **⬜ Open — never built.** Nothing reaps `refresh_tokens`. Build as one reaper with #149, which has the same problem on `magic_link_tokens` [SCRUM-78] |
| 177 | Malformed ids in URL paths 500 | Found 2026-09-21 by the e2e seed: `POST /signups/None/cancel` → 500 (`InvalidTextRepresentation` from Postgres). 52 path params across 9 routers are typed `str`, not `UUID`, so garbage reaches the DB. `/public/events/None` already 422s | Type the id params as `UUID` so FastAPI 422s before the query | L6 | **◐ Partly done** (audit 2026-09-24): some routes are typed `UUID` (e.g. `slot_id` in `check_in.py`), but about 65 `*_id: str` and `token: str` params remain across 9 routers [SCRUM-205] |

## Phase L4 — Known bugs (2–3 days) — **done 2026-09-21**

Four of the twelve were already fixed by later PRs when L4 began (#32, #39, #40, #42), found by the
readiness check on 2026-09-19; #38 was dropped; the other seven shipped in PRs #129, #130 and L4 PR 3.
Verification clicked the real flows in Chrome and turned up three faults the test suites passed over,
all fixed before merge — see #34.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 32 | Missing SendGrid var → task returns normally | Mail silently vanishes; looks like "nobody signed up" | Fail loudly. ~1h, highest value fix | L6 | **Done — already fixed by PR #82** (workers refuse to start without mail config; a send with no key raises). Found in the L4 readiness check, 2026-09-19 [SCRUM-79] |
| 33 | `magic.py:54,60,69` → `/signup/confirmed` | **Route doesn't exist; every confirmation 404s** | Add routes or fix redirect | L6 | **Done — PR #129.** Resend mail now links to the frontend confirm page; the legacy `/auth/magic/{token}` forwards the token there instead of burning it. Neither dead route was needed [SCRUM-80] |
| 34 | `/auth/magic/resend` has zero callers | A lost email is a dead end | Wire a button | L6 | **Done — PR #129.** Resend lives on the post-signup card, held for the backend's 60s idempotency window. Also fixed: resend minted tokens without `volunteer_id`, so the manage view 400'd after confirm [SCRUM-81] |
| 35 | Broadcast footer + unsubscribe links | Both broken in every email sent | Fix both | L6 | **Done — PR #130.** Manage tokens are minted at send time (only hashes are stored), per recipient for broadcasts. Left a growth follow-up: #149 [SCRUM-82] |
| 36 | `role_scope.py:39` scopes organizers by `owner_id` | Contradicts the 2026-08-12 ruling | Fix before any read tool ships | P4 | **Done — L4 PR 3.** Organizers are `see_all` in the copilot, matching `deps.ensure_event_staff_access`. Decided 2026-09-21: full alignment — 25 tests across 14 files inverted, and the organizer `cross_scope_leak` adversarial cases re-pointed at the PII boundary, since ownership is no longer one [SCRUM-83] |
| 37 | `/admin/notifications/recent` | 500s **permanently** once a shift notification exists | Fix query | L6 | **Done — L4 PR 3.** Schema bug, not a query bug: `signup_id` was required while shift rows carry `shift_signup_id` instead. Both are optional now [SCRUM-84] |
| 38 | A test pins orientation gate failing **open** | Contradicts the hard block | Invert the test | L6 | ✅ **Dropped 2026-09-20.** No backend test pins the gate open — the hard block holds (`public_signup_service.py`). The only fail-open test covers the client pre-check, and the server still returns 422. #6's 1-year credit expiry stays deferred with L11 [SCRUM-85] |
| 39 | School field dropped on event save | Accepted by form, lost server-side | Fix | L6 | **Done — already fixed by PR #76** (`EventUpdate.school`, 5 round-trip tests) [SCRUM-86] |
| 40 | Deactivation doesn't end sign-in | Deactivated staff can still log in | Revoke on deactivate | L8 | **Done — already fixed by PR #70** (`deps._account_usable` checked on every token path) [SCRUM-87] |
| 41 | 2 Exports range buttons unimplemented | Silently return all-time PII exports | Implement or remove | L6 | **Done — L4 PR 3.** Both presets implemented and labelled. Quarter presets that cannot resolve a range are now hidden rather than shown, since an empty range is read as "no filter" [SCRUM-88] |
| 42 | Legacy 24h reminder still sends | Volunteers get **two** day-before emails | Retire the legacy pair | L6 | **Done — already fixed by PR #63** (legacy beats removed from the schedule) [SCRUM-89] |
| 43 | 3 backend tests fail | Missing `/opt/hf-cache` mount, not broken code | Add mount to the documented command | L6 | **Done — L4 PR 3.** The three local-BGE tests skip, with instructions, when the weights are neither cached nor downloadable. They still run with a cache mounted. `CLAUDE.md` untouched [SCRUM-90] |

## Phase L5 — Hardening and scale (2–3 days) — *the missing Phase 37*

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 44 | Phase 37 has no directory, no plan | Load test, PII encryption, pending store all deferred here | Write the phase | L6 | None [SCRUM-91] |
| 45 | No WAF, no bot protection | App throttles fail open; nothing above them | Cloudflare rules | L9 | Depends on #1 [SCRUM-92] |
| 46 | No AWS spend cap | **The actual credit protection.** Throttles can't stop what fails open | Hard budget alarm + cap | L9 | None [SCRUM-93] |
| 47 | `_PENDING` store is in-memory | **Blocks running more than one worker** | Move to DB | L9 | **✅ Done — PR #67** (`39d6b59`). Pending confirmations moved to Redis (`copilot/agent/confirmation.py`), not the DB, so more than one worker is no longer blocked. Recorded 2026-09-21; it had shipped weeks earlier [SCRUM-94] |
| 48 | Zero load testing ever | Instance sizing is a guess; 512MB already OOM'd | Establish P50/P95 | L9 | None [SCRUM-95] |
| 49 | No Celery time limits; no API request timeout | Tasks hold DB sessions; fetches hang forever | Add both | L8 | None [SCRUM-96] |
| 50 | 2 of ~10 indexes landed; 13 FKs unindexed | W0.5 half-done | Add the rest | L8 | None [SCRUM-97] |
| 51 | CrossEncoder ~200s cold start | First request after boot stalls | Warm on startup or sidecar | L9 | None [SCRUM-98] |
| 149 | `magic_link_tokens` grows unbounded | Found in L4 (PR #130). Only a token's hash is stored, so a working manage link has to be *minted* per send — ~3 rows per signup from reminders, plus one per recipient per broadcast. No reaper, no cap. Same shape as #31, now on a second table and on a faster clock | One reaper covering both tables: consumed rows, and rows past a retention age (SCRUM-162) | L8 | None |
| 150 | Broadcast send does one INSERT per recipient, inline | Found in L4 (PR #130). Minting a per-recipient manage token added an insert to a synchronous request that already did per-recipient dedup work. Fine at current roster sizes (16 recipients was instant); a 500-volunteer event is untested | Measure under #48's load test; move the send loop to a task if it bites (SCRUM-163) | L9 | None |
| 151 | `broadcast_service.render_html` has no production caller | Found in L4 (PR #130). The send path uses `render_body_html` + `wrap_body_html` since the footer went per recipient; the old one-shot wrapper survives for a single test | Delete it and fold the test into the two it replaced (SCRUM-164) | L6 | None |
| 152 | Copilot coverage gate enforces 94.5%, not 95% | Found in L4 (PR #132). pytest-cov decides the exit code after rounding to a whole percent (`precision` defaults to 0) but prints FAIL from the unrounded total — so 94.5% and up passes while the log says FAIL. `main` has sat at 94.60% under the stated 95% bar, 0.10 above the real one, and every green run prints FAIL | Test the existing gaps (`operations`, `quarters`, `create_event_with_schedule`, `events_edit`, `orientation_credits`) until it clears 95% for real, *then* add `--cov-precision=2` to the four gate steps and update `test_coverage_gates.py` (SCRUM-175) | L6 | **✅ Done — fixed by #168, PR #135** (`80787ea`): `--cov-precision=2` on all four gates; `app.copilot` at a real 95.23%. |
| 153 | `audit_logs` retention decided, never built | Gate 0 #7 set 3 months on 2026-09-07; nothing on `main` deletes old rows and no row tracked building it | Celery beat purge of `audit_logs` older than 3 months | L9 | None. Added 2026-09-21 from the tracker audit [SCRUM-186] |
| 156 | Venue codes are 4 digits and never expire | GitHub #46: follow-ups from the #31 hardening review. The throttle is the only ceiling on guessing (residual S-02); ties to #28 | Rotate or expire venue codes; revisit with #28's fail-closed rule for unauthenticated check-in | L6 | None. Added 2026-09-21 from the tracker audit (GH #46) [SCRUM-187] |
| 157 | Celery `statement_timeout` override documented, never built | SCRUM-161: described in two files but absent; long tasks share the web 15s DB timeout | Add the Celery-side override | L9 | None. Added 2026-09-21 from the tracker audit (SCRUM-161) |
| 158 | Large CSV exports are uncapped | SCRUM-173: event, privacy-request and attendance exports load everything in memory. Close to #29, which doesn't cover them | Cap or stream them | L6 | None. Added 2026-09-21 from the tracker audit (SCRUM-173) |
| 179 | 35 known dependency advisories are baselined, not fixed | SCRUM-45: the first pip-audit run found 42 across 13 packages; `backend/.pip-audit-baseline.txt` still lists 35, so CI only fails on *new* ones. The file was meant to shrink to empty. Includes starlette's form-parsing limit (BASE-CONFIG-36), accepted on older information | Fix each or write a reachability assessment; empty the baseline. Watch the torch/transformers pins | L9 | None. Added 2026-09-21 from Jira [SCRUM-45] |
| 163 | Coverage is not 100% and code is excluded | 88.75% measured strictly: ~1,000 lines + 600 branch paths untested; 4 files omitted and 15 `pragma: no cover` lines. `tasks/reminders.py` and `seed_admin.py` run in production with 0% coverage | Ratchet from #168 (every PR fully tests what it touches), then the final PR empties the omit/exclude lists and raises every gate to a hard 100% | L6 | **Decided 2026-09-21:** 100% of code tested, no exclusions; raised as we go, final gate after L5. **Frontend included** (widened same day): vitest had gated only `authToken.js`/`authStorage.js`; whole-`src/` baseline measured 2026-09-21: statements 73.66%, branches 69.48%, functions 65.36%, lines 75.23% (697 tests); same ratchet, hard 100% on all of `frontend/src/` after L5. **◐ In progress (audit 2026-09-24):** PRs #135 and #143 raised the backend floor to 90.5 and cut `pragma: no cover` from 15 lines to 4; the omit list is 3 files. The frontend gate and the hard 100% remain [SCRUM-188] |

## Phase L6 — Verification (3–4 days) — *the long pole*

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 52 | Nothing started | Its own roadmap: "biggest single batch of code in the whole plan" | Budget 4 days, not 2 | L7 | None [SCRUM-14] |
| 53 | 53 smoke boxes unticked, sign-off blank | **Nobody has ever clicked through this app** | Run all three roles | L7 | None [SCRUM-99] |
| 54 | W6.1 every route × role × phone | Route-gating tests can't see over-disclosure *within* a page | Manual pass | L7 | None [SCRUM-18] |
| 55 | W6.2 side-effecting flows w/ Mailpit | Shifts changed everything and were never re-walked | Full pass | L7 | None [SCRUM-19] |
| 56 | W6.3 emails in real clients | Never opened in Gmail/Apple/Outlook | Test all four | L7 | None [SCRUM-20] |
| 57 | W6.4 adversarial input | Static audit only, no runtime testing | Manual pass | L7 | None [SCRUM-21] |
| 58 | INTEG-04 blocked on a human since Phase 20 | Status literally `human_needed` | Do the dry run | L7 | None [SCRUM-100] |
| 59 | 11 unrun UAT tests across phases 15/16/17 | All marked `[pending]` | Fold into this pass | L7 | None [SCRUM-101] |
| 60 | W6.5 regression tests | P0s found by hand won't stay fixed | One test per P0 | L8 | None [SCRUM-22] |
| 155 | Nothing tests real event-day conditions | SCRUM-23 / SCRUM-33: school wifi, phones, several people checking in at once. No L6 row covers it | A rehearsal under event conditions before L9 | L7 | None. Added 2026-09-21 from the tracker audit (SCRUM-23, SCRUM-33) |
| 176 | QR check-in never had a real test pass | GitHub #31: QR check-in exists (#45, #74) but was never tested end to end or promoted to preview | Test pass, then enable in preview | L7 | None. Added 2026-09-21 from the kanban board (GH #31) [SCRUM-204] |

## Phase L7 — Fix what L6 finds (2–3 days, unbounded)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 61 | Unknown scope | All ~140 known product bugs came from *reading* code | Reserve real time; expect surprises | L8 | None [SCRUM-102] |

## Phase L8 — Re-audit 3 (1 day)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 62 | Not started | Verifying your own fixes isn't verification | Independent pass over L3/L4/L5 | L9 | None [SCRUM-15] |

## Phase L9 — Deploy (2–3 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 63 | 2 personal API keys in `backend/.env` | OpenRouter + Jina; `.dockerignore` won't clear built images | Rotate everything | L10 | None [SCRUM-103] |
| 64 | Render `ENVIRONMENT` value unverified | If unset or `prod`, **OpenAPI has been public** | Check; treat as disclosed if so | L10 | None [SCRUM-104] |
| 65 | 13 `deployment.md` boxes unchecked | Never worked | Work them | L10 | None [SCRUM-105] |
| 66 | 8 AWS boxes unchecked; no domain | Let's Encrypt won't issue for a bare IP | Buy a domain | L10 | None [SCRUM-106] |
| 67 | RDS KMS not enabled | **Load-bearing condition of the PII acceptance** | Rafael enables it | L10 | None [SCRUM-107] |
| 68 | Backend port publishable | starlette CVE ceiling lives only in Caddy | Never publish it | L10 | None [SCRUM-108] |
| 69 | Frontend copilot flag is build-time | `COPILOT_ENABLED=true` does **not** cover it | Set `VITE_COPILOT_ENABLED` at build | P4 | None [SCRUM-109] |
| 70 | Corpus not ingested | Every RAG answer returns empty | Ingest once post-deploy | P4 | None [SCRUM-110] |
| 71 | Backups documented, never tested | Untested backup isn't a backup | One restore drill | L10 | None [SCRUM-111] |
| 180 | Two deploy-topology checks from the old W4 plan | SCRUM-11: `celery_worker` and `celery_beat` must run as **separate** AWS tasks (five beat schedules die silently otherwise), and the proxy-header fix lives only in `start_render.sh`, which the AWS path never runs, so rate limiting would put every caller in one bucket per path | Confirm both on the AWS task definitions at deploy | — | None. Added 2026-09-21 from Jira [SCRUM-11] |

## Phase L10 — Re-audit 4 + ZAP (1 day)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 72 | Never run | No dynamic security testing has happened at all | Exhaustive pass + ZAP on the live URL | L11 | None [SCRUM-17] [SCRUM-24] |

## Phase L11 — Handoff (1–2 days) — 🏁

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 73 | `PRODUCT-BRIEF.md` teaches soft warning ×3 | K39; `DEPLOY-ROADMAP-v2.md:29` repeats it | Fix both | — | Depends on #6 [SCRUM-112] |
| 74 | `30-not-built.md` says SSO exists | Deleted 2026-08-13 | Correct it | — | None [SCRUM-113] |
| 75 | README/CLAUDE.md describe deleted CSV pipeline | Stale by 2–3 milestones | Rewrite both | — | **◐ Half done.** CLAUDE.md rewritten in PR #137 (#172). README.md still describes the deleted CSV pipeline. [SCRUM-114] |
| 76 | 5 `appArchitecture.js` nodes claim email blocked | Resolved 2026-08-06; the site lies about the app | Correct all five | — | None [SCRUM-115] |
| 77 | `ccpa-policy.md` has 7 `TODO(copy)` | **The copilot cites this document** | Fill them in | — | Hung owns [SCRUM-116] |
| 78 | No runbook | Rafael can't operate it | Write it | 79 | None [SCRUM-117] |
| 79 | No walkthrough done | This is the exit criterion | Live walkthrough with Rafael | — | None [SCRUM-118] |
| 154 | Orientation credit never expires | Gate 0 #6 (2026-09-07) decided credit expires after 1 year; `has_orientation_credit` is still permanent | Add the expiry check and fix `PRODUCT-BRIEF.md` (K39) | — | None. Added 2026-09-21 from the tracker audit (SCRUM-151) |
| 162 | Help document is out of date | GitHub #15: rewrite to cover full functionality and policy; matters for the handoff | Rewrite it | — | None. Added 2026-09-21 from the tracker audit (GH #15) [SCRUM-189] |

---

# Milestone P — Product completion (3–4 weeks, post-launch)

Nothing here blocks launch. Ordered by value per day.

## Phase P1 — Organizer mobile (3–4 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 80 | Organizers: 67 endpoints, 2 screens | Admin shell is desktop-only; their device is a phone | Mobile-capable roster | — | None [SCRUM-191] |
| 81 | Bottom-nav "Events" → `DesktopOnlyBanner` | Dead end on the device they actually use | Fix the nav target | — | None [SCRUM-192] |
| 82 | 2 `/organizer/promote` endpoints exist | No button anywhere | Add to roster | — | None [SCRUM-119] |
| 83 | Cancel/move/swap/resend staff-allowed | No organizer control for any of them | Add to roster | — | None [SCRUM-120] |
| 84 | Grant-credit button is desktop-only | Endpoint is organizer-namespaced | Add to roster | — | None [SCRUM-121] |
| 85 | Fill rate is admin-only | Organizers can't see staffing on a phone | Add to roster | — | None [SCRUM-122] |
| 160 | Rosters don't show who is oriented | GitHub #12 / #34 (the same request filed twice). Orientation blocks signup, so organizers need it on event day | Show oriented status on module and period rosters | — | None. Added 2026-09-21 from the tracker audit (GH #12, #34) [SCRUM-190] |

## Phase P2 — Role gaps (4–5 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 86 | No signup-on-behalf path | No endpoint, no UI, no tool. **Phone-in volunteers can't be added** | Build it | — | None [SCRUM-123] |
| 87 | Phone read only by a copilot tool | Day-of "call the missing volunteer" impossible | Show on roster | — | **◐ Partly shipped — PR #115** (`ac657647`): the phone shows on the admin roster with a `tel:` link. Not on the organizer phone roster. Close, or narrow to the phone roster (P1). Noted 2026-09-24 [SCRUM-124] |
| 88 | Reminder opt-out invisible to staff | Suppressed volunteer looks like one ignoring mail | "Reminders: off" badge | — | None [SCRUM-125] |
| 89 | No volunteer self-cancel/swap | Removed 2026-08-02; seats stay falsely filled | Rebuild token-scoped | — | Revisit removal [SCRUM-126] |
| 90 | CCPA acts on staff rows only | Statutory gap for CA volunteers; export omits answers + credits | Volunteer request path | — | None [SCRUM-127] |
| 91 | Organizers grant credit, can't list/revoke | Inconsistent with the endpoint they already have | Give them the list | — | None [SCRUM-128] |
| 92 | `Forbidden` is a bare `<h2>` | No way back | Style it | — | None [SCRUM-129] |
| 161 | "Staff" spelled six ways; role maps never cross-checked | SCRUM-12 remainder: S-03 six spellings of staff, T3 frontend/backend role-map cross-check. SCRUM-12's JWT half shipped in L3 | One spelling; one test pinning frontend and backend role maps together | — | None. Added 2026-09-21 from the tracker audit (SCRUM-12) |

## Phase P3 — UX epics (2 weeks)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 93 | `EventDetailPage` is 1,407 lines | Unmaintainable | Decompose | — | None [SCRUM-29] |
| 94 | No search/filter/sort on browse | SCRUM-27 | Build it | — | None |
| 95 | No loading/empty/error states | SCRUM-28, K38 | Add throughout | — | None |
| 96 | Admin event page IA | SCRUM-32 | Restructure | — | None |
| 97 | Events list + ops dashboard | Operations shows **no** signup or fill numbers | Add them | — | **◐ Partly shipped — PRs #114** (`4a475edb`, unique-volunteer count on the events list) **and #127** (`03d2a30a`, HS/MS). Fill numbers not confirmed. Noted 2026-09-24 [SCRUM-34] |
| 98 | 4 overlay impls, 3 toast systems, 3 headers | K37 | Consolidate | — | None [SCRUM-36] |
| 159 | Volunteer pages are hard to use on a phone | SCRUM-30 (high): L6 tests on phones, nothing builds for them | Mobile pass on the volunteer pages | — | None. Added 2026-09-21 from the tracker audit (SCRUM-30) |
| 174 | No contextual help on actions | GitHub #10 (duplicate #35 closed): a '?' tooltip on every action | Add tooltips | — | None. Added 2026-09-21 from the kanban board (GH #10) [SCRUM-202] |
| 175 | Login page looks empty on a laptop | GitHub #14: mobile-first layout, centered in a void on wide screens. Check first whether closed card #27 (login redesign) already covered it | Laptop layout without regressing mobile | — | None. Added 2026-09-21 from the kanban board (GH #14) [SCRUM-203] |

## Phase P4 — Copilot completion (1 week)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 99 | Read tools written, switched off | Docs: "not finished enough to turn on" | Finish, then enable | — | **⏳ Enabled on `main`** (#67, #69: tools registered, `copilot_agent_loop_enabled=True`). Left to close it: `docs/knowledge-base/31-about-the-copilot.md` still says the tools are off, and the copilot cites that doc to users [SCRUM-206] |
| 100 | Organizer scoping wrong | Must fix #36 first or copilot is stricter than the API | Fix then ship | — | **✅ Done — PR #132** (2026-09-21). Organizers are `see_all` in the copilot, matching `deps.ensure_event_staff_access`; see L4 #36 [SCRUM-130] |
| 101 | `_dispatch` seams are stubs | Return the planned action; call no real task | Wire to Celery | — | **✅ Done — PR #78** (`5f54bce`). `_dispatch` calls `_outbound.dispatch`. Sending is off by default in config |
| 102 | Both mail tools raise `OutboundNotWired` | No transport bound | Depends on #22 | — | **✅ Done — PR #78** (`5f54bce`), the same change as L2 #22 [SCRUM-131] |
| 103 | Corpus has no real test questions | Highest-value KB docs missing | You write them | — | Depends on #12 [SCRUM-38] |
| 104 | `copilot_tool_calls` write-only | Never read back by anything | "What did the copilot do" view | D3 | None [SCRUM-132] |

## Phase P5 — Accessibility + cleanup (1 week)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 105 | **Few `:focus-visible` rules** | K40. Was "zero"; a count on 2026-09-24 found 10 rules in 5 files (`ui/Button`, `Input`, `Chip`, the browse and detail pages). No global rule, no skip link | Add throughout | — | **◐ Partly done.** Global rule, skip link and the components without one remain [SCRUM-133] |
| 106 | One Escape closes modal + drawer | K15; discards unsaved work | Focus trap + restore | — | **Partly done 2026-09-07 (SCRUM-156, PR #88): the *Cancel* route now prompts before discarding, and `EventSettingsModal` / `DuplicateEventModal` finally pass `dirty` so their prompt can fire at all. The Escape-closes-two-layers half and focus trap/restore remain open.** [SCRUM-134] |
| 107 | ~10 dead endpoints/tables/aliases | `custom_answers` has no INSERT anywhere | Delete them | — | Depends on #8 [SCRUM-135] |
| 108 | ~25 dead `api.js` exports | K35; `api.register()` doesn't exist | Delete | — | None [SCRUM-136] |
| 109 | 3 settings stored, never read | `default_privacy_mode`, `allowed_email_domain`, `visibility` | Wire or drop | — | Per setting [SCRUM-137] |
| 110 | Coverage floor 55, target 70 | "Plan 07 follow-up", never done | Raise it | — | **✅ Done 2026-09-21 — PRs #135 and #143.** The floor is 90.5 at two decimals (measured 90.61%), past the old target of 70; #163 carries it on to 100. [SCRUM-138] |
| 111 | No `app.eval` CI gate | Absent entirely, not just lowered | Add it | — | None [SCRUM-139] |
| 112 | v1.3 suite skipped **and** body is `expect(true)` | Un-skipping tests nothing | Write it or delete it | — | Write or delete [SCRUM-140] |
| 178 | No bundle splitting | SCRUM-44 (W4.10): zero `React.lazy` routes and no `manualChunks`, so every visitor downloads the admin and copilot code | Lazy-load the admin and copilot routes | — | None. Added 2026-09-21 from Jira [SCRUM-44] |
| 113 | ~113 baseline findings open | 9 High, 68 Medium, 36 Low | Work by severity | — | None [SCRUM-193] |

## Phase P6 — Copilot production hardening (added 2026-09-07)

Separate from P4 (Copilot completion, items 99–104) by Andy's decision — P4 keeps its
original scope (read tools, dispatch stubs, mail transport). This phase is the deeper
production-readiness pass: corpus quality, RAG architecture, concurrency, and guardrails.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 133 | Corpus has no real test questions | Ties to Gate 0 #12 — only Andy knows real SciTrek policy | Write real Q&A pairs against the actual corpus | 137 | Andy's to write [SCRUM-38] |
| 134 | Corpus content itself unaudited | Never reviewed for completeness/accuracy since ingestion | Update/refresh corpus content, not just add tests | 137 | None [SCRUM-194] |
| 135 | No CSV-driven event creation via the copilot | **Reverses PR #51** (CSV import removed on purpose — "modules made by hand in admin UI"). Andy confirmed 2026-09-07 this is intentional. **Update: not a clean-room build — refactor/reuse the old removed CSV-import pipeline code as the basis, wired into the copilot as a file-upload tool instead of the old standalone `/admin/imports` surface** | Refactor old CSV-import logic into a copilot file-upload tool; parse CSV, create events via existing admin endpoints | None | **Confirmed 2026-09-07: build it, via refactor of old pipeline** [SCRUM-195] |
| 136 | RAG pipeline architecture unverified | Unknown whether retrieval is naive top-k similarity or a proper production pipeline (chunking strategy, hybrid search, reranking) | Audit current retrieval code; upgrade to production-grade if naive (proper chunking, reranking via the CrossEncoder already in the stack per ROADMAP #51, evaluation against the corpus) | 137 | None [SCRUM-196] |
| 137 | RAG concurrency behavior unverified | No load/concurrency testing has been done on the copilot pipeline (ties to ROADMAP #48, zero load testing ever) | Test concurrent requests specifically against the RAG/retrieval path, not just the API layer | L6 | None [SCRUM-197] |
| 138 | No prompt-injection defense | Untested whether corpus content or user input can hijack copilot behavior | Add input/output guardrails: system-prompt hardening, output filtering, refuse out-of-scope requests | None | None [SCRUM-198] |
| 139 | No scope-limiting / topic guardrail | Copilot could be asked about anything, not just SciTrek volunteer topics | Add a scope check — refuse or redirect off-topic requests | None | None [SCRUM-199] |
| 140 | PII handling in copilot unaudited | Copilot has tool access to volunteer data (phone, email per roster tools) — no check on what it's allowed to surface to whom | Audit tool outputs for PII over-disclosure; scope tool results by caller's role | Depends on #36 fix | None [SCRUM-200] |
| 141 | No per-user/per-session rate limit on copilot specifically | Gate 0 #9 funded the account (~1,000 req budget) but nothing stops one user/session burning it all | Add a rate limit on the copilot endpoint itself, not just the general API throttles | None | **✅ Per-user limit already exists** — `copilot/guardrails.py::enforce_user_rate_limit` (Redis, 60s window), wired in `copilot/router.py`; `872d62e` (2026-07-06), #73. This row was written after it shipped. A separate per-*session* limit does not exist; add one only if needed |
| 142 | No abuse/cost monitoring on copilot usage | No visibility into who's using it or how much, until the bill arrives | Log usage per session/day; alert on anomalous spikes | Ties to #46 (AWS spend cap) | None [SCRUM-201] |

---

# Milestone D — Data & BI (3–4 weeks) — rescoped 2026-09-10

Promoted from `seeds/v1.4-data-pipeline.md`, renumbered off the 30–35
collision, then **rescoped after a full codebase scan on 2026-09-10**. Four of
the seed's decisions were overturned; see the Decision column. Was 4–6 weeks
and 5 phases; now 3–4 weeks and 8, because removing parquet and dbt is a bigger
saving than adding D0 and D6 costs.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 114 | Seed drafted 2026-04-17, never promoted | Its phases 30–35 **collide** with copilot 30–38 | Renumber to D0–D7 | D0 | Done |
| 144 | **D0** Public path emits nothing | `backend/app/routers/public/` has **zero** `log_action` calls. Every volunteer who browses and leaves is invisible, and that data is unrecoverable — every week without this is a week of funnel gone | `backend/app/telemetry.py` + `product_events` outbox table. Server-side only, off by default, transaction-scoped, per-event property allowlist | D3 | **New 2026-09-10 — was in no plan and no Jira ticket. Ship FIRST, ahead of the rest of D;** everything else reads tables that already exist and can be built retroactively at any time [SCRUM-158] |
| 115 | **D1** No warehouse schema | Nothing exists — no `analytics/`, no exports | `warehouse` schema of **materialized views** in the existing Postgres 16, model registry, refresh runner, `etl_run` table, one nightly Celery beat entry at 04:15 PT | D2 | **Changed 2026-09-10: no parquet.** The seed exported Postgres → parquet on disk → back into the same Postgres. No reader, needs a Docker volume (`docker-compose.yml` is PR-only), adds ~90MB `pyarrow`, and — decisive — dated parquet files are a third place PII lives with no deletion story [SCRUM-141] |
| 116 | **D2** No dims or facts | No star schema, no conformed grain | `dim_date/quarter/volunteer/user/event/module/school/signup_status`; `fct_commitment`, `fct_session_attendance`, `fct_bookable_unit`, `fct_orientation_credit` | D3 | **Changed 2026-09-10: plain versioned `.sql`, not dbt.** ~12 models is ~60% overhead for dbt. Adopt at ~25 models or a second SQL author; structure one model per file with explicit `warehouse.` prefixes so conversion is later a `sed`. **Full-refresh nightly, no incremental** — see #146 [SCRUM-142] [SCRUM-165] |
| 145 | **D2a** Dual signup grain | `signups` (orientation, own `checked_in_at`) vs `shift_signups` (N rows in `session_attendance`) are genuinely different grains — the hardest modelling call here | **Port `backend/app/services/attendance_facts.py::facts()`**, do not reimplement. One `fct_commitment` with a `commitment_type` discriminator | D2 | ✅ **Resolved 2026-09-10 — already solved in code.** `0037_add_shifts.py` moved every PERIOD signup into `shift_signups` and deleted the sources, so the two tables are subtypes, not parallels. Divergence between the matview and `facts()` would make a chart and the admin UI disagree about the same event — pin it with a parity test |
| 117 | **D3** No SCD-2 history | Full refresh cannot reconstruct last Tuesday's `signups.status` | `snap_signup_status` — the only persistent warehouse table. Derive from D0's event log where available; nightly poll only for pre-instrumentation backfill and reconciliation | D4 | Depends on D0 landing first [SCRUM-166] |
| 118 | **D4** No BI connection | Switched from Power BI 2026-09-07 (Mac-only dev team, no license) | `bi_reader` role: read-only, `warehouse.*` only, `REVOKE ALL ON SCHEMA public FROM PUBLIC`, per-tool login roles, `statement_timeout`. Idempotent checked-in SQL, **not** Alembic — roles are cluster objects | D5 | **Changed 2026-09-10: Metabase, not Tableau.** Gate 0 #11's Tableau choice is downgraded from an architecture decision to a client choice — the seam is a Postgres role, so Metabase/Tableau/Power BI are all ordinary clients. Metabase is $0, open source, Mac-fine, self-serve for non-technical staff. **Tableau for Teaching explicitly forbids administrative use**, so a student licence cannot legally cover the scorecard; if Tableau is wanted later, get a seat from UCSB Data Services (who already run it institutionally) rather than buying one [SCRUM-143] |
| 146 | **D4a** ETL readiness | `updated_at` missing on `users`/`events`/`signups`/`shift_signups`/`audit_logs`; `slots` has no timestamps at all; six tables spell `created_at` differently | **Add no columns. Full-refresh every model nightly** | D2 | ✅ **Decided 2026-09-10.** Three reasons: (a) largest fact is a few thousand rows — nothing to optimise; (b) SQLAlchemy `onupdate` is client-side and every bulk `.update()` bypasses it, including `ccpa_delete`'s four — an `updated_at` that lies during a deletion is worse than none; (c) full refresh makes CCPA anonymisation propagate to the warehouse in ≤24h with **zero** deletion-propagation code. The naming inconsistency is aliased in each staging model's SELECT |
| 119 | **D5** No new questions answered | Existing ~20 endpoints answer "how did X do", never "where do people drop out" or "do they come back" | Funnel, cohort retention, time-to-confirm, cancellation lead time, volunteer lifecycle, partner scorecard, pipeline health — all reading `warehouse.*` | D6 | None [SCRUM-144] [SCRUM-169] [SCRUM-170] [SCRUM-171] |
| 147 | **D6** Nothing notices a dead pipeline | No monitoring of any kind; a stale warehouse would serve three-week-old numbers silently | `etl_run` table, freshness assertions that refuse to swap an empty rebuild, `/api/v1/health/warehouse` 503 past 26h, and an amber staleness banner in `OverviewSection.jsx` | — | **New 2026-09-10.** The banner is the layer that actually works — it appears in front of the person reading the number, not in a tool nobody has open [SCRUM-159] |
| 148 | **D7** No-show guessing is manual | — | **Rules-based risk flag**: prior no-show ≥1, OR still `pending` within 48h of start, OR no orientation credit for the family. Roster dot | — | **Changed 2026-09-10: no ML model.** A few thousand labelled rows, heavily imbalanced, ~six weak features. A rule is more explainable to an organiser, gives a baseline any later model must beat, and accumulates labelled data while it runs. Revisit after two quarters. Gate 0 #4 already limits this to soft tracking — it informs, never acts [SCRUM-145] |

**Cost: $0/year.** The warehouse is a schema in the existing Postgres; Metabase
is open source. Self-hosted PostHog was considered and rejected — its cost is a
fixed ~8GB infrastructure floor (ClickHouse + Kafka + ZooKeeper + its own
Postgres + Redis) regardless of volume, i.e. ~$100/month for an idle cluster at
our ~4,000 events/month. PostHog Cloud's free tier (1M/month, ~250× our volume)
remains a $0 upgrade if a prebuilt funnel UI is ever wanted; Andy confirmed
2026-09-10 that no UCSB policy blocks pseudonymous behavioural data leaving
campus.

**Two defects found during the 2026-09-10 scan, both fixable ahead of D:**

- **✅ Fixed in PR #126 (SCRUM-160, DA-2).** `analytics_event_fill_rates` (`backend/app/routers/admin.py:2130`) was
  **numerically wrong** — it sums `slot.capacity` (a placeholder `1` for
  shift sessions, see `models.py:427-429`) and counts only `models.Signup`, so a
  15-shift × 6-seat event reports capacity 15 and fill 0. Both numbers wrong.
  `tests/test_admin_analytics_counts_shifts.py` covers this bug class but not
  this endpoint. ~1 hour.
- The Celery `statement_timeout` override documented at
  `backend/app/database.py:22` and `backend/.env.production.example:31`
  **does not exist** — `celery_app.py:23` imports the same `SessionLocal`
  carrying the 15s cap. The nightly refresh will hit it. Implement it, or fix
  both comments.

Addition kept from the original seed: tool success/failure/retry rate per tool,
sourced from `copilot_tool_calls` — a table currently write-only and never read,
so BI would be its first consumer. **Promoted to the first task for the DS
undergrad** — self-contained, no schema change, clones an existing pattern.

**Retained from the seed:** the four north-star questions, the `warehouse`
schema, the star schema, SCD-2 on signup status, `bi_reader`.
**Dropped:** parquet, dbt, Tableau-as-architecture, the scikit-learn no-show
model.

## Work breakdown — DE / DA / DS

Added 2026-09-21 at Andy's request when #118 was approved. The same work as the
D0–D7 rows above, cut by discipline, with one Jira ticket per item. **Size:**
S ≈ 1 day, M ≈ 2–4 days, L ≈ a week. **Hand-off?** says whether the item is safe to
give a new contributor (e.g. the DS undergrad) without deep app context.

### DE — Data Engineering (build the pipeline)

| # | Item | Row | Jira | Size | Hand-off? |
|---|---|---|---|---|---|
| DE-1 | **Warehouse harness.** A `warehouse` schema of materialized views in the same Postgres, a model registry, a refresh runner, and an `etl_run` table. One nightly Celery task (04:15 PT) | D1 #115 | SCRUM-141 | M | Yes |
| DE-2 | **Dimensions.** `dim_date`, `dim_quarter`, `dim_volunteer`, `dim_user`, `dim_event`, `dim_module`, `dim_school`, `dim_signup_status` | D2 #116 | SCRUM-142 | M | Yes |
| DE-3 | **Facts.** `fct_commitment` (the keystone: one row per booking, ported from `attendance_facts.facts()`, not reimplemented), `fct_session_attendance`, `fct_bookable_unit`, `fct_orientation_credit` | D2 #116, D2a #145 | SCRUM-165 | L | Yes, and the best big project |
| DE-4 | **SCD-2 snapshot** `snap_signup_status`, so the funnel can be rebuilt for any past date. The only persistent warehouse table | D3 #117 | SCRUM-166 | M | Yes, after DE-3 |
| DE-5 | **`bi_reader` role.** Read-only, scoped to `warehouse.*`. Metabase, Tableau and Power BI are then all just Postgres clients | D4 #118 | SCRUM-143 | S | Yes; Rafael does the network side |
| DE-6 | **Pipeline monitoring.** `etl_run`, freshness assertions, `/api/v1/health/warehouse` returning 503 past 26h, and a staleness banner in `OverviewSection.jsx` | D6 #147 | SCRUM-159 | S | Yes |
| DE-7 | **D0: event instrumentation.** `product_events` outbox for the public pages, which log nothing today. Needs the identity decision first (HMAC of email vs `volunteers.id`) | D0 #144 | SCRUM-158 | M–L | Partly |

**Skipped: parquet and dbt.** Parquet was a round trip to disk and back into the
same Postgres with no reader, needed a Docker volume and ~90MB of `pyarrow`, and
left dated files holding real names after a CCPA delete. dbt is ~60% overhead at
12 models. Adopt it at ~25 models or when a second person writes analytics SQL.
The `.sql` files are one model per file with explicit `warehouse.` prefixes, so
converting later is mechanical.

### DA — Data Analysis (find out what's happening)

| # | Item | Row | Jira | Size | Hand-off? |
|---|---|---|---|---|---|
| DA-1 | **Copilot tool success / failure / retry rate** per tool. `copilot_tool_calls` is written by `copilot/agent/audit_log.py` and read by nothing | D (seed addition) | SCRUM-167 | S | Yes, the best first task |
| DA-2 | **Fix `analytics_event_fill_rates`**, which reported shift events wrongly | D defect | SCRUM-160 | S | **✅ Done — PR #126** |
| DA-3 | **Staff feature usage.** `audit_logs` already records read actions (`admin_summary`, `admin_list_users`, `admin_analytics_*`). Which admin features does anyone use? Zero new code | D | SCRUM-168 | S | Yes |
| DA-4 | **Signup funnel:** the drop-off at each stage | D5 #119 | SCRUM-169 | M | Yes, after DE-7 (D0) |
| DA-5 | **Cohort retention:** cohort by quarter of first attendance. Do they come back in Q+1, Q+2? | D5 #119 | SCRUM-170 | M | Yes |
| DA-6 | **Time-to-confirm and cancellation lead time:** how many hours before start do people drop out? Tells an organizer how long they have to backfill | D5 #119 | SCRUM-171 | M | Yes |
| DA-7 | **Partner scorecard:** per school × quarter: sessions, unique volunteers, hours, fill rate, no-show %, orientation compliance | D5 #119 | SCRUM-144 | M | Yes |
| DA-8 | **Repoint the 8 aggregate analytics endpoints at the materialized views.** Same API contract; removes the attendance-rates N+1 and their load on the live tables | BASE-CONFIG-10 | SCRUM-172 | M | Yes |
| DA-9 | **Cap and stream the row-level exports** (`/events/{id}/export_csv`, CCPA export, attendance). They stay on the live tables but need a `LIMIT` cap and `StreamingResponse` over a cursor instead of `io.StringIO` | L5 #158 | SCRUM-173 | M | Yes |

The two numbers most likely to change behaviour are **cancellation lead time**
and the **one-and-done rate**. The second tells SciTrek whether its problem is
recruitment or retention. Neither can be answered today.

### DS — Data Science (predict)

| # | Item | Row | Jira | Size | Hand-off? |
|---|---|---|---|---|---|
| DS-1 | **Rules-based no-show risk flag:** prior no-show ≥ 1, OR still `pending` within 48h of start, OR no orientation credit for the module family. Shown as a roster dot | D7 #148 | SCRUM-145 | S | Yes |
| DS-2 | **No-show ML model**, only after two quarters of DS-1 running, so there is labelled data and a baseline to beat | D7 | SCRUM-174 | M | Not yet |

---

# Track X — Paper (parallel, off the critical path)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 120 | **X1** 2 branches, 82 commits, local | ~60 PRs of drift; testset gold answers now wrong | Merge, re-validate against current KB | X2 | None [SCRUM-146] |
| 121 | **X2** Control run done, treatment never finished | ~23% complete. **The paper's central evidence doesn't exist** | Run it, produce the delta table | X4 | None [SCRUM-147] |
| 122 | **X3** Contribution #1 never measured live | Agent loop raised `NotImplementedError` at eval time | Re-run with tools on the built loop | X4 | None [SCRUM-148] |
| 123 | **X4** No venue, deadline, authorship, IRB, draft | Ratings + profile text already collected from named staff | **IRB before the usage study, not after** | — | All yours [SCRUM-149] |
| 124 | 4 of 5 journal folders empty | 0 decisions, 0 concepts, 0 experiments, 0 failures | Backfill from PLAN/SUMMARY + git log | X4 | None [SCRUM-150] |
| 143 | **X5** DSPy / prompt-program experiment — un-parked 2026-09-07 | Was optional/deferred (old Phase 36); Andy now wants it done | Programmatic prompt optimization (DSPy) vs. hand-tuned prompts, compared on the same eval set as X2 | X4 | **Decided 2026-09-07: build it — un-parked, active** [SCRUM-153] |

---

# Explicitly parked — stop revisiting

| # | Item | Why parked |
|---|---|---|
| 125 | SMS / Phase 27 | ⏸ Parked. **Update 2026-09-07: A coworker owns this, not Andy — genuinely out of scope for this backlog, not just deferred** [SCRUM-43] |
| 126 | CSV import | ⏸ Parked. Deleted PR #51. **Update 2026-09-07: the old removed pipeline code is being refactored/reused as the basis for the new Phase P6 item #135 (copilot CSV-upload tool), not built clean-room** |
| 127 | Portals | ⏸ Parked. Removed. **Confirmed 2026-09-07: ignore — dead code (`PortalsAdminPage.jsx`, `PortalPage.jsx`), zero references anywhere, safe to delete whenever P5 cleanup happens** |
| 128 | SSO / OIDC | ⏸ Parked. Deleted 2026-08-13 |
| 129 | ~~Phase 36 DSPy~~ | ⏸ Parked. **Un-parked 2026-09-07 — moved to Track X as item #143 (X5), Andy wants this built, no longer optional/skipped** |
| 130 | BIOIN (40 open) + DOC (51 open) | ⏸ Parked. **Different products, different repos** — confirmed 2026-09-07: Andy's own other projects, correctly out of scope here |
| 131 | 34 missing SUMMARYs, phases 02–07 | ⏸ Parked. Paperwork; code shipped |
| 132 | ~430 unchecked `.planning/` boxes | ⏸ Parked. Only ~26 are real work |

---

# Timeline

| Milestone | Duration | Ends at |
|---|---|---|
| Gate 0 | your time | decisions made |
| **S (Stabilization)** | **1–2 days** | **trackers agree with `main`, CI honest** |
| **L (L0–L11)** | **4–6 weeks** | **live + handed over** |
| P (P1–P5) | 3–4 weeks | product complete |
| D (D0–D7) | 3–4 weeks | BI live |
| X (X1–X5) | 5–6 weeks | paper submitted |

L is 4–6 weeks rather than 3: the token migration (L3) and the missing hardening
phase (L5) add about a week, and L7 is genuinely unbounded because nobody has
clicked through the app yet.

P and X can run in parallel after L11 if alternated. D needs P's stability.

**Do today regardless of every decision:** #13 (push the eval branches) and
#18 (file the DNS request).
