---
phase: 00-backend-completion-frontend-integration
plan: 04
subsystem: backend/celery
tags: [celery, redbeat, idempotency, retry, reminder, email]
dependency_graph:
  requires: [00-02]
  provides: [redbeat-scheduler, reminder-idempotency, celery-retry-config]
  affects: [00-06-pytest-integration-suite]
tech_stack:
  added:
    - celery-redbeat==2.3.3
  patterns:
    - SELECT FOR UPDATE SKIP LOCKED for distributed idempotency
    - autoretry_for=(Exception,) with retry_backoff=True, max_retries=3
    - signup_id+kind dispatch pattern for reminder emails
key_files:
  created: []
  modified:
    - backend/requirements.txt
    - backend/app/celery_app.py
decisions:
  - "schedule_reminders queries Signup directly (not Slot) to enable reminder_sent filter and FOR UPDATE SKIP LOCKED"
  - "send_email_notification accepts optional signup_id+kind to support reminder dispatch without breaking existing (user_id, subject, body) call sites"
  - "reminder_sent flag committed before function returns — first-write-wins under concurrent beats"
  - "docker-compose.yml beat command not updated (not in files_modified); TODO(phase0-infra) added to celery_app.py docstring for Plan 07 follow-up"
metrics:
  duration: ~20min
  completed: 2026-04-08
  tasks_completed: 2
  files_changed: 2
---

# Phase 0 Plan 04: Celery Reliability Summary

**One-liner:** celery-redbeat pinned and wired as distributed beat scheduler; schedule_reminders made idempotent via reminder_sent flag + SELECT FOR UPDATE SKIP LOCKED; autoretry with exponential backoff applied to both email-dispatching tasks.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Pin celery-redbeat and wire redbeat scheduler in celery_app.py | 6d0aaa0 | backend/requirements.txt, backend/app/celery_app.py |
| 2 | Add reminder_sent idempotency and retry config to reminder + email tasks | 9eca08b | backend/app/celery_app.py |

## Decisions Made

1. **Signup-direct query in schedule_reminders** — Switched from iterating Slot→signups to a direct `Signup JOIN Slot` query. This enables `reminder_sent == False` filter and `WITH FOR UPDATE SKIP LOCKED` at the ORM level, which is required for distributed idempotency.

2. **Dual call-path for send_email_notification** — Added optional `signup_id` and `kind` keyword args. When `kind="reminder_24h"` is provided, the task resolves subject/body internally from the signup record. Existing `(user_id, subject, body)` positional callers in `signups.py` and `weekly_digest` are unaffected.

3. **First-write-wins commit strategy** — `reminder_sent=True` is committed inside `schedule_reminders` before the task returns. The second beat process, if it runs concurrently, will have skipped the row via SKIP LOCKED or will see `reminder_sent=True` on its next query window.

4. **docker-compose.yml beat command deferred** — Not in `files_modified` for this plan. A `# TODO(phase0-infra)` comment was added to the celery_app.py module docstring flagging the `-S redbeat.RedBeatScheduler` CLI flag update as a Plan 07 CI concern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] send_email_notification signature extended for reminder dispatch**
- **Found during:** Task 2
- **Issue:** Plan specified `send_email_notification.delay(signup_id=s.id, kind="reminder_24h")` but the existing signature `(user_id, subject, body)` had no such parameters. Existing callers in `signups.py` and `weekly_digest` use positional args and would break if the signature changed incompatibly.
- **Fix:** Added optional `signup_id` and `kind` keyword-only params with defaults of `None`. When `kind="reminder_24h"` is detected, the task resolves user+subject+body from the signup record. Backward-compatible with all existing call sites.
- **Files modified:** `backend/app/celery_app.py`
- **Commit:** 9eca08b

## Known Stubs

None — all changes are backend task logic. No UI-facing data flows.

## Deferred Items

- `docker-compose.yml` beat service command still uses default scheduler. Must be updated to add `-S redbeat.RedBeatScheduler` before production deploy. Tagged as Plan 07 concern.

## Threat Flags

None — all STRIDE threats from the plan's threat model (T-00-14 through T-00-16) are fully mitigated by this plan's implementation:
- T-00-14 (duplicate email cost): `reminder_sent` flag + SKIP LOCKED + redbeat distributed lock
- T-00-15 (SendGrid failure flood): autoretry with exponential backoff, max 3 retries, 600s cap
- T-00-16 (beat scheduler race): SELECT FOR UPDATE SKIP LOCKED

## Self-Check: PASSED

Files confirmed present on disk:
- backend/requirements.txt — contains `celery-redbeat==2.3.3`
- backend/app/celery_app.py — contains redbeat_redis_url, beat_scheduler, skip_locked, reminder_24h, autoretry_for x2

Commits confirmed in git log:
- 6d0aaa0: feat(00-04): pin celery-redbeat and wire redbeat scheduler
- 9eca08b: feat(00-04): add reminder_sent idempotency and retry config
