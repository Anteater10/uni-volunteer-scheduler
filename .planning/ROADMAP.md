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

## Three structural rules

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
| 1 | No CDN/WAF anywhere; Caddy only | Deferred in Phase 09 to "Phase 15+", never picked up | Adopt Cloudflare | L1, L5, all DNS | **Decided 2026-09-07: Yes, Cloudflare Free plan** |
| 2 | Both tokens in `localStorage` | PR #79 exists to *accept* this, not fix it | Reverse it — fix properly | L2, L3 | **Decided 2026-09-07: Fix properly — close PR #79** |
| 3 | F2/F3 headers unapproved | F1's acceptance is void without the CSP | Approve | L2 | **Resolved 2026-09-07: Already implemented in code (CSP live in `frontend/nginx.conf` + `backend/app/main.py:158`, Dockerfile already runs non-root). No action needed — roadmap was stale.** |
| 4 | No consequence for no-show | K21 needs a policy, not code | Pick a rule | L4 | **Decided 2026-09-07: Soft tracking only — record no-shows on the volunteer's record, visible to organizers, no automatic block/penalty** |
| 5 | PR #50 closed unmerged | Its branch is the only impl of issue #25 | Abandon | L6 scope | **Decided 2026-09-07: Drop for good — delete the branch, close issue #25 as won't-do** |
| 6 | Orientation = hard 422 | PR #48 had a revert cycle; docs disagree | Confirm final | L11 | **Decided 2026-09-07: Confirmed correct as implemented (verified in `backend/app/services/public_signup_service.py:264-291` + `orientation_service.py`) — hard block when orientation+module both present and no credit; skip if credited; soft warning when no orientation on event. ONE CHANGE: orientation credit currently never expires — must now expire after 1 year (currently permanent/no-expiry per `has_orientation_credit`). Needs a code change (add expiry check), not yet built. `PRODUCT-BRIEF.md` (K39) still stale and needs fixing to match — queued under L11.** |
| 7 | `audit_logs` grows forever | Retention never decided | 12 months | L5 | **Decided 2026-09-07: 3 months — auto-delete audit_logs entries older than 3 months** |
| 8 | 8 dormant `/admin/imports` endpoints | Pipeline deleted PR #51, endpoints remain | Delete | P5 | **Decided 2026-09-07: Confirmed — delete all 8 dead endpoints** |
| 9 | OpenRouter unfunded, ~50 req/day | Can't load-test or demo the copilot | Fund it | L6 | **Decided/already done 2026-09-07: $10 credit already added, giving ~1,000 requests — no longer blocked** |
| 10 | SendGrid CNAMEs not requested | UCSB IT may refuse | Single-sender fallback | L1 | **Resolved 2026-09-07: Moot — `sci-trek.org` is self-registered by SciTrek, not a UCSB domain. No UCSB IT approval needed; whoever holds the registrar login can add the CNAME records directly. AWS deployment already sending real confirmation emails from `no-reply@sci-trek.org` successfully.** |
| 11 | Power BI seed unpromoted | Licenses/owner/warehouse unknown | Answer all three | D1 | **Decided 2026-09-07: Switched from Power BI to Tableau — no Power BI license exists yet, no stakeholder mandate for it specifically (only general post-launch analytics need), and dev team is Mac-only (Power BI Desktop is Windows-only; Tableau has a native Mac app). Build analytics on Tableau instead once Milestone D starts post-launch. Owner/warehouse-sizing questions deferred until D1 planning.** **Superseded in part 2026-09-10: after a full codebase scan, the BI tool is downgraded from an architecture decision to a client choice — the seam is a read-only Postgres role over `warehouse.*`, so Metabase, Tableau and Power BI are all ordinary clients. Metabase is the primary ($0, open source, native Mac, self-serve for non-technical staff); Tableau stays available and, if wanted, should come from UCSB Data Services' existing institutional deployment rather than a new purchase — note Tableau for Teaching licences explicitly exclude administrative use. Warehouse sizing is also now answered: the existing Postgres 16 instance, indefinitely.** |
| 12 | Copilot corpus has no real questions | Only you know SciTrek policy | Write them | P6 | **Decided 2026-09-07: Moved into Phase P6 (item #133) — Andy will write these as part of the copilot hardening phase, not standalone** |

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
| 13 | 2 eval branches, 82 commits, local only | No remote ref — one laptop holds the paper's evidence | Push both today | X1 | **✅ Done 2026-09-07** — both pushed to `origin`, refs verified identical: `…35-02-multimodel-eval` @ `8fb1a54` (37 commits), `…35-03-grounded-eval` @ `b0f2914` (45). Archival only — no PR, no merge. Pre-push secret scan clean (repo is public). Merging them is still open as X1 #120 / SCRUM-146. |
| 14 | 6 planning files untracked | One is the only record of F6 | Commit | Nothing | **✅ Done — `3e2cab5`, merged in PR #89 (`3af0c15`)** — scope widened to the whole tree: 7 superseded docs moved into `.planning/archive/superseded-2026-09-04/` (recorded as **renames**, history preserved), the 2026-08-20/28 snapshots, ROADMAP + STATE updates, `PRODUCT-BRIEF.md`, `WORK-INVENTORY.md`. `PLAN-2026-08-20.md` — the only record of F6 / item #32 — is now in version control. |
| 15 | `architecture-site` rework uncommitted on `main` | Done and builds clean, just sitting there | Commit on a branch | Nothing | **✅ Done — `2a22a64`, merged in PR #89 (`3af0c15`)** — 5 files, +399/−110. "Builds clean" verified, not assumed: `npm run build` → vite 7.3.3, 36 modules, no errors. **Two follow-ups from the register were NOT folded in** — the dead `onNodeHover`/`onLeave` props on `FlowDiagram`, and `wrapSvgText` rendering the literal `"undefined"` for a subtitle-less node. Still outstanding. |
| 16 | `BioApp/` nested untracked git repo | Shows as untracked forever | Gitignore or move out | Nothing | **✅ Done 2026-09-07** — deleted outright rather than gitignored. It was a standalone repo (1 commit, `LICENSE` + empty readme, clean tree) already pushed to `github.com/Anteater10/BioApp`, so nothing was lost. |
| 17 | 4 stashes from April, 2 dead worktrees | Bases deleted; won't apply | Drop and prune | Nothing | **✅ Done 2026-09-07** — `git stash clear` + `git worktree prune`; dropped without patch export after review. All four were 2026-04-15 snapshots of Phase 16, which shipped in v1.2-prod on 2026-04-17 (all seven `16-0N-SUMMARY.md` + `16-VERIFICATION.md` on `main`; `scripts/verify-overrides-retired.sh` still present). Unappliable anyway — 3 of 4 bases gone. |

## Phase L1 — File the DNS request (0.5 day) — ✅ COMPLETE 2026-09-08 (done by circumstance)

Closed with **no DNS work performed**: domain authentication was already live and
nobody had recorded it. The phase's founding premise — "UCSB IT may refuse the
CNAMEs" — never applied, per Gate 0 #10. Remaining polish is deferred to the
SendGrid → SES port, where it would be redone anyway. Jira: SCRUM-69 Done.

| # | Current situation | What's wrong | Recommendation | Blocks | Status |
|---|---|---|---|---|---|
| 18 | No verified sender domain | Premise was wrong twice over | Nothing to do | L9, all email | **✅ Moot — verified from public DNS 2026-09-08.** DKIM is live: `s1._domainkey` and `s2._domainkey` → `s1`/`s2.domainkey.u113425370.wl121.sendgrid.net`, both resolving to a real RSA key. So SendGrid domain auth was configured at some point and never written down — which is why real mail from `no-reply@sci-trek.org` has been arriving. No UCSB IT step was ever needed (Gate 0 #10 — the domain is SciTrek's own, at IONOS). Rest of the zone: apex A `52.35.73.159`, MX `mx00`/`mx01.ionos.com` (inbound stays IONOS), SPF `v=spf1 include:_spf-us.ionos.com ~all` — which does **not** name SendGrid, and that is correct under CNAME-based domain auth because the return path is a SendGrid-hosted subdomain with its own SPF. **Deferred to the SES port:** confirming the third CNAME (the `emNNNN` return-path subdomain, not resolvable from outside without the number — it is in SendGrid → Sender Authentication), and adding a DMARC `rua=` (currently `p=none` with no reporting address, so nobody receives reports). No ticket ever existed for this row; recorded here instead. |
| 19 | Cloudflare not decided | CNAMEs must be DNS-only, not proxied | Decide #1 before filing | L9 | **✅ Decided (Gate 0 #1: Cloudflare Free) — and the constraint outlives this phase.** When Cloudflare is adopted, the DKIM CNAMEs and MX must be **DNS-only, never proxied**: an orange-clouded `_domainkey` resolves to a Cloudflare IP instead of SendGrid's value and breaks DKIM silently, with the records still looking correct in the dashboard. Only the web A record should be proxied. Carried onto SCRUM-56, since adopting Cloudflare is a nameserver migration off IONOS and the whole zone has to be re-created there. Sequencing it **after** the SES port avoids doing the sender records twice. |

## Phase L2 — Land what's already built (1–2 days) — ✅ COMPLETE 2026-09-08

Merged in order: **#91** `be0dbde`, **#92** `27bf2e3`, **#78** `5f54bce`,
**#80** `5cbbab7`, **#93** `89556b8` — plus **#94** for the organizer
check-in QR (see #26.1 below). PR **#79 closed**. Jira: SCRUM-8/9/10/70/71/72
all Done. Order mattered once: #91 had to precede #80, see #20.

| # | Current situation | What's wrong | Recommendation | Blocks | Status |
|---|---|---|---|---|---|
| 20 | PR #80 open (CI net) | Built but never merged; roadmap said done | Merge | L8 | **✅ Merged `5cbbab7`.** Refreshed onto current `main` first — its green checks were 10 days old and it was 9 behind. That refresh made its own pip-audit gate fail on **its first real finding**: `CVE-2026-9856` against `transformers 4.57.6`, published after the baseline was written. Baselined with reasoning inline (the fix is a **major** jump on the library the copilot's embedding + reranker use); triage → SCRUM-45, now 35 advisories. **Also carried #21's `REFRESH_TOKEN_EXPIRES_DAYS: 14→2` in `ci.yml`** — merging it before #91 would have left CI testing 2 days against an app shipping 14. Now agree: `ci.yml:51`/`:236` and `config.py:54` all say 2. |
| 21 | PR #79 open (accept localStorage) | Contradicts #2 if you're fixing tokens | Close it | L3 | **✅ Closed, salvaged into #91 `be0dbde`.** #79 bundled three things; only the acceptance document was reversed. Kept: the 14→2 refresh-window narrowing (a compensating control until L3, not a substitute) and `docs/security-review-frontend-infra.md` — which *recommends* the HttpOnly-cookie fix, so it never conflicted with Gate 0 #2. Landed with a status note so a 2026-08-20 snapshot isn't read as current state. Volunteer magic links untouched at 14 days, deliberately. |
| 22 | PR #78 open (copilot mail transport) | `nudge_understaffed_module:50-59` targets the **whole volunteer table** | Fix recipients, then merge | P4 | **✅ Merged `5f54bce`. This description was already out of date** — the mass-mail policy was fixed on the branch: 120-day window either side of the module, in scope, minus those already signed up, opt-outs skipped, hard cap 200 above which it **refuses** rather than mailing a prefix. Sending still defaults **off**. What actually blocked it was coverage, in **two** gates: `app/celery_app.py` at 100% (ci.yml:110) and `app.copilot` at 95% line+branch (ci.yml:160-165). Nine tests added; both files now 100%. |
| 23 | `Caddyfile:36` HSTS-only; Dockerfile has no `USER` | F2/F3/F4 never shipped | Ship all three | L8 | **✅ Done — but Gate 0 #3 was half wrong.** F2/F3 headers were already live (`frontend/nginx.conf:30-40`, `backend/app/main.py:157-169`); `Caddyfile:36` HSTS-only is correct, not a gap. **F4 was not done:** Gate 0 #3 recorded "Dockerfile already non-root", true of `backend/Dockerfile:54` but not the frontend, whose stock nginx runs PID 1 as root (verified by running both images). Fixed in **#92 `27bf2e3`** via `nginx-unprivileged` (uid 101), forcing `listen 8080` and a matching Caddy change. **F3 was also not done** and I first closed it wrongly: `react-router-dom` was pinned at 7.14.0 with **nine** high advisories — fixed in **#93 `89556b8`** (→7.18.3). |
| 24 | K31 commit `569c3ff` on a branch | Roadmap marked it "✅ pushed" | Merge to `main` | Nothing | **✅ Not a separate task — landed inside #78.** `569c3ff` was the middle of that branch's three commits, never a loose commit needing a cherry-pick. Verified on `main`: the retry policy is in `backend/app/tasks/extract_profile.py` with its 212-line test. **Open question this raised:** `copilot_profile_extraction_enabled` is still `False`, and its recorded reason ("off until the request budget is large enough") has partly expired now Gate 0 #9 funded ~1,000 requests. One-line change, Andy's call. |
| 25 | 9 branches with unmerged work | Includes 39-commit `origin/v1.3` | Merge or delete each | Nothing | **✅ Every branch dispositioned.** Method matters: `git diff` totals are useless here because they don't say which side is newer — the reliable test is *which files does this branch add that `main` lacks*. Deleted `fix/confirmation-email-silent-failure` (its only unique lines would have **reverted** PRs #83 and #84). **`feat/deploy-baseline` is fully landed** — all 12 files it adds are on `main`, four are byte-identical including migration `0009`, and `main` leads every other file; my earlier "1,837 lines missing" was the diff trap. **`organizer-audit` likewise superseded** — `main`'s form-schema endpoints already admit organizers via `require_staff` with no owner filter, which is what the 2026-09-08 ruling wants. **Keep `v1.3`** — sole copy of ~837 lines of SMS work (someone else owns SMS). **Keep `fix/imports-templates`** — sole copy of the bulk-add UI, input to P6 #135. ~52 further remote branches are fully-merged clutter, not yet cleared. |
| 26.1 | Check-in QR unreachable on a phone | `CheckInQRModal` rendered only by `AdminEventPage`, and `AdminLayout` swaps every `/admin/*` page for `DesktopOnlyBanner` below the desktop breakpoint | Surface it on the organizer roster | Nothing | **✅ #94 — added 2026-09-08 on Andy's requirement that organizers use both phone and laptop.** The desktop half was already correct (no `isAdmin` gate on the button; the route admits both roles) — this was a missing surface, not a permission bug. Reuses the existing modal, reading `venue_code` off the roster query the page already runs. A slice of P1 #80/#81, pulled forward because check-in is a live daily flow. |

## Phase L3 — Auth and abuse hardening (3–4 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 26 | Access + refresh in `localStorage` | One XSS takes the account | Cookie + in-memory + CSRF; ~21 files | L6 | Depends on #2 |
| 27 | 3 endpoint groups have zero throttle | `magic/{token}`, `slots/{id}/resolve`, 5 organizer routes | Add limits | L6 | None |
| 28 | Every throttle fails **open** on Redis error | Fine for uptime, useless for cost control | Fail closed on the expensive ones | L5 | Per-endpoint call |
| 29 | 4 query paths unbounded | `CONFIG-24` = ~20,000 SELECTs in one request | Row-cap + paginate | L5 | None |
| 30 | No `aud`/`iss` claims minted or verified | `SEC-36` | Add both | L8 | None |
| 31 | `refresh_tokens` grows unbounded | No reaper, no cap, can't list sessions | Reaper + cap | L8 | None |

## Phase L4 — Known bugs (2–3 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 32 | Missing SendGrid var → task returns normally | Mail silently vanishes; looks like "nobody signed up" | Fail loudly. ~1h, highest value fix | L6 | None |
| 33 | `magic.py:54,60,69` → `/signup/confirmed` | **Route doesn't exist; every confirmation 404s** | Add routes or fix redirect | L6 | None |
| 34 | `/auth/magic/resend` has zero callers | A lost email is a dead end | Wire a button | L6 | None |
| 35 | Broadcast footer + unsubscribe links | Both broken in every email sent | Fix both | L6 | None |
| 36 | `role_scope.py:39` scopes organizers by `owner_id` | Contradicts the 2026-08-12 ruling | Fix before any read tool ships | P4 | None |
| 37 | `/admin/notifications/recent` | 500s **permanently** once a shift notification exists | Fix query | L6 | None |
| 38 | A test pins orientation gate failing **open** | Contradicts the hard block | Invert the test | L6 | Depends on #6 |
| 39 | School field dropped on event save | Accepted by form, lost server-side | Fix | L6 | None |
| 40 | Deactivation doesn't end sign-in | Deactivated staff can still log in | Revoke on deactivate | L8 | None |
| 41 | 2 Exports range buttons unimplemented | Silently return all-time PII exports | Implement or remove | L6 | None |
| 42 | Legacy 24h reminder still sends | Volunteers get **two** day-before emails | Retire the legacy pair | L6 | None |
| 43 | 3 backend tests fail | Missing `/opt/hf-cache` mount, not broken code | Add mount to the documented command | L6 | None |

## Phase L5 — Hardening and scale (2–3 days) — *the missing Phase 37*

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 44 | Phase 37 has no directory, no plan | Load test, PII encryption, pending store all deferred here | Write the phase | L6 | None |
| 45 | No WAF, no bot protection | App throttles fail open; nothing above them | Cloudflare rules | L9 | Depends on #1 |
| 46 | No AWS spend cap | **The actual credit protection.** Throttles can't stop what fails open | Hard budget alarm + cap | L9 | None |
| 47 | `_PENDING` store is in-memory | **Blocks running more than one worker** | Move to DB | L9 | None |
| 48 | Zero load testing ever | Instance sizing is a guess; 512MB already OOM'd | Establish P50/P95 | L9 | None |
| 49 | No Celery time limits; no API request timeout | Tasks hold DB sessions; fetches hang forever | Add both | L8 | None |
| 50 | 2 of ~10 indexes landed; 13 FKs unindexed | W0.5 half-done | Add the rest | L8 | None |
| 51 | CrossEncoder ~200s cold start | First request after boot stalls | Warm on startup or sidecar | L9 | None |

## Phase L6 — Verification (3–4 days) — *the long pole*

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 52 | Nothing started | Its own roadmap: "biggest single batch of code in the whole plan" | Budget 4 days, not 2 | L7 | None |
| 53 | 53 smoke boxes unticked, sign-off blank | **Nobody has ever clicked through this app** | Run all three roles | L7 | None |
| 54 | W6.1 every route × role × phone | Route-gating tests can't see over-disclosure *within* a page | Manual pass | L7 | None |
| 55 | W6.2 side-effecting flows w/ Mailpit | Shifts changed everything and were never re-walked | Full pass | L7 | None |
| 56 | W6.3 emails in real clients | Never opened in Gmail/Apple/Outlook | Test all four | L7 | None |
| 57 | W6.4 adversarial input | Static audit only, no runtime testing | Manual pass | L7 | None |
| 58 | INTEG-04 blocked on a human since Phase 20 | Status literally `human_needed` | Do the dry run | L7 | None |
| 59 | 11 unrun UAT tests across phases 15/16/17 | All marked `[pending]` | Fold into this pass | L7 | None |
| 60 | W6.5 regression tests | P0s found by hand won't stay fixed | One test per P0 | L8 | None |

## Phase L7 — Fix what L6 finds (2–3 days, unbounded)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 61 | Unknown scope | All ~140 known product bugs came from *reading* code | Reserve real time; expect surprises | L8 | None |

## Phase L8 — Re-audit 3 (1 day)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 62 | Not started | Verifying your own fixes isn't verification | Independent pass over L3/L4/L5 | L9 | None |

## Phase L9 — Deploy (2–3 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 63 | 2 personal API keys in `backend/.env` | OpenRouter + Jina; `.dockerignore` won't clear built images | Rotate everything | L10 | None |
| 64 | Render `ENVIRONMENT` value unverified | If unset or `prod`, **OpenAPI has been public** | Check; treat as disclosed if so | L10 | None |
| 65 | 13 `deployment.md` boxes unchecked | Never worked | Work them | L10 | None |
| 66 | 8 AWS boxes unchecked; no domain | Let's Encrypt won't issue for a bare IP | Buy a domain | L10 | None |
| 67 | RDS KMS not enabled | **Load-bearing condition of the PII acceptance** | Rafael enables it | L10 | None |
| 68 | Backend port publishable | starlette CVE ceiling lives only in Caddy | Never publish it | L10 | None |
| 69 | Frontend copilot flag is build-time | `COPILOT_ENABLED=true` does **not** cover it | Set `VITE_COPILOT_ENABLED` at build | P4 | None |
| 70 | Corpus not ingested | Every RAG answer returns empty | Ingest once post-deploy | P4 | None |
| 71 | Backups documented, never tested | Untested backup isn't a backup | One restore drill | L10 | None |

## Phase L10 — Re-audit 4 + ZAP (1 day)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 72 | Never run | No dynamic security testing has happened at all | Exhaustive pass + ZAP on the live URL | L11 | None |

## Phase L11 — Handoff (1–2 days) — 🏁

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 73 | `PRODUCT-BRIEF.md` teaches soft warning ×3 | K39; `DEPLOY-ROADMAP-v2.md:29` repeats it | Fix both | — | Depends on #6 |
| 74 | `30-not-built.md` says SSO exists | Deleted 2026-08-13 | Correct it | — | None |
| 75 | README/CLAUDE.md describe deleted CSV pipeline | Stale by 2–3 milestones | Rewrite both | — | None |
| 76 | 5 `appArchitecture.js` nodes claim email blocked | Resolved 2026-08-06; the site lies about the app | Correct all five | — | None |
| 77 | `ccpa-policy.md` has 7 `TODO(copy)` | **The copilot cites this document** | Fill them in | — | Hung owns |
| 78 | No runbook | Rafael can't operate it | Write it | 79 | None |
| 79 | No walkthrough done | This is the exit criterion | Live walkthrough with Rafael | — | None |

---

# Milestone P — Product completion (3–4 weeks, post-launch)

Nothing here blocks launch. Ordered by value per day.

## Phase P1 — Organizer mobile (3–4 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 80 | Organizers: 67 endpoints, 2 screens | Admin shell is desktop-only; their device is a phone | Mobile-capable roster | — | None |
| 81 | Bottom-nav "Events" → `DesktopOnlyBanner` | Dead end on the device they actually use | Fix the nav target | — | None |
| 82 | 2 `/organizer/promote` endpoints exist | No button anywhere | Add to roster | — | None |
| 83 | Cancel/move/swap/resend staff-allowed | No organizer control for any of them | Add to roster | — | None |
| 84 | Grant-credit button is desktop-only | Endpoint is organizer-namespaced | Add to roster | — | None |
| 85 | Fill rate is admin-only | Organizers can't see staffing on a phone | Add to roster | — | None |

## Phase P2 — Role gaps (4–5 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 86 | No signup-on-behalf path | No endpoint, no UI, no tool. **Phone-in volunteers can't be added** | Build it | — | None |
| 87 | Phone read only by a copilot tool | Day-of "call the missing volunteer" impossible | Show on roster | — | None |
| 88 | Reminder opt-out invisible to staff | Suppressed volunteer looks like one ignoring mail | "Reminders: off" badge | — | None |
| 89 | No volunteer self-cancel/swap | Removed 2026-08-02; seats stay falsely filled | Rebuild token-scoped | — | Revisit removal |
| 90 | CCPA acts on staff rows only | Statutory gap for CA volunteers; export omits answers + credits | Volunteer request path | — | None |
| 91 | Organizers grant credit, can't list/revoke | Inconsistent with the endpoint they already have | Give them the list | — | None |
| 92 | `Forbidden` is a bare `<h2>` | No way back | Style it | — | None |

## Phase P3 — UX epics (2 weeks)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 93 | `EventDetailPage` is 1,407 lines | Unmaintainable | Decompose | — | None |
| 94 | No search/filter/sort on browse | SCRUM-27 | Build it | — | None |
| 95 | No loading/empty/error states | SCRUM-28, K38 | Add throughout | — | None |
| 96 | Admin event page IA | SCRUM-32 | Restructure | — | None |
| 97 | Events list + ops dashboard | Operations shows **no** signup or fill numbers | Add them | — | None |
| 98 | 4 overlay impls, 3 toast systems, 3 headers | K37 | Consolidate | — | None |

## Phase P4 — Copilot completion (1 week)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 99 | Read tools written, switched off | Docs: "not finished enough to turn on" | Finish, then enable | — | None |
| 100 | Organizer scoping wrong | Must fix #36 first or copilot is stricter than the API | Fix then ship | — | None |
| 101 | `_dispatch` seams are stubs | Return the planned action; call no real task | Wire to Celery | — | None |
| 102 | Both mail tools raise `OutboundNotWired` | No transport bound | Depends on #22 | — | None |
| 103 | Corpus has no real test questions | Highest-value KB docs missing | You write them | — | Depends on #12 |
| 104 | `copilot_tool_calls` write-only | Never read back by anything | "What did the copilot do" view | D3 | None |

## Phase P5 — Accessibility + cleanup (1 week)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 105 | **Zero `:focus-visible` rules** | K40; keyboard users have no focus indication | Add throughout | — | None |
| 106 | One Escape closes modal + drawer | K15; discards unsaved work | Focus trap + restore | — | **Partly done 2026-09-07 (SCRUM-156, PR #88): the *Cancel* route now prompts before discarding, and `EventSettingsModal` / `DuplicateEventModal` finally pass `dirty` so their prompt can fire at all. The Escape-closes-two-layers half and focus trap/restore remain open.** |
| 107 | ~10 dead endpoints/tables/aliases | `custom_answers` has no INSERT anywhere | Delete them | — | Depends on #8 |
| 108 | ~25 dead `api.js` exports | K35; `api.register()` doesn't exist | Delete | — | None |
| 109 | 3 settings stored, never read | `default_privacy_mode`, `allowed_email_domain`, `visibility` | Wire or drop | — | Per setting |
| 110 | Coverage floor 55, target 70 | "Plan 07 follow-up", never done | Raise it | — | None |
| 111 | No `app.eval` CI gate | Absent entirely, not just lowered | Add it | — | None |
| 112 | v1.3 suite skipped **and** body is `expect(true)` | Un-skipping tests nothing | Write it or delete it | — | Write or delete |
| 113 | ~113 baseline findings open | 9 High, 68 Medium, 36 Low | Work by severity | — | None |

## Phase P6 — Copilot production hardening (added 2026-09-07)

Separate from P4 (Copilot completion, items 99–104) by Andy's decision — P4 keeps its
original scope (read tools, dispatch stubs, mail transport). This phase is the deeper
production-readiness pass: corpus quality, RAG architecture, concurrency, and guardrails.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 133 | Corpus has no real test questions | Ties to Gate 0 #12 — only Andy knows real SciTrek policy | Write real Q&A pairs against the actual corpus | 137 | Andy's to write |
| 134 | Corpus content itself unaudited | Never reviewed for completeness/accuracy since ingestion | Update/refresh corpus content, not just add tests | 137 | None |
| 135 | No CSV-driven event creation via the copilot | **Reverses PR #51** (CSV import removed on purpose — "modules made by hand in admin UI"). Andy confirmed 2026-09-07 this is intentional. **Update: not a clean-room build — refactor/reuse the old removed CSV-import pipeline code as the basis, wired into the copilot as a file-upload tool instead of the old standalone `/admin/imports` surface** | Refactor old CSV-import logic into a copilot file-upload tool; parse CSV, create events via existing admin endpoints | None | **Confirmed 2026-09-07: build it, via refactor of old pipeline** |
| 136 | RAG pipeline architecture unverified | Unknown whether retrieval is naive top-k similarity or a proper production pipeline (chunking strategy, hybrid search, reranking) | Audit current retrieval code; upgrade to production-grade if naive (proper chunking, reranking via the CrossEncoder already in the stack per ROADMAP #51, evaluation against the corpus) | 137 | None |
| 137 | RAG concurrency behavior unverified | No load/concurrency testing has been done on the copilot pipeline (ties to ROADMAP #48, zero load testing ever) | Test concurrent requests specifically against the RAG/retrieval path, not just the API layer | L6 | None |
| 138 | No prompt-injection defense | Untested whether corpus content or user input can hijack copilot behavior | Add input/output guardrails: system-prompt hardening, output filtering, refuse out-of-scope requests | None | None |
| 139 | No scope-limiting / topic guardrail | Copilot could be asked about anything, not just SciTrek volunteer topics | Add a scope check — refuse or redirect off-topic requests | None | None |
| 140 | PII handling in copilot unaudited | Copilot has tool access to volunteer data (phone, email per roster tools) — no check on what it's allowed to surface to whom | Audit tool outputs for PII over-disclosure; scope tool results by caller's role | Depends on #36 fix | None |
| 141 | No per-user/per-session rate limit on copilot specifically | Gate 0 #9 funded the account (~1,000 req budget) but nothing stops one user/session burning it all | Add a rate limit on the copilot endpoint itself, not just the general API throttles | None | None |
| 142 | No abuse/cost monitoring on copilot usage | No visibility into who's using it or how much, until the bill arrives | Log usage per session/day; alert on anomalous spikes | Ties to #46 (AWS spend cap) | None |

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
| 144 | **D0** Public path emits nothing | `backend/app/routers/public/` has **zero** `log_action` calls. Every volunteer who browses and leaves is invisible, and that data is unrecoverable — every week without this is a week of funnel gone | `backend/app/telemetry.py` + `product_events` outbox table. Server-side only, off by default, transaction-scoped, per-event property allowlist | D3 | **New 2026-09-10 — was in no plan and no Jira ticket. Ship FIRST, ahead of the rest of D;** everything else reads tables that already exist and can be built retroactively at any time |
| 115 | **D1** No warehouse schema | Nothing exists — no `analytics/`, no exports | `warehouse` schema of **materialized views** in the existing Postgres 16, model registry, refresh runner, `etl_run` table, one nightly Celery beat entry at 04:15 PT | D2 | **Changed 2026-09-10: no parquet.** The seed exported Postgres → parquet on disk → back into the same Postgres. No reader, needs a Docker volume (`docker-compose.yml` is PR-only), adds ~90MB `pyarrow`, and — decisive — dated parquet files are a third place PII lives with no deletion story |
| 116 | **D2** No dims or facts | No star schema, no conformed grain | `dim_date/quarter/volunteer/user/event/module/school/signup_status`; `fct_commitment`, `fct_session_attendance`, `fct_bookable_unit`, `fct_orientation_credit` | D3 | **Changed 2026-09-10: plain versioned `.sql`, not dbt.** ~12 models is ~60% overhead for dbt. Adopt at ~25 models or a second SQL author; structure one model per file with explicit `warehouse.` prefixes so conversion is later a `sed`. **Full-refresh nightly, no incremental** — see #146 |
| 145 | **D2a** Dual signup grain | `signups` (orientation, own `checked_in_at`) vs `shift_signups` (N rows in `session_attendance`) are genuinely different grains — the hardest modelling call here | **Port `backend/app/services/attendance_facts.py::facts()`**, do not reimplement. One `fct_commitment` with a `commitment_type` discriminator | D2 | **Resolved 2026-09-10 — already solved in code.** `0037_add_shifts.py` moved every PERIOD signup into `shift_signups` and deleted the sources, so the two tables are subtypes, not parallels. Divergence between the matview and `facts()` would make a chart and the admin UI disagree about the same event — pin it with a parity test |
| 117 | **D3** No SCD-2 history | Full refresh cannot reconstruct last Tuesday's `signups.status` | `snap_signup_status` — the only persistent warehouse table. Derive from D0's event log where available; nightly poll only for pre-instrumentation backfill and reconciliation | D4 | Depends on D0 landing first |
| 118 | **D4** No BI connection | Switched from Power BI 2026-09-07 (Mac-only dev team, no license) | `bi_reader` role: read-only, `warehouse.*` only, `REVOKE ALL ON SCHEMA public FROM PUBLIC`, per-tool login roles, `statement_timeout`. Idempotent checked-in SQL, **not** Alembic — roles are cluster objects | D5 | **Changed 2026-09-10: Metabase, not Tableau.** Gate 0 #11's Tableau choice is downgraded from an architecture decision to a client choice — the seam is a Postgres role, so Metabase/Tableau/Power BI are all ordinary clients. Metabase is $0, open source, Mac-fine, self-serve for non-technical staff. **Tableau for Teaching explicitly forbids administrative use**, so a student licence cannot legally cover the scorecard; if Tableau is wanted later, get a seat from UCSB Data Services (who already run it institutionally) rather than buying one |
| 146 | **D4a** ETL readiness | `updated_at` missing on `users`/`events`/`signups`/`shift_signups`/`audit_logs`; `slots` has no timestamps at all; six tables spell `created_at` differently | **Add no columns. Full-refresh every model nightly** | D2 | **Decided 2026-09-10.** Three reasons: (a) largest fact is a few thousand rows — nothing to optimise; (b) SQLAlchemy `onupdate` is client-side and every bulk `.update()` bypasses it, including `ccpa_delete`'s four — an `updated_at` that lies during a deletion is worse than none; (c) full refresh makes CCPA anonymisation propagate to the warehouse in ≤24h with **zero** deletion-propagation code. The naming inconsistency is aliased in each staging model's SELECT |
| 119 | **D5** No new questions answered | Existing ~20 endpoints answer "how did X do", never "where do people drop out" or "do they come back" | Funnel, cohort retention, time-to-confirm, cancellation lead time, volunteer lifecycle, partner scorecard, pipeline health — all reading `warehouse.*` | D6 | None |
| 147 | **D6** Nothing notices a dead pipeline | No monitoring of any kind; a stale warehouse would serve three-week-old numbers silently | `etl_run` table, freshness assertions that refuse to swap an empty rebuild, `/api/v1/health/warehouse` 503 past 26h, and an amber staleness banner in `OverviewSection.jsx` | — | **New 2026-09-10.** The banner is the layer that actually works — it appears in front of the person reading the number, not in a tool nobody has open |
| 148 | **D7** No-show guessing is manual | — | **Rules-based risk flag**: prior no-show ≥1, OR still `pending` within 48h of start, OR no orientation credit for the family. Roster dot | — | **Changed 2026-09-10: no ML model.** A few thousand labelled rows, heavily imbalanced, ~six weak features. A rule is more explainable to an organiser, gives a baseline any later model must beat, and accumulates labelled data while it runs. Revisit after two quarters. Gate 0 #4 already limits this to soft tracking — it informs, never acts |

**Cost: $0/year.** The warehouse is a schema in the existing Postgres; Metabase
is open source. Self-hosted PostHog was considered and rejected — its cost is a
fixed ~8GB infrastructure floor (ClickHouse + Kafka + ZooKeeper + its own
Postgres + Redis) regardless of volume, i.e. ~$100/month for an idle cluster at
our ~4,000 events/month. PostHog Cloud's free tier (1M/month, ~250× our volume)
remains a $0 upgrade if a prebuilt funnel UI is ever wanted; Andy confirmed
2026-09-10 that no UCSB policy blocks pseudonymous behavioural data leaving
campus.

**Two defects found during the 2026-09-10 scan, both fixable ahead of D:**

- `analytics_event_fill_rates` (`backend/app/routers/admin.py:2130`) is
  **numerically wrong today** — it sums `slot.capacity` (a placeholder `1` for
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

---

# Track X — Paper (parallel, off the critical path)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 120 | **X1** 2 branches, 82 commits, local | ~60 PRs of drift; testset gold answers now wrong | Merge, re-validate against current KB | X2 | None |
| 121 | **X2** Control run done, treatment never finished | ~23% complete. **The paper's central evidence doesn't exist** | Run it, produce the delta table | X4 | None |
| 122 | **X3** Contribution #1 never measured live | Agent loop raised `NotImplementedError` at eval time | Re-run with tools on the built loop | X4 | None |
| 123 | **X4** No venue, deadline, authorship, IRB, draft | Ratings + profile text already collected from named staff | **IRB before the usage study, not after** | — | All yours |
| 124 | 4 of 5 journal folders empty | 0 decisions, 0 concepts, 0 experiments, 0 failures | Backfill from PLAN/SUMMARY + git log | X4 | None |
| 143 | **X5** DSPy / prompt-program experiment — un-parked 2026-09-07 | Was optional/deferred (old Phase 36); Andy now wants it done | Programmatic prompt optimization (DSPy) vs. hand-tuned prompts, compared on the same eval set as X2 | X4 | **Decided 2026-09-07: build it — un-parked, active** |

---

# Explicitly parked — stop revisiting

| # | Item | Why parked |
|---|---|---|
| 125 | SMS / Phase 27 | **Update 2026-09-07: A coworker owns this, not Andy — genuinely out of scope for this backlog, not just deferred** |
| 126 | CSV import | Deleted PR #51. **Update 2026-09-07: the old removed pipeline code is being refactored/reused as the basis for the new Phase P6 item #135 (copilot CSV-upload tool), not built clean-room** |
| 127 | Portals | Removed. **Confirmed 2026-09-07: ignore — dead code (`PortalsAdminPage.jsx`, `PortalPage.jsx`), zero references anywhere, safe to delete whenever P5 cleanup happens** |
| 128 | SSO / OIDC | Deleted 2026-08-13 |
| 129 | ~~Phase 36 DSPy~~ | **Un-parked 2026-09-07 — moved to Track X as item #143 (X5), Andy wants this built, no longer optional/skipped** |
| 130 | BIOIN (40 open) + DOC (51 open) | **Different products, different repos** — confirmed 2026-09-07: Andy's own other projects, correctly out of scope here |
| 131 | 34 missing SUMMARYs, phases 02–07 | Paperwork; code shipped |
| 132 | ~430 unchecked `.planning/` boxes | Only ~26 are real work |

---

# Timeline

| Milestone | Duration | Ends at |
|---|---|---|
| Gate 0 | your time | decisions made |
| **L (L0–L11)** | **4–6 weeks** | **live + handed over** |
| P (P1–P5) | 3–4 weeks | product complete |
| D (D0–D7) | 3–4 weeks | BI live |
| X (X1–X4) | 5–6 weeks | paper submitted |

L is 4–6 weeks rather than 3: the token migration (L3) and the missing hardening
phase (L5) add about a week, and L7 is genuinely unbounded because nobody has
clicked through the app yet.

P and X can run in parallel after L11 if alternated. D needs P's stability.

**Do today regardless of every decision:** #13 (push the eval branches) and
#18 (file the DNS request).
