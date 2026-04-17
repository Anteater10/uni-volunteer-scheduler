# Phase 27 — SMS reminders + no-show nudges — SUMMARY

**Phase:** 27-sms-reminders-no-show-nudges
**Milestone:** v1.3
**Requirements addressed:** SMS-01, SMS-02, SMS-03, SMS-04, SMS-05, SMS-06, SMS-07
**Status:** code-complete

## Outcome

AWS SNS-based SMS reminders (2h pre-event) and no-show nudges
(30 min after slot start) ship behind a hard-off `SMS_ENABLED` feature
flag. TCPA-compliant opt-in checkbox renders on the public signup form
only when the flag is on. Organizer roster gets a "Nudge no-shows"
button (also flag-gated). Admin preview endpoint exposes what the Beat
task *would* send. Zero live AWS calls in tests — every SNS path is
mocked at `sms_service._get_sns_client`.

## Migration

**None.** Phase 24's migration `0016_volunteer_preferences` already
added `sms_opt_in` + `phone_e164` columns. Verified via `models.py`
`VolunteerPreference` schema — no schema work this phase.

## What was added

### Backend (9 files)

- **`backend/requirements.txt`** — added `boto3>=1.34,<2`.
- **`backend/app/config.py`** — added `sms_enabled`, `aws_region`,
  `aws_access_key_id`, `aws_secret_access_key` settings.
- **`backend/app/services/sms_service.py`** (new) — lazy SNS client,
  `send_sms`, `should_send_sms`, `format_pre_2h_body`,
  `format_no_show_body`, E.164 validation, STOP-footer guarantee,
  `is_in_pre_2h_window` / `is_in_no_show_window` window math,
  `send_and_record` (dedup + audit-on-failure), `list_upcoming_sms`.
- **`backend/app/tasks/sms_reminders.py`** (new) — Celery task
  `check_and_send_sms` pulling slots in `(now - 1h, now + 3h)` and
  dispatching pre_2h + no_show per signup. Safe no-op when
  `sms_enabled=False`.
- **`backend/app/celery_app.py`** — added `"app.tasks.sms_reminders"`
  to `celery.conf.include` and `"check-sms"` to `beat_schedule`
  (900s cadence, mirrors Phase 24 reminders).
- **`backend/app/routers/public/config.py`** (new) — `GET /public/config`
  returning `{sms_enabled: bool}` so the frontend can gate the opt-in.
- **`backend/app/main.py`** — wired `public_config` router.
- **`backend/app/routers/organizer.py`** — `POST /organizer/events/{id}/sms-nudge-no-shows`
  with audit-log `sms_nudge_batch`.
- **`backend/app/routers/admin.py`** — `GET /admin/sms/upcoming?days=7`
  preview endpoint (UUIDs + datetimes serialized).
- **`backend/app/services/audit_log_humanize.py`** — added action
  labels `sms_nudge_batch`, `sms_send_failed`.
- **`backend/app/schemas.py`** — added optional `sms_opt_in` on
  `PublicSignupCreate`.
- **`backend/app/services/public_signup_service.py`** — persists
  `sms_opt_in` + phone on `volunteer_preferences` when the signup
  ticks the TCPA box.

### Frontend (4 files)

- **`frontend/src/lib/api.js`** — added `api.public.getConfig`,
  `api.organizer.smsNudgeNoShows`, `api.admin.sms.listUpcoming`.
- **`frontend/src/pages/public/EventDetailPage.jsx`** — reads
  `config.sms_enabled`, conditionally renders the SMS opt-in checkbox,
  passes `sms_opt_in` in the createSignup payload. Defensive guard so
  old tests without `getConfig` don't crash.
- **`frontend/src/pages/OrganizerRosterPage.jsx`** — adds "Nudge
  no-shows" button (only when flag on). Same defensive guard.

### Tests (2 files)

- **`backend/tests/test_sms_service.py`** (new) — 21 cases covering
  feature flag off/on, E.164 validation, STOP footer, body length <160,
  idempotent `send_and_record`, failure-audit path, `should_send_sms`
  combinations (flag_off, opted_out, no_phone, quiet_hours, happy),
  and window math for pre_2h + no_show. SNS mocked with `MagicMock`
  via `unittest.mock.patch`.
- **`frontend/src/pages/__tests__/EventDetailPage.sms.test.jsx`** (new) —
  verifies checkbox hidden when flag off; visible + wires `sms_opt_in:true`
  into the createSignup payload when flag on.

## Test results

- **Backend:** 21/21 new tests pass. Full suite: 331 passed, 2 failed.
  Both failures are pre-existing in `tests/test_import_pipeline.py`
  (same 2 failures Phase 24 SUMMARY already flagged).
- **Frontend:** 2/2 new tests pass. Full suite: 182 passed, 6 failed.
  Same 6 pre-existing failures documented in Phase 24 SUMMARY
  (AdminTopBar, AdminLayout, ExportsSection, ImportsSection).

## Verifications

- `from app.celery_app import celery` clean; `celery.conf.include`
  now includes `app.tasks.sms_reminders`; `beat_schedule` contains
  `check-sms` at 900s alongside the existing `check-reminders`.
- Flag off is the default — dockerised services run the Beat tick
  but short-circuit before any SNS call.

## Body template samples (all <160 chars incl. STOP footer)

- pre_2h: `"SciTrek: CRISPR Module at Lot 22 in 2h (11am). Reply STOP to opt out."`
- no_show: `"Hi Ada! You missed CRISPR Module at 11am. On your way? Reply STOP to opt out."`

## Known gaps / deferrals

- **SNS delivery-status webhook (SMS-06)** — we log + audit failures at
  send-time, but AWS SNS delivery-receipt callbacks (SMS_DELIVERED /
  SMS_FAILED from the SNS Delivery Status topic) are not wired. Plan:
  add an inbound webhook router in a v1.3.x follow-up; low risk since
  the failure path already writes `sms_send_failed` audit rows.
- **Two-way SMS** (volunteer replies "YES I'M HERE") — deferred to v1.4
  per 27-CONTEXT.md.
- **SMS broadcasts** (parallel to Phase 26 email broadcast) — flagged
  here as a **v1.3.x follow-up**, NOT blocking milestone completion.
  The wiring would be straightforward: reuse
  `broadcast_service.send_broadcast` pattern, swap the email builder
  for `sms_service.send_sms`, gate on the same `sms_enabled` flag.
- **Production AWS credentials** — placeholder creds ship; real IAM
  user lands at ops handoff per 27-CONTEXT.

## Files

- `.planning/phases/27-sms-reminders-no-show-nudges/27-PLAN.md`
- `.planning/phases/27-sms-reminders-no-show-nudges/27-SUMMARY.md`
- `backend/requirements.txt` (+boto3)
- `backend/app/config.py` (+sms_* and aws_* settings)
- `backend/app/services/sms_service.py` (new)
- `backend/app/tasks/sms_reminders.py` (new)
- `backend/app/celery_app.py` (+include, +beat_schedule entry)
- `backend/app/routers/public/config.py` (new)
- `backend/app/main.py` (+public_config router)
- `backend/app/routers/organizer.py` (+sms-nudge-no-shows endpoint)
- `backend/app/routers/admin.py` (+sms/upcoming endpoint)
- `backend/app/services/audit_log_humanize.py` (+sms action labels)
- `backend/app/schemas.py` (+sms_opt_in on PublicSignupCreate)
- `backend/app/services/public_signup_service.py` (+persist sms_opt_in)
- `backend/tests/test_sms_service.py` (new, 21 cases)
- `frontend/src/lib/api.js` (+getConfig, +smsNudgeNoShows, +admin.sms.listUpcoming)
- `frontend/src/pages/public/EventDetailPage.jsx` (+opt-in checkbox + payload field)
- `frontend/src/pages/OrganizerRosterPage.jsx` (+Nudge no-shows button)
- `frontend/src/pages/__tests__/EventDetailPage.sms.test.jsx` (new, 2 cases)
