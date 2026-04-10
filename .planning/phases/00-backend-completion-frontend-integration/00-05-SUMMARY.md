---
phase: 00-backend-completion-frontend-integration
plan: 05
subsystem: backend/refactors
tags: [refactor, waitlist, emails, deps, pydantic-v2, error-shape, audit-03]
dependency_graph:
  requires: [00-02, 00-03, 00-04]
  provides:
    - signup_service.promote_waitlist_fifo
    - emails.BUILDERS
    - deps.ensure_event_owner_or_admin
    - global-http-exception-handler
  affects: [00-06-pytest-integration-suite, 00-07-playwright-e2e-ci]
tech_stack:
  added: []
  patterns:
    - Single canonical waitlist promotion (ordering + SKIP LOCKED)
    - BUILDERS dispatch table for transactional emails
    - Pydantic v2 model_dump (replacing deprecated .dict)
    - Explicit field allow-list for user self-update (T-00-18)
    - Global FastAPI HTTPException handler for uniform error shape (AUDIT-03)
key_files:
  created:
    - backend/app/signup_service.py
    - backend/app/emails.py
    - backend/app/utils.py
  modified:
    - backend/app/deps.py
    - backend/app/main.py
    - backend/app/celery_app.py
    - backend/app/routers/signups.py
    - backend/app/routers/admin.py
    - backend/app/routers/events.py
    - backend/app/routers/slots.py
    - backend/app/routers/users.py
    - backend/app/routers/auth.py
decisions:
  - "promote_waitlist_fifo promotes one row per call; callers loop and own slot.current_count bookkeeping (matches existing loop semantics without double-owning the counter)"
  - "emails.BUILDERS returns {to, subject, body} (not html/text split) to match the existing SendGrid helper and Notification table columns"
  - "Global handler targets StarletteHTTPException so both FastAPI and Starlette raise paths are covered; RequestValidationError (422) intentionally untouched per AUDIT-03 scope"
  - "Only AUTH_REFRESH_INVALID converted to dict-detail form; other routers keep bare-string details and fall back to http_{status} slug"
metrics:
  duration: ~25min
  completed: 2026-04-08
  tasks_completed: 4
  files_changed: 12
---

# Phase 0 Plan 05: Refactor Extractions Summary

**One-liner:** Extracted signup_service.promote_waitlist_fifo, emails.BUILDERS, deps.ensure_event_owner_or_admin, and utils.utcnow into single-source-of-truth modules; cleaned up Pydantic v1 .dict calls; added an allow-list to PATCH /users/me; and registered a global HTTPException handler normalizing every 4xx/5xx to `{error, code, detail}` (AUDIT-03).

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Extract signup_service.promote_waitlist_fifo; rewire signups.py + admin.py | 103f71b | backend/app/signup_service.py, routers/signups.py, routers/admin.py |
| 2 | Extract emails.BUILDERS; celery dispatch-by-kind; cancel enqueues cancellation + confirmation | 3ee8e8b | backend/app/emails.py, celery_app.py, routers/signups.py |
| 3 | utils.py, deps.ensure_event_owner_or_admin, .dict→model_dump, update_me allow-list | 4bd2095 | backend/app/utils.py, deps.py, routers/{events,users,slots,admin}.py |
| 4 | Global HTTPException handler enforcing {error, code, detail}; AUTH_REFRESH_INVALID coded raise | 3982653 | backend/app/main.py, routers/auth.py |

## Decisions Made

1. **Single-row promotion, caller loops.** The canonical `promote_waitlist_fifo` promotes one waitlisted signup per call (ordering `(timestamp ASC, id ASC)`, `SKIP LOCKED`). Both `signups.cancel_signup` and `admin._promote_waitlist_fifo` loop until `slot.current_count == slot.capacity`. This preserves the existing semantics where the caller owns the `current_count` counter and avoids accidentally double-incrementing it inside the service.

2. **Signup model uses `timestamp`, not `created_at`.** The plan sketch referenced `Signup.created_at`; the real schema uses `Signup.timestamp` as the creation column, so the canonical ordering is `(timestamp ASC, id ASC)`. Same column was already used by the admin-side helper, so no behavior change for existing cancels — only the signups.py path was upgraded from the old `timestamp ASC` (no id tiebreaker) ordering.

3. **BUILDERS return `{to, subject, body}`**, not `{to, subject, html, text}`. The existing SendGrid helper takes a plain-text body and the `Notification` table has `subject` + `body` columns. Splitting html/text would have forced a wider refactor outside this plan's scope.

4. **Only `AUTH_REFRESH_INVALID` converted to dict-detail form.** The global handler wraps any string-detail HTTPException with a default `http_{status}` slug, so bare raises remain functional. Only the refresh-token path was upgraded to the coded form because Plan 06 tests will assert the `AUTH_REFRESH_INVALID` code specifically.

5. **Handler scope: HTTPException only.** Per AUDIT-03 and the plan, no generic `Exception` handler was added, and `RequestValidationError` (422) responses are untouched. FastAPI's default 422 body remains.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan's `promote_waitlist_fifo` body referenced `created_at`, `updated_at`, and locked the slot internally**
- **Found during:** Task 1
- **Issue:** The plan sketch used `Signup.created_at.asc()`, set `next_up.updated_at`, and called `db.query(Slot)...with_for_update().one()` inside the service. The real `Signup` model has neither `created_at` nor `updated_at` (creation column is `timestamp`, no updated column at all). Locking the slot inside the service would also have double-locked: both `signups.cancel_signup` and `admin.admin_cancel_signup` already hold a `FOR UPDATE` on the slot when they enter the promotion path.
- **Fix:** Ordering switched to `(Signup.timestamp ASC, Signup.id ASC)`. `updated_at` assignment removed. Slot locking moved out of the service and documented via a module-level note that the caller is responsible for it. This matches the pre-existing admin-side helper behavior exactly while still eliminating the ordering divergence flagged by research.
- **Files modified:** `backend/app/signup_service.py`
- **Commit:** 103f71b

**2. [Rule 3 - Blocking] emails.BUILDERS return shape**
- **Found during:** Task 2
- **Issue:** Plan sketch had builders returning `{to, subject, html, text}`. Existing celery task + Notification table use plain-text `body` only.
- **Fix:** Builders return `{to, subject, body}`. Celery dispatch code consumes those keys unchanged.
- **Files modified:** `backend/app/emails.py`, `backend/app/celery_app.py`
- **Commit:** 3ee8e8b

**3. [Rule 2 - Security] Plan didn't specify the exact allow-list for `update_me`**
- **Found during:** Task 3
- **Issue:** Plan suggested `{"name", "phone"}` but the real `UserUpdate` schema has `{name, university_id, notify_email}` (no phone field).
- **Fix:** `_USER_UPDATE_ALLOWED_FIELDS = {"name", "university_id", "notify_email"}` — exactly the `UserUpdate` schema's fields, excluding anything sensitive that a malicious client could otherwise attempt to smuggle in via hand-crafted JSON.
- **Files modified:** `backend/app/routers/users.py`
- **Commit:** 4bd2095

## Known Stubs

None — this plan is pure refactor/cleanup. No new UI-facing data flows.

## Deferred Items

- **Admin broadcast email templating** (`routers/admin.py::notify_event_participants` and `admin_move_signup` / `admin_resend_signup_email`): still inline. Explicitly deferred by CONTEXT.md "Refactors bundled into Phase 0". These paths continue to call `send_email_notification.delay(user_id, subject, body)` directly.
- **Admin-side transactional emails** (`admin_cancel_signup`, `admin_promote_signup`, `admin_move_signup`, `admin_resend_signup_email`): still use the legacy `(user_id, subject, body)` path with inline bodies. Migrating these to `kind=`-based dispatch is a future cleanup; the plan only mandated migrating `signups.cancel_signup`.
- **Coded error details for non-auth routers**: only `AUTH_REFRESH_INVALID` was converted to dict-form. Other routers still use string details and rely on the handler's `http_{status}` fallback. If Plan 06 needs additional codes (e.g. `SIGNUP_CAPACITY_FULL`), they can be added then.

## Threat Flags

None new. All STRIDE threats from the plan's threat register are mitigated:
- T-00-18 (update_me privilege escalation): `_USER_UPDATE_ALLOWED_FIELDS` allow-list
- T-00-19 (concurrent-cancel double-promote): single canonical `promote_waitlist_fifo` with `SKIP LOCKED` + caller's slot `FOR UPDATE`
- T-00-20 (untestable inline emails): `emails.BUILDERS` centralization
- T-00-21 (ownership-check divergence): single `deps.ensure_event_owner_or_admin`
- T-00-22 (inconsistent 4xx shapes): global HTTPException handler

## Self-Check: PASSED

Files confirmed present on disk:
- backend/app/signup_service.py — `promote_waitlist_fifo`, `timestamp.asc()`, `skip_locked`
- backend/app/emails.py — `BUILDERS` with confirmation/cancellation/reminder_24h
- backend/app/utils.py — `utcnow()`
- backend/app/deps.py — `ensure_event_owner_or_admin`
- backend/app/main.py — `@app.exception_handler(StarletteHTTPException)`, `{error, code, detail}`
- backend/app/routers/users.py — `_USER_UPDATE_ALLOWED_FIELDS`
- backend/app/routers/events.py, slots.py, admin.py — no duplicate `_ensure_event_owner_or_admin`; no `.dict(exclude_unset` remains
- backend/app/routers/signups.py — imports `promote_waitlist_fifo`; enqueues `kind="cancellation"` + `kind="confirmation"`
- backend/app/routers/auth.py — `AUTH_REFRESH_INVALID` dict-detail raise

Commits confirmed in git log:
- 103f71b: refactor(00-05): extract signup_service.promote_waitlist_fifo
- 3ee8e8b: refactor(00-05): extract emails.BUILDERS
- 4bd2095: refactor(00-05): centralize ensure_event_owner_or_admin + pydantic v2 cleanups
- 3982653: feat(00-05): global HTTPException handler
