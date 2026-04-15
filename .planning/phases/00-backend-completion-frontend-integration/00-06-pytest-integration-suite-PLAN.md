---
phase: 00-backend-completion-frontend-integration
plan: 06
type: execute
wave: 4
depends_on: [01, 02, 03, 04, 05]
files_modified:
  - backend/tests/test_auth.py
  - backend/tests/test_signups.py
  - backend/tests/test_admin.py
  - backend/tests/test_celery_reminders.py
  - backend/tests/test_contract.py
  - backend/tests/test_update_me_privilege.py
  - backend/pytest.ini
autonomous: true
requirements:
  - TEST-01
  - TEST-02
  - AUDIT-02
  - E2E-03
  - AUTH-01
  - AUTH-02
  - CELERY-02
  - CELERY-04
  - REFACTOR-01
must_haves:
  truths:
    - "pytest exits 0 with ≥ 25 integration tests passing"
    - "Coverage report shows ≥ 70% line coverage on backend/app/ and ≥ 90% on signups.py + signup_service.py + celery_app.py"
    - "Running schedule_reminders twice in a test produces exactly one Notification row per signup"
    - "update_me privilege test asserts is_admin cannot be elevated via PATCH /users/me"
    - "Cancel flow test asserts freed slot capacity is reusable by a second user"
    - "Contract test asserts POST /signups/ trailing slash returns 2xx (not 307)"
  artifacts:
    - path: "backend/tests/test_auth.py"
      provides: "Login, register, refresh rotation, SHA-256 hash verification"
    - path: "backend/tests/test_signups.py"
      provides: "Concurrency, waitlist FIFO, cancel + reusable capacity"
    - path: "backend/tests/test_celery_reminders.py"
      provides: "Idempotency: run twice → one email"
    - path: "backend/tests/test_contract.py"
      provides: "api.js path/method assertions for all 4 fixed mismatches"
    - path: "backend/tests/test_update_me_privilege.py"
      provides: "is_admin escalation blocked"
  key_links:
    - from: "backend/tests/test_signups.py::test_cancel_frees_capacity"
      to: "signup_service.promote_waitlist_fifo"
      via: "second-user signup assertion"
      pattern: "promote_waitlist_fifo|reusable"
---

<objective>
Build the pytest integration suite that locks every fix from Plans 01–05 and meets the 70% line / 90% critical-path coverage targets from CONTEXT.md.

Purpose: Without these tests, regressions will silently land. The cancel→reusable-capacity test is the only thing that proves the waitlist ordering fix (Plan 05) actually works end-to-end on the backend before Playwright exercises the full UI path in Plan 07.
Output: ≥ 25 integration tests, coverage report meeting targets, all tests runnable via `pytest`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md
@.planning/phases/00-backend-completion-frontend-integration/00-01-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-02-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-03-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-04-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-05-SUMMARY.md
@backend/conftest.py
@backend/tests/fixtures/factories.py
@backend/app/routers/signups.py
@backend/app/routers/auth.py
@backend/app/celery_app.py
@backend/app/signup_service.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Auth + contract + privilege integration tests</name>
  <files>backend/tests/test_auth.py, backend/tests/test_contract.py, backend/tests/test_update_me_privilege.py</files>
  <read_first>
    - backend/conftest.py (fixtures from Plan 01: client, db_session, engine)
    - backend/tests/fixtures/factories.py (UserFactory etc.)
    - backend/app/routers/auth.py (post Plan 03 — _hash_refresh_token, rotation flow)
    - backend/app/routers/users.py (post Plan 05 — _USER_UPDATE_ALLOWED_FIELDS)
    - frontend/src/lib/api.js (contract expectations for test_contract.py)
    - .planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md (authoritative list)
  </read_first>
  <action>
    1. `backend/tests/test_auth.py` — minimum 8 tests:
       - `test_register_returns_access_and_refresh_token`: POST /auth/register, assert both tokens present.
       - `test_login_happy_path`: POST /auth/token, assert 200 + tokens.
       - `test_login_wrong_password`: assert 401.
       - `test_refresh_rotates_token`: login, POST /auth/refresh with raw refresh token, assert new tokens differ from originals and old refresh token is deleted from DB.
       - `test_refresh_token_stored_as_sha256_hash`: after register, query `RefreshToken` row and assert `token_hash` matches `hashlib.sha256(raw).hexdigest()` and has length 64.
       - `test_refresh_with_invalid_token_returns_401`: assert 401 + error code `AUTH_REFRESH_INVALID`.
       - `test_refresh_with_expired_token_returns_401`: set `expires_at` to past, assert 401.
       - `test_logout_deletes_refresh_token`: assert row count decreases.
    2. `backend/tests/test_contract.py` — one test per fix in API-AUDIT.md:
       - `test_createSignup_trailing_slash`: POST to `/signups/` (trailing slash) returns 2xx, NOT 307.
       - `test_updateEvent_accepts_put`: PUT /events/{id} returns 2xx.
       - `test_updateEvent_patch_hidden`: PATCH /events/{id} returns 404 or is not in schema (assert router path not exposed).
       - `test_updateEventQuestion_path`: PUT/PATCH /events/questions/{id} returns 2xx; `/event-questions/{id}` returns 404.
       - `test_deleteEventQuestion_path`: DELETE /events/questions/{id} returns 204.
       - `test_error_response_shape`: probe **at least three distinct routers** (auth, signups, admin) to prove the global handler covers the whole surface. For each, trigger a known 4xx and assert the JSON body contains ALL THREE keys `error`, `code`, `detail` (AUDIT-03). Concretely:
         a) `POST /auth/refresh` with invalid token → 401 → assert `body['error']` and `body['code']` and `body['detail']` all present; assert `body['code'] == 'AUTH_REFRESH_INVALID'`.
         b) `POST /signups/` with non-existent slot_id → 404 → assert all three keys present.
         c) `GET /admin/summary` as non-admin user → 403 → assert all three keys present.
         Test fails if any router returns a body missing any of the three keys.
    3. `backend/tests/test_update_me_privilege.py` — 3 tests:
       - `test_update_me_cannot_elevate_to_admin`: create non-admin user, PATCH /users/me with `{is_admin: True}`, assert response 200 but DB user row still `is_admin=False`.
       - `test_update_me_cannot_change_email`: PATCH with `{email: "new@x"}`, assert DB unchanged.
       - `test_update_me_allows_name_and_phone`: PATCH with `{name: "X", phone: "1"}`, assert DB updated.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_auth.py tests/test_contract.py tests/test_update_me_privilege.py -v 2>&1 | tee /tmp/pytest-auth.log && grep -E "passed" /tmp/pytest-auth.log | grep -v failed</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_auth.py` exists with ≥ 8 `def test_` functions
    - File `backend/tests/test_contract.py` exists with ≥ 6 `def test_` functions
    - File `backend/tests/test_update_me_privilege.py` exists with ≥ 3 `def test_` functions
    - `grep -c "^def test_" backend/tests/test_auth.py` returns ≥ 8
    - `grep -c "^def test_" backend/tests/test_contract.py` returns ≥ 6
    - `grep -q "is_admin" backend/tests/test_update_me_privilege.py` succeeds
    - `grep -q "sha256" backend/tests/test_auth.py` succeeds
    - `grep -q "'/signups/'" backend/tests/test_contract.py` succeeds
    - `grep -q "test_error_response_shape" backend/tests/test_contract.py` succeeds
    - `grep -q "AUTH_REFRESH_INVALID" backend/tests/test_contract.py` succeeds
    - `grep -q "/admin/summary" backend/tests/test_contract.py` succeeds (admin router probed)
    - `grep -cE "'error'|\"error\"" backend/tests/test_contract.py` returns ≥ 3 (shape asserted in ≥3 places)
    - `python -m pytest tests/test_auth.py tests/test_contract.py tests/test_update_me_privilege.py` exits 0 from `backend/`
  </acceptance_criteria>
  <done>17+ tests passing; contract fixes and auth hardening locked against regression.</done>
</task>

<task type="auto">
  <name>Task 2: Signup concurrency, waitlist FIFO, cancel-reuses-capacity tests + admin router tests</name>
  <files>backend/tests/test_signups.py, backend/tests/test_admin.py</files>
  <read_first>
    - backend/app/routers/signups.py (post Plan 05)
    - backend/app/signup_service.py (Plan 05)
    - backend/app/routers/admin.py (admin CRUD endpoints)
    - backend/tests/fixtures/factories.py
    - 00-CONTEXT.md specific: "cancel E2E test MUST verify the freed capacity is reusable"
  </read_first>
  <action>
    1. `backend/tests/test_signups.py` — minimum 8 tests:
       - `test_signup_within_capacity`: create slot capacity=2, POST /signups/, assert 200 + status=confirmed.
       - `test_signup_over_capacity_goes_to_waitlist`: capacity=1, two users sign up, second is `waitlisted`.
       - `test_cancel_frees_capacity_for_second_user`: capacity=1, user A signs up, user A cancels, user B signs up, assert user B is `confirmed` and slot available count correct. This is the canonical Plan 07 cancel E2E assertion at the API layer.
       - `test_cancel_promotes_waitlist_fifo`: capacity=1, A confirmed, B waitlisted (older), C waitlisted (newer). A cancels. Assert B is now confirmed and C still waitlisted. Verify canonical ordering from `promote_waitlist_fifo`.
       - `test_waitlist_ordering_uses_created_at_then_id`: insert B and C with identical `created_at`, assert B (lower id) promoted first.
       - `test_cannot_cancel_other_users_signup`: assert 403.
       - `test_cancel_enqueues_cancellation_email`: monkeypatch `send_email_notification.delay`, assert called with `kind="cancellation"`.
       - `test_cancel_with_waitlist_enqueues_confirmation_email_for_promoted`: assert second `delay` call with `kind="confirmation"` for the promoted user.
    2. `backend/tests/test_admin.py` — minimum 6 tests:
       - `test_admin_list_users_requires_admin`: non-admin → 403.
       - `test_admin_create_user`: admin POST /users, assert row created.
       - `test_admin_delete_user`: admin DELETE /admin/users/{id}, assert deleted.
       - `test_admin_cancel_signup_promotes_waitlist`: same canonical assertion as in test_signups but via admin path — proves admin.py uses the same `promote_waitlist_fifo`.
       - `test_admin_list_portals`: 200 for admin.
       - `test_admin_audit_logs_filter`: assert filter by user_id works.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_signups.py tests/test_admin.py -v 2>&1 | tee /tmp/pytest-sig.log && grep -q "test_cancel_frees_capacity_for_second_user PASSED" /tmp/pytest-sig.log && grep -q "test_cancel_promotes_waitlist_fifo PASSED" /tmp/pytest-sig.log</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_signups.py` exists
    - `grep -c "^def test_" backend/tests/test_signups.py` returns ≥ 8
    - `grep -q "test_cancel_frees_capacity_for_second_user" backend/tests/test_signups.py` succeeds
    - `grep -q "test_cancel_promotes_waitlist_fifo" backend/tests/test_signups.py` succeeds
    - `grep -q "test_waitlist_ordering_uses_created_at_then_id" backend/tests/test_signups.py` succeeds
    - File `backend/tests/test_admin.py` exists with ≥ 6 test functions
    - `grep -q "test_admin_cancel_signup_promotes_waitlist" backend/tests/test_admin.py` succeeds
    - `python -m pytest tests/test_signups.py tests/test_admin.py` exits 0
  </acceptance_criteria>
  <done>Waitlist correctness, cancel-reuses-capacity, and admin CRUD locked against regression.</done>
</task>

<task type="auto">
  <name>Task 3: Celery reminder idempotency test + coverage gate</name>
  <files>backend/tests/test_celery_reminders.py, backend/pytest.ini</files>
  <read_first>
    - backend/app/celery_app.py (post Plan 04 — schedule_reminders with reminder_sent guard)
    - backend/app/emails.py (BUILDERS dict from Plan 05)
    - 00-RESEARCH.md "Pitfall 5: freezegun does not patch Celery internal scheduler clock"
    - backend/pytest.ini (current config)
  </read_first>
  <action>
    1. `backend/tests/test_celery_reminders.py` — minimum 4 tests:
       - `test_schedule_reminders_sends_one_email_per_signup`: seed 3 confirmed signups with slot start_time = now+24h; monkeypatch `send_email_notification.delay`; call `schedule_reminders()` synchronously (via `.apply()` or direct function call); assert `delay` called 3 times and each `Signup.reminder_sent` is now `True`.
       - `test_schedule_reminders_is_idempotent`: run `schedule_reminders()` twice in a row; assert `delay` call count is 3 (not 6). This is the canonical idempotency assertion from CONTEXT.md.
       - `test_schedule_reminders_ignores_already_sent`: seed a signup with `reminder_sent=True`, call task, assert NOT called for that signup.
       - `test_schedule_reminders_respects_window`: seed signups outside the [24h, 24h+5min] window; assert skipped.
       - Use `freezegun.freeze_time` to pin `datetime.now(timezone.utc)`. Do NOT rely on Celery's internal clock — call the task function directly with test DB session.
    2. Update `backend/pytest.ini` to add coverage gating:
       ```
       [pytest]
       testpaths = tests
       addopts = -ra --strict-markers --tb=short --cov=app --cov-report=term-missing --cov-fail-under=70
       markers =
           integration: integration tests hitting the real Postgres via TestClient
           unit: fast unit tests with no I/O
       ```
    3. Document the 90% critical-path target in a comment at the top of pytest.ini:
       `# 70% global line coverage required; critical paths (signup_service.py, routers/signups.py, celery_app.py) must reach 90% — enforced by grep check in CI, not by pytest-cov selector.`
       Add a companion test file check: create `backend/tests/test_critical_path_coverage.py` with a single test that parses the coverage JSON report and asserts lines-covered/lines-total ≥ 0.90 for each of the three critical files. (If too complex, leave as a SUMMARY follow-up and enforce via a shell grep in Plan 07 CI step.) Recommended: shell script approach in Plan 07 CI; keep this task focused on the pytest-cov 70% gate.
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_celery_reminders.py -v 2>&1 | tee /tmp/pytest-cel.log && grep -q "test_schedule_reminders_is_idempotent PASSED" /tmp/pytest-cel.log && python -m pytest 2>&1 | tee /tmp/pytest-all.log && grep -qE "TOTAL.*[789][0-9]%|TOTAL.*100%" /tmp/pytest-all.log</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/test_celery_reminders.py` exists
    - `grep -c "^def test_" backend/tests/test_celery_reminders.py` returns ≥ 4
    - `grep -q "test_schedule_reminders_is_idempotent" backend/tests/test_celery_reminders.py` succeeds
    - `grep -q "freeze_time" backend/tests/test_celery_reminders.py` succeeds
    - `grep -q "reminder_sent" backend/tests/test_celery_reminders.py` succeeds
    - `grep -q "cov-fail-under=70" backend/pytest.ini` succeeds
    - `python -m pytest` from `backend/` exits 0 and reports ≥ 70% coverage
    - Total test count (all files) ≥ 25: `grep -rc "^def test_" backend/tests/` sums to ≥ 25
  </acceptance_criteria>
  <done>Celery idempotency proven in a test; coverage gate enforced at 70%.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test suite → production credentials | conftest uses TEST_DATABASE_URL, never prod |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-22 | Repudiation | Regressions ship without tests catching them | mitigate | ≥ 25 integration tests + 70% coverage gate; contract tests lock api.js fixes |
| T-00-23 | Elevation of Privilege | update_me escalation regression | mitigate | `test_update_me_cannot_elevate_to_admin` asserts DB state, not just response |
| T-00-24 | Denial of Service | Duplicate reminder regression | mitigate | `test_schedule_reminders_is_idempotent` locks the Plan 04 guard |
| T-00-25 | Tampering | Waitlist ordering divergence returning | mitigate | `test_waitlist_ordering_uses_created_at_then_id` + `test_admin_cancel_signup_promotes_waitlist` prove both paths use the same function |
</threat_model>

<verification>
- `python -m pytest` exits 0
- Total test function count ≥ 25
- Coverage ≥ 70%
- Critical tests named above all PASSED
</verification>

<success_criteria>
Integration suite exists, passes, and enforces 70% coverage; every Plan 01–05 fix is locked by at least one test.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-06-SUMMARY.md`
</output>
