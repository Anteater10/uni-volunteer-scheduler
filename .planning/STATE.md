# STATE

**Updated:** 2026-09-10
**Branch:** `feature/L3-auth-hardening` (off `main` @ `b4fd214`) — **implemented and
verified, NOT yet committed or PR'd**
**Roadmap:** `.planning/ROADMAP.md` — the single source of truth

> The previous STATE.md was dated 2026-05-23 and said "next action: merge Phase
> 35-01". It was 3.5 months stale and any `/gsd-*` command was acting on May's
> picture. Archived to `.planning/archive/superseded-2026-09-04/STATE.md`.

## Current milestone

**L — Launch.** Target: live, verified, handed over to Rafael.
Estimated 4–6 weeks from Gate 0 being answered.

## Current phase

**Phases L0, L1 and L2 all complete as of 2026-09-08**, and **Gate 0 is fully
closed** — all 12 decisions made and Jira level with them (SCRUM-51 umbrella
plus 56–63 Done). L1 closed done-by-circumstance with no DNS work performed.
Audited across Jira, these planning docs and GitHub on 2026-09-08 before
starting L3; the gaps that audit found are recorded in the outcome blocks below.

**Phase L3 — auth and abuse hardening: code complete on
`feature/L3-auth-hardening` as of 2026-09-10, awaiting commit + PR.** Gate 0 #2
is implemented (see the L3 outcome block below). Of Gate 0, only #12 (write
real corpus test questions) remains, and it's just Andy's to-do, not a
blocking call.

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

1. **Commit and PR Phase L3.** The work is done and verified (outcome block
   below) but the tree is still uncommitted on `feature/L3-auth-hardening`.
   Nothing else should start before this lands, because it touches the auth
   path every other phase depends on. Jira: SCRUM-157 (created 2026-09-10);
   **SCRUM-12's JWT half is absorbed by L3** — its remaining items (S-03 six
   spellings of "staff", T3 frontend/backend role-map cross-check, W5.6/W5.7)
   are untouched and stay open.
2. **At the next AWS deploy** (L9 notes, cumulative): `VITE_COPILOT_ENABLED`
   is now **required** or the deploy fails fast by design; confirm the site
   loads after the frontend's internal port change (80 → 8080); and the Celery
   worker must deploy together with the backend. On
   `COPILOT_PROFILE_EXTRACTION_ENABLED` — Andy is enabling it in AWS; note
   `backend/.env.production.example:176` already ships it as `true` and the
   K31 note in `backend/app/tasks/extract_profile.py:32-36` records the budget
   objection as resolved on 2026-08-20, so check whether it is already set.
3. **Answer Gate 0 #12** — write real copilot corpus test questions. Andy's
   own task, tracked as P6 item #133, blocking nothing else.
4. **Phase P6** — copilot production hardening: corpus refresh,
   CSV-upload-via-copilot tool (its starting material is the deliberately-kept
   `fix/imports-templates` branch), production-grade RAG audit, concurrency
   testing, guardrails. See `.planning/ROADMAP.md` items 133–142.
5. **Open, not gating L3:** SCRUM-45 dependency triage — now 35 advisories,
   including `CVE-2026-9856` against `transformers 4.57.6`, whose fix is a
   major version jump that wants the embedding pipeline re-verified. GitHub
   issue #9 also stays open: its RBAC is already correct (all seven
   module/template endpoints use `require_staff`, unscoped) but its two
   deliverables — an audit doc and a regression test asserting organizer ==
   admin — do not exist, and `test_admin_modules.py` / `test_modules_crud.py`
   have **zero** organizer coverage.

## Phase L3 outcome (code complete 2026-09-10 — not yet merged)

Gate 0 #2 implemented. Refresh token moved out of `localStorage` into an
`HttpOnly` cookie; access token now lives in a module-scoped JS variable and
is re-minted on boot by a silent `/auth/refresh`. Plus CSRF on the
cookie-authenticated routes, throttles on `/auth/refresh` and `/auth/logout`,
and `aud`/`iss` claims on access tokens.

Files: `backend/app/routers/auth.py`, `deps.py`, `config.py`, `schemas.py`;
`frontend/src/lib/authToken.js` (new), `authStorage.js`, `api.js`,
`state/authContext.jsx`, plus the copilot/check-in/roster call sites.

**Read this part before touching auth again — a showstopper got past a fully
green test suite.**

The first implementation was reported done with backend 2109 passing,
frontend 633 passing, and a hand-run curl pass over login → refresh → logout.
It was broken in a way that would have logged every member of staff out on
every page reload. Both cookies were set with `Path=/api/v1/auth`;
`document.cookie` only exposes cookies whose `Path` prefix-matches **the
current page**, and the SPA's pages are `/`, `/login`, `/admin/...`. So the
JS-readable csrf cookie was invisible, no `X-CSRF-Token` header could be
built, and every refresh 403'd.

Why each green signal was worthless here, because the pattern will repeat:

- **vitest/jsdom** — the test did `document.cookie = "csrf_token=..."`, which
  defaults to the *current document's* path (`/`). It fabricated a cookie the
  server never sends, so it proved nothing about the server's `Path`.
- **curl** — matches cookies against the **request** URL
  (`/api/v1/auth/refresh`, which does match). "The page the JS is running on"
  has no representation in curl at all.
- **pytest TestClient** — same jar semantics as curl. The test asserted
  `HttpOnly` and `Secure` and never asserted `Path`.
- **Playwright** would have caught it on the first `page.reload()`. It was
  not run.

Fix: the two cookies now get deliberately different paths —
`REFRESH_COOKIE_PATH = "/api/v1/auth"` (only the browser sends it, only
there) and `CSRF_COOKIE_PATH = "/"` (JS must be able to read it from every
route; it is a random nonce, not a credential). Proven in chromium, firefox
and webkit, and pinned by `e2e/auth-session.spec.js` plus a backend test
asserting the literal `Path=/`. Reintroducing the old path was verified to
fail 4 of the 5 e2e tests — the suite can actually fail.

**Nine further defects found in the same review** (me line-by-line, plus an
Opus security reviewer and an Opus frontend reviewer in parallel). All fixed:

1. **Logout silently revoked nothing** (HIGH). It depended on
   `get_current_user`, but the access token is memory-only now and is
   routinely absent at logout — so those requests 401'd before the body ran:
   no revoke, no cookie clear, while the UI said "logged out". The refresh
   cookie stayed live for its full 2 days. **On a shared campus machine the
   next person's boot refresh resumed the previous session.** Now uses
   `get_optional_user`, always revokes and clears, returns 200, and requires
   CSRF (it is cookie-authenticated now, so a Bearer header no longer makes
   it CSRF-safe).
2. **Two tabs revoked every session** (HIGH). Refresh moved onto every page
   load, so two tabs reloading both replay the same cookie; reuse detection
   read that as theft and revoked the whole rotation family. Now a 15s
   grace window (`AUTH_REFRESH_RACE`) when the *immediate* successor is still
   live, plus a `navigator.locks` Web Lock so tabs serialize and the second
   one picks up the rotated cookie.
3. **TOCTOU in `_consume_refresh_token`** (HIGH). Plain `.first()` with no
   row lock: under `--workers 4`, two requests could both see
   `consumed_at IS NULL` and both mint a successor, so rotation failed
   **open**. Now `.with_for_update()`.
4. **Any failed refresh logged the user out** (HIGH). A 429 from the per-IP
   throttle, a 5xx, or a proxy blip all wiped the session — and staff behind
   one campus NAT share a throttle bucket. Now only 401/403 clear state.
   `/auth/refresh` also raised to 120/min from 30, because it is on the boot
   path of every page load.
5. **`Secure` failed open** (MED). It was derived from `request.url.scheme`,
   which only reads "https" because compose passes `--proxy-headers`; the
   image's own Dockerfile CMD does not, and the trusted CIDR assumes
   Docker's default address pool. Now always `Secure` outside
   `development`.
6. **CSRF was defeatable by cookie tossing** (MED). Double-submit alone
   assumes an attacker cannot write cookies for the site; a sibling
   subdomain breaks that (Starlette's parser is last-wins). Added an
   `Origin` allow-list check and `secrets.compare_digest`.
7. **`aud` validation was decorative** (MED). python-jose's `_validate_aud`
   *accepts* a token with no `aud` claim at all, so only `iss` was
   load-bearing. Now `require_aud`/`require_iss`/`require_exp`.
8. **Stale tokens on existing staff machines** (LOW). Everyone who used the
   old build still had a server-valid `uvse_refresh_token` in
   `localStorage` — the exact exposure this phase closes, left open for the
   people who already had it. Now cleaned up on module load.
9. Smaller: `delete_cookie` dropped `Secure`/`HttpOnly`; `schemas.Token`
   still advertised a `refresh_token` field nothing populates;
   `authorizedFetch` skipped the retry when no token was held, and
   `{...new Headers()}` silently drops headers.

**A regression the e2e suite caught that nothing else did.** With the boot
refresh running on every page load, an anonymous visitor to the *public*
site had no cookies, so the refresh 403'd — a console error on a surface
where `public-signup.spec.js` forbids them (PART-02), and a wasted throttle
slot per public page view. `refreshAccessToken` now returns early when there
is no csrf cookie, since without it a refresh cannot succeed anyway.

Also deleted: three dead refresh helpers in `deps.py`, including a
`verify_refresh_token` that validated a token *without* rotating it or
detecting reuse — a plausible-looking footgun in a shared module.

## Phase L1 outcome (completed 2026-09-08 — done by circumstance)

Roadmap items #18 and #19. **No DNS work was performed, and none was needed.**

- **Domain authentication was already live and nobody had recorded it.** Verified
  from public DNS: `s1._domainkey` / `s2._domainkey` on `sci-trek.org` point at
  `u113425370.wl121.sendgrid.net` and resolve to a real RSA key. That is why real
  confirmation mail from `no-reply@sci-trek.org` has been arriving since at least
  2026-09-02.
- **The phase's founding premise never applied.** It was written around "UCSB IT
  may refuse the CNAMEs"; Gate 0 #10 established the domain is SciTrek's own, at
  IONOS. No external approval was ever in the path.
- **Deferred to the SendGrid → SES port**, deliberately, because both get redone
  there: confirming the third SendGrid CNAME (the `emNNNN` return-path subdomain,
  invisible from outside without the number) and adding a DMARC `rua=` — DMARC is
  currently `p=none` with no reporting address, so nobody receives reports.
- **A constraint that outlives the phase:** whenever Cloudflare is adopted
  (Gate 0 #1, decided yes), the DKIM CNAMEs and MX must stay **DNS-only, never
  proxied** — a proxied `_domainkey` resolves to a Cloudflare IP instead of
  SendGrid's value and breaks DKIM while still looking correct in the dashboard.
  Also note adopting Cloudflare is a **nameserver migration off IONOS**, not just
  adding records, so the whole zone must be re-created.

Jira: SCRUM-69 Done. Item #18 never had a ticket; recorded in the roadmap row.

**Correction to an earlier reading in this file:** an earlier next-action here
described L1 as "mostly resolved, remaining work is adding CNAME records."
Wrong — the records were already there. The remaining work was only the third
CNAME and DMARC polish.

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

## Verified test status (2026-09-10, `feature/L3-auth-hardening`)

- Backend: **2,145 passing**, 13 skipped (all environmental — see the
  2026-09-08 reading below for why)
- Frontend: **676 passing**, 76 files
- **Changed-line coverage: 100%** on `auth.py`, `deps.py`, `config.py`,
  `schemas.py` — statements *and* branches, measured by intersecting
  `git diff` line numbers with coverage.py's missing set
  (`backend/tools/changed_line_coverage.py`, added this phase). Whole-file
  coverage was 94%/88% and would have hidden this: a file sits at 94% while
  every new line is in the missing 6%, which is how the cookie bug shipped.
- Frontend `authToken.js` + `authStorage.js` at **100%** statements,
  branches, functions and lines, enforced by thresholds in
  `vitest.config.js` (`npm run test:coverage:auth`). `@vitest/coverage-v8`
  was added this phase — the project had no coverage provider at all.
  Coverage is a separate scoped command on purpose: instrumenting all 76
  jsdom environments takes ~10 minutes and starts timing out workers.
- E2E: `e2e/auth-session.spec.js` (5 tests) green on **chromium, firefox and
  webkit**; the full pre-existing suite green on chromium (38 passed, 7
  skipped) against L3 code.

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

**L3 deploy notes (carry into L9).**

- **`CORS_ALLOWED_ORIGINS` is now load-bearing for login itself, not just
  XHR.** `verify_csrf` rejects a request whose `Origin` is not on that list,
  and the auth cookies need `credentials: "include"`, which CORS must
  permit. If the SPA is ever served from an origin missing from that list,
  staff cannot log in at all. Found the hard way: moving the dev server to an
  unlisted port broke all 15 e2e tests.
- **Cookie host, not just port.** The cookies are host-scoped to whatever
  host the API is reached on. `localhost` and `127.0.0.1` are *different
  hosts* for cookies (ports are ignored, hosts are not) — the SPA origin and
  `VITE_API_URL` must agree on which one they use, or the browser stores
  cookies the app can never read.
- **Existing sessions survive the deploy but their localStorage copies do
  not get revoked.** The new build deletes the legacy keys from each browser
  that loads it, but the tokens they held stay valid server-side until they
  expire (≤2 days). A `DELETE FROM refresh_tokens` at deploy time would
  close that window at the cost of logging everyone out once — Andy's call.

**The e2e seed is not idempotent against a used dev database.**
`seed_e2e.py` fails with `quarter create failed: 409 Dates overlap Fall 2026`
against the dev DB, because `_ensure_quarters` cannot reconcile with quarters
that already exist. Not an L3 issue and not fixed here. Workaround used for
this phase's e2e run: a throwaway `e2e_uvs` database (create, `alembic
upgrade head`, `python -m app.seed_admin` with `SEED_ADMIN_EMAIL`/`_PASSWORD`,
then the seed), with a backend container pointed at it. The seed works
perfectly on a clean DB — worth fixing before anyone relies on `npm run e2e`
locally.

**Port 5173 collides with another project on Andy's machine.** A second
SciTrek app ("SciTrek Bioinformatics") listens on `127.0.0.1:5173` while
vite binds `*:5173` (IPv6). Chromium resolves `localhost` to `::1` and gets
the right app; **firefox resolves to IPv4 and gets the wrong one**, which
looks exactly like a mysterious browser-specific failure. Use an explicit
free port for e2e.

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
