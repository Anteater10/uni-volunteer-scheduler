# SQLAlchemy ORM and Transactions — Lecture Notes

This is interview-prep material for general backend roles. The framing is
broad — Python's most widely deployed ORM — but every claim is grounded in
either the SQLAlchemy documentation or the actual `backend/app/` code in this
repo. The goal is to be able to walk a senior interviewer through how an
ORM session relates to a database transaction, where ACID guarantees come
from, and how to reason about concurrency under load.

## Why this matters

Almost every backend engineer writes data-access code, and almost every
production incident has a database transaction at its core. Common failure
modes — lost updates, deadlocks, phantom reads, "why does this row have
stale data after I committed?", "why is my Celery task seeing the row I
just inserted in the request?" — all collapse into a single question: do
you understand the unit-of-work pattern that the ORM implements on top of
the database's transactional machinery?

For interviews, this concept clusters with:
- ACID and isolation levels
- Optimistic vs pessimistic concurrency control
- Connection pooling
- N+1 and lazy-load pitfalls
- Idempotency in HTTP handlers

## The design choice

When a Python service needs to read and write SQL, there are roughly three
layers of abstraction available:

1. **Raw SQL via DB-API** (`psycopg2`, `psycopg`, `asyncpg`). You write
   strings, bind parameters, manage transactions by hand. Maximum control,
   maximum boilerplate, and you re-invent the unit-of-work pattern every
   time.
2. **Query builder** — e.g. SQLAlchemy Core, Peewee's lighter modes,
   `pypika`. SQL composition is in Python, but rows come back as tuples or
   dicts and you map them to domain objects yourself.
3. **ORM** — SQLAlchemy ORM, Django ORM, Tortoise, SQLModel. Rows hydrate
   into Python objects; the library tracks which ones you changed and
   issues `UPDATE`/`INSERT`/`DELETE` automatically on flush.

### SQLAlchemy is unusual

It is both a Core (query builder) and an ORM, and the ORM is opt-in. You
can mix the two: this codebase uses ORM declarative models for write paths
and `select(...)` Core constructs for reads. That dual nature shows up in
every interview question — "do I need the Session, or just an Engine and a
Connection?" The answer depends on whether you want unit-of-work tracking.

### Pros / cons table

| Layer | Pro | Con |
|---|---|---|
| Raw SQL | Full control, no surprise queries | Manual mapping, leaky transaction handling |
| Core / query builder | Composable SQL in Python, no ORM cache | No identity map, no automatic flush ordering |
| ORM | Unit-of-work, identity map, relationship loading | Lazy-load surprises, autoflush traps, N+1 |

### ACID, in one paragraph

Whatever layer you pick, the database — Postgres in this project — gives
you the ACID guarantees inside a transaction:

- **Atomicity** — `BEGIN ... COMMIT` runs all-or-nothing; a `ROLLBACK`
  undoes every change made since `BEGIN`.
- **Consistency** — constraints (NOT NULL, UNIQUE, FK, CHECK) hold at
  commit time. ORMs add another layer (validation, defaults) on top.
- **Isolation** — concurrent transactions see a defined snapshot, governed
  by the isolation level you ask for. Default in Postgres is
  `READ COMMITTED`.
- **Durability** — once `COMMIT` returns, the change survives a crash
  because the write-ahead log (WAL) has been fsynced.

Every interview answer about transactions should pin one or more of those
letters. The ORM does not invent ACID — it only decides *when* to issue
`BEGIN` and `COMMIT`.

### Why an ORM at all?

For CRUD-heavy apps with many relationships (events, slots, signups,
volunteers, audit logs in this project), the ORM saves you from writing
the same `INSERT signups ... ; UPDATE slots SET current_count = ...`
sequence over and over, and lets the rest of the team read business logic
without mentally parsing SQL.

You give up: predictable query shape. The ORM may emit an extra `SELECT`
to refresh a row, or N selects to walk a relationship. You have to know
the pitfalls.

## How it works under the hood

### The Session is a unit of work

A SQLAlchemy `Session` is three things rolled together:

1. A **connection holder** — it lazily checks out a DB connection from
   the engine's pool when you first need it, and returns it on
   `close()`.
2. An **identity map** — a dict from `(model_class, primary_key)` to the
   live Python instance. If you load the same primary key twice in one
   session, you get the *same object* back. This makes `signup.slot` and
   `slot.signups[0]` consistent.
3. A **change tracker** — every attribute mutation on an attached
   instance is recorded. When you call `flush()`, the session emits the
   `UPDATE`/`INSERT`/`DELETE` statements needed to reconcile the
   in-memory state with the DB.

In this codebase, the session is created per request via a FastAPI
dependency (`backend/app/database.py`):

```python
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

`autoflush=False` is a deliberate choice — autoflush can fire a `flush()`
before every query so the query sees your pending writes, which is great
for correctness and terrible for surprise SQL. We turn it off and call
`db.flush()` explicitly in service code.

### Flush vs commit

These are not the same thing, and confusing them is a top-five interview
failure mode:

- `db.flush()` — sends the pending SQL to the DB, inside the current
  transaction. The rows are visible to *this connection's* later queries
  but not to other connections. Nothing is durable yet.
- `db.commit()` — calls flush, then issues `COMMIT`. Other connections
  now see the rows. The transaction ends; the next operation starts a
  fresh `BEGIN` implicitly.
- `db.rollback()` — discards pending SQL and the transaction. The
  identity map is partially cleared; previously loaded objects become
  "expired" and the next attribute access triggers a re-fetch.

You flush so that a subsequent operation in the same request sees
your write (e.g. you insert a `Signup` then ask "how many signups for
this slot?"). You commit at the boundary of the unit of work — usually
when the HTTP handler is done.

### The identity map

```python
v1 = db.get(Volunteer, vid)
v2 = db.query(Volunteer).filter_by(id=vid).first()
assert v1 is v2  # same Python object
```

This is what gives you object identity across a session. It also means
that if you mutate `v1.email`, the change is visible through `v2`
immediately, before any SQL fires.

### Flush order

When you call `flush()`, SQLAlchemy topologically sorts pending changes
so that parents are inserted before children, FK dependencies are
respected, and deletes happen after dependent rows are gone. You almost
never have to think about it — until you do, at which point you reach
for `session.flush()` calls between operations to force ordering.

### ACID under the hood — Postgres MVCC

Postgres implements isolation using Multi-Version Concurrency Control
(MVCC). Every row has hidden `xmin` and `xmax` columns marking the
transaction that created and (optionally) deleted it. Each transaction
gets a snapshot of which other transactions were committed at its start
(or at each statement, depending on isolation level), and the visibility
rules use `xmin`/`xmax` against that snapshot.

Practical consequence: **readers do not block writers and writers do not
block readers**. The price is dead-row bloat that `VACUUM` cleans up
later.

### Isolation levels

| Level | Dirty read | Non-repeatable read | Phantom read | Notes |
|---|---|---|---|---|
| READ UNCOMMITTED | possible (other DBs) | possible | possible | Postgres treats this as READ COMMITTED |
| READ COMMITTED | no | possible | possible | Postgres default |
| REPEATABLE READ | no | no | no (in PG) | PG actually gives snapshot isolation here |
| SERIALIZABLE | no | no | no | PG uses SSI (Serializable Snapshot Isolation) |

- **READ COMMITTED** — each statement sees a fresh snapshot of committed
  data. Two `SELECT`s in the same transaction can return different rows.
  This is fine for most web requests because each HTTP handler completes
  fast and operates on small row sets.
- **REPEATABLE READ** — the snapshot is taken at the first statement and
  reused for the whole transaction. Useful for read-only report
  endpoints that need consistency across multiple queries.
- **SERIALIZABLE** — Postgres tracks predicate dependencies and aborts
  one of any pair of transactions whose schedule could not have been
  produced by some serial order. You get correctness; you pay with
  occasional `serialization_failure` errors that you must retry.

### Locks

When you write, Postgres acquires row-level locks automatically:
`UPDATE` and `DELETE` take a `FOR UPDATE` lock on touched rows. You can
escalate from "I'll lock on write" to "lock now, before anyone else can
update" with `SELECT ... FOR UPDATE`.

### Optimistic vs pessimistic concurrency

The classic dueling-banker problem ("lost update"):

```text
T1: SELECT balance FROM accounts WHERE id=1   -> 100
T2: SELECT balance FROM accounts WHERE id=1   -> 100
T1: UPDATE accounts SET balance=100-30 WHERE id=1
T2: UPDATE accounts SET balance=100-50 WHERE id=1
COMMIT order: T1 then T2
Final balance: 50, not 20. T1's deduction is lost.
```

Two well-known fixes:

- **Pessimistic** — `SELECT ... FOR UPDATE` at the top of the
  transaction. The second `SELECT` blocks until the first commits, then
  reads `70`, deducts 50, writes `20`. This codebase does this for slot
  capacity (see `swap_service.py` below). Trade-off: contention; rows
  are held until commit.
- **Optimistic** — add a `version` column or use a `WHERE balance = 100`
  predicate on the update; check `rowcount`. If 0 rows were updated,
  someone else got there first and you retry. Trade-off: write code that
  can retry.

## How this codebase uses it

### Session per request

`backend/app/database.py` builds a single `engine` (synchronous psycopg2)
and a `sessionmaker` with `autoflush=False`. Every router endpoint
declares `db: Session = Depends(get_db)` — for example
`backend/app/routers/magic.py`:

```python
from ..database import get_db

@router.post("/magic/{token}")
def consume_magic_link(token: str, db: Session = Depends(get_db)):
    ...
```

`get_db()` yields a session and closes it in `finally`. The session is
not shared across requests, which is what you want — a session is
stateful (identity map, pending changes) and per-request scope keeps
state contained.

### Explicit flush, explicit commit

Service modules under `backend/app/services/` flush so that downstream
helpers see the writes, then return without committing. The router
commits once at the end. From `template_service.py`:

```python
db.add(template)
db.flush()
... derive ID, write child rows ...
db.commit()
```

Some services commit themselves (Celery tasks, the broadcast worker)
because there is no HTTP boundary; in that case the service owns the
unit of work.

### Pessimistic locking — `SELECT ... FOR UPDATE`

The most interview-worthy code in this repo is
`backend/app/services/swap_service.py`. Moving a signup from one slot to
another must atomically decrement one slot's `current_count` and
increment another's. Two concurrent swaps targeting the same slots
could lose one of the updates. The fix is `with_for_update()`, with
both rows locked in primary-key order to prevent deadlocks:

```python
def _lock_slots_in_order(db: Session, slot_a_id, slot_b_id):
    ids = sorted([str(slot_a_id), str(slot_b_id)])
    rows = (
        db.query(models.Slot)
        .filter(models.Slot.id.in_(ids))
        .order_by(models.Slot.id.asc())
        .with_for_update()
        .all()
    )
    ...
```

Two transactions that try to lock the same pair of slots will both
attempt to acquire the lower-id row first; one wins, one blocks, and
once the first commits the second proceeds without deadlock.

`backend/app/services/check_in_service.py` shows the simpler
single-row pattern:

```python
signup = db.execute(
    select(Signup).where(Signup.id == signup_id).with_for_update()
).scalar_one_or_none()
```

The lock is held until commit, so two concurrent organizers cannot
race to flip the same signup's status.

`backend/app/services/public_signup_service.py` does the same on the
slot when a participant signs up:

```python
slot = (
    db.query(Slot)
    .filter(Slot.id == slot_id)
    .with_for_update()
    .first()
)
... check capacity, write Signup, increment slot.current_count ...
```

Capacity check + increment must be inside the locked window or the
classic lost-update bug returns. In interview terms: this is the
canonical use of pessimistic locking — short transactions that read,
decide, and write a single contended row.

### Timezone forced at connection

`database.py` listens for `connect` events and runs `SET TIME ZONE
'UTC'` on every new DB connection. This is not a transaction concern
per se, but it shows the pattern of using SQLAlchemy events to enforce
invariants at the connection layer.

## Common pitfalls

### N+1 queries

```python
events = db.query(Event).all()
for e in events:
    print(len(e.signups))   # one SELECT per event
```

The fix is `joinedload` or `selectinload`:

```python
from sqlalchemy.orm import selectinload
events = db.query(Event).options(selectinload(Event.signups)).all()
```

The ORM emits one `SELECT events` and one `SELECT signups WHERE
event_id IN (...)`. Two queries, not N+1.

### Lazy-load after commit / detached instance

After `db.commit()`, attributes are *expired* — the next read triggers
a refresh from the DB. After `db.close()`, the instance is *detached* —
attribute access raises `DetachedInstanceError`. Either eager-load
before commit, set `expire_on_commit=False` on the session, or
re-attach with `db.merge(obj)`.

### Forgetting `await` on async sessions

This codebase is synchronous (psycopg2), so no `await` traps here. But
in an `AsyncSession` codebase the most common bug is `await
session.execute(...)` working fine and then `result.scalars().all()`
returning a coroutine because someone forgot the chain pattern.

### Autoflush surprises

If you leave `autoflush=True` (the default), a `db.query(...)` can
trigger a flush of pending writes, which can in turn fail a constraint
and abort the transaction. Our `autoflush=False` setting means
queries do not silently emit writes, but you have to remember to flush
manually when ordering matters.

### Sessions held across requests

If you store a session on a global or on `app.state`, two requests
will share an identity map and a transaction. Symptoms: stale data,
"I see your uncommitted writes", and occasional `OperationalError:
this Session's transaction has been rolled back`. Always per-request.

### Overlong transactions

A session held open while you do slow IO (an external API call, an LLM
request) holds a connection from the pool and possibly row locks. The
pool exhausts; everyone waits. Always commit or rollback before
calling out.

## Interview Q&A

**Q1 (junior).** What is the difference between `db.flush()` and
`db.commit()`?
**A.** `flush()` emits pending SQL inside the open transaction so this
connection sees the writes; `commit()` flushes then issues `COMMIT` so
all connections see them and the changes are durable.

**Q2 (junior).** Why is there an identity map in the Session?
**A.** So that loading the same primary key twice returns the same
Python object — relationships are consistent, in-memory mutations are
visible everywhere, and the change tracker has exactly one place to
record dirty state.

**Q3 (mid).** Explain the lost-update problem and two ways to fix it.
**A.** Two transactions read a value, both compute new values from
that read, both write back; the second write overwrites the first.
Pessimistic fix: `SELECT ... FOR UPDATE` so the second read blocks
until the first commits. Optimistic fix: include the original value in
the `WHERE` clause (or a `version` column), check `rowcount`, retry on
zero.

**Q4 (mid).** What is the difference between READ COMMITTED and
REPEATABLE READ in Postgres?
**A.** READ COMMITTED takes a fresh snapshot at each statement, so two
selects in the same transaction can see different committed data.
REPEATABLE READ takes one snapshot at the first statement and reuses it
for the whole transaction. In Postgres, REPEATABLE READ also prevents
phantom reads — it is essentially snapshot isolation.

**Q5 (mid).** Why might you call `db.flush()` without `commit()`?
**A.** To make pending writes visible to subsequent queries in the
same transaction (for example, to get the auto-generated primary key
of a newly inserted row, or to let a helper that does its own query
see the row), while leaving the unit of work open so the caller can
still roll back.

**Q6 (senior).** A team reports that concurrent slot bookings sometimes
exceed capacity by one. Walk through how you'd diagnose and fix it.
**A.** Suspect a missing lock between the capacity check and the
increment. Confirm by reproducing under load (two clients, same slot,
same instant) or by reading the service code. Fix by wrapping the
read-check-write in a single transaction and adding `SELECT ... FOR
UPDATE` on the slot row, so the second writer blocks until the first
commits and then sees the updated count. Verify with a stress test;
log any `409` rejections so capacity contention is observable.

**Q7 (senior).** When would you reach for SERIALIZABLE in Postgres?
**A.** When the correctness invariant spans multiple rows or
predicates and you do not want to design explicit locks for every
predicate (classic example: "the sum of pending withdrawals must not
exceed the balance"). SERIALIZABLE uses SSI to detect dangerous
schedules and aborts one transaction with a serialization failure;
you handle that by retrying. Trade-off: you need a retry loop and
should keep transactions short.

**Q8 (senior).** What's the failure mode of holding a `Session` open
across an external HTTP call?
**A.** The session holds a DB connection from the pool and any row
locks it has acquired. If the external call is slow, you exhaust the
pool, every other request waits on a connection, and any blocked
writers on the locked rows pile up too. Fix: commit or rollback
before the external call, do the call, then start a new transaction
to record the result.

## Further reading

- SQLAlchemy ORM tutorial — https://docs.sqlalchemy.org/en/20/orm/tutorial.html
- "Session basics" in the SQLAlchemy docs — covers flush/commit/expire
  and the unit-of-work model precisely.
- PostgreSQL "Concurrency Control" chapter —
  https://www.postgresql.org/docs/current/mvcc.html
- PostgreSQL "Explicit Locking" chapter — row-level and table-level
  locks, including `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`.
- Martin Kleppmann, *Designing Data-Intensive Applications*, chapter 7
  (Transactions). The standard interview prep for isolation and
  concurrency control.
- Heroku's "Postgres at scale" engineering posts — battle-tested
  examples of lock contention and how to find it.
- This repo: `backend/app/database.py`,
  `backend/app/services/swap_service.py`,
  `backend/app/services/check_in_service.py`,
  `backend/app/services/public_signup_service.py`.
