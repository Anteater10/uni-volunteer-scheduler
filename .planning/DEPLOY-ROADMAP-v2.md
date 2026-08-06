# Deploy Roadmap v2 — Andy's priority order

**Created:** 2026-07-16
**Supersedes ordering in:** `.planning/HANDOFF-ROADMAP.md` (kept for reference; this file re-sequences it to Andy's stated priorities)
**Goal:** SciTrek fixes → finalize the AI chatbot + copilot feedback → error sweep → production hardening/deploy/audit → hand to Rafael, so the **entire app works completely** at handoff.
**Based on:** full-codebase audit 2026-07-16 (backend, frontend, all `.md` docs, repo-wide error sweep).

## Legend
- 🔴 blocks handoff (deploy-critical)
- 🟡 paper-only / optional (does NOT block handoff)
- 🟢 handoff deliverable
- ✅ already done (verified in audit) — mostly landed via the `release/v1.4-prod` merge

## Critical path (Andy's order)
`A → K → B → C → 37 → 38 → 39 → 40 → 41 → 42`
Paper track (`35-02`, `35-03`, `36`) runs in parallel and does **not** gate deploy or Rafael.

## ⚠️ Read first — audit reconciliation
1. **Much of Phase 37/38 is already done.** The 31 commits merged from `release/v1.4-prod` added cost caps + rate limits (`backend/app/copilot/guardrails.py`), observability/Sentry (`backend/app/observability.py`), `docker-compose.prod.yml`, `Caddyfile`, `backend/.env.production.example`, `scripts/backup_db.sh`, frontend `Dockerfile`/`nginx.conf`, security-hardening tests, and `docs/deployment.md`/`docs/demo-runbook.md`. The `.planning/STATE.md` + `HANDOFF-ROADMAP.md` predate this and are stale.
2. **The chatbot already works in RAG mode.** Plain retrieval-grounded streaming chat (real OpenRouter + hybrid retrieval + rerank + citations) is complete and production-usable once the flag is flipped. The **tool-using agent** (write actions from chat) is NOT wired and crashes if enabled — see Phase B decision.
3. **The copilot feedback system is fully working** — the "stub" docstrings in `router.py` are stale; the SQL is real.

---

## PHASE A — SciTrek-requested fixes 🔴 (Andy-owned)
Andy's own list, tracked in a personal notes app; tackled one-by-one in a separate session.
- Source of truth: Andy's notes (not in repo).
- Domain rules the fixes must not regress (from `PRODUCT-BRIEF.md` + `.planning/notes/2026-04-15-scitrek-orientation-rule.md`): orientation is a **soft warning, not a hard block**; **cross-week/cross-module orientation credit** carries forward within a module family; **account-less** volunteer signup; **quarterly** (every 11 weeks) CSV import — never "yearly".
- Note: CSV "quarterly vs yearly" copy is **already correct** in the wired import UI (`frontend/src/pages/admin/ImportsSection.jsx`); no fix needed there.
- **Exit:** Andy's SciTrek list cleared; no regression in the four domain rules above.

---

## PHASE K — Knowledge base / corpus overhaul 🔴
**Root cause found (2026-07-16):** the copilot gives subpar answers (e.g. "what is an event") because the corpus is built from **the codebase itself**, not a curated knowledge base. `backend/app/corpus/walker.py:37` (`SOURCE_GLOBS_V1`) ingests Python/JS docstrings, alembic migration docstrings, `.planning/phases/**/*.md` planning docs, `docs/learning/` + `docs/copilot-journal/` dev notes, `ROADMAP.md`, `README.md`, `CLAUDE.md`. These are engineering + project-management artifacts, wrong-audience for admin/organizer domain questions. Retrieval + rerank are fine; the *content* is the problem (garbage/wrong-audience in → wrong out).

### K1 — Author a curated knowledge base
- Write authoritative, user-facing docs (new dir, e.g. `docs/knowledge-base/`) that define the SciTrek domain the way an admin/organizer asks about it: **event, module, module family, orientation credit (soft-warning + cross-week carry-forward), signup, waitlist + auto-promote, roles (participant/organizer/admin), quarter/week model + quarterly CSV import, check-in, broadcasts, reminders**. One concept per doc, plain language, grounded in the real product behavior (cross-check against `PRODUCT-BRIEF.md` + the domain rules).
- Include the FAQ an admin/organizer would actually ask (the questions Andy has been testing with).

### K2 — Narrow the ingestion sources
- Revise `SOURCE_GLOBS_V1` (`walker.py:37`) to make the curated KB the primary/authoritative source and **stop ingesting noise**: drop `.planning/phases/**`, `docs/copilot-journal/**`, `.planning/ROADMAP.md`, and reconsider ingesting raw function/module docstrings + frontend comments as "knowledge." Keep genuinely useful reference docs.
- Decide source-precedence / weighting so KB docs win over incidental matches.

### K3 — Re-ingest and evaluate
- Rebuild the corpus (`python -m app.corpus.ingest --rebuild`) against the new sources; verify doc/chunk counts and that KB docs are chunked well.
- Re-ask the test questions ("what is an event", orientation credit, waitlist, etc.); confirm answers are now correct and cite KB docs. This doubles as the retrieval-quality signal the grounded-eval (35-03) needs.
- **Exit:** the copilot answers core domain questions correctly, citing curated KB documents; the corpus no longer surfaces planning/dev-journal noise as authoritative knowledge.

---

## PHASE B — Finalize AI chatbot + copilot feedback 🔴
The feedback system is done; the chatbot needs a scope decision, then small polish.

### B0 — DECISION (LOCKED 2026-07-16): full tool-using agent
Andy wants a chatbot that can **do things**, not just answer questions. This is the paper's headline contribution (Phase 33 tool-calling). The four missing pieces below must be built; RAG Q&A alone is not the target.

**B0.1 — Structured-tool LLM adapter.** `backend/app/copilot/router.py:582` `_get_agent_llm()` currently `raise NotImplementedError`; only tests monkeypatch it. Build a real adapter that drives OpenRouter tool/function-calling so `run_turn` can select tools in prod. Without this, flipping `COPILOT_AGENT_LOOP_ENABLED=True` crashes every turn.

**B0.2 — Wire the write tools to Celery.** `backend/app/copilot/agent/tools/send_reminder_email.py:32` and `nudge_understaffed_module.py:33` have `_dispatch()` stubs that `return True` and send nothing while reporting success counts. Connect to the real Celery tasks (`app.celery_app.send_email_notification` / `app.tasks.reminders`).

**B0.3 — Durable confirmation store.** `backend/app/copilot/agent/confirmation.py:26` `_PENDING` is an in-memory dict (5-min TTL, process-local). Move to Redis/DB so Approve survives multi-worker + restarts (else `ConfirmationNotFound` → 404).

**B0.4 — Tool-use evaluation (paper).** Unblocked by B0.1: run the agent-loop eval (`--use-agent-loop` currently emits `hard_failure`) to measure tool-selection correctness. This is the deferred "Phase 35-04."

> Scope note: B0.1–B0.3 are the deploy-critical hard part of Phase 37, pulled forward into Phase B by this decision. Phase 37 below now only carries the non-agent hardening items.

### B1 — Chatbot polish (both options)
- Fix stale banner: `frontend/src/copilot/CopilotDrawer.jsx:191` still says **"Beta — no live data access yet."** — inaccurate now (live citations stream). Update copy.
- Gate the memory panel: `CopilotMemorySettings` renders on `ProfilePage.jsx:38` **unconditionally** — not behind `VITE_COPILOT_ENABLED` like the FAB/nav. Gate it so it disappears when the copilot is off.
- `frontend/.env` ships `VITE_COPILOT_ENABLED=true` + `VITE_API_URL=http://localhost:8000`; these are inlined at **build time** — set correctly for prod builds (also tracked in Phase 38).

### B2 — Feedback system (verify only — already working)
- Confirm the four endpoints + UI work end-to-end (`MessageRatingButtons`, `SessionRatingModal`, `AdminCopilotFeedbackPage`, weekly rollup, bottom-messages drill-down).
- Cleanup: remove stale "stub"/"real SQL lands later" docstrings at `backend/app/copilot/router.py:934,956` (misleading; impl is real).
- **Exit:** chatbot behaves per the B0 decision with no stale/beta copy; feedback verified end-to-end.

---

## PHASE C — Error / bug sweep 🔴
Fix the concrete red baselines the audit confirmed. "The whole app works" starts here.
- **2 failing backend tests** (documented red since Phase 21): `backend/tests/test_import_pipeline.py::test_commit_rejects_unresolved_low_confidence` and `::test_commit_rollback_on_integrity_error`. Will fail CI's full `pytest`. Triage + fix.
- **Frontend failing test:** `frontend/src/pages/admin/__tests__/AdminLayout.test.jsx:49` — env-coupled ("hides Copilot feedback nav when flag off" but committed `.env` has flag on). Stub the env in the test.
- **6 failing frontend vitest** documented in Phase 23 SUMMARY (AdminTopBar / AdminLayout / ExportsSection / ImportsSection) — confirm current status; fix or confirm already-fixed.
- **Skipped/no-op tests to re-enable or consciously accept:** `frontend/tests/playwright/v1.3-integration.spec.js:55` (whole describe skipped); public-signup e2e assertions that no-op without `EXPOSE_TOKENS_FOR_TESTING`; `test_public_signups.py` 8 tests that silently skip on "Token capture failed".
- **Missing dev `.env.example`** (backend + frontend) — only a prod example exists; blocks clean-clone runs. (Overlaps Phase 38.)
- Cosmetic (non-blocking, large volume): ~46 `TODO(copy)`/`TODO(brand)` placeholders across admin/participant pages + email templates. Decide finalize-now vs accept-for-launch.
- **Exit:** full backend + frontend suite green on a fresh checkout; no silently-skipped critical assertions.

---

## PHASE 37 — Production hardening 🔴 (mostly done — remainder only)
- ✅ **Cost caps** (80% warn / 100% hard-stop) — implemented in `guardrails.py` (`enforce_daily_token_budget`), wired at `router.py:500`.
- ✅ **Rate limits** — `enforce_message_rate_limit` (Redis, 10/min) wired for `POST …/messages`.
- ✅ **Structured logging + Sentry** — `observability.py` (Sentry off until `SENTRY_DSN` set).
- ➡️ **Wire the write tools** — MOVED to Phase B0.2 (agent ships in Phase B).
- ➡️ **DB/Redis-backed pending-confirmation store** — MOVED to Phase B0.3.
- 🔴 **Encrypt PII at rest** — `copilot_user_profiles.profile_text` and feedback `comment` are plaintext `Text`; only defense today is persist-time redaction. Add encryption or explicitly accept the risk.
- 🔴 **CrossEncoder warm hook** — `rerank.py` lazy-loads a ~278MB model on first request per worker; no startup warm-up in `main.py`. Add a lifespan prewarm and/or bake weights into the image.
- 🟡 **Rate-limit the `/confirm` + rating + profile endpoints** (only `messages` is limited today).
- **Exit:** copilot is cost-bounded, rate-limited, multi-worker-safe, PII handled per decision; write tools fire (if in scope).

---

## PHASE 38 — Production deploy readiness (AWS) 🔴 (partially done)
- ✅ `docker-compose.prod.yml`, `Caddyfile`, frontend `Dockerfile` + `nginx.conf`, `scripts/backup_db.sh`, `backend/.env.production.example`, `docs/deployment.md`, `docs/demo-runbook.md` all exist now.
- 🔴 **Rotate secrets** before any public deploy: `OPENROUTER_API_KEY`, `JINA_API_KEY`, `SENDGRID_API_KEY`, `JWT_SECRET` (personal keys in local `backend/.env`, gitignored/not committed).
- 🔴 **Create dev `.env.example`** (backend + frontend) — only the prod template exists.
- 🔴 **Disable** `EXPOSE_TOKENS_FOR_TESTING` in prod (already refuses to boot if set with `ENVIRONMENT=production` — good); replace `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`.
- 🔴 **Flip prod flags:** `COPILOT_ENABLED`, `VITE_COPILOT_ENABLED` (build-time), and `COPILOT_AGENT_LOOP_ENABLED` **only if** Phase B chose Option 2.
- 🔴 **Infra mapping:** Postgres → RDS **with `vector` extension** (migration 0019 needs pgvector); Redis → ElastiCache; point `DATABASE_URL`/`REDIS_URL`/`VITE_API_URL`/`FRONTEND_BASE_URL` at real hosts.
- 🔴 **Image:** keep torch CPU-pinned; bake/pre-cache BGE + CrossEncoder weights (~240MB) so first request doesn't download.
- 🔴 **Runtime topology:** backend + celery_worker + celery_beat + redis all load-bearing (reminders, broadcast rate-limit, idle-session sweep).
- 🔴 **Email:** verified SendGrid sender (dev uses Mailpit).
- 🔴 **Migrations:** 0002→0023 apply on deploy; note latent `downgrade()` `DuplicateObject` bug (fresh upgrades fine, rollbacks not).
- **Exit:** documented, reproducible deploy; no personal secrets; flags correct.

---

## PHASE 39 — Security review (entire app, v1.0–v1.4) 🔴
- Auth surface: JWT issuance/expiry, magic-link generation + single-use + expiry.
- Public endpoints: public signup, `manage-my-signup`, and the **no-auth `POST /events/{id}/check-in-by-email`**.
- PII end-to-end: volunteer name/email/phone storage, exports, audit logs.
- Email/broadcast: broadcasts currently **bypass the unsubscribe link** (CAN-SPAM risk at scale).
- Secrets posture: confirm no secrets in repo; rotation done; `EXPOSE_TOKENS_FOR_TESTING` off in prod.
- Copilot PII boundary: assert the 2 inert adversarial cases (`token_budget_exhaustion`, `indirect_injection`); confirm tool-boundary redaction holds; note plaintext-at-rest decision from Phase 37.
- Tooling: `security-review` / `gsd-secure-phase`.
- **Exit:** findings report with severities; all high/critical remediated or explicitly accepted.

---

## PHASE 40 — Test & e2e sweep (entire app) 🔴
- Full backend + frontend suite green on a **fresh checkout**; restore/verify 95% per-package coverage gates.
- Resolve the **Playwright contradiction** (Phase 20 ran a 6-project suite at `e2e/`; Phase 29 says Playwright isn't configured) — establish one true e2e state.
- **Run the never-executed v1.3 e2e** for features 21–29.
- Stand up a **copilot smoke checklist** (current `docs/smoke-checklist.md` predates v1.4).
- **Jina embedding path never run end-to-end** — test it or document "local-BGE only" as supported.
- (Phase C already fixes the failing unit tests; this is the holistic e2e/prod verification.)
- **Exit:** green reproducible run + documented smoke passes.

---

## PHASE 41 — Milestone audit sweep (v1.0–v1.4) 🔴
- Run the never-completed **v1.2 INTEG-04 manual smoke sign-off**.
- Run the **v1.3 milestone audit** (Phase 29 INTEG-05, never run).
- Run a **v1.4 milestone audit**.
- Note traceability caveats: Phase 28 & 33 PLANs written retroactively.
- Tooling: `gsd-audit-milestone`, `gsd-audit-uat`.
- **Exit:** one consolidated production sign-off doc covering all milestones.

---

## PHASE 42 — Hand over to Rafael 🟢
- **Runbook:** deploy steps, run migrations, rotate secrets, start the 4 services, flip flags (much now in `docs/deployment.md` — consolidate).
- **Env-var reference** + the dev `.env.example` from Phase 38.
- **Known-issues list:** latent Alembic downgrade bug, CrossEncoder cold start, local-BGE-only corpus, SMS/Phase 27 deferred, `31-.../salvage/` disposition, any accepted security findings.
- **Live walkthrough** with Rafael; confirm he can deploy from a clean clone.
- **Exit:** Rafael deploys successfully and owns the runbook.

---

## PAPER TRACK (parallel, non-blocking) 🟡
- **35-02** multi-model eval: harness code-complete; raw safety baseline done (2026-05-24/25); fill `baseline-phase-33.json` + the `35-eval-results.md` comparison table.
- **35-03** grounded eval: run genuinely started (~23% — 30 ok / 98 rate-limited across 8 models), needs multi-day resume passes; commit or park the untracked `backend/eval-results/grounded-run/`. **This is the branch currently checked out.**
- **36** DSPy experiment: optional; recommend deferring past handoff.
- **Housekeeping:** `.planning/phases/31-.../salvage/` holds 3 undocumented Python artifacts — decide disposition; commit or delete the loose eval output.

---

## Summary table

| Phase | Title | Type | Blocks handoff | State |
|---|---|---|---|---|
| A | SciTrek-requested fixes | Product | **Yes** | Andy-owned (notes) |
| K | Knowledge base / corpus overhaul | Product | **Yes** | Corpus = codebase, not a KB — root cause of bad answers |
| B | Finalize chatbot + feedback (**full tool-using agent**) | Product | **Yes** | Feedback done; agent = build B0.1–B0.4 |
| C | Error / bug sweep | Quality | **Yes** | 2 backend + ≥1 frontend tests red |
| 37 | Production hardening | Deploy | **Yes** | Caps/limits/logging ✅; PII+warm+pending remain |
| 38 | Deploy readiness (AWS) | Deploy | **Yes** | Compose/Caddy/docs ✅; secrets+flags+infra remain |
| 39 | Security review (whole app) | Gate | **Yes** | Not started |
| 40 | Test & e2e sweep (whole app) | Gate | **Yes** | Not started |
| 41 | Milestone audit (v1.0–v1.4) | Gate | **Yes** | Not started |
| 42 | Hand to Rafael | Handoff | — | Not started |
| 35-02/03, 36 | Paper track | Paper | No | In progress / optional |
