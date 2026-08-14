# Steps to W7 — numbered, platform-tagged

**Written:** 2026-08-13 · **Verified against:** `feat/w5-remainder` @ `ab51e21`
**Companion to:** `.planning/ROAD-TO-DEPLOY.md` (the reasoning) — this file is the order of operations.

Platform column: **Render** = only touches your rehearsal deploy · **AWS** = only Rafael's
target · **both** = application-level, moves to AWS untouched.

Render is a rehearsal, not a stepping stone. Its *config* is throwaway; the *defects it
finds* are not. ~two-thirds of what remains below is "both".

---

## Block A — decisions and Render config (0.5 day, mostly not code)

| Step | What | Platform | Blocks |
|---|---|---|---|
| 1 | **Ask Rafael: SendGrid or AWS SES?** `EMAIL_MODE` supports both; SES is plain SMTP. Choosing late means verifying DNS twice. | both | step 21 |
| 2 | **Confirm the AWS shape with Rafael:** RDS Postgres must allow `CREATE EXTENSION vector` (migration 0019 fails without it); ElastiCache Redis is load-bearing, not a cache; celery worker + beat are separate task definitions. | AWS | step 28 |
| 3 | **Rotate 4 secrets + reseed admin** (W4.4) — `OPENROUTER_API_KEY`, `JINA_API_KEY`, `SENDGRID_API_KEY`, `JWT_SECRET`, plus `SEED_ADMIN_*`. They were readable in a published image layer, so they are burned on every platform. Rotate once, paste into both dashboards. | both | — |
| 4 | **Set `ENVIRONMENT=production` in the Render dashboard.** Confirmed `development` on 2026-08-13, which left `/docs` public for the whole trial. Code default is now `production` (ab51e21), so this is dashboard-only. | Render | — |
| 5 | **Redeploy Render** to pick up S-01 (`--proxy-headers`). Until then every caller shares one rate-limit bucket per path. | Render | step 19 |
| 6 | **Confirm `celery_worker` and `celery_beat` are actually running** as their own Render services. Five beat schedules are silently dead if not — reminders, broadcast rate limit, idle-session sweep, `expire_pending_signups`. | both | step 20 |
| 7 | **Start sender verification** for whichever provider step 1 picks. DNS + propagation waits on nobody. | both | step 21 |
| 8 | **Sign `docs/pii-at-rest-decision.md`** — encrypt the three plaintext columns or accept in writing. | both | — |
| 9 | **`backend/Dockerfile` hf-cache fix** (W4.2, 2 lines, PR-only file — needs your go-ahead). | both | — |
| 10 | **Decide PR #50** (bulk event builder): rebase and land, or close with a salvage note. Open since 2026-07-24. | both | step 20 scope |
| 11 | **Decide K21**: does a late cancellation / no-show carry any consequence? Left unguessed on purpose. | both | — |

## Block B — finish W5 (0.5 day, all **both**)

Authz sweep is done: 160/160 endpoints, 19 routers, no unguarded staff endpoint. What's left:

| Step | What | Platform |
|---|---|---|
| 12 | ✅ **W5.4** — JWT expiry + magic-link single-use/expiry, both proven by mutation rather than by adding redundant tests. `tests/test_jwt_expiry.py`. | both |
| 13 | ✅ **W5.5 / S-04** — OIDC deleted (handlers, settings, Authlib). The callback created users from any IdP-asserted email. `tests/test_no_sso_surface.py`. | both |
| 14 | ✅ **W5.6** — `docs/broadcast-email-policy-decision.md`, pinned by `tests/test_broadcast_optout_policy.py`. | both |
| 15 | ✅ **W5.7** — both cases run; `indirect_injection` was mis-specified and was rewritten. Structural fix: a category with no runner now fails. | both |
| 16 | ✅ **S-03** — one `STAFF_ROLES` + `require_admin`/`require_staff`, ~120 call sites, guard test `tests/test_staff_guard_canonical.py`. | both |
| 17 | ✅ **Frontend authz review** — negative result: no frontend-only gating anywhere. One real finding (K33's mitigation claim was false). `routeAuthz.test.jsx`, 19 cases. | both |
| 18 | ☐ **Land the W5 remainder PR** — includes the working-tree `test_security_hardening.py` change, CI green, merge. | both |

## Block C — W6 runtime verification, on Render (3–4 days, all **both**)

⛔️ **The stage that finds new things.** Every bug found so far came from reading code. All
1,600+ tests passed while `api.slots` did not exist. Nobody has clicked through this app.
Budget W6 for producing new work, not confirming the list. Checklist: `.planning/W6-CHECKLIST.md`.

| Step | What | Platform |
|---|---|---|
| 19 | **W6.1** — walk all 40+ routes as each role, desktop and a real phone viewport. | both |
| 20 | **W6.2** — walk every flow with real side effects, mail client open: signup → confirm → reminder → manage; orientation block → credit persisting; waitlist → staff promote → confirm; admin create → shifts → roster → export; organizer on a phone. **All of it against the shifts model**, which is newer than the audit. | both |
| 21 | **W6.3** — open every email in a real client (Gmail web, Gmail iOS, Apple Mail, Outlook), not Mailpit's preview. Nine builders, six templates. Email *is* the product for an account-less app. Gated on steps 1 + 7. | both |
| 22 | **W6.4** — adversarial input: double-submit, back button mid-flow, two tabs, expired token, shift filling between render and submit, network drop, clock skew, non-ASCII and very long names, `+`-addressed email. | both |
| 23 | **W6.5** — turn every P0 into a regression test and delete the mocks that hid them (`EventsSection.test.jsx:489` mocks a shape the real module never had — the only reason K1 shipped). | both |
| 24 | **W6.6** — real conditions: a full quarter of data in the unbounded tables (K36); 30 concurrent signups against one event (does `slot.current_count` hold?); Safari date parsing; a real iPhone. | both |
| 25 | **Fix the W6 findings** and land them. Expect this to be the biggest single batch of code in the whole plan. | both |

## Block D — the two remaining re-audits (1 day)

Three audits have run: exhaustive pre-W4, targeted re-audit 1 (PR #73), security re-audit 2 (PRs #74/#75).

| Step | What | Platform |
|---|---|---|
| 26 | **Re-audit 3 — targeted, verifies the W6 fixes.** Not optional and routinely skipped. Step 25's fixes were written under time pressure against a live deploy and have had no review at all. Every prior pass found defects in code believed finished. | both |
| 27 | **Re-audit 4 — exhaustive, pre-handover.** Scope it to the **diff since re-audit 2**, not the whole tree — the tree has been swept, the diff has not. This is the last gate before Rafael. | both |

Standing caveat: audits read code, so they cannot find "confusing", "in the wrong place",
or "renders broken in Outlook". W6 and the re-audits do not substitute for each other.

## Block E — W7 handoff (0.5 day)

Rafael deploys and nothing else. Deployment knowledge only, not a codebase handover.

| Step | What | Platform |
|---|---|---|
| 28 | **Write the runbook platform-neutrally** — consolidate `docs/deployment.md`, don't rewrite. Must state: (a) **memory budget** ~880 MB per worker with both models resident → 2 workers means 4 GB minimum, same arithmetic on ECS; (b) **`--proxy-headers` / `--forwarded-allow-ips` restated for ECS** — the fix currently lives in `start_render.sh`, which Rafael will never run, and an ALB terminates TLS exactly as Render's proxy does, so the shared-bucket defect silently returns without it; (c) **never roll back a deploy that applied a migration** — forward-only migration + code rollback leaves the old image unable to find the revision the DB is stamped with, which can permanently brick the service; disable auto-rollback on any service whose release step migrates; (d) **celery worker + beat as separate services/tasks**. | both |
| 29 | **Env-var reference**, including `ENVIRONMENT` (default now `production`), `COPILOT_AGENT_LOOP_ENABLED` (ships **on**; setting it false is the rollback), `COPILOT_PROFILE_EXTRACTION_ENABLED` (ships off), and `frontend/.env.example`. | both |
| 30 | **Fix K39 — the instruction files teach wrong rules.** `CLAUDE.md:73` still says CSV import is quarterly (that surface is gone); `PRODUCT-BRIEF.md` still calls orientation a soft warning (it is a hard block). Both predate shifts and the agent decision. This makes *your own* future sessions and the copilot wrong, so it is yours regardless of handoff. | both |
| 31 | **Clean-clone dry run yourself** — deploy from the runbook as written, on Render, from a fresh clone with no personal secrets. Finds the missing step before Rafael does. | Render |
| 32 | **Live walkthrough — Rafael deploys to AWS from a clean clone while you watch.** This is the exit criterion, not the document. | AWS |
| 33 | **Post-deploy smoke on AWS** — the ~30-minute three-window pass in `docs/smoke-checklist.md`, plus confirm celery beat fired, one real email arrived, and `/docs` is closed. | AWS |

---

## Timeline

| Block | Days | Platform mix |
|---|---|---|
| A — decisions + Render config | 0.5 | Render config, decisions are both |
| B — finish W5 | 0.5 | all both |
| C — W6 on Render | **3–4** | all both, run on Render |
| D — re-audits 3 and 4 | 1 | all both |
| E — W7 handoff | 0.5 | both, ending on AWS |

**5–7 working days**, of which W6 is the long pole. Start steps 1 and 7 today — DNS waits
on nobody and it is the only thing that can block W6 from the outside.

## Known non-bugs to state in the handover

- **~50 OpenRouter requests/day on an unfunded account.** An agent turn spends several, so
  the copilot cannot be meaningfully load-tested in W6. Funding item, not a code item.
- **Ten deferred K-items** (K6, K15, K34–K38, K40–K42) — UI polish, accessibility, motion,
  mobile. None blocks deploy. All of them stay yours after it.
