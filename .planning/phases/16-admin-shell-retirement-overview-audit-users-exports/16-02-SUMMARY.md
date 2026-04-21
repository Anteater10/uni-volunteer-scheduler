---
phase: 16
plan: 02
subsystem: admin-backend
tags: [users, invite, summary, audit-log, csv, quarter, ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07, ADMIN-18, ADMIN-19, ADMIN-20, ADMIN-21, ADMIN-22, ADMIN-23]
requirements: [ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07, ADMIN-18, ADMIN-19, ADMIN-20, ADMIN-21, ADMIN-22, ADMIN-23]
dependency_graph:
  requires:
    - backend/app/models.py (User.is_active, User.last_login_at from 16-01)
    - backend/app/services/audit_log_humanize.py (from 16-01)
  provides:
    - POST /users/invite, /deactivate, /reactivate + safety rails (Plan 04 FE)
    - GET /admin/summary expanded shape (Plan 05 FE)
    - GET /admin/audit-logs humanized rows (Plan 06 FE)
    - GET /admin/analytics/{attendance,no-show}-rates.csv (Plan 07 FE)
    - backend/app/services/quarter.py 11-week helper (canonical, FE mirrors)
  affects:
    - backend/app/routers/auth.py (/auth/token now stamps last_login_at)
    - backend/app/schemas.py (UserRead exposes is_active + last_login_at)
tech_stack:
  added: []
  patterns:
    - "FOR UPDATE on materialized row IDs instead of aggregate COUNT (Postgres
      refuses FOR UPDATE + aggregates). Admin-count set is tiny, so Python
      len() is fine."
    - "Humanized rows computed at read time by audit_log_humanize.humanize()
      — frontend never does second-round DB lookups"
    - "CSV-injection prefix hardening via _csv_safe() on every admin CSV cell
      that can contain user-controlled strings"
key_files:
  created:
    - backend/app/services/invite.py
    - backend/app/services/quarter.py
    - backend/tests/test_users_invite.py
    - backend/tests/test_users_deactivate.py
    - backend/tests/test_admin_summary_expanded.py
    - backend/tests/test_admin_analytics_csv.py
    - backend/tests/test_admin_audit_logs_humanized.py
  modified:
    - backend/app/routers/users.py
    - backend/app/routers/auth.py
    - backend/app/routers/admin.py
    - backend/app/schemas.py
    - backend/tests/test_admin.py
    - backend/tests/test_admin_phase7.py
decisions:
  - "D-11 applied: POST /users/invite creates user with hashed_password=NULL,
    is_active=TRUE and fires best-effort invite email via
    app.services.invite.send_invite_email. Email failure does not roll back
    user creation."
  - "D-12 applied: self-demote and last-active-admin demote blocked on PATCH
    /users/{id}; last-admin deactivate blocked on POST /deactivate."
  - "D-13 applied: GET /users/ excludes participants entirely and filters
    is_active=False by default; ?include_inactive=true brings deactivated
    users back for the admin Users page toggle."
  - "D-37 applied: /auth/token stamps user.last_login_at on every successful
    login. Deviation from plan: plan suggested patching magic.py, but the
    real admin-login path is /auth/token (magic.py is the volunteer
    signup-confirm flow). Application-code driven, not a DB trigger."
  - "D-14..D-29 applied: /admin/summary returns the full expanded shape
    (users_total, events_total, slots_total, signups_total,
    signups_confirmed_total, *_quarter siblings, this_week_events,
    this_week_open_slots, volunteer_hours_quarter, attendance_rate_quarter,
    week_over_week{users,events,signups}, quarter_progress{week,of,pct},
    fill_rate_attention[], last_updated)."
  - "D-23 applied: signups_last_7d field removed from /admin/summary response
    entirely (was a buggy query returning total signups regardless of date).
    Frontend consumes week_over_week.signups instead."
  - "D-19 / D-34 applied: /admin/audit-logs list response and /audit-logs.csv
    export both run each row through audit_log_humanize.humanize() at read
    time; CSV columns are When/Who/Role/What/Target/Raw Action/Entity ID."
  - "D-47 applied: two new CSV endpoints —
    /admin/analytics/attendance-rates.csv and /no-show-rates.csv — mirror the
    existing JSON endpoints with the same filter params and the same
    aggregation helpers inlined."
  - "RESEARCH Open Q 3 resolved: QUARTER_ANCHOR = date(2026, 3, 30),
    WEEKS_PER_QUARTER = 11. backend/app/services/quarter.py is the canonical
    source. frontend/src/lib/quarter.js must mirror."
metrics:
  tasks: 2
  files_created: 7
  files_modified: 6
  tests_added: 13
  completed: 2026-04-15
---

# Phase 16 Plan 02: Wave 1 Admin Backend Surface Summary

One-liner: Landed every backend endpoint the Phase 16 frontend needs — invite/deactivate/reactivate with race-safe last-admin guards, expanded /admin/summary with 11-week quarter helper, humanized audit-log responses, and two new analytics CSV exports.

## What shipped

### Task 1 — users.py surfaces + safety rails (commit a41f4a1)

- `backend/app/services/invite.py`: tiny invite-email helper. Reads
  `settings.frontend_base_url`, composes a text email with a login URL, and
  fires it via `celery_app._send_email_via_sendgrid`. The router catches any
  exception so SMTP outages never roll back user creation.
- `backend/app/routers/users.py`:
  - `POST /users/invite` (admin-only): creates a user with
    `hashed_password=NULL`, `is_active=TRUE`, audit-logs `user_invite`, commits,
    then best-effort fires the invite email.
  - `POST /users/{id}/deactivate`: self-deactivate guard (409) + last-admin
    guard (409) via `_count_active_admins_locked()`, which uses
    `with_for_update()` on `User.id` rows (Postgres refuses FOR UPDATE on an
    aggregate COUNT, so we materialize IDs under the lock and `len()` in
    Python — admin set is tiny).
  - `POST /users/{id}/reactivate`: flips `is_active=True`, audit-logs
    `user_reactivate`.
  - `PATCH /users/{id}`: blocks self-demote (admin→non-admin on caller.id ==
    target.id) and last-active-admin demote before applying any field
    changes.
  - `GET /users/` excludes `role == participant` (D-13) and
    `is_active == False` (by default); `?include_inactive=true` brings
    deactivated rows back.
- `backend/app/routers/auth.py` `/auth/token` login path: on successful login,
  sets `user.last_login_at = datetime.now(UTC)` and commits atomically with
  the existing `user_login` audit row.
- `backend/app/schemas.py`: `UserRead` now exposes `is_active` and
  `last_login_at` with safe defaults so existing fixtures still serialize.
  New `UserInvite` schema: name + email + role (admin|organizer) only.
- Tests: `test_users_invite.py` (6 cases — happy, duplicate, bad role,
  non-admin caller, email-failure resilience, last_login_at stamping) +
  `test_users_deactivate.py` (7 cases — happy deactivate, last-admin block,
  self-deactivate block, reactivate, self-demote block, last-admin demote via
  race simulation, list filters).

### Task 2 — admin.py expanded summary, humanized audit, new CSVs (commit 8be37ae)

- `backend/app/services/quarter.py`: 11-week academic quarter helper.
  `QUARTER_ANCHOR = date(2026, 3, 30)`, `WEEKS_PER_QUARTER = 11`. Exposes
  `current_quarter_bounds(now)`, `previous_quarter_bounds(now)`,
  `quarter_index(now)`, and `quarter_progress(now)`. UTC throughout;
  tolerates naive datetimes by assuming UTC.
- `backend/app/routers/admin.py`:
  - **`GET /admin/summary`** fully rewritten to the D-14..D-29 shape. Drops
    the `signups_last_7d` field entirely (D-23). Uses
    `func.count()` aggregates where possible and a single loop over next-2-week
    events for `fill_rate_attention` (red if <30% filled AND <3 days out,
    amber if <50%, else green). Computes `volunteer_hours_quarter` by pulling
    attended rows joined to Slot, summing slot durations in hours.
    `attendance_rate_quarter` is `attended / (confirmed+attended+no_show)`.
  - **`GET /admin/audit-logs`** (paginated) now returns a dict of
    `{items, total, page, page_size, pages}` where each item is the output of
    `audit_log_humanize.humanize(log, db)`. Response model annotation dropped
    so the humanized shape flows through untouched.
  - **`GET /admin/audit-logs.csv`**: column set rewritten to
    `When, Who, Role, What, Target, Raw Action, Entity ID`. Every cell goes
    through a new `_csv_safe()` helper that prefixes `= + - @` leading
    characters with a single quote for CSV-injection hardening.
  - **`GET /admin/analytics/attendance-rates.csv`** and
    **`GET /admin/analytics/no-show-rates.csv`**: new endpoints mirroring the
    existing JSON variants. Same filter params (`from_date`, `to_date`), same
    aggregation, CSV-injection-safe cells, proper Content-Disposition
    headers.
- Tests:
  - `test_admin_summary_expanded.py` (2 cases — expanded shape + admin-only).
    Asserts every required key is present, `signups_last_7d` is absent,
    `week_over_week` has ints, `quarter_progress.of == 11`,
    `fill_rate_attention` is a list, `last_updated` is ISO.
  - `test_admin_analytics_csv.py` (3 cases — attendance/no-show 200+headers +
    non-admin 403).
  - `test_admin_audit_logs_humanized.py` (2 cases — list rows include
    `action_label/actor_label/actor_role/entity_label`; CSV headers include
    the humanized columns).

## Verification results

- `pytest -q tests/test_users_invite.py tests/test_users_deactivate.py
  tests/test_admin_summary_expanded.py tests/test_admin_analytics_csv.py
  tests/test_admin_audit_logs_humanized.py` → **20 passed**
- Regression suite
  `pytest -q tests/test_admin.py tests/test_admin_phase7.py tests/test_auth.py
  tests/test_audit_log_humanize.py tests/test_users_invite.py
  tests/test_users_deactivate.py tests/test_admin_summary_expanded.py
  tests/test_admin_analytics_csv.py tests/test_admin_audit_logs_humanized.py`
  → **51 passed**

## Deviations from Plan

### [Rule 1 — Plan pseudocode vs real auth flow] last_login_at update site

The plan's `<action>` for Task 1 instructs to patch
`backend/app/routers/magic.py` to stamp `user.last_login_at` on magic-link
verification. That file is the **volunteer signup-confirm** flow — it
operates on `Signup` rows, not `User` rows, and has no user-row update path.
The real admin login path is `/auth/token` in `backend/app/routers/auth.py`.
Fixed: added `user.last_login_at = datetime.now(UTC)` plus a `db.add(user)`
immediately before the existing `log_action` call in `/auth/token`. Test
`test_login_stamps_last_login_at` confirms the field is non-null and within 5
seconds of now after a successful login.

### [Rule 1 — Postgres constraint] FOR UPDATE + aggregate COUNT

Plan pseudocode used `.with_for_update().count()` for the race-safe admin
count. Postgres refuses this combination with
`FeatureNotSupported: FOR UPDATE is not allowed with aggregate functions`.
Fixed: `_count_active_admins_locked` materializes `User.id` rows under the
lock and returns `len(q.all())`. Admin set is tiny so the `O(n)` fetch is
negligible.

### [Rule 1 — Test flaw] last-admin PATCH demote test

My first draft of `test_patch_blocks_last_admin_demote` tried to reach the
409 branch via the happy-path demote sequence, but with an active admin
caller that configuration can never reach the guard (the caller themselves
satisfies the "active admin not including target" count). Fixed: the test
now simulates a post-issuance deactivation race — the caller holds a valid
JWT but has been deactivated out-of-band, leaving the target as the only
active admin. Demoting the target now correctly 409s with
`"last active admin"`.

### [Rule 1 — Pre-existing tests locked the legacy shape]

`tests/test_admin.py::test_admin_summary_requires_admin` asserted `"total_users"`
etc. (the legacy `AdminSummary` schema), which we intentionally replaced
with the D-14..D-29 expanded shape (`users_total`, ...). Updated the
assertion to the new keys. `tests/test_admin_phase7.py::test_audit_logs_csv_export`
asserted `"timestamp" in header_row`, which is the legacy CSV header;
updated it to assert `"When"` and `"Raw Action"`.

## Known Stubs

None. Every backend surface promised to Plans 04/05/06/07 is wired end-to-end
with real data and real tests. The `signups_last_7d` field was deliberately
removed rather than stubbed.

## Threat Flags

None. No new authentication paths, no new file-read surfaces, no new trust
boundaries. The new `/users/invite` endpoint is admin-only; the new CSV
exports are admin-only and share the existing CSV-injection hardening
(`_csv_safe`).

## Commits

- `a41f4a1` — feat(16-02): invite/deactivate/reactivate + safety rails on users router
- `8be37ae` — feat(16-02): expanded /admin/summary + humanized audit logs + analytics CSVs

## Self-Check: PASSED

- backend/app/services/invite.py — FOUND
- backend/app/services/quarter.py — FOUND
- backend/app/routers/users.py — FOUND (modified)
- backend/app/routers/auth.py — FOUND (modified)
- backend/app/routers/admin.py — FOUND (modified)
- backend/app/schemas.py — FOUND (modified)
- backend/tests/test_users_invite.py — FOUND
- backend/tests/test_users_deactivate.py — FOUND
- backend/tests/test_admin_summary_expanded.py — FOUND
- backend/tests/test_admin_analytics_csv.py — FOUND
- backend/tests/test_admin_audit_logs_humanized.py — FOUND
- Commit a41f4a1 — FOUND
- Commit 8be37ae — FOUND
