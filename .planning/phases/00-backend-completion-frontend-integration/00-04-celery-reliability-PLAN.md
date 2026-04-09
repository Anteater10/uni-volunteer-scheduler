---
phase: 00-backend-completion-frontend-integration
plan: 04
type: execute
wave: 2
depends_on: [02]
files_modified:
  - backend/requirements.txt
  - backend/app/celery_app.py
  - backend/app/routers/signups.py
autonomous: true
requirements:
  - CELERY-01
  - CELERY-02
  - CELERY-04
must_haves:
  truths:
    - "celery-redbeat==2.3.3 is pinned in requirements.txt"
    - "celery_app sets redbeat_redis_url and redbeat_lock_timeout"
    - "schedule_reminders filters on reminder_sent == False and sets it to True after SendGrid success"
    - "send_email_notification has autoretry_for=(Exception,), retry_backoff=True, max_retries=3"
    - "schedule_reminders has the same retry config"
    - "Running schedule_reminders twice against the same window produces no duplicate sends (asserted in test)"
  artifacts:
    - path: "backend/app/celery_app.py"
      provides: "redbeat scheduler config, reminder_sent idempotency, retry config"
      contains: "redbeat_redis_url"
  key_links:
    - from: "backend/app/celery_app.py::schedule_reminders"
      to: "backend/app/models.py::Signup.reminder_sent"
      via: "filter + update inside the task"
      pattern: "reminder_sent"
    - from: "backend/app/celery_app.py"
      to: "celery-redbeat scheduler"
      via: "app.conf.beat_scheduler or CLI -S flag documented in docstring"
      pattern: "redbeat"
---

<objective>
Make the Celery reminder pipeline production-reliable: swap in celery-redbeat for distributed beat scheduling, add `reminder_sent` idempotency to `schedule_reminders`, and configure retry backoff on both `send_email_notification` and `schedule_reminders`.

Purpose: Running `schedule_reminders` twice under the current code sends duplicate emails. Plan 02 already added the `reminder_sent` column; this plan wires it.
Output: Idempotent reminder pipeline that survives beat restarts and duplicate dispatches.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/00-02-SUMMARY.md
@backend/app/celery_app.py
@backend/app/models.py
@backend/app/routers/signups.py
@backend/requirements.txt
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pin celery-redbeat and wire redbeat scheduler in celery_app.py</name>
  <files>backend/requirements.txt, backend/app/celery_app.py</files>
  <read_first>
    - backend/requirements.txt (current celery-related pins)
    - backend/app/celery_app.py (full file — beat schedule, reminder window, SendGrid helper, task definitions)
    - 00-RESEARCH.md "Pattern 4: celery-redbeat Configuration" (~line 430) and "Pitfall 4: Celery-redbeat Requires REDIS_URL for Beat Only"
  </read_first>
  <action>
    1. Append `celery-redbeat==2.3.3` to `backend/requirements.txt` if not already present (Plan 01 may have added it — check first).
    2. In `backend/app/celery_app.py`, after the `celery = Celery(...)` construction, add:
       ```python
       celery.conf.update(
           redbeat_redis_url=settings.redis_url,
           redbeat_lock_timeout=300,
           beat_scheduler="redbeat.RedBeatScheduler",
           task_acks_late=True,
           task_reject_on_worker_lost=True,
       )
       ```
    3. Keep the existing `beat_schedule` dict — redbeat reads it automatically on first run.
    4. Update the module docstring at the top of the file to note: `# Start beat with: celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler`.
    5. In `docker-compose.yml` beat service command (if this plan is allowed to touch it — check CONTEXT.md; if not explicit, update only the docstring comment and note in SUMMARY that docker-compose update is a follow-up). Actually: `docker-compose.yml` is NOT in `files_modified` for this plan — leave it and add a `# TODO(phase0-infra)` line in celery_app.py docstring flagging the compose update as a Plan 07 CI concern.
  </action>
  <verify>
    <automated>grep -q "celery-redbeat==2.3.3" backend/requirements.txt && grep -q "redbeat_redis_url" backend/app/celery_app.py && grep -q "beat_scheduler" backend/app/celery_app.py && cd backend && python -c "from app.celery_app import celery; assert celery.conf.beat_scheduler == 'redbeat.RedBeatScheduler'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "celery-redbeat==2.3.3" backend/requirements.txt` succeeds
    - `grep -q "redbeat_redis_url" backend/app/celery_app.py` succeeds
    - `grep -q 'beat_scheduler="redbeat.RedBeatScheduler"' backend/app/celery_app.py` succeeds
    - `grep -q "redbeat_lock_timeout=300" backend/app/celery_app.py` succeeds
    - `python -c "from app.celery_app import celery; assert celery.conf.beat_scheduler == 'redbeat.RedBeatScheduler'"` from `backend/` exits 0
  </acceptance_criteria>
  <done>redbeat is pinned and configured; celery app imports cleanly.</done>
</task>

<task type="auto">
  <name>Task 2: Add reminder_sent idempotency and retry config to reminder + email tasks</name>
  <files>backend/app/celery_app.py</files>
  <read_first>
    - backend/app/celery_app.py (post Task 1 + Plan 02 changes — find `schedule_reminders` and `send_email_notification` task definitions)
    - backend/app/models.py (Signup.reminder_sent column added in Plan 02)
    - 00-CONTEXT.md "Celery Reliability" decision (retries config + reminder_sent flag)
    - 00-RESEARCH.md "Pitfall 5: freezegun does not patch Celery's internal scheduler clock"
  </read_first>
  <action>
    1. Change the `@celery.task` decorator on `schedule_reminders` to:
       ```python
       @celery.task(
           bind=True,
           autoretry_for=(Exception,),
           retry_backoff=True,
           retry_backoff_max=600,
           retry_jitter=True,
           max_retries=3,
       )
       def schedule_reminders(self):
           ...
       ```
    2. Inside `schedule_reminders`:
       - Open a DB session.
       - Query: `Signup` rows where `status == SignupStatus.confirmed` AND `reminder_sent == False` AND the joined `Slot.start_time` falls inside `[now+24h, now+24h+5min]` (use timezone-aware `datetime.now(timezone.utc)`).
       - For each matching row, call `send_email_notification.delay(signup_id=s.id, kind="reminder_24h")` THEN set `s.reminder_sent = True`. Commit the flag BEFORE returning (first-write-wins — if another beat process claimed the row, its update wins and the second call sees `reminder_sent=True` on next query).
       - Use `SELECT ... FOR UPDATE SKIP LOCKED` in the query to prevent double-claim under concurrent beats:
         ```python
         rows = db.query(Signup).join(Slot).filter(...).with_for_update(skip_locked=True).all()
         ```
    3. Change the `@celery.task` decorator on `send_email_notification` the same way (autoretry, backoff, max_retries=3). Inside the task, if SendGrid returns a success status, write a `Notification` row (existing behavior) — do NOT set `reminder_sent` here (the scheduler owns that flag).
    4. Add a brief docstring to `schedule_reminders` explaining the idempotency contract: "Running this task twice against the same signup produces at most one reminder email thanks to the `reminder_sent` flag and SELECT FOR UPDATE SKIP LOCKED."
  </action>
  <verify>
    <automated>grep -q "autoretry_for=(Exception,)" backend/app/celery_app.py && grep -q "retry_backoff=True" backend/app/celery_app.py && grep -q "max_retries=3" backend/app/celery_app.py && grep -q "reminder_sent" backend/app/celery_app.py && grep -q "skip_locked" backend/app/celery_app.py && cd backend && python -c "from app.celery_app import schedule_reminders, send_email_notification; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "autoretry_for=(Exception,)" backend/app/celery_app.py` returns ≥ 2
    - `grep -c "max_retries=3" backend/app/celery_app.py` returns ≥ 2
    - `grep -q "reminder_sent == False\|reminder_sent.is_(False)\|Signup.reminder_sent" backend/app/celery_app.py` succeeds
    - `grep -q "skip_locked=True" backend/app/celery_app.py` succeeds
    - `grep -q "reminder_24h" backend/app/celery_app.py` succeeds (kind string matches Plan 06 tests)
    - `python -c "from app.celery_app import schedule_reminders, send_email_notification"` exits 0
  </acceptance_criteria>
  <done>Running schedule_reminders twice against the same window writes the flag once, enqueues one email per signup, and retries on transient errors up to 3 times.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Celery beat → worker | Task dispatch; duplicate dispatch is the main DoS-cost vector |
| Worker → SendGrid | Outbound HTTP; retry storm risk |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-14 | Denial of Service (cost) | Duplicate reminder emails burning Resend/SendGrid quota | mitigate | `reminder_sent` flag + `SELECT FOR UPDATE SKIP LOCKED` + redbeat distributed lock; three independent layers |
| T-00-15 | Denial of Service | Transient SendGrid failure floods logs with errors | mitigate | `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3`, `retry_backoff_max=600` |
| T-00-16 | Tampering | Race between two beat schedulers reading the same row | mitigate | `SELECT ... FOR UPDATE SKIP LOCKED` ensures at most one worker claims a given signup |
| T-00-17 | Information Disclosure | Celery task logs reminder email body | accept | Existing `logger.exception` pattern logs stack not body; no change |
</threat_model>

<verification>
- `grep -q "redbeat" backend/app/celery_app.py` succeeds
- `grep -c "max_retries=3" backend/app/celery_app.py` ≥ 2
- `grep -q "skip_locked" backend/app/celery_app.py` succeeds
- `python -c "from app.celery_app import celery, schedule_reminders"` exits 0
- (Plan 06 will add the idempotency integration test that proves duplicate runs produce one email)
</verification>

<success_criteria>
Redbeat pinned and wired; reminder task is idempotent via `reminder_sent` + SKIP LOCKED; retry config applied to both email-dispatching tasks.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-04-SUMMARY.md`
</output>
