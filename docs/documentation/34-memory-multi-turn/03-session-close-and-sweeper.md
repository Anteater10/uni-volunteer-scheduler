# Sub-phase 34-03 — Session close endpoint + idle sweeper

This document specifies the two complementary paths that retire a copilot
session into the long-term profile-extraction pipeline: an explicit HTTP
close call from the frontend, and a Celery-driven idle sweep that catches
sessions the frontend never explicitly closes.

## Surface

### `POST /api/v1/copilot/sessions/{session_id}/close`

- **Auth:** required (`Authorization: Bearer …`). Same role guard as the
  rest of the copilot surface — admin and organizer only. Volunteer/
  participant accounts get 403.
- **Feature flag:** the whole copilot router 404s when
  `settings.copilot_enabled` is false, so the close endpoint vanishes
  along with everything else.
- **Ownership:** sessions owned by another user 404 (not 403) so cross-
  user existence is not observable.
- **Response:** `204 No Content`, always (success and no-op idempotent
  repeat both look the same to the client).

### Side effects

1. If `closed_at IS NULL`, set `closed_at = now()` in UTC and commit.
2. Enqueue `extract_profile_facts.delay(str(session_id))` exactly once.
3. If `closed_at IS NOT NULL` at request time, short-circuit — no
   timestamp mutation, no extractor enqueue, still 204.

The idempotency guard makes the endpoint safe to call from naive
frontend logic (e.g. `beforeunload` + drawer-close listener firing in
quick succession) without producing duplicate extraction jobs.

## Idle sweeper

### `app.tasks.extract_profile.sweep_idle_sessions`

A Celery beat job registered on a 300-second (5-minute) cadence:

```python
celery.conf.beat_schedule["copilot-sweep-idle-sessions"] = {
    "task": "app.tasks.extract_profile.sweep_idle_sessions",
    "schedule": 300.0,
}
```

Behaviour:

1. Compute `cutoff = now() - 30 minutes`.
2. Select all `copilot_sessions` rows where `closed_at IS NULL`
   AND `last_message_at < cutoff`.
3. Stamp `closed_at = now()` on each row in a single commit.
4. After the commit, enqueue `extract_profile_facts.delay(str(sess.id))`
   for each newly-closed session.
5. Return the count of sessions closed (used by tests and observability).

The 30-minute idle threshold balances two concerns: long enough that
genuine "user took a phone call" pauses don't truncate a session
prematurely; short enough that abandoned sessions are not still sitting
unextracted hours later. The 5-minute beat cadence keeps the actual
close-to-extract latency bounded at ≤35 minutes.

## `last_message_at` — the activity signal

The sweeper relies on `copilot_sessions.last_message_at` being kept
fresh. That column is bumped to `now()` inside the same transaction as
the user-message insert in the `POST /sessions/{id}/messages` handler.
This co-located write is important — putting the timestamp update on a
separate commit would let a partial failure leave a session with a stale
`last_message_at` and trigger an early close.

Sessions are created with `last_message_at = func.now()` (the column's
server default), so a fresh session that never gets a user message will
still age out of the idle window normally — no special-case handling
needed.

## Race-condition analysis

The two close paths can in principle race:

- **HTTP close runs first, then sweeper:** the sweeper's `WHERE
  closed_at IS NULL` filter excludes the now-closed row, so no
  duplicate enqueue. Safe.
- **Sweeper runs first, then HTTP close:** the HTTP handler reloads
  the session, sees `closed_at IS NOT NULL`, and short-circuits. Safe.
- **Two HTTP close calls in parallel:** each transaction sees the row's
  state as it was when the request began. SQLAlchemy's default isolation
  (PostgreSQL `READ COMMITTED`) means the second transaction will see
  the first's commit only after that first transaction completes; the
  loser will then hit the idempotency guard on retry. Worst case is a
  double-enqueue, which is itself idempotent because the future Task 19
  extractor checks `profile_extracted_at` before doing any work.

Within a single sweeper run, all newly-closed sessions are committed
before any extractor delays are sent, so a crash between the commit and
the first `.delay()` leaves the DB consistent but skips enqueues for
that batch. The next sweep pass (5 minutes later) re-detects nothing —
those rows now have `closed_at IS NOT NULL` and are filtered out. The
forthcoming `profile_extracted_at` check inside `extract_profile_facts`
(landing in 34-06) is the canonical exactly-once gate; the sweeper just
needs to avoid obvious duplication.

## Test coverage

- `backend/tests/copilot/api/test_session_close_endpoint.py` — 6 tests:
  basic close + enqueue, idempotency, cross-user 404, feature-flag 404,
  volunteer 403, and the `last_message_at` bump on message append.
- `backend/tests/copilot/tasks/test_sweep_idle_sessions.py` — 4 tests:
  idle session closed + enqueued, fresh session skipped, already-closed
  session not re-enqueued, multi-session batch handling.

All tests use the standard `client` + `db_session` fixtures and the
`make_user` / `auth_headers` helpers; no new fixtures introduced. The
sweeper tests monkeypatch `SessionLocal` to share the test transaction
so assertions can observe writes immediately without a separate commit.
