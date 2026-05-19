# SQLAlchemy ORM and Transactions — Reference

Reference companion to
`docs/learning/concepts/sqlalchemy-orm-transactions.md`. Use this page when
you need to look up the Session API, the mental model, or how the
codebase wires things up.

## TL;DR

- A `Session` is a unit-of-work: identity map + change tracker + lazy
  connection holder, scoped per HTTP request via FastAPI's
  `Depends(get_db)`.
- `flush()` sends SQL inside the open transaction; `commit()` ends it
  and makes changes visible to other connections.
- This codebase uses `autoflush=False` and `expire_on_commit` at
  default; service functions flush explicitly and routers commit at
  the boundary.
- Pessimistic locking (`SELECT ... FOR UPDATE`, via `with_for_update()`)
  guards capacity counters and signup state transitions. See
  `swap_service.py`, `check_in_service.py`, `public_signup_service.py`.
- Default Postgres isolation is `READ COMMITTED`, which is fine for
  short web transactions where contended writes are protected by
  row-level locks.

## API surface

### Engine and sessionmaker

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

engine = create_engine(database_url, future=True)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)
Base = declarative_base()
```

`future=True` opts into SQLAlchemy 2.0 behavior. `autoflush=False` is
the project's deliberate choice; see "Mental model" below.

### Session lifecycle

| Method | What it does |
|---|---|
| `Session()` / `SessionLocal()` | Allocate a session. No connection checked out yet. |
| `db.add(obj)` | Mark `obj` pending for INSERT on the next flush. |
| `db.add_all([...])` | Bulk version of `add`. |
| `db.delete(obj)` | Mark `obj` pending for DELETE. |
| `db.flush()` | Emit pending SQL in the open transaction. |
| `db.commit()` | flush + COMMIT. Ends the transaction. |
| `db.rollback()` | Abandon pending changes, ROLLBACK, expire instances. |
| `db.refresh(obj)` | Re-read `obj` from the DB. |
| `db.expire(obj)` | Mark attributes stale; next access re-reads. |
| `db.close()` | Return the connection to the pool, clear the identity map. |
| `db.get(Model, pk)` | Identity-map-aware primary-key lookup. |
| `db.execute(stmt)` | Run a Core `select`/`insert`/`update` statement. |

### Querying

Two styles work side by side in SQLAlchemy 2.x:

```python
# Legacy ORM Query
events = db.query(Event).filter(Event.status == "open").all()

# Core-style (preferred in 2.0)
from sqlalchemy import select
events = db.execute(
    select(Event).where(Event.status == "open")
).scalars().all()
```

The `select()` form composes with `with_for_update()`, eager-load
options (`joinedload`, `selectinload`), and arbitrary expressions.

### Locking

```python
from sqlalchemy import select

row = db.execute(
    select(Slot).where(Slot.id == slot_id).with_for_update()
).scalar_one_or_none()
```

Variants: `with_for_update(read=True)` for `FOR SHARE`,
`with_for_update(skip_locked=True)` for "skip rows another transaction
has locked", `with_for_update(nowait=True)` for "fail immediately if
locked".

## Mental model

### Three things the Session tracks

1. **Identity map** — `{(Model, pk): instance}`. Loading the same pk
   twice returns the same Python object. Mutations on one reference
   are visible through every reference.
2. **State machine** for each instance:
   - *transient* — never seen by a session
   - *pending* — `db.add()` called, not yet flushed
   - *persistent* — flushed and attached
   - *detached* — was persistent, session closed
3. **Pending writes** — when `flush()` runs, the session walks dirty
   instances in topological order (parents before children) and emits
   `INSERT`/`UPDATE`/`DELETE`.

### Two timing concepts

- *Flush* — write to the open transaction. Other connections cannot
  see it yet. SQL has been issued; rollback still works.
- *Commit* — end the transaction. Other connections see it. After
  this, every attribute on persistent instances is expired and the
  next access re-reads.

`autoflush=False` means a `query()` does **not** flush automatically.
You must call `db.flush()` if a query needs to see your pending writes.

### Transactional boundaries

The unit of work is bounded by `BEGIN` (implicit on first SQL) and
`COMMIT`/`ROLLBACK`. In this codebase, the typical pattern is:

```
HTTP request in
  -> get_db() opens Session
  -> router calls service
       service does add/query/flush
  -> router calls db.commit()
  -> get_db() finally block closes Session
HTTP response out
```

### Isolation levels at a glance

| Level | Use when |
|---|---|
| READ COMMITTED | Short OLTP transactions. Project default. |
| REPEATABLE READ | Multi-query read-only reports that need consistency. |
| SERIALIZABLE | Multi-row invariants you cannot easily lock for. |

Set per-engine: `create_engine(url, isolation_level="REPEATABLE READ")`,
or per-connection: `engine.connect().execution_options(
isolation_level="REPEATABLE READ")`.

## Usage in this codebase

### Engine + session

`backend/app/database.py` builds a single sync engine using the
configured `database_url`, forces UTC at the connection layer via an
`on connect` event, and exposes `SessionLocal` and the `get_db()`
dependency.

### Dependency injection

Routers under `backend/app/routers/` declare `db: Session =
Depends(get_db)`. Examples:

- `backend/app/routers/magic.py` — `consume_magic_link`
- `backend/app/routers/users.py` — multiple endpoints

### Service layer

Services live in `backend/app/services/` and accept a `Session` as
their first argument. The contract in this repo is:

- Services **flush** so internal helpers see writes.
- Services do **not commit** unless they own the unit of work
  (Celery tasks, background workers).
- Routers commit at the end of the request.

### Locking patterns

| File | Lock target | Why |
|---|---|---|
| `services/swap_service.py` | Two `Slot` rows, ordered by id | Prevent deadlocks when swapping signups between slots |
| `services/check_in_service.py` | A `Signup` row | Serialize state-machine transitions |
| `services/public_signup_service.py` | Slot rows on signup | Capacity check + increment must be atomic |

### Models

All models live in `backend/app/models.py` (single-file ORM module
inheriting from the `Base` declared in `database.py`). Enums are
declared as Python `enum.Enum` subclasses and bound to columns via
`SqlEnum`.

## Operational concerns

### Connection pool

`create_engine` defaults to `QueuePool` with `pool_size=5` and
`max_overflow=10`. Production sizing rule of thumb: at most one
connection per concurrent worker; verify against Postgres'
`max_connections` (default 100). Use `pool_pre_ping=True` if you run
behind a connection-killing proxy (PgBouncer in `session` mode is
safe; `transaction` mode requires care with prepared statements).

### Session lifetime

Per-request. Never module-global. Never stash in `app.state`. Sessions
hold both a connection and an identity map; sharing them across
requests causes stale reads and transaction confusion.

### Lock-wait timeouts

Postgres' `lock_timeout` defaults to 0 (wait forever). Set it per
session for long-locking endpoints:

```python
db.execute(text("SET LOCAL lock_timeout = '5s'"))
```

`SET LOCAL` scopes the change to the current transaction.

### Long transactions

Avoid holding a session open across slow IO. Pattern: commit before
calling an external service, do the call, open a new session to
record the result.

### Connection leaks

`get_db()` uses `try/finally` so a raised exception still closes the
session. If you write background code that builds sessions manually,
prefer `with SessionLocal() as db: ...` to guarantee close on error.

### Migrations and transactions

DDL in Postgres is transactional except for a few statements (e.g.
`ALTER TYPE ... ADD VALUE`, concurrent index builds). Alembic
migrations wrap `upgrade()` and `downgrade()` in a transaction by
default; statements that cannot run in a transaction must be wrapped
in `with op.get_context().autocommit_block(): ...` — see
`backend/alembic/versions/0003_add_pending_status_and_magic_link_tokens.py`.

### Observability

For diagnosing slow ORM queries, enable echo:

```python
create_engine(url, echo="debug")
```

In production, prefer `sqlalchemy.engine` logging at INFO level, or
attach `before_cursor_execute` / `after_cursor_execute` events to
record latency to your metrics system.

## Glossary

- **ACID** — Atomicity, Consistency, Isolation, Durability. The four
  guarantees a database transaction provides.
- **Autoflush** — Session option that emits a flush before each query.
  Off in this project.
- **Connection pool** — Reusable set of DB connections so requests do
  not pay TCP/auth cost each time.
- **Detached instance** — A previously persistent ORM object whose
  session has been closed. Attribute access raises.
- **Dirty tracking** — The Session's recording of attribute changes on
  attached instances, used to compute flush statements.
- **Engine** — The connection factory plus dialect plus pool.
- **Expire** — Mark an instance's attributes as stale so the next
  access reloads from the DB. Happens automatically on commit by
  default.
- **Flush** — Emit pending SQL inside the open transaction.
- **Identity map** — Cache that maps `(class, primary_key)` to the
  attached Python object inside a session.
- **MVCC** — Multi-Version Concurrency Control. Postgres' mechanism
  for snapshot isolation without read locks.
- **Optimistic concurrency** — Detect conflicts at commit time, retry.
- **Pessimistic concurrency** — Acquire locks up front to prevent
  conflicts.
- **`SELECT ... FOR UPDATE`** — Take a row-level lock so other
  transactions trying to update the same row will block.
- **Session** — SQLAlchemy ORM's unit-of-work object.
- **Snapshot isolation** — Each transaction sees a consistent view of
  the DB as of a fixed point in time.
- **Transaction** — A unit of work between `BEGIN` and `COMMIT`/`ROLLBACK`.
- **Unit of work** — The pattern of batching mutations and reconciling
  them with the DB in one commit.
- **WAL** — Write-Ahead Log. Postgres writes changes here first; fsync
  on commit gives durability.
