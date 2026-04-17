# Phase 24: Scheduled reminder emails — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Automatic reminder emails: kickoff (Monday 07:00 PT of event week), 24h pre-event, 2h pre-event. Idempotent. Opt-out per volunteer. Quiet hours 21:00–07:00 PT. Celery Beat with RedBeat scheduler (already configured in `backend/app/celery_app.py`).

</domain>

<decisions>
## Implementation Decisions

### Reminder kinds
- `kickoff` — Monday 07:00 PT of event's week.
- `pre_24h` — 24 hours before `slot.starts_at`.
- `pre_2h` — 2 hours before `slot.starts_at`.

### Scheduling strategy
Run a single Celery Beat task every 15 minutes: `check_and_send_reminders`.
The task:
1. Pulls all future slots within the next 30 hours (covers kickoff + pre_24h + pre_2h windows).
2. For each slot, walks confirmed signups.
3. For each (signup, kind) tuple determines whether "now" is within the kind's send window:
   - `kickoff`: Monday 07:00 PT of slot's week, ±15 min drift.
   - `pre_24h`: `slot.starts_at - 24h ± 15 min`.
   - `pre_2h`: `slot.starts_at - 2h ± 15 min`.
4. If yes, tries `_dedup_insert(signup_id, f"reminder_{kind}")`. Only the winner sends.
5. Checks volunteer preferences + quiet hours before sending.

### Idempotency
Reuse the existing `sent_notifications` table + `_dedup_insert` helper in `celery_app.py`. Add kinds: `reminder_kickoff`, `reminder_pre_24h`, `reminder_pre_2h`.

### Opt-out
New table `volunteer_preferences` keyed by `volunteer_email` (string PK). Columns: `email_reminders_enabled` bool default true, `sms_opt_in` bool default false (for Phase 27), `created_at`, `updated_at`. Upsert on manage-page toggle.

### Quiet hours
Hard rule: between 21:00 and 07:00 PT, skip sending. If a window would fire during quiet hours, defer: kickoff waits until 07:00 PT; pre_24h slips to the next 15-min tick outside quiet hours; pre_2h is edge-case (if event is 07:00 AM, the 2h reminder fires at 05:00 — within quiet hours — we skip it entirely, since the 24h one already fired).

### Email templates
New `backend/app/emails/reminder.py` builder (mirrors existing `BUILDERS` pattern in `backend/app/emails/`). One builder per kind with plain + HTML bodies. Include unsubscribe link (links to manage page with mailer-token prefilled), event context (title, slot start time in PT, venue).

### Admin "Reminders" page
- `/admin/reminders` — lists upcoming reminders for next 7 days (computed preview, no writes).
- "Send now" button per row that short-circuits the scheduler for that (signup, kind) — writes the idempotency row + triggers the email task directly.

### Frontend
- `ManageSignupsPage.jsx` — "Email reminder preferences" section: toggle "send me reminder emails" (default on) → hits `PUT /signups/preferences`.
- New `/admin/reminders` page `frontend/src/pages/admin/AdminRemindersPage.jsx` (or `RemindersSection.jsx` matching other admin sections). Wire into admin nav.

### API
- `GET /signups/preferences?manage_token=...` — read.
- `PUT /signups/preferences` — update (requires manage_token).
- `GET /admin/reminders/upcoming?days=7` — list.
- `POST /admin/reminders/send-now` — `{signup_id, kind}`.

### Tests
- `test_reminder_service.py`: window math (kickoff/24h/2h drift), idempotency, opt-out honored, quiet hours skip.
- `test_volunteer_preferences_service.py`: upsert, read.
- Frontend: preferences toggle state + API call; AdminRemindersPage list + send-now.

</decisions>

<code_context>
## Existing Code Insights
- `backend/app/celery_app.py` — Celery app + RedBeat scheduler + `_dedup_insert` already in place. Extend via `celery.conf.beat_schedule` dict.
- `backend/app/emails/` — email builder pattern (BUILDERS dict).
- `sent_notifications` table — idempotency already modeled.
- `frontend/src/pages/public/ManageSignupsPage.jsx` — target for opt-out toggle.
- `backend/app/services/public_signup_service.py` — volunteer_email lookup patterns.

</code_context>

<specifics>
## Specific Ideas
- Quiet hours are America/Los_Angeles (PT). Use zoneinfo.
- 15-min drift window is explicit so we're not hunting for exact-second ticks.

</specifics>

<deferred>
## Deferred Ideas
- Per-event admin override ("don't send reminders for this event") — not in v1.3.
- Reminder analytics dashboard — not in v1.3.

</deferred>

---

*Phase: 24-scheduled-reminder-emails*
