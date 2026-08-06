# Handoff Roadmap — v1.4 finish → Hand over to Rafael

**Created:** 2026-05-28
**Goal:** Finish the v1.4 paper work, harden the app for production, verify the **entire** codebase (v1.0–v1.4), and hand a deployable system to Rafael (AWS deploy owner).
**Scope note:** Rafael deploys the whole app, not just the copilot. Security/testing/audit phases below cover **all milestones (v1.0–v1.4)**, not v1.4 alone — the largest PII/auth/public-endpoint surface lives in v1.0–v1.3.

**Source of truth for prior state:** `.planning/ROADMAP.md`, `.planning/STATE.md`. This file is the forward plan to handoff; it does not replace the GSD roadmap.

## Legend
- 🔴 blocks handoff (deploy-critical)
- 🟡 paper-only / optional (does NOT block handoff)
- 🟢 handoff deliverable

## Critical path to handoff
`37 → 38 → 39 → 40 → 41 → 42`
Paper track (`35-02, 35-03, 36`) runs in parallel and does **not** gate Rafael.

---

## PAPER TRACK (parallel, non-blocking)

### Phase 35-02 — Run the multi-model eval harness 🟡
Harness is code-complete but **never run against the network**.
- Run `python -m app.eval.run` against OpenRouter (env + command in `.planning/phases/35-02-multimodel-eval/HANDOFF.md`)
- Fill `backend/eval-results/baseline-phase-33.json` (currently a placeholder)
- Generate the real `docs/documentation/35-eval-results.md` 5–8 model comparison table (a v1.4 success criterion — currently unfilled)
- Restore the `app.eval` coverage gate 90% → 95% (`TODO(35-02-G+)`)
- **Exit:** real results table published; harness reproducible.

### Phase 35-03 — Grounded retrieval eval 🟡
Uncommitted work exists (`feature/v1.4-phase-35-03-grounded-eval` branch + untracked `backend/eval-results/grounded-run/`, `.planning/phases/31-.../salvage/`). No phase directory yet.
- Decide: finish or shelve. Commit/stash the loose work either way.
- Fill real RAGAS rerank-lift numbers — Phase 32 `rerank-lift.{csv,png}` are still zeros / 1×1 placeholders.
- **Exit:** branch committed/merged or explicitly parked; no orphan untracked eval output.

### Phase 36 — DSPy / prompt-program experiment 🟡
Roadmap marks this "optional, paper-strengthening." **Recommend deferring until after handoff** unless the paper needs it.

---

## DEPLOY-CRITICAL PATH

### Phase 37 — Production hardening 🔴
All items below were explicitly deferred *to Phase 37* across phases 32/33/34.
- **Cost caps** — per-session warning at 80%, hard-stop at 100% (soft requirement, unmet)
- **Rate limits** — per-session + per-org on copilot endpoints; also the feedback/rating endpoints
- **Wire the write tools** — `send_reminder_email` / `nudge_understaffed_module` currently hit a stub `_dispatch` that returns the planned action but sends nothing. Connect to real Celery tasks.
- **DB-backed pending-confirmation store** — `_PENDING` is in-memory; breaks on a multi-worker deploy (lost confirmations)
- **Encrypt PII at rest** — `profile_text` and feedback `comment` stored plaintext
- **CrossEncoder warm hook** — ~200s cold start on first request looks like a hang in prod
- **Structured-log retention policy**
- **Exit:** copilot is cost-bounded, rate-limited, multi-worker-safe; write tools actually fire.

### Phase 38 — Production deploy readiness (AWS) 🔴
Project was scoped for **UCSB infra, not AWS** — no IaC, no `.env.example`, no production compose exists today. Greenfield infra work.
- **Rotate secrets** before any public deploy: `OPENROUTER_API_KEY`, `JINA_API_KEY`, `SENDGRID_API_KEY`, `JWT_SECRET` (personal keys currently in local `backend/.env` — gitignored, not committed)
- **Create `.env.example`** documenting every var (none exists)
- **Disable** `EXPOSE_TOKENS_FOR_TESTING`; replace `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` test creds
- **Flip flags on for prod:** `COPILOT_ENABLED`, `VITE_COPILOT_ENABLED`, `COPILOT_AGENT_LOOP_ENABLED`
- **Infra mapping:** Postgres → RDS *with the `vector` extension available*; Redis → ElastiCache; point `DATABASE_URL` / `REDIS_URL` / `VITE_API_URL` / `FRONTEND_BASE_URL` at real hosts
- **Image:** rebuild backend (Phase 26 added `Markdown` + `beautifulsoup4`); keep torch CPU-pinned (`--extra-index-url .../whl/cpu`) or image balloons ~2GB; bake/pre-cache BGE + CrossEncoder weights (~240MB) so first request doesn't download
- **Runtime topology:** backend + **celery_worker + celery_beat + redis** all load-bearing (reminders, broadcast rate limit, idle-session sweep)
- **Email:** verified SendGrid sender (dev uses Mailpit)
- **Migrations:** 0014→0023 must apply on deploy; note known latent `downgrade()` `DuplicateObject` bug (fresh upgrades fine, rollbacks not)
- **Exit:** documented, reproducible deploy; no personal secrets; flags correct.

---

## WHOLE-APP READINESS GATE (v1.0–v1.4)
Scope = entire codebase. Listed-and-scoped only; execute when triggered.

### Phase 39 — Security review (entire app) 🔴
Covers all milestones, not v1.4 alone.
- **Auth surface:** JWT issuance/expiry, magic-link token generation + single-use + expiry
- **Public endpoints:** public signup, `manage-my-signup`, and the **no-auth `POST /events/{id}/check-in-by-email`** (flagged "worth a security review before public deploy")
- **PII handling end-to-end:** volunteer name/email/phone storage, exports, audit logs
- **Email/broadcast:** broadcasts currently **bypass the unsubscribe link** (possible CAN-SPAM issue at scale)
- **Secrets posture:** confirm no secrets in repo; rotation done; `EXPOSE_TOKENS_FOR_TESTING` off in prod
- **v1.4 copilot PII boundary:** assert the 2 currently-inert adversarial cases (`token_budget_exhaustion`, `indirect_injection`); confirm tool-boundary redaction holds
- **Tooling:** `security-review` / `gsd-secure-phase`
- **Exit:** findings report with severities; all high/critical remediated or explicitly accepted.

### Phase 40 — Test & e2e sweep (entire app) 🔴
Tests exist (~799 backend passing); this is holistic prod verification, not from-scratch.
- Fix the **2 failing `test_import_pipeline.py` tests** (documented baseline, never fixed)
- Full backend + frontend suite green on a **fresh checkout**; restore 95% coverage gate
- Resolve the **Playwright contradiction** (Phase 20 ran a 6-project suite at `e2e/`; Phase 29 says Playwright isn't configured) — establish one true e2e state
- **Run the never-executed v1.3 e2e** for features 21–29
- Stand up a **copilot smoke checklist** (current `smoke-checklist.md` predates v1.4)
- **Jina embedding path never run end-to-end** — test it or document "local-BGE only" as the supported config
- **Exit:** green reproducible run + documented smoke passes.

### Phase 41 — Milestone audit sweep (v1.0–v1.4) 🔴
- Run the never-completed **v1.2 INTEG-04 manual smoke sign-off** ("no sign-off recorded")
- Run the **v1.3 milestone audit** ("deferred to user", Phase 29 INTEG-05 — never run)
- Run a **v1.4 milestone audit**
- Note traceability caveats: Phase 28 & 33 PLANs written retroactively
- **Tooling:** `gsd-audit-milestone`, `gsd-audit-uat`
- **Exit:** one consolidated production sign-off doc covering all milestones.

---

### Phase 42 — Hand over to Rafael 🟢
- **Runbook:** deploy steps, run migrations, rotate secrets, start the 4 services (backend, worker, beat, redis), flip flags
- **Env-var reference** (lean on `architecture-site`) + the `.env.example` from Phase 38
- **Known-issues list:** latent Alembic downgrade bug, CrossEncoder cold start, local-BGE-only corpus, SMS/Phase 27 deferred, any accepted security findings
- **Live walkthrough** with Rafael; confirm he can deploy from a clean clone
- **Exit:** Rafael deploys successfully and owns the runbook.

---

## Summary table

| Phase | Title | Type | Blocks handoff |
|---|---|---|---|
| 35-02 | Run multi-model eval harness | Paper | No |
| 35-03 | Grounded retrieval eval | Paper | No |
| 36 | DSPy experiment | Paper/optional | No |
| 37 | Production hardening | Deploy | **Yes** |
| 38 | Production deploy readiness (AWS) | Deploy | **Yes** |
| 39 | Security review (entire app) | Gate | **Yes** |
| 40 | Test & e2e sweep (entire app) | Gate | **Yes** |
| 41 | Milestone audit sweep (v1.0–v1.4) | Gate | **Yes** |
| 42 | Hand over to Rafael | Handoff | — |
