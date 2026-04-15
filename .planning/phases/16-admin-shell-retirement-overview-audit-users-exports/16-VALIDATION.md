---
phase: 16
slug: admin-shell-retirement-overview-audit-users-exports
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-15
updated: 2026-04-15
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
- **Exception:** Plan 07 Task 2 (`admin-a11y.spec.js`) is a long-run phase-closing Playwright a11y gate and may take 60–180s. It is run at the END of Phase 16, not after each task commit, and is therefore exempt from the 30s per-task feedback-latency target.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 16-01-T1 | 01 | 0 | ADMIN-01 (foundation) | — | Alembic 0011 round-trip | pytest integration | `docker run ... pytest -q tests/test_smoke.py` (after alembic upgrade/downgrade/upgrade) | ⬜ | ⬜ pending |
| 16-01-T2 | 01 | 0 | ADMIN-01 | — | Audit kind data consistency | pytest integration | `docker run ... pytest -q tests/test_audit_log_normalization.py tests/test_seed_templates_retired.py` | ⬜ | ⬜ pending |
| 16-01-T3 | 01 | 0 | ADMIN-01 | CSV injection (defer to T2 of Plan 02) | Humanization XSS — React auto-escapes | pytest + bash gate | `bash scripts/verify-overrides-retired.sh && docker run ... pytest -q tests/test_audit_log_humanize.py && npm run test -- --run api.test.js` | ⬜ | ⬜ pending |
| 16-02-T1 | 02 | 1 | ADMIN-18, 19, 20, 21 | Last-admin lockout, self-demote, email enum | SELECT FOR UPDATE + last-admin guard | pytest integration | `docker run ... pytest -q tests/test_users_invite.py tests/test_users_deactivate.py` | ⬜ | ⬜ pending |
| 16-02-T2 | 02 | 1 | ADMIN-04, 05, 06, 07, 22, 23 | CSV injection | CSV cell sanitization on new .csv endpoints | pytest integration | `docker run ... pytest -q tests/test_admin_summary_expanded.py tests/test_admin_analytics_csv.py tests/test_admin_audit_logs_humanized.py` | ⬜ | ⬜ pending |
| 16-03-T1 | 03 | 1 | ADMIN-03, 25, 26 | — | Focus management in SideDrawer | vitest component | `cd frontend && npm run test -- --run src/components/admin/__tests__/` | ⬜ | ⬜ pending |
| 16-03-T2 | 03 | 1 | ADMIN-03, 26 | — | Below 768px renders banner (no broken reflow) | vitest component | `cd frontend && npm run test -- --run src/pages/admin/__tests__/AdminLayout.test.jsx` | ⬜ | ⬜ pending |
| 16-03-T3 | 03 | 1 | ADMIN-01 (guard), ADMIN-19, 21, 23 | PR-only file coordination (COLLABORATION.md) | api.admin.overrides stays undefined | vitest | `cd frontend && npm run test -- --run src/lib/__tests__/api.test.js` | ✅ (api.test.js exists) | ⬜ pending |
| 16-04-T1 | 04 | 2 | ADMIN-04, 05 | — | No UUIDs in rendered UI (regression gate) | vitest component | `cd frontend && npm run test -- --run src/pages/admin/__tests__/OverviewSection.test.jsx` | ⬜ | ⬜ pending |
| 16-04-T2 | 04 | 2 | ADMIN-06, 07 | — | Deep-linkable filters, Escape closes drawer | vitest component | `cd frontend && npm run test -- --run src/pages/__tests__/AuditLogsPage.test.jsx` | ⬜ | ⬜ pending |
| 16-05-T1 | 05 | 2 | ADMIN-18, 19, 20, 21, 24 | Self-demote, last-admin demote, email enum | Shared-err bug regression gate | vitest component | `cd frontend && npm run test -- --run src/pages/__tests__/UsersAdminPage.test.jsx` | ⬜ | ⬜ pending |
| 16-06-T1 | 06 | 2 | ADMIN-22, 23 | CSV injection (backend-side) | Download buttons for all 3 panels wired | vitest component | `cd frontend && npm run test -- --run src/pages/admin/__tests__/ExportsSection.test.jsx` | ⬜ | ⬜ pending |
| 16-06-T2 | 06 | 2 | ADMIN-27 | — | Loading/empty/error present on every touched page | grep + existing tests | `grep -n "TODO\|md:hidden" frontend/src/pages/admin/ImportsSection.jsx frontend/src/pages/AdminEventPage.jsx frontend/src/pages/PortalsAdminPage.jsx \|\| echo CLEAN` | ⬜ | ⬜ pending |
| 16-07-T1 | 07 | 3 | ADMIN-02 | — | Audit doc exists with all routes | file + grep | `test -f docs/ADMIN-AUDIT.md && grep -c '/admin/' docs/ADMIN-AUDIT.md` | ⬜ | ⬜ pending |
| 16-07-T2 | 07 | 3 | ADMIN-25, 26 | XSS via humanized labels | @axe-core/playwright on every admin route | playwright e2e | `cd frontend && npx playwright test e2e/admin-a11y.spec.js` | ⬜ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Sampling continuity: every task above has an automated command. No 3 consecutive tasks lack automated verify.

---

## Wave 0 Requirements

All satisfied by Plan 01:

- [x] Alembic migration `0011_add_is_active_and_last_login_to_users.py` — adds `users.is_active`, `users.last_login_at`, `hashed_password` nullable (Plan 01 Task 1)
- [x] Alembic migration `0012_soft_delete_seed_module_templates_and_normalize_audit_kinds.py` — soft-delete 5 seed rows + `signup_cancel → signup_cancelled` data backfill (Plan 01 Task 2)
- [x] Backend humanization service `app/services/audit_log_humanize.py` + ACTION_LABELS dict (Plan 01 Task 3)
- [x] Overrides retirement gate script `scripts/verify-overrides-retired.sh` (Plan 01 Task 3)
- [x] Backend test stubs: `test_audit_log_normalization.py`, `test_seed_templates_retired.py`, `test_audit_log_humanize.py` (Plan 01)
- [x] Additional backend test stubs: `test_users_invite.py`, `test_users_deactivate.py`, `test_admin_summary_expanded.py`, `test_admin_analytics_csv.py`, `test_admin_audit_logs_humanized.py` (Plan 02)
- [x] Frontend component test stubs: `AdminLayout.test.jsx`, `DesktopOnlyBanner.test.jsx`, `AdminTopBar.test.jsx`, `SideDrawer.test.jsx`, `DatePresetPicker.test.jsx`, `Pagination.test.jsx` (Plan 03)
- [x] Frontend page test stubs: `OverviewSection.test.jsx` (Plan 04), `AuditLogsPage.test.jsx` (Plan 04), `UsersAdminPage.test.jsx` (Plan 05), `ExportsSection.test.jsx` (Plan 06)
- [x] Playwright a11y spec `frontend/e2e/admin-a11y.spec.js` (Plan 07) — first admin a11y coverage

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 375px mobile audit on every admin route | ADMIN-27 | Visual check beyond axe — confirm DesktopOnlyBanner renders cleanly at 375px | Open each admin route at 375px width; verify the banner appears and no layout glitch |
| WCAG AA color-contrast spot check | ADMIN-26 | axe catches most but not all contrast cases in dynamic states | For each admin page, tab through in keyboard-only mode; verify focus ring visible on every interactive element |
| Magic-link invite email end-to-end | ADMIN-19 | Requires real email delivery (or Mailhog) | Invite a user via /admin/users, check logs or Mailhog for the magic-link message, click the link, verify first-login succeeds |
| CCPA Export + Delete modal copy | ADMIN-24 | Human readability check | Open each modal in the Users page, read the copy out loud, confirm it's plain English and not jargon |

---

## Threat Model (STRIDE — security_enforcement enabled)

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-01 | Elevation of Privilege | PATCH /users/{id} role change | mitigate | Plan 02 Task 1: block self-demote via `actor.id == user_id` check; block last-admin demote via SELECT FOR UPDATE count |
| T-16-02 | Denial of Service | POST /users/{id}/deactivate (last-admin race) | mitigate | Plan 02 Task 1: `_count_active_admins_locked` uses SELECT FOR UPDATE inside the same txn |
| T-16-03 | Information Disclosure | POST /users/invite (email enumeration) | accept | Endpoint is admin-only (require_role); enumeration requires prior auth; low risk for internal admin tool |
| T-16-04 | Tampering | audit_logs append-only | mitigate | No UPDATE/DELETE endpoints on audit_logs; 0012 one-shot data backfill is explicit admin migration |
| T-16-05 | Tampering (downstream Excel) | /admin/analytics/*.csv endpoints | mitigate | Plan 02 Task 2: `_safe()` helper prefixes cells starting with `=+-@` with `'` — apply on new attendance-rates.csv + no-show-rates.csv |
| T-16-06 | Spoofing | Magic-link invite token replay | mitigate | Plan 02 Task 1: reuses existing single-use token invariant from `backend/app/routers/magic.py`; Phase 2 hardening stands |
| T-16-07 | Tampering (XSS) | Humanized audit labels | mitigate | Plan 01 Task 3: humanize service returns plain strings; React auto-escapes at render; NEVER use dangerouslySetInnerHTML |
| T-16-08 | Supply chain | PR-only file stale merge | mitigate | Plan 03 Task 3: batch all api.js changes into one PR per COLLABORATION.md; pull + rebase before landing |
| T-16-09 | Input Validation | POST /users/invite body | mitigate | Plan 02 Task 1: Pydantic schema with `EmailStr`, `Literal["admin","organizer"]`, `min_length=1, max_length=200` on name |
| T-16-10 | DoS | Audit log filter free-text search | accept | Backend ILIKE is indexed on audit_logs columns (existing); no rate limit needed for admin-only endpoint |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags in automated commands
- [x] Feedback latency < 30s per-task / < 180s full
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-approved 2026-04-15. Execution pending.
</content>
</invoke>
