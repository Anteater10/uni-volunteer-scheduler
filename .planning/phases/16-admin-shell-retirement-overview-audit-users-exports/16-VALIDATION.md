---
phase: 16
slug: admin-shell-retirement-overview-audit-users-exports
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest (backend/tests) |
| **Frontend framework** | vitest + Playwright + @axe-core/playwright |
| **Backend quick run** | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q <path>"` |
| **Backend full suite** | same command with `pytest -q` (no path) |
| **Frontend quick run** | `cd frontend && npm run test -- --run <file>` |
| **Frontend full suite** | `cd frontend && npm run test -- --run` |
| **E2E command** | `cd frontend && npx playwright test` |
| **Estimated full-suite runtime** | ~180 seconds |

Postgres and Redis are only reachable from inside `uni-volunteer-scheduler_default` docker network — always wrap backend tests in the docker-run invocation above.

---

## Sampling Rate

- **After every task commit:** Run backend quick run OR frontend quick run (targeted at the file changed)
- **After every plan wave:** Run full backend suite + full frontend unit suite
- **Before `/gsd-verify-work`:** Full backend + frontend + Playwright E2E all green, including new admin a11y specs
- **Max feedback latency:** 30 seconds for targeted tests; 180 seconds for full suite

---

## Per-Task Verification Map

> This map is filled in by the planner when PLAN.md files are authored. Each task in every PLAN.md must reference back to one row here.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | — | — | — | — | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Planner fills in during PLAN authoring. Candidates from RESEARCH.md:

- [ ] Alembic migration `0011_users_is_active_last_login.py` — adds `users.is_active` BOOLEAN NOT NULL DEFAULT true, `users.last_login_at` TIMESTAMPTZ NULL, makes `users.hashed_password` NULLABLE (for invite-only flows)
- [ ] Alembic migration `0012_soft_delete_seed_templates.py` — soft-delete 5 seed module templates
- [ ] Data backfill migration — `UPDATE audit_logs SET action='signup_cancelled' WHERE action='signup_cancel'` (D-20 normalization)
- [ ] `backend/tests/routers/test_admin_analytics_csv.py` — stubs for new `attendance-rates.csv` + `no-show-rates.csv` endpoints
- [ ] `backend/tests/routers/test_users_invite_deactivate.py` — stubs for invite + deactivate + reactivate endpoints + last-admin + self-demote safety rails
- [ ] `frontend/e2e/admin-a11y.spec.ts` — bootstrap @axe-core/playwright against every in-scope admin route (first admin a11y coverage)

*If none apply to a particular plan: "Existing infrastructure covers all tasks in this plan."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 375px mobile audit on every admin route | ADMIN-27 | Visual/responsive check beyond automated a11y scan | Open each admin route at 375px width; verify either graceful layout OR explicit `DesktopOnlyBanner` |
| WCAG AA color-contrast spot check | ADMIN-26 | axe catches most but not all contrast cases in dynamic states | For each admin page, tab through in keyboard-only mode; verify focus ring visible on every interactive element |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags in automated commands
- [ ] Feedback latency < 30s per-task / < 180s full
- [ ] `nyquist_compliant: true` set in frontmatter once planner fills the per-task map

**Approval:** pending
