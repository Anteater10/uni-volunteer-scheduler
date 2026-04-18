# Phase 24 — Scheduled reminder emails — SUMMARY

**Phase:** 24-scheduled-reminder-emails
**Milestone:** v1.3
**Requirements addressed:** REM-01, REM-02, REM-03, REM-04, REM-05, REM-06, REM-07
**Status:** code-complete

## Outcome

Automatic reminder emails land at three instants per signup —
kickoff (Monday 07:00 PT of the event's ISO week), 24h pre-event,
and 2h pre-event. The pipeline is:

1. Celery Beat fires `app.tasks.reminders.check_and_send_reminders` every
   15 minutes (schedule registered in `celery_app.py`).
2. The task iterates confirmed signups whose slot starts within the next
   ~8 days (wide window because kickoff can be up to a week before the slot).
3. For each `(signup, kind)` tuple it asks
   `reminder_service.compute_reminder_window(slot, kind, now_utc)` whether
   "now" is within ±15 min of the target instant.
4. If yes, `reminder_service.send_reminder` checks opt-out + quiet hours +
   idempotency (`sent_notifications(signup_id, kind)`), then dispatches to
   `send_email_notification.delay(signup_id, kind=reminder_{kind})`, which
   routes through the existing `BUILDERS` map.

## What was added

### Backend
- **Migration 0016** (`backend/alembic/versions/0016_volunteer_preferences.py`)
  creates `volunteer_preferences` keyed by `volunteer_email`.
- **Model** `VolunteerPreference` + **schemas** `VolunteerPreferenceRead`,
  `VolunteerPreferenceUpdate`, `UpcomingReminderRow`,
  `ReminderSendNowRequest/Response`.
- **Service** `backend/app/services/reminder_service.py` — deterministic
  window math, quiet-hours check, opt-out lookup, idempotent send,
  upcoming-reminders preview, Celery-free to stay unit-testable.
- **Celery task** `backend/app/tasks/reminders.py` + beat registration in
  `celery_app.py` (`check-reminders` at 900s, added
  `"app.tasks.reminders"` to `celery.conf.include`).
- **Email builders** `send_reminder_kickoff`, `send_reminder_pre_24h`,
  `send_reminder_pre_2h` appended to `BUILDERS` under keys
  `reminder_kickoff`, `reminder_pre_24h`, `reminder_pre_2h` — each returns
  `{to, subject, text_body, html_body}` and reuses the shared
  `reminder.html` template.
- **Public router** `backend/app/routers/preferences.py` with
  `GET/PUT /public/preferences?manage_token=...` (token-gated, rate-limited).
- **Admin router** extensions in `backend/app/routers/admin.py`:
  - `GET /admin/reminders/upcoming?days=7`
  - `POST /admin/reminders/send-now {signup_id, kind}` (admin +
    organizer; both actions audit-logged).

### Frontend
- `frontend/src/lib/api.js` — `public.getPreferences`,
  `public.updatePreferences`, `admin.reminders.listUpcoming`,
  `admin.reminders.sendNow`.
- New component `frontend/src/components/ReminderPreferencesCard.jsx`
  embedded at the bottom of `ManageSignupsPage.jsx` — toggle flips the
  backend preference via PUT, optimistic with revert on error.
- New page `frontend/src/pages/admin/AdminRemindersPage.jsx` at
  `/admin/reminders` — preview table + per-row "Send now" confirmation
  modal. Wired into `AdminLayout` nav ("Reminders", admin + organizer).

### Tests
- `backend/tests/test_reminder_service.py` — 12 cases: window math for all
  three kinds, quiet-hours math (22:00/06:30 quiet vs 07:00/14:00 allowed),
  idempotency (second send in window returns `already_sent`), opt-out
  path, quiet-hours block + `force=True` bypass, upcoming-reminders
  preview surfacing all three kinds.
- `backend/tests/test_volunteer_preferences.py` — upsert-read default,
  toggle email_reminders, set phone + sms_opt_in.
- `frontend/src/components/__tests__/ReminderPreferencesCard.test.jsx` —
  checkbox reflects server state; toggle fires PUT with correct payload.
- `frontend/src/pages/admin/__tests__/AdminRemindersPage.test.jsx` —
  renders rows, empty state, send-now wiring.

## Test results

- **Backend:** 19/19 new tests pass. Full suite: 293 passed, 2 failed.
  Both failures are pre-existing in `tests/test_import_pipeline.py` —
  verified unchanged by `git stash && pytest && git stash pop`.
- **Frontend:** 5/5 new tests pass. Full suite: 174 passed, 6 failed.
  Same 6 failures occur on a clean stash — all pre-existing.

## Verifications

- `alembic upgrade head` clean: `0015_custom_form_fields ->
  0016_volunteer_preferences`.
- `from app import celery_app` import-only smoke returned
  `include=['app.tasks.import_csv', 'app.tasks.reminders']` and the
  beat schedule contained `check-reminders` at 900s.

## Known gaps / deferrals

- **ICS attachment in reminder emails:** deferred — the manage page
  already exposes a per-signup `.ics` download; the reminder body links
  back to the manage page.
- **Magic-link prefilled manage URL:** we link to
  `/signup/manage?signup_id=...` (no raw token on server side). A future
  phase may issue fresh `SIGNUP_MANAGE` tokens at reminder time so the
  page loads without the volunteer re-pasting their token.
- **Per-event "skip reminders" admin toggle** — marked out of scope in
  24-CONTEXT.md. Will likely land in v1.4.
- **Reminder analytics dashboard** — deferred, per CONTEXT.

## Phase-25 handoff note

Waitlist auto-promotion (Phase 25) reuses this phase's infrastructure:
- **Email builder contract** `build(signup) -> {to, subject, text_body,
  html_body}` is stable — Phase 25 can register a new key (e.g.
  `waitlist_promoted`) in `BUILDERS` and route through
  `send_email_notification.delay(signup_id, kind="waitlist_promoted")`.
- **Idempotency** via the same `sent_notifications(signup_id, kind)`
  constraint — no schema work needed.
- **Preferences table** already covers opt-out; promotion emails are
  transactional (not the weekly reminders), so they should bypass the
  opt-out flag unless Phase 25's CONTEXT decides otherwise.

## Files

- `.planning/phases/24-scheduled-reminder-emails/24-PLAN.md`
- `.planning/phases/24-scheduled-reminder-emails/24-SUMMARY.md`
- `backend/alembic/versions/0016_volunteer_preferences.py`
- `backend/app/models.py` (+VolunteerPreference)
- `backend/app/schemas.py` (+VolunteerPreference*, UpcomingReminderRow,
  ReminderSendNow*)
- `backend/app/services/reminder_service.py` (new)
- `backend/app/tasks/reminders.py` (new)
- `backend/app/emails.py` (+3 builders, +BUILDERS keys)
- `backend/app/celery_app.py` (+beat schedule, +include)
- `backend/app/routers/preferences.py` (new)
- `backend/app/routers/admin.py` (+reminders endpoints)
- `backend/app/main.py` (+preferences router)
- `backend/tests/test_reminder_service.py` (new)
- `backend/tests/test_volunteer_preferences.py` (new)
- `frontend/src/lib/api.js` (+api.public.*Preferences, +api.admin.reminders.*)
- `frontend/src/components/ReminderPreferencesCard.jsx` (new)
- `frontend/src/pages/admin/AdminRemindersPage.jsx` (new)
- `frontend/src/pages/public/ManageSignupsPage.jsx` (+preferences card)
- `frontend/src/App.jsx` (+/admin/reminders route)
- `frontend/src/pages/admin/AdminLayout.jsx` (+nav item)
- `frontend/src/components/__tests__/ReminderPreferencesCard.test.jsx` (new)
- `frontend/src/pages/admin/__tests__/AdminRemindersPage.test.jsx` (new)
