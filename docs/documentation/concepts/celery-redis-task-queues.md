# Celery + Redis brokers + Celery Beat

A reference page for the task-queue layer that powers reminders, broadcast
emails, CSV imports, and scheduled cleanup in this app.

## TL;DR

Celery is a Python distributed-task framework. A **producer** (your web
process) enqueues task messages to a **broker** (Redis), **workers** pop
those messages off and execute the task code, and an optional **result
backend** (also Redis here) stores return values. **Celery Beat** is a
separate process that emits scheduled task messages on a cron-like timer.
The whole queue is "fire and (mostly) forget" — the web request returns as
soon as the message is enqueued.

## API surface

### Defining a task

```python
from celery import Celery

celery = Celery(
    "uni_volunteer_scheduler",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
)

@celery.task(name="app.tasks.send_email", bind=True, max_retries=3)
def send_email(self, to: str, subject: str, body: str) -> None:
    try:
        smtp_send(to, subject, body)
    except SMTPException as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

Key decorator options:

| Option | Default | Meaning |
|---|---|---|
| `name` | `module.func` | Stable task name. Pin this — renaming the function silently breaks queued messages. |
| `bind=True` | `False` | First arg becomes `self` (the task instance). Needed for `self.retry()` and `self.request`. |
| `max_retries` | 3 | Caps automatic retries via `self.retry()`. |
| `acks_late` | False | Ack only after success. Combine with `task_reject_on_worker_lost`. |
| `autoretry_for` | () | Tuple of exceptions to auto-retry on. |
| `retry_backoff` | False | Exponential backoff in seconds for autoretry. |
| `default_retry_delay` | 180 | Fallback if `retry(countdown=...)` is omitted. |

### Calling a task

```python
# Async — returns an AsyncResult immediately, worker runs it later
send_email.delay("a@b.com", "Hi", "Body")

# With Celery-specific kwargs (countdown, queue, eta)
send_email.apply_async(
    args=("a@b.com", "Hi", "Body"),
    countdown=30,
    queue="emails",
)

# Sync (test mode only — blocks the caller until the result is ready)
result = send_email.apply(args=(...))
```

### Inspecting results

```python
r = send_email.delay(...)
r.id        # task id (uuid)
r.state     # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
r.ready()   # bool
r.get(timeout=5)   # blocks until done, raises on failure
```

### Beat schedule

```python
from celery.schedules import crontab

celery.conf.beat_schedule = {
    "weekly-digest": {
        "task": "app.celery_app.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
    "every-5-minutes": {
        "task": "app.celery_app.send_reminders_24h",
        "schedule": 300.0,   # plain int/float = seconds
    },
}
```

### CLI

```bash
# Worker
celery -A app.celery_app.celery worker -l info --concurrency=4

# Beat (this app uses RedBeat so the schedule lives in Redis, not on disk)
celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler

# Inspect
celery -A app.celery_app.celery inspect active
celery -A app.celery_app.celery inspect reserved
celery -A app.celery_app.celery inspect stats
```

## Mental model

Hold these four invariants in your head:

1. **The broker is the source of truth for "what's left to do."** If the
   broker (Redis) loses its data, the queue is gone. RDB/AOF persistence
   in Redis matters.
2. **Tasks must be idempotent.** With `acks_late=True` a worker crash will
   re-deliver the message. Without idempotency you'll send the same email
   twice. This app uses a `sent_notifications(signup_id, kind)` unique
   index + `ON CONFLICT DO NOTHING` to enforce "send once."
3. **Beat is a singleton.** Two Beat processes pointing at the same
   schedule will double-fire. RedBeat avoids this by holding a Redis lock
   (`redbeat_lock_timeout=300`); plain `PersistentScheduler` does not.
4. **The web process never executes task code.** It only writes a message
   to Redis. If the worker is down, tasks pile up; the web layer keeps
   responding to HTTP requests as normal.

## Usage in this codebase

| File | Role |
|---|---|
| `backend/app/celery_app.py` | App + broker config, `acks_late=True`, `task_reject_on_worker_lost=True`, RedBeat config, tasks `send_email_notification`, `send_signup_confirmation_email`, `send_broadcast_email`, `weekly_digest`, `expire_pending_signups`, and the `beat_schedule` dict. |
| `backend/app/tasks/reminders.py` | `check_and_send_reminders` — runs every 900s via Beat, scans for signups in the 24h / 2h windows, idempotent via `sent_notifications` unique index. |
| `backend/app/tasks/import_csv.py` | Long-running CSV ingest task — produces progress rows during the run so the admin UI can poll. |
| `backend/app/services/reminder_service.py:203` | Producer side — calls `send_email_notification.delay(...)` after a signup. |
| `backend/app/services/public_signup_service.py:160` | Producer — fires confirmation email task right after a successful signup. |
| `backend/app/services/broadcast_service.py:315` | Producer — fans out a broadcast into one task per recipient. |
| `docker-compose.yml` | Three services: `redis`, `celery_worker`, `celery_beat`. Worker and beat share the backend image; only the command differs. |
| `backend/app/config.py` | `celery_broker_url`, `celery_result_backend`, `redis_url` — all read from env vars, default to `redis://redis:6379/0`. |

### The idempotency pattern actually used

```python
def _dedup_insert(db: Session, signup_id, kind: str) -> bool:
    """Insert into sent_notifications; return True only if the row was
    inserted (first sender wins)."""
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup_id, kind=kind,
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    return result.rowcount == 1
```

The unique index `(signup_id, kind)` is the source of truth: even if the
task is delivered twice (worker crash, retry, late ack), only the first
attempt actually sends the email.

### The retry pattern actually used

The app does *not* use `autoretry_for` everywhere — many tasks catch
exceptions explicitly and log them so a poison message doesn't loop
forever. For transient SMTP errors, `self.retry(exc=exc, countdown=...)`
with `max_retries=3` is the standard.

## Operational concerns

### Broker memory

Redis stores every queued message in RAM. With 100k pending messages
averaging 1KB each, that's 100MB just for the queue. Mitigations:

- Cap input: rate-limit upstream so the queue can't grow unbounded
- Add a worker autoscale rule
- Switch to RabbitMQ or SQS for very large queues (Redis works best for
  ≤ ~1M messages)

### Acknowledgment policy

This app sets `task_acks_late=True` and `task_reject_on_worker_lost=True`:

- **Late ack** → ack happens *after* the task body returns successfully.
  A worker that dies mid-execution will have the message redelivered.
- **Reject on lost** → if the worker process is killed (OOM, SIGKILL),
  Celery rejects the in-flight message so the broker can requeue it.

The price: tasks must be idempotent (covered above). The win: no silent
data loss when a worker pod is recycled.

### Beat reliability

RedBeat stores the schedule and last-run timestamps in Redis under
`redbeat::schedule::<name>`. The lock (`redbeat_lock_timeout=300`)
prevents two Beat processes from double-firing during a deploy where
old + new beat run for ~30s. If you ever see schedule entries with
last-fire timestamps in the future, you have clock drift between Beat
and Redis — fix NTP, don't patch the schedule.

### Concurrency model

- `prefork` (default) — one OS process per worker; CPU-bound friendly,
  high memory cost.
- `gevent` / `eventlet` — coroutine-based; good for IO-bound tasks like
  email sending. The app's worker is IO-bound (network → SMTP) so
  `--pool=gevent --concurrency=50` would scale better than the default
  prefork.
- `solo` — single-threaded; only for tests.

Concurrency interacts with `worker_prefetch_multiplier` (default 4). A
worker grabs `prefetch × concurrency` messages at once. For long tasks,
set `worker_prefetch_multiplier=1` so a slow task doesn't starve
neighbours.

### Observability

- **Flower** — web UI at `:5555`, lists workers, tasks, queues. Not
  deployed in this app but trivial to add.
- **Logs** — `celery worker -l info` writes per-task start/finish lines
  with task id. Pipe to your aggregator.
- **Metrics** — Prometheus exporter (`celery-prometheus-exporter`) for
  queue depth, task duration, success rate.

The most useful alert: **broker queue depth > N for > 5 min**. If
messages are arriving faster than workers can drain them, you're at
risk of an outage.

### Failure modes

| Symptom | Likely cause |
|---|---|
| Tasks "stuck" in PENDING | Worker isn't running, or task name mismatch (renamed function). |
| Same email sent N times | Missing idempotency key (no `_dedup_insert`). |
| Beat double-fires | Two Beat processes without RedBeat / lock. |
| Worker eats all RAM | `prefetch × concurrency` too high, or big payloads pickled into messages. |
| Redis OOM | Queue depth not monitored; messages with large payloads. |
| Mysterious "Lost connection" retries | TCP keepalive mismatch between worker and broker. |

## Glossary

- **Broker** — message bus where tasks are queued. Redis here; RabbitMQ /
  SQS are alternatives.
- **Result backend** — where return values + status live after a task
  completes. Redis here.
- **Worker** — long-running process that pops messages off the broker
  and runs the task function.
- **Beat** — scheduler process that publishes messages on a clock.
- **Task** — a function decorated with `@celery.task`. Has a stable name.
- **AsyncResult** — handle returned by `task.delay()`; you can poll its
  state and result.
- **Prefetch** — how many messages a worker grabs from the broker before
  executing. `prefetch=1` means strictly one in flight per worker.
- **acks_late** — config where the message is ack'd only after the task
  function returns. Trades extra duplicate-delivery risk for at-least-once.
- **Idempotency key** — a value (often a DB unique index) that ensures
  re-running a task is a no-op after the first success.
- **Poison message** — a message that always fails. Without a dead-letter
  queue it can re-loop indefinitely.
- **Dead-letter queue (DLQ)** — a separate queue where Celery dumps
  messages that exceed `max_retries`. Inspect manually.
- **RedBeat** — Celery Beat backend that stores the schedule in Redis
  and uses a Redis lock to allow safe failover.
- **Crontab schedule** — Celery's `crontab(hour=..., minute=...)` helper.
  Standard cron-style scheduling, evaluated in Beat's local time.
- **Exponential backoff** — retry delay `base * 2^attempt`. Stops thunder
  herds on a recovering service.
