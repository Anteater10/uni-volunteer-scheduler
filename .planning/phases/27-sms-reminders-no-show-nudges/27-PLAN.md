# Phase 27 — SMS reminders + no-show nudges — PLAN

**Phase:** 27-sms-reminders-no-show-nudges
**Milestone:** v1.3
**Requirements addressed:** SMS-01, SMS-02, SMS-03, SMS-04, SMS-05, SMS-06, SMS-07
**Dependencies:** Phase 24 (reminder infra patterns + volunteer_preferences),
Phase 26 (broadcast pattern for organizer nudge).

## Goal

Ship SMS reminders (2h pre-event) and no-show nudges (30 min after slot start)
via AWS SNS, behind a `SMS_ENABLED` feature flag. TCPA-compliant opt-in on
the public signup form, STOP footer on every body. Organizer roster gets a
manual "nudge no-shows" button. No new migration: `volunteer_preferences`
already carries `sms_opt_in` + `phone_e164` (Phase 24 / migration 0016).

## Waves

### Wave A — Backend foundations (SMS-01, SMS-02)

1. **Config + deps**: add `boto3>=1.34` to `backend/requirements.txt`;
   extend `backend/app/config.py` with `sms_enabled`, `aws_region`,
   `aws_access_key_id`, `aws_secret_access_key`.
2. **`backend/app/services/sms_service.py`** — lazy SNS client, `send_sms`,
   `should_send_sms`, body formatters, E.164 validation, STOP-footer guarantee.
   Feature-flag-off short-circuits to `{status: "skipped_flag_off"}`.
3. **`GET /public/config`** tiny endpoint returning `{sms_enabled: bool}` so
   the frontend can conditionally render the opt-in checkbox.
4. **Public signup opt-in**: extend `PublicSignupCreate` with optional
   `sms_opt_in` bool; `public_signup_service` writes the prefs row on signup.

### Wave B — Scheduled sends (SMS-03)

5. **`backend/app/tasks/sms_reminders.py`** — `check_and_send_sms` Celery task.
   Pulls slots between `now - 1h` and `now + 3h`; walks every signup in
   (confirmed, pending); applies pre_2h + no_show window math; dedups via
   `sent_notifications(kind in ("sms_pre_2h","sms_no_show"))`.
6. **Beat schedule** in `backend/app/celery_app.py`:
   `check-sms` every 900s; append `"app.tasks.sms_reminders"` to
   `celery.conf.include`.

### Wave C — Organizer nudge + admin preview (SMS-05)

7. **`POST /organizer/events/{id}/sms-nudge-no-shows`** — loops confirmed-
   not-checked-in signups, calls `send_sms` when eligible, returns
   `{sent, skipped}`. Audit-log entry `sms_nudge_batch`.
8. **`GET /admin/sms/upcoming?days=7`** — preview of what `check_and_send_sms`
   will send, shape mirrors Phase 24's upcoming-reminders preview.
9. **Audit humanize** keys `sms_nudge_batch`, `sms_send_failed`.

### Wave D — Frontend (SMS-02, SMS-05)

10. **`frontend/src/lib/api.js`** — `api.public.getConfig()`,
    `api.organizer.smsNudgeNoShows(eventId)`,
    `api.admin.sms.listUpcoming(days)`.
11. **EventDetailPage** — read `config.sms_enabled` on mount; when true,
    render opt-in checkbox below phone field with TCPA copy.
12. **OrganizerRosterPage** — "Nudge no-shows" button when flag is enabled;
    preview eligible count via a confirm dialog; POST to nudge endpoint.

### Wave E — Tests (SMS-07)

13. **`backend/tests/test_sms_service.py`** — feature flag off, opt-in required,
    E.164 validation, STOP footer appended, body < 160 chars, idempotency,
    no_show + pre_2h window math. boto3 mocked with `unittest.mock.patch`.
14. **Frontend vitest** — opt-in checkbox renders only when flag on; nudge
    button triggers API call.

### Wave F — Ship (SMS-07)

15. Backend pytest + frontend vitest clean.
16. Commits with `(27)` scope.
17. `27-SUMMARY.md` mapping SMS-01..07, flagging SMS broadcasts as v1.3.x
    deferral.

## Constraints (repeated)

- Feature flag OFF by default. No live AWS calls in any test.
- Quiet hours rule from Phase 24 — reuse `reminder_service.is_quiet_hours`.
- Don't break existing Beat schedule for Phase 24 reminders.
- Per 27-CONTEXT: no migration needed.

## Out of scope / deferred

- Two-way SMS (volunteer replies YES) — v1.4.
- SMS broadcast (parallel to Phase 26 email broadcast) — v1.3.x follow-up.
- Live SNS delivery-status webhook wiring — log only for now.
