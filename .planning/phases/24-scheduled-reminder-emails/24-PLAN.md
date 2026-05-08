# Phase 24 — Scheduled reminder emails — PLAN

**Phase:** 24-scheduled-reminder-emails
**Milestone:** v1.3
**Requirements addressed:** REM-01, REM-02, REM-03, REM-04, REM-05, REM-06, REM-07
**Depends on:** Phase 21 (orientation engine landed); reuses the existing
`sent_notifications` dedup table and `BUILDERS` email pattern from phase 6.
**Status:** planned → execute

## Goal

Automatic reminder emails at kickoff (Monday 07:00 PT of event week),
24h pre-event, and 2h pre-event — idempotent, opt-out aware, quiet-hours
compliant. Exactly-once delivery is enforced via
`sent_notifications (signup_id, kind)`. Volunteers control the opt-out
from the manage-my-signup page (magic-link token). Admins see an upcoming
list + send-now fallback at `/admin/reminders`.

## Build shape

### 1. Database (migration 0016)

`backend/alembic/versions/0016_volunteer_preferences.py`:

- Create table `volunteer_preferences`:
  - `volunteer_email` VARCHAR(255) PRIMARY KEY
  - `email_reminders_enabled` BOOLEAN NOT NULL DEFAULT true
  - `sms_opt_in` BOOLEAN NOT NULL DEFAULT false
  - `phone_e164` VARCHAR(20) NULL
  - `created_at`, `updated_at` timestamptz with server_default = now()
- Clean `downgrade()` drops the table.

Note: `volunteer_email` is the stable identity across signups, matching the
orientation credits pattern. No FK — a preferences row can predate or outlive a
volunteer row without breaking consent records.

### 2. Models + schemas

- `app/models.py`: new `VolunteerPreference` ORM class.
- `app/schemas.py`:
  - `VolunteerPreferenceRead` — returned on GET.
  - `VolunteerPreferenceUpdate` — optional `email_reminders_enabled`,
    `sms_opt_in`, `phone_e164`.

### 3. Service `app/services/reminder_service.py`

Pure deterministic logic, no Celery imports:

- `get_preferences(db, email)` — upsert-read; returns default row if missing.
- `update_preferences(db, email, patch)` — partial update; returns the row.
- `is_quiet_hours(now_pt)` — True if 21:00 <= hour or hour < 7:00 (PT).
- `compute_reminder_window(slot, kind, now_utc)` — bool; ±15 min tolerance:
  - `kickoff`: Monday 07:00 PT of slot's ISO week.
  - `pre_24h`: `slot.start_time - 24h`.
  - `pre_2h`: `slot.start_time - 2h`.
- `list_upcoming_reminders(db, days=7)` — preview shape for admin.
- `send_reminder(db, signup_id, kind)` — respects opt-out + quiet hours,
  dedups via `_dedup_insert`, dispatches via `send_email_notification.delay`.

### 4. Celery task `app/tasks/reminders.py`

- `@celery.task check_and_send_reminders()` — every 15 min:
  1. Find slots starting within next 30h (covers kickoff + pre_24h + pre_2h).
  2. Walk confirmed signups per slot.
  3. For each (signup, kind): if in window, call `send_reminder`.
- `celery_app.py`: add `"app.tasks.reminders"` to `celery.conf.include` and
  `beat_schedule["check-reminders"]` at 900s.

### 5. Email builder `app/emails.py`

Add three builders and register them:
- `send_reminder_kickoff(signup)` — "See you this week"
- `send_reminder_pre_24h(signup)` — "Your SciTrek event is tomorrow"
- `send_reminder_pre_2h(signup)` — "Starting in 2 hours"

Each returns `{to, subject, text_body, html_body}`; HTML includes an
unsubscribe link that deep-links to the manage page with the volunteer's
magic-link manage_token prefilled (via `MagicLinkToken` purpose =
`SIGNUP_MANAGE` for the volunteer).

Register with keys `reminder_kickoff`, `reminder_pre_24h`, `reminder_pre_2h`.

### 6. Routers

- `app/routers/preferences.py` (new public, token-gated):
  - `GET  /public/preferences?manage_token=...` → VolunteerPreferenceRead
  - `PUT  /public/preferences?manage_token=...` → VolunteerPreferenceRead
- `app/routers/admin.py` (extend):
  - `GET  /admin/reminders/upcoming?days=7` — list preview shape.
  - `POST /admin/reminders/send-now` `{signup_id, kind}` — audit-logged
    call to `reminder_service.send_reminder` short-circuiting the window.

### 7. Frontend

- `frontend/src/lib/api.js`: add
  `getPreferences`, `updatePreferences`, `adminListUpcomingReminders`,
  `adminSendReminderNow`.
- `ManageSignupsPage.jsx`: add an "Email reminder preferences" Card with a
  toggle bound to the API. Optimistic.
- `frontend/src/pages/admin/AdminRemindersPage.jsx` (new) + route
  `/admin/reminders` (admin role), wired into `AdminLayout` nav between
  "Orientation Credits" and "Help".

### 8. Tests

- `backend/tests/test_reminder_service.py`:
  - Window math for each kind (too early / in window / too late).
  - Opt-out skip.
  - Quiet hours skip.
  - Idempotency (second call in-window does not re-send).
- `backend/tests/test_volunteer_preferences.py`:
  - Upsert-read default.
  - PUT toggles email_reminders_enabled.
- Frontend: preferences toggle test + AdminRemindersPage test (light).

### 9. Run

- `alembic upgrade head` inside docker network.
- pytest for backend.
- vitest for frontend.
- Import-only smoke of `app.celery_app` to verify the beat schedule registers.

### 10. Commit

Single commit with scope `(24)` after tests pass.

## Out of scope

- Per-event admin reminder override (deferred — v1.4+).
- Reminder analytics dashboard (deferred).
- Actual Beat trigger in tests — scheduler configuration only.

## Risks

- Phase 25 (waitlist promote) will reuse the reminder builder for "You're
  in" emails — keep the builder signature compatible with `Signup` only.
- ICS attachment for reminders is deferred to keep the phase scoped;
  existing `GET /signups/{id}/ics` route already emits one.
