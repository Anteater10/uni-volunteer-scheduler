---
phase: 06
plan: 03
name: Cancellation + reschedule email tasks with dedup
wave: 2
depends_on: [01]
files_modified:
  - backend/app/celery_app.py
  - backend/app/routers/signups.py
  - backend/app/routers/slots.py
autonomous: true
requirements:
  - Cancellation email dispatched via Celery task with sent_notifications dedup
  - Reschedule email on slot time change with old reminder row cleanup
  - send_email_notification wired to dedup before Resend call
---

# Plan 06-03: Cancellation + Reschedule Email Tasks

<objective>
Wire cancellation and reschedule emails through the `sent_notifications` dedup layer.
Update `send_email_notification` to INSERT into `sent_notifications` before calling
the email provider. Add reschedule detection in the slot update endpoint.

Purpose: Cancellation emails are already dispatched from the cancel endpoint (phase 0),
but not deduped. Reschedule emails are new. Both need the same ON CONFLICT DO NOTHING
guard.
Output: Cancellation + reschedule emails are exactly-once; slot time changes trigger
reschedule notifications and invalidate prior reminder rows.
</objective>

<must_haves>
- `send_email_notification` task enhanced:
  - When `kind` is provided, INSERT into `sent_notifications` ON CONFLICT DO NOTHING before sending
  - If dedup insert returns 0 rows, skip the send (already sent)
  - On successful send, update `provider_id` in the `sent_notifications` row
- Cancel endpoint (`signups.py`): already calls `send_email_notification.delay(signup_id=..., kind="cancellation")` -- verify dedup works
- Slot update endpoint (`slots.py`): when `start_time` or `end_time` changes:
  - Delete existing `sent_notifications` rows with `kind IN ('reminder_24h', 'reminder_1h')` for all signups on that slot
  - Reset `reminder_24h_sent_at` and `reminder_1h_sent_at` to NULL on affected signups
  - Dispatch `send_email_notification.delay(signup_id=..., kind="reschedule")` for each confirmed signup
- Reschedule email builder already added in plan 02
</must_haves>

<tasks>

<task id="06-03-01" parallel="false">
<action>
Edit `backend/app/celery_app.py` — update `send_email_notification`:

1. Import `pg_insert` (if not already from plan 02) and `SentNotification`.
2. In the `kind is not None` branch, after resolving the signup and builder:
   ```python
   # Dedup: insert before send
   if not _dedup_insert(db, signup.id, kind):
       return  # Already sent by another worker
   ```
3. After successful email send (after `_send_email_via_sendgrid`), update the `sent_notifications` row:
   ```python
   # Update provider_id if Resend returns one (future: swap SendGrid for Resend)
   # For now, leave provider_id NULL until Resend integration in this plan
   ```
4. Keep the existing `Notification` table logging as-is (it serves the user-facing notification feed).
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.celery_app import send_email_notification; print('ok')"</automated>
</verify>
<done>send_email_notification uses dedup insert before sending.</done>
</task>

<task id="06-03-02" parallel="false">
<action>
Edit `backend/app/routers/slots.py` — add reschedule detection:

1. In the slot update endpoint (PUT or PATCH), detect if `start_time` or `end_time` changed.
2. If time changed:
   ```python
   # Invalidate prior reminders so new window triggers fresh ones
   db.query(models.SentNotification).filter(
       models.SentNotification.signup_id.in_(
           db.query(models.Signup.id).filter(
               models.Signup.slot_id == slot.id,
               models.Signup.status == models.SignupStatus.confirmed,
           )
       ),
       models.SentNotification.kind.in_(["reminder_24h", "reminder_1h"]),
   ).delete(synchronize_session=False)

   # Reset denormalized columns
   db.query(models.Signup).filter(
       models.Signup.slot_id == slot.id,
       models.Signup.status == models.SignupStatus.confirmed,
   ).update({
       models.Signup.reminder_24h_sent_at: None,
       models.Signup.reminder_1h_sent_at: None,
   }, synchronize_session=False)

   # Notify affected signups
   confirmed_signups = db.query(models.Signup).filter(
       models.Signup.slot_id == slot.id,
       models.Signup.status == models.SignupStatus.confirmed,
   ).all()
   ```
3. After commit, dispatch reschedule emails:
   ```python
   for s in confirmed_signups:
       send_email_notification.delay(signup_id=str(s.id), kind="reschedule")
   ```
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.routers.slots import router; print('ok')"</automated>
</verify>
<done>Slot time changes invalidate reminders and dispatch reschedule emails.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-06 | DoS (cost) | Double cancellation email on rapid cancel clicks | mitigate | sent_notifications UNIQUE(signup_id, 'cancellation') prevents second send |
| T-06-07 | Tampering | Reschedule clears reminders but email fails | accept | Reminder rows are deleted optimistically; next beat cycle will re-insert if still in window |
</threat_model>

<verification>
- Cancel endpoint dedup: calling cancel twice produces one `sent_notifications` row with kind='cancellation'
- Slot time change: old reminder rows deleted, new reschedule row inserted
- `send_email_notification` checks dedup before sending
</verification>

<success_criteria>
Cancellation and reschedule emails are exactly-once. Slot rescheduling invalidates old reminders so new-window reminders fire correctly.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-03-SUMMARY.md`
</output>
