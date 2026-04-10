---
phase: 06
plan: 02
name: Idempotent 24h + 1h reminder tasks with sent_notifications dedup
wave: 2
depends_on: [01]
files_modified:
  - backend/app/celery_app.py
  - backend/app/emails.py
autonomous: true
requirements:
  - 24h reminder fires for confirmed signups in [now+23h45m, now+24h15m] window
  - 1h reminder fires for confirmed signups in [now+45m, now+75m] window
  - Dedup via INSERT INTO sent_notifications ON CONFLICT DO NOTHING before Resend call
  - Denormalized reminder_*_sent_at updated after successful send
  - 1h reminder respects Event.reminder_1h_enabled toggle
---

# Plan 06-02: Idempotent 24h + 1h Reminder Tasks

<objective>
Rewrite `schedule_reminders` into two separate beat tasks (`send_reminders_24h` and
`send_reminders_1h`) that use `sent_notifications` INSERT-before-send dedup instead of
the existing `reminder_sent` boolean flag. Add `reminder_1h` email builder.

Purpose: The existing `schedule_reminders` task uses a boolean flag which is racy under
concurrent beat fires. The `sent_notifications` table with ON CONFLICT DO NOTHING
provides database-level exactly-once guarantee.
Output: Two beat tasks that provably never double-send, even under 5 concurrent fires.
</objective>

<must_haves>
- `send_reminders_24h` Celery beat task (every 5 min):
  - Queries `confirmed` signups where slot starts in `[now+23h45m, now+24h15m]` AND `reminder_24h_sent_at IS NULL`
  - For each signup: INSERT into `sent_notifications(signup_id, kind='reminder_24h')` with ON CONFLICT DO NOTHING
  - If insert returns 1 row affected: call Resend (via `send_email_notification.delay`), update `provider_id`, set `signup.reminder_24h_sent_at = now()`
  - If insert returns 0 rows: skip (already sent by another worker)
  - Uses SELECT FOR UPDATE SKIP LOCKED on signup rows
- `send_reminders_1h` Celery beat task (every 5 min):
  - Same pattern, window `[now+45m, now+75m]`, kind `'reminder_1h'`
  - Skips signups where joined `Event.reminder_1h_enabled == False`
  - Sets `signup.reminder_1h_sent_at`
- `reminder_1h` email builder added to `emails.py` and `BUILDERS` dict
- Old `schedule_reminders` task removed or aliased
- Beat schedule updated with both tasks
</must_haves>

<tasks>

<task id="06-02-01" parallel="false">
<action>
Edit `backend/app/emails.py`:

1. Add `send_reminder_1h` builder (shared template with 24h but different lead_time wording):
   ```python
   def send_reminder_1h(signup: models.Signup) -> dict:
       user = signup.user
       slot = signup.slot
       event = slot.event
       subject = f"Starting soon: volunteer slot for '{event.title}'"
       body = (
           f"Hi {user.name},\n\n"
           f"Your volunteer slot starts in about 1 hour:\n"
           f"- Event: {event.title}\n"
           f"- When: {_fmt_when(slot)}\n"
           f"- Where: {event.location or 'TBD'}\n\n"
           "See you there!"
       )
       return {"to": user.email, "subject": subject, "body": body}
   ```

2. Add `send_reschedule` builder:
   ```python
   def send_reschedule(signup: models.Signup) -> dict:
       user = signup.user
       slot = signup.slot
       event = slot.event
       subject = f"Schedule change: '{event.title}'"
       body = (
           f"Hi {user.name},\n\n"
           f"The time for your volunteer slot has changed:\n"
           f"- Event: {event.title}\n"
           f"- New time: {_fmt_when(slot)}\n"
           f"- Where: {event.location or 'TBD'}\n\n"
           "If you can no longer attend, please cancel your signup."
       )
       return {"to": user.email, "subject": subject, "body": body}
   ```

3. Update `BUILDERS` dict to include `reminder_1h` and `reschedule`.
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.emails import BUILDERS; assert 'reminder_1h' in BUILDERS and 'reschedule' in BUILDERS; print('ok')"</automated>
</verify>
<done>All 5 email builders registered in BUILDERS dict.</done>
</task>

<task id="06-02-02" parallel="false">
<action>
Rewrite `backend/app/celery_app.py` reminder logic:

1. Remove old `schedule_reminders` task.

2. Add helper function for dedup insert:
   ```python
   from sqlalchemy.dialects.postgresql import insert as pg_insert

   def _dedup_insert(db: Session, signup_id, kind: str) -> bool:
       """Insert into sent_notifications; return True if row was inserted (first sender wins)."""
       stmt = pg_insert(models.SentNotification).values(
           signup_id=signup_id, kind=kind
       ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
       result = db.execute(stmt)
       return result.rowcount == 1
   ```

3. Add `send_reminders_24h` task:
   ```python
   @celery.task(bind=True, autoretry_for=(Exception,), retry_backoff=True,
                retry_backoff_max=600, retry_jitter=True, max_retries=3)
   def send_reminders_24h(self) -> None:
       db = SessionLocal()
       try:
           now = datetime.now(timezone.utc)
           window_start = now + timedelta(hours=23, minutes=45)
           window_end = now + timedelta(hours=24, minutes=15)
           signups = (
               db.query(models.Signup).join(models.Slot)
               .filter(
                   models.Signup.status == models.SignupStatus.confirmed,
                   models.Signup.reminder_24h_sent_at.is_(None),
                   models.Slot.start_time.between(window_start, window_end),
               )
               .with_for_update(skip_locked=True).all()
           )
           for s in signups:
               if _dedup_insert(db, s.id, "reminder_24h"):
                   send_email_notification.delay(signup_id=str(s.id), kind="reminder_24h")
                   s.reminder_24h_sent_at = now
           db.commit()
       finally:
           db.close()
   ```

4. Add `send_reminders_1h` task (same pattern, different window, checks `Event.reminder_1h_enabled`):
   - Window: `[now+45m, now+75m]`
   - Additional filter: `.join(models.Event).filter(models.Event.reminder_1h_enabled == True)`
   - Kind: `reminder_1h`, sets `reminder_1h_sent_at`

5. Update beat schedule:
   ```python
   celery.conf.beat_schedule = {
       "send-reminders-24h-every-5-minutes": {
           "task": "app.celery_app.send_reminders_24h",
           "schedule": 300.0,
       },
       "send-reminders-1h-every-5-minutes": {
           "task": "app.celery_app.send_reminders_1h",
           "schedule": 300.0,
       },
       "weekly-digest-every-monday-8am": {
           "task": "app.celery_app.weekly_digest",
           "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
       },
   }
   ```
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.celery_app import send_reminders_24h, send_reminders_1h; print('ok')"</automated>
</verify>
<done>Both reminder tasks use sent_notifications dedup; old schedule_reminders removed; beat schedule updated.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-03 | DoS (cost) | Duplicate reminder emails burning Resend quota | mitigate | INSERT ON CONFLICT DO NOTHING + SELECT FOR UPDATE SKIP LOCKED + reminder_*_sent_at column = three independent layers |
| T-06-04 | DoS | Retry storm on Resend outage | mitigate | max_retries=3, retry_backoff_max=600, retry_jitter=True |
| T-06-05 | Tampering | Race between concurrent beat workers | mitigate | SKIP LOCKED + DB-level unique constraint = at most one sender per (signup, kind) |
</threat_model>

<verification>
- `send_reminders_24h` and `send_reminders_1h` importable
- Beat schedule contains both tasks at 300s interval
- `_dedup_insert` uses ON CONFLICT DO NOTHING
- Old `schedule_reminders` task is removed
</verification>

<success_criteria>
Exactly-once reminder delivery for both 24h and 1h windows, even under concurrent beat fires.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-02-SUMMARY.md`
</output>
