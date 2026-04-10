---
phase: 06
plan: 05
name: Admin notifications endpoint + Resend monitoring
wave: 3
depends_on: [01, 02, 03]
files_modified:
  - backend/app/routers/admin.py
  - backend/app/config.py
  - backend/app/celery_app.py
autonomous: true
requirements:
  - GET /admin/notifications/recent returns last 100 sent_notifications
  - Resend free-tier 80% threshold warning logged to stderr
  - provider_id stored for Resend status lookup
---

# Plan 06-05: Admin Notifications Endpoint + Resend Monitoring

<objective>
Add an admin-only endpoint to view recent sent notifications (reused in phase 7 dashboard),
and wire Resend free-tier usage monitoring with an 80% threshold warning.

Purpose: Organizers and admins need visibility into what emails have been sent and whether
the system is approaching Resend rate limits.
Output: `/admin/notifications/recent` endpoint + stderr warning at 80% of daily limit.
</objective>

<must_haves>
- `GET /admin/notifications/recent`:
  - Admin or organizer role required
  - Returns last 100 `sent_notifications` rows ordered by `sent_at DESC`
  - Response includes: `id`, `signup_id`, `kind`, `sent_at`, `provider_id`
  - Pydantic response schema `SentNotificationRead`
- Resend daily usage monitoring:
  - Track daily send count via `sent_notifications` table (COUNT WHERE sent_at >= today midnight)
  - Config: `RESEND_DAILY_LIMIT` (default 100, free tier)
  - When daily count >= 80% of limit, log WARNING to stderr/logger
  - When daily count >= limit, log ERROR and skip further sends (graceful degradation)
- `_send_email_via_sendgrid` renamed/aliased to `_send_email` with Resend SDK swap path noted as `# TODO(resend): swap SendGrid client for Resend SDK`
</must_haves>

<tasks>

<task id="06-05-01" parallel="false">
<action>
1. Add Pydantic schema `SentNotificationRead` to `backend/app/schemas.py`:
   ```python
   class SentNotificationRead(BaseModel):
       id: uuid.UUID
       signup_id: uuid.UUID
       kind: str
       sent_at: datetime
       provider_id: str | None
       model_config = ConfigDict(from_attributes=True)
   ```

2. Add endpoint to `backend/app/routers/admin.py`:
   ```python
   @router.get("/notifications/recent", response_model=List[SentNotificationRead])
   def recent_notifications(
       db: Session = Depends(get_db),
       current_user: models.User = Depends(get_current_user),
   ):
       if current_user.role not in (models.UserRole.admin, models.UserRole.organizer):
           raise HTTPException(status_code=403, detail="Admin or organizer required")
       return (
           db.query(models.SentNotification)
           .order_by(models.SentNotification.sent_at.desc())
           .limit(100)
           .all()
       )
   ```
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.routers.admin import router; print('ok')"</automated>
</verify>
<done>Admin notifications endpoint returns last 100 sent_notifications.</done>
</task>

<task id="06-05-02" parallel="false">
<action>
Add Resend monitoring to `backend/app/celery_app.py`:

1. Add to `backend/app/config.py`:
   ```python
   resend_daily_limit: int = Field(default=100, env="RESEND_DAILY_LIMIT")
   ```

2. Add monitoring helper in `celery_app.py`:
   ```python
   import logging
   logger = logging.getLogger(__name__)

   def _check_daily_send_limit(db: Session) -> bool:
       """Check if daily send limit is approaching. Returns False if limit exceeded."""
       today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
       count = db.query(func.count(models.SentNotification.id)).filter(
           models.SentNotification.sent_at >= today_start
       ).scalar() or 0

       limit = settings.resend_daily_limit
       if count >= limit:
           logger.error("Resend daily limit reached (%d/%d). Skipping further sends.", count, limit)
           return False
       if count >= int(limit * 0.8):
           logger.warning("Resend daily usage at %d%% (%d/%d).", int(count / limit * 100), count, limit)
       return True
   ```

3. Call `_check_daily_send_limit(db)` at the top of `send_email_notification` — if False, return early without sending.
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -c "from app.celery_app import send_email_notification; print('ok')"</automated>
</verify>
<done>Daily send monitoring with 80% warning and 100% circuit breaker.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-10 | DoS (cost) | Exceeding Resend free-tier burns money | mitigate | Daily count check + circuit breaker at 100% of limit |
| T-06-11 | Info Disclosure | Admin endpoint leaks signup data | mitigate | Only admin/organizer can access; response contains IDs not PII |
</threat_model>

<verification>
- `GET /admin/notifications/recent` returns 200 for admin, 403 for participant
- Daily limit warning logged at 80%
- Sends blocked at 100% of daily limit
</verification>

<success_criteria>
Admins can monitor email delivery; system gracefully degrades when approaching Resend limits.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-05-SUMMARY.md`
</output>
