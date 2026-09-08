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
| 11 | Power BI seed unpromoted | Licenses/owner/warehouse unknown | Answer all three | D1 | **Decided 2026-09-07: Switched from Power BI to Tableau — no Power BI license exists yet, no stakeholder mandate for it specifically (only general post-launch analytics need), and dev team is Mac-only (Power BI Desktop is Windows-only; Tableau has a native Mac app). Build analytics on Tableau instead once Milestone D starts post-launch. Owner/warehouse-sizing questions deferred until D1 planning.** |
| 12 | Copilot corpus has no real questions | Only you know SciTrek policy | Write them | P6 | **Decided 2026-09-07: Moved into Phase P6 (item #133) — Andy will write these as part of the copilot hardening phase, not standalone** |

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

## Phase L1 — File the DNS request (0.5 day)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 18 | No verified sender domain | **Update 2026-09-07: Resolved — `sci-trek.org` self-registered, already sending real email from AWS deploy (confirmed via real confirmation email received 2026-09-02).** No UCSB IT step needed; remaining work is just adding CNAME records via the domain registrar for full domain authentication (optional, deliverability upgrade only) | Add CNAMEs directly via registrar, no external approval wait | L9, all email | — |
| 19 | Cloudflare not decided | CNAMEs must be DNS-only, not proxied | Decide #1 before filing | L9 | Depends on #1 (already decided: yes, Free plan) |

## Phase L2 — Land what's already built (1–2 days)

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 20 | PR #80 open (CI net) | Built but never merged; roadmap said done | Merge | L8 | None |
| 21 | PR #79 open (accept localStorage) | Contradicts #2 if you're fixing tokens | Close it | L3 | Depends on #2 |
| 22 | PR #78 open (copilot mail transport) | `nudge_understaffed_module:50-59` targets the **whole volunteer table** | Fix recipients, then merge | P4 | None |
| 23 | `Caddyfile:36` HSTS-only; Dockerfile has no `USER` | F2/F3/F4 never shipped | Ship all three | L8 | Depends on #3 |
| 24 | K31 commit `569c3ff` on a branch | Roadmap marked it "✅ pushed" | Merge to `main` | Nothing | None |
| 25 | 9 branches with unmerged work | Includes 39-commit `origin/v1.3` | Merge or delete each | Nothing | Per branch |

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

# Milestone D — Data & BI (4–6 weeks) — Tableau, not Power BI (Gate 0 #11, decided 2026-09-07)

Promoted from `seeds/v1.4-data-pipeline.md`, renumbered off the 30–35 collision.

| # | Current situation | What's wrong | Recommendation | Blocks | Decision |
|---|---|---|---|---|---|
| 114 | Seed drafted 2026-04-17, never promoted | Its phases 30–35 **collide** with copilot 30–38 | Renumber to D1–D5 | D1 | None |
| 115 | **D1** No warehouse schema | Nothing exists — no `analytics/`, no exports | Nightly parquet + schema | D2 | Depends on #11 |
| 116 | **D2** No dbt project | No dims, no facts, no history | Star schema + SCD-2 on signup status | D3 | None |
| 117 | **D3** No Tableau connection | Switched from Power BI 2026-09-07 (Mac-only dev team, no license) | `bi_reader` role + ops/funnel dashboards in Tableau | D4 | Decided — Tableau |
| 118 | **D4** No scorecard | Partner reporting done by hand | Orientation compliance + Tableau scorecard | D5 | None |
| 119 | **D5** No prediction | No-show guessing is manual | scikit-learn → `noshow_probability` → roster dot | — | None |

Addition not in the original seed: tool success/failure/retry rate per tool,
sourced from `copilot_tool_calls` — a table currently write-only and never read,
so BI would be its first consumer.

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
| D (D1–D5) | 4–6 weeks | BI live |
| X (X1–X4) | 5–6 weeks | paper submitted |

L is 4–6 weeks rather than 3: the token migration (L3) and the missing hardening
phase (L5) add about a week, and L7 is genuinely unbounded because nobody has
clicked through the app yet.

P and X can run in parallel after L11 if alternated. D needs P's stability.

**Do today regardless of every decision:** #13 (push the eval branches) and
#18 (file the DNS request).
