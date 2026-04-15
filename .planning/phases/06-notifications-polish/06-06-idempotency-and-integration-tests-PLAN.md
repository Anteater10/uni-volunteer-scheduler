---
phase: 06
plan: 06
name: Idempotency + beat-overlap + cancellation latency tests
wave: 3
depends_on: [02, 03]
files_modified:
  - backend/tests/test_notifications_phase6.py
autonomous: true
requirements:
  - Idempotency test proves double-run produces one send
  - Beat-overlap test proves 5 concurrent runs produce one send
  - Cancellation latency test proves task enqueued from cancel endpoint
  - All tests use mocked Resend/SendGrid (no real emails)
---

# Plan 06-06: Idempotency & Integration Tests

<objective>
Write the test suite that proves phase 6 success criteria: exactly-once delivery under
double-run, concurrent beat fires, and cancellation dispatch. All tests mock the email
provider and use the real database with savepoint isolation.

Purpose: ROADMAP success criteria 2 and 4 require provable idempotency.
Output: Test file with 5+ tests covering all dedup paths.
</objective>

<must_haves>
- Test: `test_reminder_24h_idempotency` — call `send_reminders_24h` twice against the same signup; assert exactly 1 row in `sent_notifications` with kind='reminder_24h', exactly 1 call to `send_email_notification.delay`
- Test: `test_reminder_1h_idempotency` — same for 1h reminder
- Test: `test_beat_overlap_5_concurrent` — spawn 5 concurrent calls to `send_reminders_24h` using threads or asyncio; assert exactly 1 `sent_notifications` row and 1 email dispatch
- Test: `test_cancellation_dispatches_task` — call cancel endpoint; assert `send_email_notification.delay` called with `kind='cancellation'`
- Test: `test_reschedule_invalidates_reminders` — send 24h reminder, then update slot time; assert old `sent_notifications` reminder row deleted and `reminder_24h_sent_at` reset to NULL
- Test: `test_daily_limit_blocks_sends` — set `RESEND_DAILY_LIMIT=1`, send one email, attempt second; assert second is skipped
- All tests use `@pytest.fixture` with DB savepoint rollback (existing conftest pattern from phase 0 plan 06)
- `send_email_notification.delay` mocked via `unittest.mock.patch` (no real Celery worker)
- `_send_email_via_sendgrid` mocked (no real email sends)
</must_haves>

<tasks>

<task id="06-06-01" parallel="false">
<action>
Create `backend/tests/test_notifications_phase6.py`:

1. Import fixtures from existing conftest (db session with savepoint, test users, test events/slots).

2. Helper: `_create_confirmed_signup(db, user, slot)` — creates a Signup with status=confirmed and a slot starting in ~24h.

3. Implement all 6 tests listed in must_haves:

   For `test_beat_overlap_5_concurrent`:
   ```python
   import concurrent.futures

   def test_beat_overlap_5_concurrent(db, ...):
       # Create signup with slot in 24h window
       # Patch send_email_notification.delay
       with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
           futures = [executor.submit(send_reminders_24h) for _ in range(5)]
           concurrent.futures.wait(futures)
       # Assert exactly 1 sent_notifications row
       count = db.query(func.count(SentNotification.id)).filter(
           SentNotification.signup_id == signup.id,
           SentNotification.kind == "reminder_24h"
       ).scalar()
       assert count == 1
   ```

   Note: Concurrent test requires each thread to use its own DB session (SessionLocal()),
   not the test session with savepoint. Use a separate test database or mark as
   `@pytest.mark.integration` if savepoint isolation conflicts with concurrent access.

4. For `test_daily_limit_blocks_sends`:
   - Monkeypatch `settings.resend_daily_limit = 1`
   - Insert 1 `sent_notifications` row for today
   - Call `send_email_notification` — assert it returns early without sending
</action>
<verify>
  <automated>cd /home/kael/work/uni-volunteer-scheduler/backend && python -m pytest tests/test_notifications_phase6.py -v --tb=short 2>&1 | tail -20</automated>
</verify>
<done>All 6 tests pass, proving exactly-once delivery guarantees.</done>
</task>

</tasks>

<threat_model>
| Threat ID | Category | Component | Disposition | Mitigation |
|-----------|----------|-----------|-------------|------------|
| T-06-12 | Tampering | Test uses mocked provider, misses real API failure modes | accept | Integration with real Resend is deferred to staging; unit tests cover logic paths |
</threat_model>

<verification>
- `pytest tests/test_notifications_phase6.py` passes with 6+ tests
- No real emails sent during test run
- Concurrent test proves thread-safety of dedup
</verification>

<success_criteria>
All ROADMAP Phase 6 success criteria are covered by automated tests. CI will catch idempotency regressions.
</success_criteria>

<output>
After completion, create `.planning/phases/06-notifications-polish/06-06-SUMMARY.md`
</output>
