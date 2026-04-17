# Phase 27: SMS reminders + no-show nudges — Context

**Gathered:** 2026-04-17

<domain>
## Phase Boundary

AWS SNS for SMS reminders (2h pre-event) + no-show nudges (30 min after event start). TCPA-compliant opt-in on signup; STOP/HELP footer. Feature-flagged behind `SMS_ENABLED`. Placeholder AWS creds during dev; prod creds land at ops handoff.

</domain>

<decisions>
## Implementation Decisions

### Feature flag
- `SMS_ENABLED` env var / `settings.sms_enabled` (default False). When False, all SMS paths short-circuit (log "SMS disabled, skipping" and return), including Celery tasks, organizer nudge button, signup-form opt-in checkbox (hidden when False).

### AWS SNS client
- New `backend/app/services/sms_service.py` wraps `boto3.client('sns', ...)`. Config via env: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (all from existing config.py — add if missing).
- Placeholder creds (`test-access-key` / `test-secret`) fine for dev. Production creds land at handoff (noted in SUMMARY.md).
- Dev short-circuit: when `SMS_ENABLED` is False, `send_sms(phone, body)` logs and returns without actually calling SNS.

### Phone opt-in + TCPA
- `volunteer_preferences.sms_opt_in` Boolean (Phase 24 migration already added this).
- `volunteer_preferences.phone_e164` String (Phase 24 migration already added this).
- Signup form gains an "SMS reminders" checkbox labeled: "Text me reminders about this event. Message and data rates may apply. Reply STOP to opt out, HELP for help."
- Opt-in persisted via `PUT /signups/preferences` (Phase 24 endpoint).

### Scheduled sends
- New Celery Beat task `check_and_send_sms` every 15 min (same pattern as Phase 24 reminders). Windows:
  - `sms_pre_2h` — 2h before slot.starts_at ± 15 min.
  - `sms_no_show` — 30 min AFTER slot.starts_at if signup still in `confirmed` or `pending` (not yet checked_in).
- Respects quiet hours (21:00–07:00 PT — reuse Phase 24 helper `is_quiet_hours`).
- Idempotent via `sent_notifications` with kinds `sms_pre_2h`, `sms_no_show`.
- Only sends if volunteer.sms_opt_in==True AND phone_e164 present AND `SMS_ENABLED` feature flag.

### Body templates
- `<160 chars` each; STOP/HELP footer.
- Pre-2h: `"SciTrek reminder: {event_title} at {venue} in 2h ({time_pt}). Reply STOP to opt out."`
- No-show: `"Hi {first_name}! You missed {event_title} at {time_pt}. If you're on your way, open {manage_url}. Reply STOP to opt out."`

### Organizer nudge button
- `POST /organizer/events/{id}/sms-nudge-no-shows` — sends `sms_no_show` to all currently-unmarked attendees (status in (confirmed, pending), not checked_in). Respects opt-in + feature flag + idempotency.
- Button on organizer roster page: "Nudge no-shows via SMS". Shows "N volunteers eligible" preview.

### Delivery status
- AWS SNS returns message ID; we log + audit. SNS Delivery Status webhooks (future) would be wired to a webhook router — out of scope for v1.3, just log for now.
- Bounce / failure: logged as audit entry `sms_send_failed` with payload.

### API additions
- `POST /organizer/events/{id}/sms-nudge-no-shows` — organizer nudge.
- `GET /admin/sms/upcoming?days=7` — preview upcoming scheduled sends (similar to Phase 24 reminders preview).

### Tests
- `backend/tests/test_sms_service.py`:
  - Send respects feature flag (off → no-op).
  - Opt-in required.
  - Phone format validation (E.164).
  - STOP footer present.
  - No-show window math.
- Frontend: signup-form opt-in checkbox hidden when flag off; organizer nudge button works.

### Dependency
- Add `boto3` to `backend/requirements.txt`.

</decisions>

<code_context>
## Existing Code Insights
- Phase 24 `reminder_service.py` — mirror for SMS: quiet hours, idempotency, Beat schedule, opt-out paths.
- `volunteer_preferences` table from Phase 24 — `sms_opt_in` + `phone_e164` already columns.
- Celery schedule registered in `backend/app/celery_app.py::celery.conf.beat_schedule`.

</code_context>

<specifics>
## Specific Ideas
- Organizer nudge is a manual safety net — organizers at the venue can fire it when N unmarked attendees are late.
- STOP handling is done by AWS SNS automatically (SMS-provider-level), but we still include the footer text for compliance.

</specifics>

<deferred>
## Deferred Ideas
- Two-way SMS (volunteer replies "YES I'M HERE") — needs SNS inbound wiring, not v1.3.
- SMS broadcasts (parallel to Phase 26 email broadcast) — considered in SUMMARY handoff; probably a small v1.3.x follow-up, not blocking milestone.

</deferred>

---

*Phase: 27-sms-reminders-no-show-nudges*
