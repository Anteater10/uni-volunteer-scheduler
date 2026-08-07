# Final roadmap — ship, then hand to Rafael

**Written:** 2026-08-05 · **Verified against:** `origin/main` @ `5484333` + `feat/shifts` @ `81ee6a0`
**Supersedes:** `.planning/DEPLOY-ROADMAP-v2.md` (2026-07-16) and `.planning/HANDOFF-ROADMAP.md` (2026-05-28).
**Keeps as the detail reference:** `.planning/HANDOFF-EXECUTION-ROADMAP.md` (2026-07-28) — every `K` number below points into it for the `file:line` evidence. This file is the *sequencing and status* layer; that file is the *evidence* layer.

Every status marker in this document was re-verified against the working tree today, not copied from a prior doc. Where a prior doc was wrong, it is called out.

---

## Contents

- [The one-page picture](#the-one-page-picture)
- [Where the code actually is](#where-the-code-actually-is)
- [What closed since 2026-07-28](#what-closed-since-2026-07-28)
- [The spine](#the-spine)
- [W0 — Land what is already built](#w0--land-what-is-already-built)
- [W1 — Finish shifts](#w1--finish-shifts)
- [W2 — Bugs that lie or break](#w2--bugs-that-lie-or-break)
- [W3 — Decide Phase B](#w3--decide-phase-b)
- [W4 — Deploy blockers](#w4--deploy-blockers)
- [W5 — Security review](#w5--security-review)
- [W6 — Runtime verification](#w6--runtime-verification)
- [W7 — The handoff itself](#w7--the-handoff-itself)
- [Decisions only Andy can make](#decisions-only-andy-can-make)
- [What Rafael inherits as documented backlog](#what-rafael-inherits-as-documented-backlog)
- [Full K-item status table](#full-k-item-status-table)
- [If the week compresses](#if-the-week-compresses)

---

## The one-page picture

You listed eight gaps. Here is what each one actually is, verified today:

| Your gap | Reality | Where |
|---|---|---|
| **corpus** | Done on a branch. PR #54 is complete and self-describes as done; it is red only on a **stale** CI run that predates the test fix in #57. Blocked externally on the OpenRouter key. | [W0](#w0--land-what-is-already-built) |
| **fix api.js** | The P0 (`api.slots` missing) **is fixed** — PR #56 merged. What remains is ~25 dead exports (K35), cosmetic. | [W0](#w0--land-what-is-already-built), [W2](#w2--bugs-that-lie-or-break) |
| **fix celery for tests** | The red backend suite is fixed — PR #57 is **green on all three checks** including Playwright. Merge it first; it unblocks the other two PRs' CI. | [W0](#w0--land-what-is-already-built) |
| **fix bugs** | 42 audited items. **6 closed**, 36 open. Of those, 4 lie to the user in ways that will generate mail to your inbox. | [W2](#w2--bugs-that-lie-or-break) |
| **phase B** (AI agent) | ~1200 lines that have **never executed.** `_get_agent_llm` still raises `NotImplementedError`. This is a scope decision, not a task. | [W3](#w3--decide-phase-b) |
| **prod hardening** (37) | Caps, rate limits, Sentry, prod compose, Caddy all exist. Missing: **no `/health` endpoint**, no dev `.env.example`, no model-cache volume, PII plaintext at rest. | [W4](#w4--deploy-blockers) |
| **ai chatbot prod hardening** | Same phase; the copilot-specific remainder is the CrossEncoder cold start and the `/confirm`+rating rate limits. | [W4](#w4--deploy-blockers) |
| **security audits** (39) | Not started as a sweep — but four real findings already landed piecemeal on main (unauthenticated slot/signup reads, visibility fail-open). K33 is still open. | [W5](#w5--security-review) |
| **phases 37–42** | 37/38 are ~70% done. 39/40/41 not started. 42 is the handoff. Renumbered below as W4–W7 because the old numbering no longer matches the work. | [W4](#w4--deploy-blockers)–[W7](#w7--the-handoff-itself) |

**And one thing that was on none of your lists: `feat/shifts`.** Six backend commits plus ~1,700 lines of **uncommitted frontend work** in your working tree right now. It is the largest single piece of unlanded work in the repo and it changes the booking model. See [W1](#w1--finish-shifts).

---

## Where the code actually is

### Open PRs

| PR | Branch | Age | CI | State |
|---|---|---|---|---|
| **#57** | `fix/quarter-boundaries-date-drift` | 2 days | ✅ **all 3 green** | Ready. **Merge first.** |
| **#54** | `fix/copilot-corpus-refresh` | 6 days | ❌ backend (stale run, 74 commits behind) | Complete per its own description. Needs rebase + re-run. |
| **#50** | `fix/imports-templates` | 12 days | ❌ backend (stale run) | Complete per its own description. Needs rebase + re-run. Carries migration 0029. |

Both red checks are from **before** #57 fixed the expired `test_first_week_of_each_summer_session`. That one test broke every branch's backend job from 2026-07-31 onward. Do not debug #54 or #50 until they are rebased on a main that contains #57.

### Unlanded local work

| Branch | Contents | Status |
|---|---|---|
| **`feat/shifts`** | 6 commits, 34 files, +5,136/−443. Backend: `shifts` / `shift_signups` / `session_attendance` tables, Alembic `0037`, all-or-nothing booking, per-session check-in, rosters/exports/analytics, promote/reorder/swap. | Backend looks feature-complete against `docs/superpowers/specs/2026-08-02-shifts-design.md`. **Not pushed. No PR.** |
| **Working tree (uncommitted)** | `EventsSection.jsx` +691, `public/EventDetailPage.jsx` +364, `api.js` +112, four test files +756. | The shifts **frontend**, mid-flight. Uncommitted and unbacked-up. |

There are ~40 other remote branches, all merged or superseded milestone branches. They are noise; nothing is waiting in them.

---

## What closed since 2026-07-28

The July 28 execution roadmap is one week old and six of its items are now done. Verified in the tree today:

| Item | Status | How |
|---|---|---|
| **K1** — admin cannot add/edit/delete slots | ✅ **fixed** | `api.js:650` now has a real `slots:` namespace. PR #56. |
| **K2** — default deploy retrieves nothing | ✅ **fixed** | `config.py:117` defaults `corpus_embedding_primary = "local"`. |
| **K3** — cancel permanently bars re-signup | ✅ **dissolved** | PR #55 **removed volunteer self-cancel entirely.** The bug's entry point no longer exists. |
| **K16/K17/K19** — dead manage link, closed-loop expiry, silent cancel/swap | ✅ **largely dissolved** | PR #55 made the manage page read-only with an organizer contact notice; #53 made promotion require email confirmation. The self-service surfaces those bugs lived on are gone. **Re-read them before fixing — the ground moved.** |
| **K34** (part) — dead pages | ⚠️ **half** | `PortalPage.jsx` and `PortalsAdminPage.jsx` deleted. **`AdminDashboardPage.jsx` still present** with 14 of the 48 `TODO(copy)` markers. |
| **S0.2** — "does e2e even run?" | ✅ **answered: yes** | `playwright e2e` **passed** on PR #57. 12 spec files in `e2e/`. It is now real evidence, not a claim. |

Also landed: four security fixes (unauthenticated `GET /slots` and `GET /signups/{id}` narrowed; visibility fail-closed on NULL), a `generate_slots` 500 fix, swap/cancel guards for terminal statuses, and a 39-doc knowledge-base rewrite against current behaviour.

**Net: the July 28 doc's Stage 1 is 3-of-6 done, and its Stage 3a is mostly obsolete.** Everything else stands.

---

## The spine

```
W0  land #57 → rebase #54, #50 → land           ← do today; unblocks CI for everything
     │
     ▼
W1  commit + PR feat/shifts                      ← biggest risk; uncommitted right now
     │
     ▼
W2  K4 K5 K7 K9 K10 K11 K12 K13 K14 K20 K22      ← bugs that lie or break
     │
     ├──────────────┐
     ▼              ▼
W3  Phase B      W4  deploy blockers             ← can run in parallel
   decision         /health, .env.example,
     │              model cache, flags
     └──────┬───────┘
            ▼
W5  security review (K33 + authz sweep)
            │
            ▼
W6  runtime verification ⚠️ finds new things
            │
            ▼
W7  handoff to Rafael
```

Two hard orderings:

- **W0 before everything.** With CI red on every branch, a real regression is indistinguishable from the noise. #55 and #56 both had to be cleared by hand-checking. That does not scale and it is how a bad merge gets in.
- **W1 before W2.** `feat/shifts` touches `emails.py`, `api.js`, `EventsSection.jsx`, `EventCheckInPage.jsx` and `public/EventDetailPage.jsx` — the same files as K4, K12, K13, K22 and K38. Fixing them on main first means resolving every one of those conflicts twice.

**Do not put W6 last with no slack behind it.** Its entire purpose is to find unknowns. If it finds six things, that is normal, and you need days behind it.

---

## W0 — Land what is already built

**~half a day.** Nothing here is new code.

### W0.1 — Merge PR #57 · S
All three checks green, including Playwright. This restores CI as a merge signal.

### W0.2 — Rebase and re-run PR #54 (corpus) · S
74 commits behind. It already merged main once (`84baa66`) and took main's newer doc text. Rebase, push, re-run. Expect green.

⛔️ **Then the external blocker:** the OpenRouter key returns `PermissionDeniedError`, so answers cannot stream. Retrieval is verified working. **Raise the key limit or provision a new one — this is on the critical path for any copilot demo, and nothing in the repo can fix it.**

### W0.3 — Rebase and re-run PR #50 (bulk event builder) · S
Carries migration **0029**, which seeds the 5 confirmed SciTrek modules (CRISPR 1, CRISPR 2, Glucose Sensing, Bioinformatics, Thermodynamics) and archives placeholder templates. **Those need to exist at handover**, so this PR is not optional polish.

Note the interaction: #50 retires the Imports nav item but deliberately leaves the CSV page and its 8 backend endpoints dormant and unrouted. That is the K34 `/admin/imports` decision, answered *implicitly* — see [Decisions](#decisions-only-andy-can-make) to make it explicit.

### W0.4 — Follow-up from #57 · S
`test_event_on_last_day_of_quarter_gets_final_week` uses `date.today()` with `end_date == today`, against a rule that compares to **UTC** today. One-day flakiness window west of UTC. Switch to the UTC basis and give it margin, or it rots the same way.

**Gate:** CI green on main. Every open PR either merged or consciously parked.

---

## W1 — Finish shifts

**~1–2 days.** The highest-risk item in this document, because part of it exists only in your working tree.

### W1.1 — Commit the frontend work now · S
~1,700 uncommitted lines across 7 files. Commit it — even as WIP on the branch — before doing anything else today. An accidental `git checkout` costs you a day.

### W1.2 — Push `feat/shifts` and open a PR · S
Six commits have never left the laptop. Push for CI and for backup.

### W1.3 — Verify against the design spec · M
`docs/superpowers/specs/2026-08-02-shifts-design.md` has a **Tests** section (:174) and an **Out of scope** section (:192). Walk both. Confirm the migration (`0037`) is round-trip safe against old-shape data — `test_shifts_migration.py` (466 lines) suggests you already built that harness.

### W1.4 — Decide: does shifts ship before handoff? ⛔️ · decision
This is a **booking-model change**, not a feature. It changes what a volunteer commits to. Shipping it in the final week means W2's bug fixes, W6's runtime walkthrough, and Rafael's runbook all describe a model that just changed.

Two honest options:
- **Ship it.** Then W6 must re-walk every signup, check-in, roster and email flow against the new model. Budget for that.
- **Park the branch.** Hand it to Rafael as a documented, tested, unmerged feature branch with the design spec. Ship the current session-based model.

There is no third option where it ships and W6 stays cheap.

**Gate:** shifts is either merged with its flows re-verified, or parked with a written disposition.

---

## W2 — Bugs that lie or break

**~2 days.** Nothing here crashes the app. Everything here states something false to a user. Detail and `file:line` for every item: `.planning/HANDOFF-EXECUTION-ROADMAP.md`.

### Fix first — these reach volunteers

**K4 — Nine emails print raw UTC as the shift time** ✅verified · S
`emails.py:68-69` — `_fmt_when` still returns `f"{slot.start_time} to {slot.end_time}"`, rendering `2026-04-16 16:00:00+00:00`. `_fmt_slot_time` (`:30`) converts correctly and is used by one email. **One swap fixes nine builders** — and note `feat/shifts` now routes `_fmt_shift_when` (`:76`) through the broken `_fmt_when`, so on that branch it is nine builders plus every shift email.

**K20 — Every volunteer email is branded for the wrong product** ✅verified · S
`email_templates/base.html` brands everything "University Volunteer Scheduler" with `TODO(brand)` ×2. Everything wraps in it. `signup_confirm.html` is the only complete template.

**K22 — Copy that contradicts the server** ⚠️ · S
`SelfCheckInPage.jsx` says check-in opens 15 min before; `check_in_service.py:28` says 30. No email contains a check-in link at all — a volunteer at the van cannot self-check-in without the organizer's screen.

### Fix second — these break the day-of organizer

**K5 — Two primary organizer actions unreachable on a phone** ✅verified · S
`ui/Modal.jsx:44` is still `mx-auto w-full max-w-md mt-[15vh] … p-5` — **no backdrop padding, no `max-height`, no `overflow-y-auto`.** Broadcast's Send and ResolveEvent's Save scroll off the bottom. Copy the three classes from `FormModal.jsx:28,35`. These are phone actions performed at a school.

**K10 — Past slots stay bookable** ⚠️ · S
No `end_time` filter anywhere in `_build_event_response`, `get_event`, or `create_public_signup`. Passed sessions render live Sign-up buttons and the signup succeeds.

**K13/K14 — Destructive actions with the weakest dialogs** ⚠️ · S
Deactivate-a-user is one unguarded click in the same drawer as a type-to-confirm CCPA delete. Delete-event — event + slots + signups — is a bare `<div>` with no `role="dialog"`, no Escape, no focus trap, while `ui/Modal` (which has all of it) guards *module archive*.

**K11/K12 — Error branches that lie, exports that fail silently** ⚠️ · S–M
`QuartersManager` renders "No quarters yet — add the current quarter" on a **failed fetch**, telling an admin who already entered quarters to re-enter them. Nine exports call `downloadBlob` with no `await` and no `catch`; a failed export is an unhandled rejection and the button looks dead.

### Fix third — copilot correctness (do before W3)

**K7 — Every week-aware copilot tool asks an impossible question** ✅verified · M
`_iso_week.py` is still imported by `list_modules`, `signup_stats_for_week` and others. `Event.week_number` is **quarter-relative** (1–11); the tools pass **ISO** week (1–52). `list_modules` always returns `{"modules": []}`. `find_understaffed_modules` renders quarter week 3 as `2026-W03` — January. `create_module_from_template` gets it right, so a module the copilot creates is invisible to `list_modules` on the next turn.

**Fix at the tool boundary in one shared helper. Then check the fixtures** — suspected to use ISO values, which is why this passes tests.

**K9 — Four reminder emails; the opt-out covers two** ⚠️verified · S
`celery_app.py:991,995` — `send-reminders-24h-every-5-minutes` and `send-reminders-1h-every-5-minutes` are **both still on beat**, alongside `check_and_send_reminders`, with different `sent_notifications` dedup keys so both fire. And the legacy pair never checks preferences: **turning reminders off still delivers the 24h and 1h emails.** Dropping the two legacy beat entries fixes the double-send *and* the broken toggle in one edit. This is your "fix celery somewhere" item.

### The blind spot you should close in parallel

**S0.1 — Mock-honesty sweep** ⛔️ · L, background
The record is **4 for 4**: every bug verified by hand was hidden by a test mocking the exact broken seam. 1,214 backend + 409 frontend tests pass. Green means "no regressions," never "it works." Run this in the background while W2 proceeds — it costs no wall-clock time and it is the only thing standing between you and a fifth P0.

Scope: tests that monkeypatch the seam they claim to test; hollow assertions; the 11 skipped backend tests; fixtures encoding wrong assumptions (suspect ISO `week_number` — see K7).

**Gate:** no known surface states something false.

---

## W3 — Decide Phase B

**Decision first, then 2–4 days if yes.**

`_get_agent_llm` still raises `NotImplementedError` at `router.py:591`, and `copilot_agent_loop_enabled` is off. The entire tool layer — 12 tools, ~1,200 lines, a confirmation-card flow, an adversarial suite — **has never executed outside a monkeypatch.**

> ## ✅ DECIDED 2026-08-06 — affirm the full agent
>
> **The copilot ships as a tool-using agent.** The 2026-07-16 lock stands;
> this document's own recommendation below is **overruled** and kept only as
> the record of what the tradeoff looked like at the time.
>
> The reasoning: the agent is the paper's headline contribution, and reversing
> it to protect a deploy date would have spent the contribution to buy time
> for everything else. The cost is accepted knowingly — W3 was the largest
> block of work in the milestone, and it is done.
>
> **What actually shipped:** K23, K25, K26, K28, K29, K30, K31, K32 are all
> complete on `feat/phase-b-agent`. B0.1–B0.3 (adapter, write-tool wiring,
> confirmation store) are built.
>
> **The flag stays OFF for the deploy.** `COPILOT_AGENT_LOOP_ENABLED=0` in
> `.env.production.example`, documented there with the reason. Off is not
> indecision here — the tool layer has never run against a real model on real
> data, and the ~50 requests/day ceiling on the unfunded OpenRouter account
> is not enough to earn that confidence before handoff. K23 is what makes
> "off" safe rather than a trap: flipping the flag now returns a real 503
> instead of a bare 500. Turning it on is a deliberate, reversible act taken
> after the account is funded and the agent has been exercised end to end.

⛔️ ~~**The decision:** ship the copilot as **retrieval-grounded Q&A** (which works today and is production-usable the moment the OpenRouter key is unblocked), or as a **tool-using agent that takes actions**?~~ *(Settled above.)*

`.planning/DEPLOY-ROADMAP-v2.md` locked this on 2026-07-16 as "full tool-using agent — this is the paper's headline contribution." **Three weeks later none of B0.1–B0.3 is built, and you now have one week.** Re-affirm or reverse it deliberately; do not let it decay by default.

### If you reverse to Q&A-only (~~recommended for the deploy~~ — NOT TAKEN)
Then W3 is ~1 day:
- **K23** · S — `router.py:559` calls `_get_agent_llm()` synchronously *before* the `StreamingResponse` is built, so flipping the flag returns a bare **HTTP 500** on every message with `Stream failed: HTTP 500` in the drawer. Return 503 with a real message, or refuse at boot. ~10 lines. **Do this regardless of the decision** — it is the difference between "off by default" and "a trap for the next dev."
- **K26** · S — `_dispatch()` in `send_reminder_email.py:33` and `nudge_understaffed_module.py:34` still `return True` and send nothing while reporting `sent_count: 47`. **A stub that lies about success is worse than one that raises.** And `nudge_understaffed_module:50-59` builds recipients as "any volunteer with any non-cancelled signup in scope" — for an admin, **the entire volunteer table.** Harmless while `_dispatch` is a no-op; a mass-mail incident the day someone wires SMTP. **Fix the recipient set before any SMTP wiring, or delete the tools.**
- **K31** · S — turn profile extraction **off**. An unattended Celery job on the same free rate limit as chat can 429 a real user for reasons they cannot see.
- Then document the whole tool layer as built-not-wired in the known-issues list.

### If you affirm the full agent
Then B0.1 (adapter, L) + B0.2 (wire write tools, M) + B0.3 (Redis/DB confirmation store, M) + **K25** (approve has literally never worked — `loop.py:149` yields the confirmation event and returns without ever calling `store_pending`, so `POST /confirm` with `approved=True` 404s; and even fixed, the turn dead-ends with an empty assistant message so the user clicks Confirm, the card vanishes, and nothing is ever said) + **K28** (one bad tool argument ends the turn) + **K29** (the agent loop builds its own three-line prompt, dropping every guardrail, and the persisted session history then lies about what the model was told) + **K30** (agent turns spend tokens off-books, so the daily cost cap doesn't meter them).

That is not a one-week item on top of everything else in this document. ~~**Recommendation: reverse to Q&A-only for the deploy, keep the agent as the paper track, hand the branch to Rafael documented.**~~

**This is the path taken.** All of it is built — see the DECIDED box at the top of W3. The estimate was right that it was not a one-week item on top of everything else; it took the week, and the runtime-verification items it competed with are the ones that slipped.

**Gate:** flag state matches a written decision; no stub reports success it did not achieve.

---

## W4 — Deploy blockers

**~1–2 days.** Runs in parallel with W3. Much of the old Phase 37/38 is already done — `docker-compose.prod.yml`, `Caddyfile`, frontend `Dockerfile` + `nginx.conf`, `scripts/backup_db.sh`, `backend/.env.production.example`, `docs/deployment.md`, `docs/demo-runbook.md`, cost caps, rate limits, Sentry hooks. Verified present today. What is left:

### Hard blockers

- **No `/health` endpoint** ✅verified — grep finds none in `main.py`. Returns 404 today. **Every load balancer and container orchestrator needs this.** Cheapest blocker in the document.
- **No dev `.env.example`** ✅verified — `backend/` has `.env` (gitignored) and `.env.production.example`; **`frontend/` has only `.env`, no example at all.** The only working configuration is a gitignored file on your laptop. A clean clone cannot run. Must document `CORPUS_EMBEDDING_PRIMARY=local`, the `COPILOT_*` vars, and that `COPILOT_AGENT_LOOP_ENABLED` stays off.
- **Rotate secrets** — `OPENROUTER_API_KEY`, `JINA_API_KEY`, `SENDGRID_API_KEY`, `JWT_SECRET` are personal keys. Replace `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`.
- **No model-cache volume** in `docker-compose.yml` — BGE (~130MB) and the reranker (~278MB) re-download on every rebuild. Bake the weights into the image or mount a volume.
- **CrossEncoder cold start** — `rerank.py` lazy-loads ~278MB on first request *per worker*, with no lifespan prewarm in `main.py`. First real question after a deploy times out.
- **Infra mapping** — Postgres → RDS **with the `vector` extension** (migration 0019 requires pgvector); Redis → ElastiCache. Point `DATABASE_URL` / `REDIS_URL` / `VITE_API_URL` / `FRONTEND_BASE_URL` at real hosts.
- **Build-time flags** — `VITE_COPILOT_ENABLED` and `VITE_API_URL` are inlined at build. Getting them wrong is invisible until a user clicks.
- **Verified SendGrid sender** — dev uses Mailpit; nothing has ever sent through a real provider.
- **Runtime topology** — backend + celery_worker + celery_beat + redis are **all load-bearing** (reminders, broadcast rate-limit, idle-session sweep). A deploy that starts only the API silently stops sending mail.

### Decide, don't necessarily fix

- **PII plaintext at rest** — `copilot_user_profiles.profile_text` and feedback `comment` are plaintext `Text`. Only defence is persist-time redaction. Encrypt, or **accept in writing.**
- Single ~606KB JS bundle, no code splitting (the build warns).
- Rate-limit `/confirm`, rating and profile endpoints (only `messages` is limited).

**Gate:** a clean clone deploys from documented steps with no personal secrets.

---

## W5 — Security review

**~1 day.** Not started as a sweep, but four findings already landed piecemeal on main (unauthenticated `GET /slots` and `GET /signups/{id}` narrowed, visibility fail-closed ×2). That is evidence the surface has real holes, not evidence it is clean.

- **K33 — `/admin/feedback/*` is readable by organizers** ⚠️verified · S
  `router.py:938,959` still gate with `_require_admin_or_organizer`, and `aggregates.bottom_messages` has no user filter. Any organizer can read other staff's verbatim assistant **and** user messages plus thumbs-down comments. The nav item is admin-gated, so the UI looks correct.
- **Authz sweep.** K33 was found by reading one file. Assume it is not the only one — walk every router's role guard against its intended audience. This is the single highest-value item in W5.
- **Public endpoints:** public signup, magic-link manage, and the **no-auth `POST /events/{id}/check-in-by-email`**.
- **Auth surface:** JWT expiry, magic-link single-use + expiry.
- **Broadcasts bypass the unsubscribe link** — deliberate (operational, not promotional), but a CAN-SPAM exposure at scale. Document the reasoning.
- **OIDC/SSO endpoints exist** (`auth.py:265,273`) with no UI entry point and `oidc_*` all `None`. Decide before exposing.
- **Copilot PII boundary:** the two inert adversarial cases (`token_budget_exhaustion`, `indirect_injection`) are documented surfaces with no runner assertions.

**Gate:** findings report with severities; every high/critical remediated **or explicitly accepted in writing.**

---

## W6 — Runtime verification

**~3–4 days. ⛔️ This is the stage that finds new things — and nobody has done any of it.**

Every bug in this document came from *reading code*. All 1,600+ tests passed while `api.slots` did not exist. **Nobody has clicked through this application during the audit at all.**

One thing improved since July 28: **e2e demonstrably runs** — Playwright passed on PR #57. That is a real foundation to build on, not a claim.

### W6.1 — Walk every page in a browser · L
All 40+ routes from `App.jsx`, as each role, on desktop **and** a real phone viewport. Does it load, does it show real data, do the controls do what they claim. Playwright MCP is available — drive it and screenshot each state.

**This is where "confusing" and "in the wrong place" get found.** Code review structurally cannot find those.

### W6.2 — Walk every flow end to end with real side effects, Mailpit open · L
- browse → slots → identity → confirm → reminder → manage (now **read-only** — verify the organizer-contact notice actually helps)
- orientation-required block → pick orientation → signup → credit persists to a later event
- waitlist → staff promote → **promotion now requires email confirmation** (#53) → confirm link works
- admin: create event → add slots (verify K1's fix by hand, not by test) → duplicate → roster → end slot → export
- organizer on a phone: today → roster → check-in → broadcast (K5, K6)
- **bulk event builder** (#50) — mixed orientation + module batch, two-week split, re-add merge
- **if shifts ships: every one of the above again**, against the new model

### W6.3 — Open every email in a real mail client · M
Not Mailpit's preview. Gmail web, Gmail iOS, Apple Mail, Outlook. Nine builders, six templates. Check times (K4), branding (K20), layout. **Email is the app for an account-less product** and it renders differently everywhere.

### W6.4 — Adversarial input · M
Double-submit; back-button mid-flow; two tabs; expired token; slot fills between render and submit; network drop mid-submit; clock skew. Non-ASCII names, very long names, `+`-addressed emails.

### W6.5 — Turn every P0 into a regression test, and delete the mocks that hid them · M
`EventsSection.test.jsx:489-491` mocks a shape the real module never had — that mock is the only reason K1 shipped. `test_router_confirm.py:86,131,184` hand-park pending calls so the real path never runs. **A regression test for a bug that actually shipped is worth ten coverage tests.**

### W6.6 — Real conditions, if there is time · M
The unbounded tables (K36) with a full quarter of data, 500+ rows. 30 volunteers hitting one event at once — does `slot.current_count` stay correct? Safari's date parsing. An actual iPhone for `env(safe-area-inset-bottom)` and the 36px tap targets.

**Gate:** every route and flow executed by a human or browser agent; every email seen in a real client.

---

## W7 — The handoff itself

**~1 day.** The deliverable is not the code. It is Rafael deploying from a clean clone without you.

- **Runbook** — deploy steps, run migrations, rotate secrets, start the four services, flip the flags. Much of this is in `docs/deployment.md`; consolidate rather than rewrite.
- **Env-var reference** + the dev `.env.example` from W4.
- **Known-issues list** — everything not fixed, written down. See [What Rafael inherits](#what-rafael-inherits-as-documented-backlog).
- **Fix the instruction files that teach wrong rules** (K39) · S — `CLAUDE.md:73` still says CSV import is quarterly (that surface is gone); `PRODUCT-BRIEF.md:31,342,343` still says orientation is a soft warning (it is a **hard block**); `DEPLOY-ROADMAP-v2.md` repeats both. **Every new session and every human reading the brief currently learns the wrong product.** This is part of *why* the copilot was wrong.

  The verified current rules: orientation is a **hard requirement at signup time** (advisory only when the event offers no orientation slots); credit is **permanent**, keyed `(volunteer_email, family_key)`; waitlist moves **only by staff promote**, and a promoted seat needs its own confirmation; understaffed is **below 6 mentors**; cancellation notice is **2 days**; volunteers **cannot self-cancel or self-swap** — they contact the organizer; there is **no CSV import**.
- **Live walkthrough with Rafael.** Confirm he can deploy from a clean clone while you watch. This is the actual exit criterion.

**Gate:** Rafael deploys successfully and owns the runbook.

---

## Decisions only Andy can make

Nothing downstream closes without these. Answer them **on day one** — several block work in W2 and W3.

| # | Question | Blocks | Recommendation |
|---|---|---|---|
| 1 | **Does `feat/shifts` ship before handoff, or get parked as a documented branch?** | W1, and the size of W6 | Park it. A booking-model change in the final week doubles the verification surface. |
| 2 | **Phase B: tool-using agent, or retrieval-grounded Q&A?** The 2026-07-16 "full agent" decision has had three weeks and zero of B0.1–B0.3 built. | W3, W4 flags, K23–K33 | ✅ **DECIDED 2026-08-06: full agent, affirmed.** Built and merged; ships behind `COPILOT_AGENT_LOOP_ENABLED=0`. This row's original recommendation (Q&A-only) was overruled. |
| 3 | **Does a late cancellation or no-show carry any consequence for the volunteer?** | K21, and `docs/knowledge-base/35-cancellation-notice.md` — deliberately left silent rather than guessed | — |
| 4 | **`/admin/imports` — delete the 8 endpoints, or keep them dormant?** PR #50 leaves them unrouted, which answers this implicitly. Make it explicit. | K34, K35, and W5's "live endpoints with no UI" finding | Delete. Dormant endpoints are attack surface with no owner. |
| 5 | **PII at rest: encrypt `profile_text` + feedback comments, or accept the risk in writing?** | W4 | Accept in writing, given the timeline. |
| 6 | **The real copilot test questions.** The 10/10 eval used the auditor's own questions, not yours. | Phase K's stated exit criterion; the KB's FAQ doc | — |
| 7 | **SciTrek policy knowledge that exists nowhere in the code** — what a classroom visit looks like, what orientation covers, volunteer expectations, who to contact for what. | The highest-value KB docs; cannot be derived from anything in the repo | — |
| 8 | **Is the OpenRouter key going to be unblocked?** `PermissionDeniedError` today. | Any copilot demo at all | — |

---

## What Rafael inherits as documented backlog

Write these down rather than fixing them. Each is real; none blocks a working deploy.

**Consistency and code health**
- **K37** — 4 overlay implementations (`ui/Modal` ×13, `SideDrawer` ×6, `FormModal` ×3, hand-rolled ×2), 3 notification patterns, 3 page-header components, `ui/Button` ×200 vs raw `<button>` ×57, 3 duplicate date helpers. Five overlay implementations are reachable from two adjacent admin pages.
- **K35** — ~25 dead `api.js` exports. Plus a latent break: `authContext.jsx:38` calls `api.register()`, which **does not exist** and has no route. No caller today; breaks instantly if one appears. And `AdminLayout.jsx:198` passes `user`/`onSignOut` to a component that accepts neither, so `handleSignOut` — the only code that navigates to `/login` after logout — is **never called.**
- **K34** — `AdminDashboardPage.jsx` is unreferenced and holds 14 of 48 `TODO(copy)` markers.
- **K36** — `Pagination.jsx` has 2 consumers; 9 other tables ignore it. No table anywhere is sortable or has a sticky header. `OrientationCreditsSection` grows monotonically forever. `AuditLogsPage:163` passes `keepPreviousData`, a react-query **v4** option, on v5 — silently ignored.
- ~46 `TODO(copy)` / `TODO(brand)` markers.

**Accessibility** (K40, K15) — error toasts are `aria-live="polite"` and auto-dismiss in 3.5s, and the live region is created in the same tick as its content, so screen readers likely never announce them at all. Toasts are a `<div onClick>` — not focusable, no dismiss button. `SideDrawer` and `FormModal` have **no focus trap and no focus restore**, and one Escape keypress closes both a modal and the drawer behind it, discarding unsaved work. `index.css` has no `:focus-visible` rules at all. Tabs declare `role="tab"` with no `tabpanel`, no `aria-controls`, no arrow keys. 36×36px tap targets on the per-volunteer marking control.

**Motion** (K41) — 26 of 124 `.jsx` files mention any transition; no animation library installed. Starts from zero. Do it last or not at all.

**Mobile** (K42, K6) — bottom-nav overlap on `/organizer/*` and `/admin/*` (`pb-8` against a ≥56px fixed nav plus safe-area = zero clearance; the last card sits under the nav). Timezone drift: five call sites use `toLocaleTimeString` with **no `timeZone`** while the page they came from pins `America/Los_Angeles` and says "Times shown in Pacific Time." **K6:** all three admin mobile nav items point inside a shell gated behind `DesktopOnlyBanner` at 768px — an admin on a phone has **no working navigation destination.** The comment at `Layout.jsx:8-15` documents this exact bug being fixed, and it was applied to two of three items in one of two lists.

**Known-issue list for the runbook**
- Alembic `downgrade()` `DuplicateObject` on enum round-trips — fresh upgrades fine, rollbacks not.
- CrossEncoder cold start (if W4 doesn't bake the weights).
- Local-BGE-only corpus; the Jina embedding path has **never run end-to-end.**
- SMS (Phase 27) reserved in the schema, not built.
- `.planning/phases/31-.../salvage/` holds 3 undocumented Python artifacts — decide disposition.
- Whatever W5 accepted rather than remediated.
- **`feat/shifts`**, if parked: branch name, design spec path, test status, what remains.

**Paper track (yours, not Rafael's, and it blocks nothing)** — 35-02 multi-model eval (harness code-complete; fill `baseline-phase-33.json` and the results table), 35-03 grounded eval (~23% complete: 30 ok / 98 rate-limited across 8 models; needs multi-day resume passes), 36 DSPy (optional — defer past handoff).

---

## Full K-item status table

Re-verified against the working tree 2026-08-05. `✅fixed` / `⚠️open` / `➖dissolved` (the surface it lived on no longer exists).

| K | Item | Was | Now | Where |
|---|---|---|---|---|
| K1 | Admin cannot add/edit/delete slots | P0 | ✅ fixed (PR #56) | — |
| K2 | Default deploy retrieves nothing | P0 | ✅ fixed (`config.py:117`) | — |
| K3 | Cancel permanently bars re-signup | P0 | ➖ dissolved (PR #55) | — |
| K4 | Nine emails print raw UTC | P0 | ✅ **fixed** — `emails.py` converts to `VENUE_TZ` (`America/Los_Angeles`) in `_fmt_slot_time`/`_fmt_slot_day`. Landed in `a9da85a`; this row said "open" for a week after the fix was on main. | W2 |
| K5 | Organizer actions unreachable on phone | P0 | ⚠️ **open** (`ui/Modal.jsx:44`) | W2 |
| K6 | Admin mobile nav has no destination | P0 | ⚠️ open | Backlog |
| K7 | Copilot week tools ask an impossible question | P1 | ⚠️ **open** (`_iso_week.py`) | W2 |
| K8 | `max_signups_per_user` never enforced | P1 | ⚠️ open | W2 |
| K9 | Four reminders, opt-out covers two | P1 | ⚠️ **open** (`celery_app.py:991,995`) | W2 |
| K10 | Past slots stay bookable | P1 | ⚠️ open | W2 |
| K11 | Error branches render first-run cards | P1 | ⚠️ open | W2 |
| K12 | Exports fail silently ×9 | P1 | ⚠️ open | W2 |
| K13 | Destructive actions unconfirmed | P1 | ⚠️ open | W2 |
| K14 | Delete-event has the weakest dialog | P1 | ⚠️ open | W2 |
| K15 | One Escape discards unsaved work | P1 | ⚠️ open | Backlog |
| K16 | Manage link in reminders is a dead end | P1 | ➖ mostly dissolved (PR #55) | Re-read |
| K17 | Expired magic link is a closed loop | P1 | ➖ mostly dissolved (PR #55) | Re-read |
| K18 | Pending signups hold a seat, then vanish | P1 | ⚠️ open | W2 |
| K19 | Cancel/swap/waitlist tell volunteers nothing | P1 | ➖ partly dissolved (#53, #55) | Re-read |
| K20 | Every email branded for the wrong product | P1 | ⚠️ **open** | W2 |
| K21 | 2-day cancellation notice doesn't exist | P1 | ⚠️ open ⛔️ | Decision 3 |
| K22 | Copy contradicts the server | P1 | ⚠️ open | W2 |
| K23 | Flag-on returns a bare 500 | Phase B | ✅ done | W3 |
| K24 | B0.1 the adapter | Phase B | ✅ done (full agent affirmed) | W3 |
| K25 | Confirmation approve has never worked | Phase B | ✅ done | W3 |
| K26 | Write tools report success without acting | Phase B | ✅ done | W3 |
| K27 | Tool-layer correctness | Phase B | ✅ done | W3 |
| K28 | One bad tool arg kills the turn | Phase B | ✅ done | W3 |
| K29 | Agent loop drops every guardrail | Phase B | ✅ done | W3 |
| K30 | Token budget doesn't see agent turns | Phase B | ✅ done | W3 |
| K31 | Profile extraction should go off | Phase B | ✅ done | W3 |
| K32 | Copilot drawer can trap the user | Phase B | ✅ done | W3 |
| K33 | `/admin/feedback/*` readable by organizers | Security | ⚠️ **open** (`router.py:938,959`) | W5 |
| K34 | Delete dead pages | Cleanup | ⚠️ half (portals gone) | Backlog |
| K35 | Dead client + endpoint surface | Cleanup | ⚠️ open | Backlog |
| K36 | Tables: no pagination, sort, sticky headers | Cleanup | ⚠️ open | Backlog |
| K37 | Pick one of each (4 overlays, 3 toasts…) | Cleanup | ⚠️ open | Backlog |
| K38 | Loading and empty states | Cleanup | ⚠️ open | Backlog |
| K39 | Instruction files teach wrong rules | Docs | ⚠️ **open** | W7 |
| K40 | Accessibility | A11y | ⚠️ open | Backlog |
| K41 | Motion | Polish | ⚠️ open | Backlog |
| K42 | Mobile leftovers | Mobile | ⚠️ open | Backlog |

**6 closed, 36 open. 11 of the 36 are in W2 and land in ~2 days.**

---

## If the week compresses

Cut from the back, never the front.

| Cut | Consequence |
|---|---|
| Backlog items (K35–K42) | Inconsistent and inaccessible, but **correct**. Rafael's problem, documented. |
| **W6.6** real conditions | Ships; may break on Safari or at quarter-scale. |
| **W1** shifts (park it) | Ships the current booking model. **Recommended cut** — it buys back the most time for the least loss. |
| ~~**W3** full agent (ship Q&A)~~ **NOT CUT** | ✅ The full agent was built. K23/K26/K28–K32 all done. Ships flag-off, so the copilot answers but cannot act *until someone turns it on* — the capability exists rather than being absent. |
| **W6.1–W6.5** runtime verification | **Ships with unknown unknowns.** The one cut worth feeling bad about. |
| **W5** security review | Ships with an unswept authz surface after one was already found open. Do not cut. |
| **W2** | Ships something that lies to volunteers over email. Do not cut. |
| **W4** | Rafael cannot deploy. Do not cut. |
| **W0** | You don't know what you're shipping. **Never cut.** |

### Where the risk actually is, ranked

1. **W6 findings.** Highest-confidence prediction in this document: walking the app in a browser will surface issues no audit found. Nobody has done it.
2. **A fifth mock-hidden P0** (S0.1). The record is 4 for 4.
3. **`feat/shifts`.** A booking-model change, uncommitted, in the final week.
4. **Phase B** if affirmed — ~1,200 lines that have never executed. Well-tested and untried are different things.
5. **Email rendering.** Nine builders, six templates, never opened in a real client.
6. **The OpenRouter key.** Not a code risk, and it can make the copilot undemonstrable on handoff day.

### The single cheapest high-value action available right now

Merge PR #57. CI has been red on every branch since July 31, which means **no merge signal exists today.** Everything else in this plan is harder to trust until that is true again.

---

*Last verified 2026-08-05 against `origin/main` @ `5484333`. Confidence markers carried from `.planning/HANDOFF-EXECUTION-ROADMAP.md`, with every ✅verified/⚠️open status in the table above re-checked in the tree today.*
