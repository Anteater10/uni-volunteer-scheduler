# Road to deploy — everything left

**Written:** 2026-08-07 · **Verified against:** `main` @ `886b6b5` (post-W2, post-W3)
**Supersedes:** the W4–W7 sections of `.planning/FINAL-ROADMAP.md`, which were
written on 2026-08-05 and are stale in both directions — some blockers listed
there are already built, and its premise that a backlog gets handed off is wrong.

**Scope correction that reshapes this document:** Rafael does **deployment
only**. Every other item here is Andy's own work. Nothing is "handed off as
documented backlog" — deferring an item means *you* do it later.

Every ✅/❌ below was checked against the tree today, not carried over.

---

## Where things stand

| Phase | Status |
|---|---|
| W0 land what's built | ✅ done (PR #50 still open, see below) |
| W1 shifts | ✅ merged |
| W2 bugs that lie or break | ✅ done — PRs #60–#66 |
| W3 Phase B / full agent | ✅ done — PR #67 |
| **W4 deploy blockers** | **← you are here** |
| W5 security review | not started |
| W6 runtime verification | not started |
| W7 deployment handoff | not started |

**29 of 42 K-items closed. 13 open, of which exactly one (K33) blocks deploy.**

---

## Corrections to the previous roadmap

Three of its W4 "hard blockers" are not blockers. They were asserted from a
grep that missed, and repeating them would have sent you to build things that
already exist:

| Claim | Reality |
|---|---|
| "No `/health` endpoint — returns 404 today" | ❌ **Wrong.** `main.py:103` serves `GET /api/v1/health`, and it pings the DB. `docker-compose.prod.yml:82` already healthchecks it every 15s. |
| "No prod compose" | ❌ **Wrong.** `docker-compose.prod.yml` exists with all six services, plus `Caddyfile`, `frontend/Dockerfile`, `nginx.conf`, `scripts/backup_db.sh`. |
| K4, K18 listed open | ❌ **Wrong.** Both were already fixed on main when the table was written. |

What survives verification is below.

---

## W4 — Deploy blockers · ~1–2 days

### Must fix before a deploy can work

**W4.1 — `frontend/.env.example` does not exist** · S · ✅verified
`frontend/` has a gitignored `.env` and nothing else. A clean clone cannot
build. Three variables are read in the source; the current `.env` only sets
two of them:

| Variable | In `.env` today | Notes |
|---|---|---|
| `VITE_API_URL` | yes | Inlined at build time |
| `VITE_COPILOT_ENABLED` | yes | Inlined at build time |
| `VITE_PUBLIC_BASE_URL` | **no** | Used in source, undefined in the only working config |

That third row is its own small bug: something reads a variable nobody sets.
Resolve it while writing the example.

**W4.2 — No model-cache volume** · S · ✅verified
Neither `docker-compose.yml` nor `docker-compose.prod.yml` mounts one — prod
declares only `pgdata`, `redisdata`, `caddy_data`, `caddy_config`. BGE (~130MB)
and the reranker (~278MB) re-download on every container rebuild. Mount a
volume or bake the weights into the image.

**W4.3 — No CrossEncoder prewarm** · S · ✅verified
`rerank.py:30` lazy-loads ~278MB behind `lru_cache(maxsize=1)`, and `main.py`
has **no lifespan handler at all**. The first real question after each deploy
pays the download-and-load cost inside a request, per worker. Add a lifespan
that touches `_model()` at boot.

**W4.4 — Rotate every secret** · S · ⛔️ only you can do this
`OPENROUTER_API_KEY`, `JINA_API_KEY`, `SENDGRID_API_KEY`, `JWT_SECRET` are all
personal keys in your gitignored `backend/.env`. Replace `SEED_ADMIN_EMAIL` and
`SEED_ADMIN_PASSWORD`. **Do not paste real values into any file I touch.**

**W4.5 — Point config at real infrastructure** · M · ⛔️ needs your hosting decision
Postgres must have the **`vector` extension** — migration 0019 requires pgvector,
so a stock managed Postgres will fail to migrate. Redis is load-bearing, not a
cache. Then set `DATABASE_URL`, `REDIS_URL`, `VITE_API_URL`, `FRONTEND_BASE_URL`.

**W4.6 — All four services must run** · S
`backend` + `celery_worker` + `celery_beat` + `redis` are each load-bearing:
reminders, the broadcast rate limit, the idle-session sweep, and the hourly
`expire_pending_signups` sweep all live in Celery. **A deploy that starts only
the API silently stops sending mail** and silently stops freeing held seats.
Write this into the runbook as a check, not a footnote.

**W4.7 — Verified SendGrid sender** · S
Dev has only ever sent to Mailpit. Nothing has gone through a real provider.
Sender verification is a DNS-and-waiting task — start it early, it blocks W6.3.

### Decide, don't necessarily fix

**W4.8 — PII plaintext at rest** · ⛔️ decision
`copilot_user_profiles.profile_text` (`models.py:1366`) and two feedback
`comment` columns (`1398`, `1439`) are plaintext `Text`. The only defence is
persist-time redaction. Encrypt them, or **accept it in writing** — an
unrecorded acceptance is indistinguishable from an oversight later.

**W4.9 — Rate-limit the rest of the LLM surface** · S · ✅verified
`router.py:512` limits `/messages` and nothing else. `/confirm`, message rating
and session rating are unlimited.

**W4.10 — Single ~606KB JS bundle**, no code splitting. The build warns. Cosmetic
unless volunteers are on bad phone connections at a school — which they are.

**Gate:** a clean clone deploys from documented steps, with no personal secrets,
and all four services running.

---

## W5 — Security review · ~1 day

**W5.1 — K33** · ✅ **CLOSED 2026-08-13 — accepted in writing, not fixed.**
Organizers keep this access: they are trusted staff, and the 2026-08-12 ruling
made organizer reads unscoped. Two tests already asserted the behaviour on
purpose. Exposure, grounds, and the revisit trigger (**re-decide before the
copilot is opened to any non-staff role**) are in
[docs/security-review-w5.md](../docs/security-review-w5.md#accepted-risks).
**This was the last open K-item blocking deploy; nothing on that list remains.**
The original finding text follows, for the record:

**W5.1 — K33: `/admin/feedback/*` is readable by organizers** · S · ✅verified
`router.py:1093` and `1114` guard `GET /admin/feedback/weekly` and
`GET /admin/feedback/bottom-messages` with `_require_admin_or_organizer`. Any
organizer can read other staff's verbatim user **and** assistant messages plus
thumbs-down comments. The nav item is admin-gated, so the UI looks correct and
nobody would notice. **This is the one open K-item that blocks deploy.**

**W5.2 — Authz sweep** · M — *the highest-value item in W5*
K33 was found by reading one file. Four more findings already landed piecemeal
on main. That is evidence the surface has holes, not that it is clean. Walk
every router's role guard against its intended audience.

**W5.3 — The unauthenticated surface** · S
Public signup, magic-link manage, and `POST /events/{id}/check-in-by-email`
(`check_in.py:522`) — no auth at all. Confirm each is intentionally open and
cannot be used to enumerate volunteers.

**W5.4 — Auth surface** · S — JWT expiry, magic-link single-use and expiry.

**W5.5 — OIDC is half-wired** · S · ✅verified
`auth.py:131` registers an OIDC client when three settings are present. They
are all `None` and there is no UI entry point. Decide: remove, or finish and
document. Dormant auth paths are the worst kind of dead code.

**W5.6 — Broadcasts bypass the unsubscribe link.** Deliberate — they're
operational, not promotional — but that reasoning has to be written down before
it's a CAN-SPAM question rather than after.

**W5.7 — Two inert adversarial cases** (`token_budget_exhaustion`,
`indirect_injection`) are documented surfaces with no runner assertions.

**Gate:** findings report with severities; every high/critical remediated **or
explicitly accepted in writing**.

---

## W6 — Runtime verification · ~3–4 days

⛔️ **The stage that finds new things, and none of it has been done.**

Every bug in this project's audit came from *reading code*. All 1,600+ tests
passed while `api.slots` did not exist. **Nobody has clicked through this
application.** Budget for W6 finding new work, not for it confirming the
existing list.

One real foundation: Playwright demonstrably runs — it passed on PR #57.

- **W6.1 — Walk every route** · L — all 40+ routes from `App.jsx`, as each role,
  desktop and a real phone viewport. This is where "confusing" and "in the wrong
  place" get found; code review structurally cannot find those.
- **W6.2 — Walk every flow with real side effects, Mailpit open** · L — signup →
  confirm → reminder → manage; orientation block → credit persisting to a later
  event; waitlist → staff promote → confirm; admin create → slots → duplicate →
  roster → export; organizer on a phone; the bulk event builder (#50). **And all
  of it against the shifts model**, which is new since the audit.
- **W6.3 — Open every email in a real client** · M — Gmail web, Gmail iOS, Apple
  Mail, Outlook. Not Mailpit's preview. Nine builders, six templates. **Email is
  the app for an account-less product.** Blocked on W4.7.
- **W6.4 — Adversarial input** · M — double-submit, back button mid-flow, two
  tabs, expired token, slot filling between render and submit, network drop,
  clock skew, non-ASCII and very long names, `+`-addressed email.
- **W6.5 — Turn every P0 into a regression test and delete the mocks that hid
  them** · M — `EventsSection.test.jsx:489` mocks a shape the real module never
  had, and that mock is the only reason K1 shipped. **A regression test for a bug
  that actually shipped is worth ten coverage tests.**
- **W6.6 — Real conditions, if time** · M — unbounded tables (K36) with a full
  quarter of data; 30 concurrent signups against one event (does
  `slot.current_count` hold?); Safari date parsing; a real iPhone.

**Gate:** every route and flow executed by a human or browser agent; every email
seen in a real client.

---

## W7 — Deployment handoff · ~0.5 day

**Smaller than previously scoped.** Rafael deploys and nothing else, so this is
deployment knowledge only — not a codebase handover.

- **Runbook** — deploy, migrate, rotate secrets, start all four services, flip
  flags. Consolidate `docs/deployment.md`; don't rewrite it.
- **Env-var reference** — including `frontend/.env.example` from W4.1 and the
  now-documented `COPILOT_AGENT_LOOP_ENABLED`.
- **Live walkthrough** — Rafael deploys from a clean clone while you watch.
  **This is the actual exit criterion**, not the document.

**K39 stays with you, and it grew.** "Instruction files teach wrong rules" is
not a handoff item now — it's the thing that makes *your own* future sessions
and the copilot wrong. `CLAUDE.md:73` still says CSV import is quarterly (that
surface is gone). `PRODUCT-BRIEF.md:31,342,343` still says orientation is a soft
warning; it is a **hard block**. Both now also predate shifts and the agent
decision.

The verified current rules, for whoever fixes those files:
orientation is a **hard requirement at signup time** (advisory only when the
event offers no orientation slots); credit is **permanent**, keyed
`(volunteer_email, family_key)`; waitlist moves **only by staff promote**, and a
promoted seat needs its own confirmation; understaffed is **below 6 mentors**;
cancellation notice is **2 days**; volunteers **cannot self-cancel or self-swap**;
there is **no CSV import**; a booking is a **shift**, not a single session; and
`max_signups_per_user` now caps **shifts per volunteer**, orientation exempt.

---

## Decisions only you can make

These block work rather than being work. None can be defaulted safely.

| # | Decision | Blocks |
|---|---|---|
| 1 | **Where does this host?** Postgres must support the `vector` extension. | W4.5, and therefore the whole deploy |
| 2 | **PII at rest** — encrypt the three plaintext columns, or accept in writing? | W4.8 |
| 3 | **K21** — does a late cancellation or no-show carry any consequence for the volunteer? Deliberately left unguessed. | K21, `docs/knowledge-base/35-cancellation-notice.md` |
| 4 | **PR #50** (bulk event builder) — rebase and land it, or close it with a salvage note? Open since 2026-07-24. It changes what W6.2 has to cover. | W6.2 scope |
| 5 | **OIDC** — finish it or remove it? | W5.5 |

---

## What is deliberately deferred — and is still yours

Not a handoff list. This is your own queue after deploy: **K6** (admin mobile
nav has no destination), **K15** (one Escape discards unsaved work), **K34**
(dead pages, half done), **K35** (dead client + endpoint surface), **K36**
(tables: no pagination, sort, sticky headers), **K37** (four overlay patterns,
three toast systems — pick one of each), **K38** (loading and empty states),
**K40** (accessibility), **K41** (motion), **K42** (mobile leftovers).

Ten items. None blocks deploy. All of them are work you will do.

---

## Known conditions that are not bugs

- ~~**GitHub CI cannot run.**~~ ✅ **Resolved 2026-08-12.** Runner acquisition
  was failing (`The job was not acquired by Runner of type hosted`) —
  infrastructure, not code — and W2 and W3 were merged on locally-run
  verification standing in for it. PR #70 ran all three jobs green (backend
  15m24s, frontend 58s, Playwright 12m7s), so CI is a merge signal again
  going into W6.
- **~50 OpenRouter requests/day** on an unfunded account. An agent turn spends
  several of them, so a busy day rate-limits a real question, and the copilot
  cannot be meaningfully load-tested in W6. This is a funding item, not a code
  item, and it is the one prerequisite of the flag-on decision still open.
- **The agent ships ON** — superseded 2026-08-08, after this document was
  written. `.env.production.example:89` sets `COPILOT_AGENT_LOOP_ENABLED=true`
  and `config.py` defaults to it; PR #69 landed the flip. Setting it false is
  the rollback, and returns a real 503 rather than a bare 500 (K23).
  `COPILOT_PROFILE_EXTRACTION_ENABLED` does still ship **off** (:65).
  The drawer copy that this document flagged as needing to change with the flip
  has already been changed (`CopilotDrawer.jsx:273`).

---

## Shortest path to deployable

```
W4.1 .env.example ─┐
W4.2 model volume  ├─ half a day, all mechanical
W4.3 prewarm       │
W4.9 rate limits  ─┘
        │
W5.1 K33 authz fix ── the one open K-item that blocks deploy
        │
W4.4 rotate secrets ─┐
W4.5 real infra      ├─ needs Decision 1 and only you can do them
W4.7 SendGrid sender ┘   (start 4.7 early — DNS waits on nobody)
        │
W6 runtime verification ── expect new findings; this is the long pole
        │
W7 runbook + live walkthrough with Rafael
```

**W4.1/4.2/4.3/4.9 and W5.1 are the next block** — mechanical, verifiable, and
they clear everything that doesn't need a decision from you first.
