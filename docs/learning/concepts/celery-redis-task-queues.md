# Celery, Redis, and task queues

This is an interview-prep lecture on background work. It is not a
Celery tutorial. It is the model you need to walk into an
infra/backend interview and explain why you'd put a job on a queue
instead of running it inline, what the components of a queue
system are doing, and where the failure modes live.

The lecture is structured around the journey of one task: how it
gets enqueued, how a worker picks it up, what happens when it
fails halfway through, and how to keep the system honest under
load.

---

## Why this matters

Background work is a universal interview topic because every
non-trivial system has it. Sending email, processing uploads,
fanning out webhooks, computing aggregates, generating reports —
none of these belong on the request path. Interviewers ask:

1. **System design** — "design a notification system", "design a
   webhook delivery service", "how would you process 1M uploads
   per day".
2. **Backend** — "what happens if a worker crashes mid-task",
   "how do you make a task idempotent", "what's the difference
   between at-least-once and exactly-once".
3. **Reliability** — "how do you handle a retry storm", "what's a
   dead-letter queue", "what does Celery do with a lost task".

You will be asked one of these in any backend interview with a
queue in the stack. You don't need to memorize Celery's surface —
you need to be able to draw the diagram, name the parts, and
discuss the trade-offs.

---

## The design choice

### Queue vs cron vs serverless function

You have four shapes of background work:

| Shape | Examples | When to pick |
|---|---|---|
| Inline (do it in the request) | none, this is the anti-pattern | Latency budget < 50ms total |
| Cron job | systemd timer, k8s CronJob, `crontab` | Tasks tied to wall clock, no user trigger |
| Task queue | Celery + Redis, Sidekiq, BullMQ, RQ | User-triggered or many-per-second async work |
| Serverless | AWS Lambda + SQS, Cloud Run jobs | Spiky load, want to pay per execution |

The honest distinction:

- **Cron** is for *scheduled* work — "run nightly at 3am".
  Triggered by the clock, not by user actions. One process, no
  parallelism, no retry semantics, no observability without
  building it yourself.
- **Queue** is for *triggered* work — "send this email", "process
  this upload". A producer enqueues a task; one of many workers
  picks it up. Built-in retry, parallelism, observability.
- **Serverless** is a managed queue with auto-scaling workers,
  paid per execution. Wins on spiky load (zero idle workers cost
  zero); loses on steady-state (functions are slower to invoke
  than persistent workers).

Celery covers both: it has a task queue for triggered work and
Celery Beat for scheduled work. The Beat scheduler doesn't run
tasks — it produces them onto the queue, then the worker pool
runs them. That separation is intentional.

### Why a broker?

The producer (your web request) and the consumer (the worker)
must not be coupled. If the worker is down, the producer should
still be able to enqueue. If the producer is slow, the worker
should not block. If you scale workers out, the producer should
not need to know.

The broker decouples them. The producer writes to the broker. The
worker reads from the broker. Neither needs to know the other
exists.

A broker provides four things:

1. **Persistence** — enqueued tasks survive a producer crash and
   a worker crash.
2. **Routing** — tasks go to the right queue, and workers
   subscribe to the queues they handle.
3. **Visibility timeout / ack** — a worker that crashes
   mid-processing gives the message back to the queue.
4. **Backpressure** — when workers can't keep up, the queue
   grows; you can see this and decide whether to scale workers
   or shed load.

### Redis vs RabbitMQ vs SQS as broker

Three real choices:

| Broker | Strengths | Weaknesses |
|---|---|---|
| **Redis** | Already-installed, fast, simple ops | In-memory by default; not durable across crashes unless AOF is enabled. No native dead-letter queue. |
| **RabbitMQ** | Built for messaging. Durable, native DLQs, complex routing | One more service to operate. Slower than Redis. Memory pressure can pause publishers. |
| **AWS SQS** | Fully managed, infinite scale, durable | Higher per-message latency. No native pub/sub (need SNS). Vendor lock-in. |

Celery supports all three. Most codebases pick Redis because
they're already running Redis for caching — one less service.
This codebase does exactly that (see
`backend/app/celery_app.py` and `docker-compose.yml`).

The Redis trade-off is real:

- **Durability.** Default Redis snapshots every few seconds. A
  crash between snapshots loses in-flight tasks. Mitigations:
  enable AOF (append-only file) for per-write fsync, or accept
  that a small window of task loss is acceptable for your domain.
- **No native DLQ.** RabbitMQ has dead-letter queues built in.
  With Celery + Redis you build them yourself: a task that
  exceeds `max_retries` writes to a "dead" Redis list or to a
  Postgres table for operator review.
- **Memory bound.** All in-flight tasks live in Redis memory. A
  10M-task backlog on RabbitMQ disk is fine; on Redis it is an
  OOM.

For most teams the right answer is "Redis until you can quote a
real durability or scale number that forces RabbitMQ or SQS".

---

## How it works under the hood

### The four roles

A Celery deployment has four moving parts:

```
   +----------+         +--------+         +---------+
   | Producer | ----->  | Broker | <-----  | Worker  |
   | (web)    | enqueue | (Redis)| consume |         |
   +----------+         +--------+         +---------+
                            ^                   |
                            |                   v result
   +----------+             |              +---------+
   |   Beat   | ------------+              | Result  |
   |scheduler |   schedule                 | backend |
   +----------+                            +---------+
```

- **Producer.** Your FastAPI / Django code calls
  `task.delay(args)` or `task.apply_async(...)`. This writes the
  task payload to the broker. The producer doesn't wait.
- **Broker.** Holds the queues. Redis lists per queue name. A
  task is a JSON (or pickled) blob with the task name, args,
  kwargs, retry counter, and headers.
- **Worker.** A long-running process. Subscribes to one or more
  queues. Pops a task, dispatches to a Python function, acks the
  task back to the broker on success.
- **Result backend.** Optional. Stores the return value or
  exception so the producer can poll later. Usually Redis or
  Postgres. Many codebases skip this — fire-and-forget.
- **Beat scheduler.** A separate process. Holds the schedule of
  recurring tasks (cron entries). Wakes up, decides which tasks
  are due, enqueues them. Does **not** run them.

The separation between Beat and worker is critical for
reliability. Beat is single-process by design (otherwise the same
cron entry would fire twice). The worker pool is many processes.
You scale worker capacity without affecting the schedule.

### Serialization

Celery serializes the task payload to send it over the broker.
Two choices:

- **JSON** (default for new deployments). Safe — no arbitrary code
  execution. Limits args to JSON-serializable types.
- **Pickle** (legacy default). Allows arbitrary Python objects.
  *Dangerous* — a malicious or buggy producer can ship a pickle
  that executes code on the worker. Never enable pickle on a
  multi-tenant queue.

The interview-rigorous answer: "JSON for safety, pickle only when
you control both ends and the broker is locked down."

### Prefetch multiplier

Workers don't pop one task at a time. They prefetch a batch from
the broker to reduce round-trips. `worker_prefetch_multiplier`
defaults to 4 — each worker process pre-fetches 4 tasks per
concurrency slot.

This matters when tasks vary in length. If task A takes 60s and
the worker prefetched 4 short tasks behind it, those tasks wait
60s in the worker's local buffer even though other idle workers
could pick them up. Fix: set `worker_prefetch_multiplier = 1` for
heterogeneous workloads, accept the slight throughput hit.

### Ack policy: early vs late

When does a worker tell the broker "I've handled this task"?

- **Early ack** (Celery default): ack as soon as the task is
  popped from the broker. If the worker crashes mid-task, the
  task is lost.
- **Late ack** (`task_acks_late = True`): ack *after* the task
  function returns successfully. If the worker crashes mid-task,
  the broker re-delivers it to another worker.

Late ack costs you "exactly-once" — a crash after the function
returned but before the ack means the task runs twice. That's why
late-ack tasks must be **idempotent**.

This codebase uses late ack — see `backend/app/celery_app.py`:

```python
celery.conf.update(
    ...
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    ...
)
```

`task_reject_on_worker_lost=True` is the matching half: if the
worker process is killed (OOM, sigkill), the broker should treat
the task as failed and re-deliver it.

### Retries and backoff

A task that raises an exception can be retried automatically:

```python
@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def send_email_notification(self, ...):
    ...
```

The arguments shape failure behaviour:

- **`autoretry_for=(Exception,)`** — retry on any exception. In
  practice you scope this to transient errors (`httpx.NetworkError`,
  `smtplib.SMTPServerDisconnected`).
- **`retry_backoff=True`** — exponential backoff. Delay is
  `min(retry_backoff_max, 2 ** retry_count)` seconds.
- **`retry_backoff_max=600`** — cap at 10 minutes.
- **`retry_jitter=True`** — add randomness so a thundering herd
  doesn't all retry at the same second.
- **`max_retries=3`** — after the third failure the task gives up
  and raises `MaxRetriesExceededError`.

Without jitter, a downstream service outage causes a retry
storm: every task that failed at T+0 retries at T+2, T+4, T+8. If
the downstream comes back at T+10 it gets hit with the entire
herd at once and falls over again.

### Idempotency

A late-ack queue *will* run some tasks more than once. The
contract is "at least once delivery". To make this safe each task
must be **idempotent**: running it twice has the same effect as
running it once.

Three patterns:

- **Database unique constraint.** Insert with `ON CONFLICT DO
  NOTHING`. The first run inserts; the duplicate is a no-op.
- **Idempotency key.** Pass a request-id-style key. Store
  processed keys in Redis or Postgres. Check before acting.
- **State machine guards.** "Mark this signup confirmed if it is
  currently pending". The transition is the guard.

This codebase uses the first pattern. See
`backend/app/celery_app.py`:

```python
def _dedup_insert(db: Session, signup_id, kind: str) -> bool:
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup_id, kind=kind
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    return result.rowcount == 1
```

`_dedup_insert` is called *before* sending the email. If the row
already exists, the email was already sent by another worker (or
by a previous, crashed-after-send run). The function returns
`False` and the task short-circuits.

### Beat scheduling

Beat reads a schedule from `celery.conf.beat_schedule`:

```python
celery.conf.beat_schedule = {
    "send-reminders-24h-every-5-minutes": {
        "task": "app.celery_app.send_reminders_24h",
        "schedule": 300.0,
    },
    "weekly-digest-every-monday-8am": {
        "task": "app.celery_app.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
}
```

Schedules can be a float (seconds) or a `crontab(...)`. Beat
checks once per second; when an entry is due it calls
`task.apply_async()` — which enqueues to the broker, same as any
producer.

Two failure modes:

- **Beat clock drift.** Beat uses the host clock. A container
  with bad NTP fires tasks at the wrong time.
- **Beat double-fire.** If you run two Beat processes for HA, the
  same schedule entry fires twice. The fix is single Beat +
  some kind of lock. This codebase uses **RedBeat**
  (`redbeat.RedBeatScheduler`) which moves the schedule storage
  to Redis and holds a lock so only one Beat is active.

```python
celery.conf.update(
    redbeat_redis_url=settings.redis_url,
    redbeat_lock_timeout=300,
    beat_scheduler="redbeat.RedBeatScheduler",
    ...
)
```

### Concurrency models

Celery workers can use four execution models:

- **prefork** (default). One master process forks N child
  processes. Each child runs one task at a time. CPU-bound tasks
  benefit. Memory: N copies of the worker.
- **gevent.** Greenlets. Lightweight cooperative threads. Good
  for IO-bound tasks (lots of HTTP / DB waiting). Don't use for
  CPU-bound tasks — one greenlet hogs the loop.
- **eventlet.** Similar to gevent.
- **solo.** Single-process, single-task. Useful for testing.

For an app like this one — emails, DB writes — gevent would be
the throughput-maximizing choice. The codebase uses prefork
because Celery's stability story is more battle-tested there.

### Eager mode for tests

`task_always_eager = True` makes `task.delay(...)` run the task
synchronously in the same process. No broker, no worker. Useful
for unit tests:

```python
celery.conf.task_always_eager = True
celery.conf.task_eager_propagates = True
```

The trade-off is real: eager mode does not exercise serialization,
worker setup, or retry behaviour. A test that passes in eager
mode can fail in production because it sent a non-JSON-
serializable object. Production-grade test suites mock the broker
instead of using eager mode.

---

## How this codebase uses it

The Celery deployment is at
`/Users/andysubramanian/uni-volunteer-scheduler/backend/app/celery_app.py`.

### Broker and result backend

```python
celery = Celery(
    "uni_volunteer_scheduler",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
```

Both point at Redis. `docker-compose.yml` at the repo root runs
`db`, `redis`, `backend`, `migrate`, `celery_worker`,
`celery_beat`.

### Reliability config

```python
celery.conf.update(
    redbeat_redis_url=settings.redis_url,
    redbeat_lock_timeout=300,
    beat_scheduler="redbeat.RedBeatScheduler",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    include=["app.tasks.import_csv", "app.tasks.reminders"],
)
```

Two important choices visible here:

- **RedBeat.** Single-Beat HA via a Redis lock.
- **Late ack + reject on worker lost.** At-least-once delivery.
  Every task in this codebase is built to handle being run
  twice.

### A real task

```python
@celery.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)
def send_email_notification(self, user_id=None, subject=None, body=None,
                            *, signup_id=None, kind=None):
    db = SessionLocal()
    try:
        if not _check_daily_send_limit(db):
            return
        if kind is not None and signup_id is not None:
            ...
            if not _dedup_insert(db, signup.id, kind):
                return  # Already sent by another worker
            ...
```

Three patterns to notice:

1. **Circuit breaker.** `_check_daily_send_limit` aborts before
   work if the daily send cap is exceeded. Cheap, prevents
   runaway costs.
2. **Atomic dedup.** `_dedup_insert` is the idempotency guard —
   the insert is the "I am about to send" claim.
3. **Bind + retry config.** `bind=True` gives `self`, which the
   retry decorator uses to track retry count.

### A periodic task

```python
@celery.task(bind=True, ...)
def send_reminders_24h(self) -> None:
    db = SessionLocal()
    try:
        signups = (
            db.query(models.Signup)
            .join(models.Slot)
            .filter(
                models.Signup.status == models.SignupStatus.confirmed,
                models.Signup.reminder_24h_sent_at.is_(None),
                models.Slot.start_time.between(window_start, window_end),
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for s in signups:
            if _dedup_insert(db, s.id, "reminder_24h"):
                send_email_notification.delay(signup_id=str(s.id), kind="reminder_24h")
                s.reminder_24h_sent_at = now
```

Beat fires this every 5 minutes. The task scans signups in a
30-minute window around T+24h. Three safety nets:

- **`with_for_update(skip_locked=True)`** — if two Beat instances
  somehow fire the same task at once, only one acquires the row
  lock; the other skips.
- **`_dedup_insert(s.id, "reminder_24h")`** — idempotent send
  guard.
- **`reminder_24h_sent_at`** — denormalized timestamp, lets the
  query filter out already-sent rows efficiently.

### Schedule

```python
celery.conf.beat_schedule = {
    "send-reminders-24h-every-5-minutes": {
        "task": "app.celery_app.send_reminders_24h",
        "schedule": 300.0,
    },
    "weekly-digest-every-monday-8am": {
        "task": "app.celery_app.weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
    "expire-pending-signups-daily-3am": {
        "task": "app.celery_app.expire_pending_signups",
        "schedule": crontab(hour=3, minute=0),
    },
    "check-reminders": {
        "task": "app.tasks.reminders.check_and_send_reminders",
        "schedule": 900.0,
    },
}
```

Four schedules. Three of them use second-counts; one uses
`crontab(...)` for clock-aligned firing.

---

## Common pitfalls

**1. Tasks that aren't idempotent.**

A late-ack queue *will* deliver some tasks twice. If your task
sends a charge, that's a double charge. The first thing to ask
about any new task is "what happens if this runs twice".

The fix is structural: dedup before the side effect, or guard the
side effect with a state machine transition.

**2. Retry storms.**

A downstream service is down. 10k tasks are in flight. Each
retries at `2^n` seconds with no jitter. They all hit the
downstream at the same moment when it recovers.

Fix: `retry_jitter=True`. Always. Without jitter your retry
schedule is a synchronized waveform.

**3. Lost tasks on broker crash.**

Redis is configured with default snapshots. The Redis container
OOMs. Anything enqueued between the last snapshot and the crash
is gone.

Three mitigations:

- Enable AOF (append-only file) on Redis. Per-write fsync.
- Switch to RabbitMQ if durability matters more than ops
  simplicity.
- Make tasks recoverable from source state: instead of
  `send_email_now`, do `mark_email_needed`, and have a periodic
  task that scans for unsent rows and enqueues. The work
  survives any broker loss because the truth lives in Postgres.

This codebase uses the third pattern. The
`send_reminders_24h` Beat task scans signups whose
`reminder_24h_sent_at` is NULL. If a previous reminder enqueue
was lost, the next Beat fire picks it up.

**4. Beat clock drift / double-fire.**

You run two `celery beat` processes for HA. Both wake at 8am and
both enqueue `weekly_digest`. Every user gets two emails.

Fix: RedBeat or another single-Beat lock. Never run two plain
`celery beat` processes.

**5. Eager mode hides bugs.**

A test passes in eager mode. The task argument is a datetime
object. JSON serialization would have thrown — but eager mode
bypasses serialization. The first time the task runs in
production it fails immediately.

Fix: write tests against the real broker for at least the happy
path, even if most unit tests use eager mode.

**6. Long-running tasks block prefetched siblings.**

Worker prefetches 4 tasks. The first is a 60s task. The other
three wait in the worker's local buffer for 60s, even though
other workers are idle.

Fix: `worker_prefetch_multiplier = 1` for queues with high
task-duration variance. Or split into two queues — fast and
slow — with separate worker pools.

**7. Result backend you don't need.**

You configure Redis as result backend "just in case". Now every
task writes its return value to Redis. The Redis instance is now
storing not just the queue but every task result, and it fills
up. The worker stalls because Redis is OOM.

Fix: only configure a result backend if you actually call
`AsyncResult(...).get()`. For fire-and-forget, set
`task_ignore_result = True`.

**8. No observability.**

A task fails. You find out three days later because a user
complains. You have no metrics on queue depth, no histogram of
task duration, no alert on failure rate.

Fix: stand up Flower (Celery's web monitor) at minimum. For
production, ship Celery's signals (`task_failure`, `task_retry`,
`task_success`) to Prometheus / Datadog. Alert on backlog depth
and failure rate.

---

## Interview Q&A

**Q (junior): Why use a queue instead of just running the work in
the request handler?**

A. Three reasons. Latency: queue work runs after the response is
sent, so user-perceived latency doesn't include it. Reliability:
if the work fails, the queue retries; the user doesn't see a 500.
Scaling: you can add workers independently of web servers — useful
when work is bursty or compute-heavy.

**Q (junior): What is a broker?**

A. The intermediary between the producer (who enqueues) and the
consumer (the worker). It holds the queue, persists tasks, hands
them out one at a time, and tracks which ones have been
acknowledged. In Celery the broker is usually Redis or RabbitMQ.

**Q (junior): What's the difference between Celery Beat and a
worker?**

A. The worker runs tasks. Beat decides when to enqueue them. A
recurring task ("nightly at 3am") is configured in
`beat_schedule`; the Beat process wakes up at 3am, calls
`task.apply_async()`, and a worker picks the task off the queue
and runs it. Beat is single-process; workers can be many.

**Q (mid): Explain at-least-once vs exactly-once delivery.**

A. At-least-once means a task may be delivered more than once —
under crashes, network partitions, or late acks. Exactly-once is
the absence of duplicates, which most distributed message systems
do not provide. Celery + Redis is at-least-once when
`task_acks_late=True`. The way you get "effectively exactly-once"
is **idempotent tasks**: design the task so running it twice has
the same effect as running it once. That's the practical answer.

**Q (mid): How would you design a webhook delivery system?**

A. Outline:

1. Inbound API writes the event to Postgres (durable, transactional).
2. A row-status worker enqueues a Celery task to deliver each
   pending event.
3. Delivery task posts to the customer's URL with a signed
   payload. On non-2xx, raise — Celery's retry decorator handles
   exponential backoff with jitter.
4. After N retries the task gives up; the row gets marked
   `failed` and shows in an operator dashboard (DLQ pattern).
5. Idempotency: include an event-id; the customer must dedup.

The interview hook is "what if the customer is down for a week".
Answer: the task gives up after N retries (say 12, 24h max
backoff), but the *row* lives in Postgres. Operators can replay
from the row anytime. Don't conflate "task gave up" with "event
is lost".

**Q (mid): How do you make a task idempotent?**

A. Three patterns. Database unique constraint with `ON CONFLICT
DO NOTHING` — the row is the "I did this" claim. Idempotency key
— a request-scoped UUID; processed keys are stored in Redis or
Postgres; second invocation finds the key and skips. State
machine transition — "mark X confirmed if it is pending" — the
transition fails idempotently. This codebase uses pattern one
(see `_dedup_insert` in `backend/app/celery_app.py`).

**Q (senior): What is a dead-letter queue and why do you need
one?**

A. A queue that holds messages a worker couldn't process after N
retries. Without a DLQ, those messages either get retried forever
(retry storm) or get dropped (lost work). With a DLQ they sit in
a separate place where operators can inspect them, fix the
underlying issue, and replay.

RabbitMQ has DLQs natively. Celery + Redis doesn't — you build it
yourself: catch `MaxRetriesExceededError`, write to a Postgres
table or Redis list with the task name, args, and last exception.
Surface it in an operator dashboard.

**Q (senior): How do you scale workers?**

A. Two dimensions. **Concurrency** within a worker process —
prefork (CPU) or gevent (IO-bound). **Pool size** across worker
processes — add more containers / pods. The scaling signal is
queue depth: if depth grows faster than it shrinks, add workers.

Two gotchas. First, the broker becomes the bottleneck at some
point — Redis maxes out around 100k tasks/sec, RabbitMQ around
10-50k, SQS scales further. Second, prefetch multiplier defaults
to 4 — when scaling out, set this to 1 if tasks are long or
variable so newly-added workers can pick up backlog.

**Q (senior): How do you keep tasks safe across deploys?**

A. The risk is a task in flight with one signature, picked up by
a worker that expects a different signature. Three mitigations:

1. Backward-compatible task signatures — never remove an arg in
   the same deploy as the producer change. Two-step: add the new
   arg with a default, deploy worker, switch producer, remove
   old arg.
2. Drain workers before deploy. `celery worker -P prefork
   --soft-time-limit ...` lets in-flight tasks finish before
   shutdown.
3. Versioned task names — `send_email_v2` — if the change is too
   invasive for backward compat.

---

## Further reading

- Celery docs — `docs.celeryq.dev`. The "User Guide" and
  "Configuration" pages are reference-grade; the rest is dated.
  Read in particular: Periodic Tasks, Optimizing, Routing Tasks.
- "Designing Data-Intensive Applications", Kleppmann, Chapter 11.
  The single best treatment of messaging semantics
  (at-least-once, at-most-once, exactly-once).
- Honeycomb, "What I Wish Someone Had Told Me About SQS" — real
  trade-off discussion of managed queues vs self-hosted.
- The CAP-of-the-week paper for queues is "Online, Asynchronous
  Schema Change in F1" (Rae et al., 2013) — not Celery-specific
  but shapes how to reason about deploys against a queue.
- RedBeat docs — `github.com/sibson/redbeat`. The single-Beat HA
  pattern, useful when you outgrow plain `celery beat`.
- Flower — `flower.readthedocs.io`. Celery's web monitor. Set
  one up in any new Celery deployment; it pays for itself the
  first time something goes wrong.
