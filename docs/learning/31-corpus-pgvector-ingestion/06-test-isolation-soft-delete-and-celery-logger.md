# Lecture 06 — Test isolation: soft-delete seed rows and Celery's logger hijack

## Why this lecture exists

After CI got pgvector wired up (lecture 05), four backend tests still failed.
Not because the code under test was wrong — because the **test environment**
had two hidden coupling points nobody had to think about until Phase 31
introduced more tests. Both are general-purpose lessons about how test
isolation fails in subtle ways.

The two bugs:

1. `test_magic_link_email_log_redacted` — `caplog` saw no records, even
   though the route definitely emitted the log line.
2. `test_templates_crud.py` (3 tests) — the `_seed_templates` fixture
   thought rows were already seeded, but the API endpoint returned an
   empty list.

Different symptoms. Same root cause family: **shared global state
across tests is invisible until something else mutates it.**

## Bug 1 — Celery hijacks the root logger

### The symptom

```python
def test_magic_link_email_log_redacted(client, caplog):
    with caplog.at_level("INFO"):
        client.post("/api/v1/auth/magic-link", json={"email": "x@y.com"})
    assert "magic_link_dispatched" in caplog.text  # FAILS
```

The application code clearly logged `magic_link_dispatched`. Running
the route by hand emitted the line. But `caplog.text` was empty.

### What was actually happening

Celery's default config sets `worker_hijack_root_logger=True`. When
the Celery worker boots — and that happens the first time *any* test
triggers a `.delay()` call, because tests run Celery in eager mode —
Celery walks the logging tree, finds every logger whose
`propagate=True`, and **replaces their handlers** with its own.

Pytest's `caplog` works by attaching a `LogCaptureHandler` to the root
logger. Application loggers propagate to root, so under normal
circumstances `caplog` sees their records. After Celery hijacks, those
records go to Celery's handler instead. `caplog` records nothing,
even though the log message was emitted exactly as expected.

The bug only surfaces when Celery boots before the test runs. In a
fresh test process, the magic-link test ran first and passed. In CI,
where pytest ordering loads many corpus + admin tests before it,
Celery had already booted and the hijack had already happened.

### The fix

Two layers, because Celery is only one of several offenders:

1. In the `_celery_eager_mode` fixture, set
   `celery.conf.worker_hijack_root_logger = False`. This blocks
   Celery specifically.
2. In the test itself, **stop relying on `caplog`** for this assertion.
   Attach a `StreamHandler` directly to the `app.emails` logger:

   ```python
   target = logging.getLogger("app.emails")
   buf = io.StringIO()
   handler = logging.StreamHandler(buf)
   handler.setLevel(logging.INFO)
   target.addHandler(handler)
   target.setLevel(logging.INFO)
   try:
       send_magic_link(...)
   finally:
       target.removeHandler(handler)
   ```

   The handler is bound directly to the logger we care about, so the
   test no longer depends on propagation reaching the root handler.
   Celery, sentence-transformers, huggingface_hub, and any future
   library that mutates root-logger state can't reach this test.

Why both: layer 1 keeps `caplog` working for other tests in the suite
that depend on it (e.g. `test_celery_app_full.py`). Layer 2 makes
this *specific* test indifferent to whatever order the suite runs in.
The lesson is that `caplog` is a convenience that bets on propagation
staying clean; bet only when the stakes are low.

### The pattern to remember

`caplog` is not a magic spy. It is a handler attached to a logger,
and **handlers are mutable global state**. Any library that calls
`logger.addHandler` or `logger.handlers = [...]` can break your
log-capture tests without ever touching your code.

Suspect categories: Celery, structlog config blocks, Sentry init,
loguru `logger.configure`, any "logging setup" helper. If a `caplog`
test passes alone and fails in a suite, ask what configured logging
between the two states.

## Bug 2 — Migration-inserted seed rows get soft-deleted across tests

### The symptom

```python
def test_list_templates_returns_seeded(client, admin_headers):
    resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    slugs = [t["slug"] for t in resp.json()]
    assert "orientation" in slugs  # FAILS — slugs is []
```

The `_seed_templates` fixture inserts 5 templates including
`orientation`. The route lists templates. The list came back empty.

### What was actually happening

The fixture's logic was:

```python
existing = db_session.query(ModuleTemplate).filter_by(slug=slug).first()
if existing is None:
    db_session.add(ModuleTemplate(slug=slug, name=name))
```

"Insert if missing" — reasonable. Now follow the chain of events
that breaks it:

1. The session-scoped `engine` fixture calls `Base.metadata.create_all`
   on a fresh DB. The `module_templates` table is empty.
2. The Phase 31 corpus tests need a fully migrated schema. They
   invoke `alembic upgrade head` against the same database.
3. Migration 0006 inserts the five seed templates including
   `orientation` (with `deleted_at = NULL`).
4. Migration 0012 then sets `deleted_at = NOW()` on those same five
   rows. The product no longer ships seeded templates by default.
5. A later test runs `_seed_templates`. It queries for slug
   `orientation`, finds the row (soft-deleted), takes the
   `if existing is None: insert` branch's `else` — and does nothing.
6. The route filters `deleted_at IS NULL`, so the list is empty.

The fixture was correct against assumption #1 (fresh-DB world).
After step 4, assumption #1 no longer holds. The fixture never
adapted to the new world.

### The fix

Resurrect any soft-deleted seed row instead of treating it as
"already there":

```python
existing = db_session.query(ModuleTemplate).filter_by(slug=slug).first()
if existing is None:
    db_session.add(ModuleTemplate(slug=slug, name=name))
elif existing.deleted_at is not None:
    existing.deleted_at = None
    existing.name = name
db_session.flush()
```

### The pattern to remember

**Test fixtures encode assumptions about the schema's history that
go stale when migrations change.** This fixture was written when
the table was either empty (fresh `create_all`) or already had the
five rows you wanted. Migration 0012 added a third possible state
the fixture never considered: rows-present-but-soft-deleted.

Two general defenses:

1. **Fixtures that "ensure X exists" should ensure X is in the
   desired *state*, not just that a row exists.** "Slug exists" is
   not the same as "slug exists and is active."
2. **Cross-test schema state survives in a real database.** Unlike
   in-memory SQLite, Postgres tests share rows when one test runs
   `alembic upgrade head` and another runs `create_all`. The
   surface area for "test A leaves a footprint test B sees" is
   wider than people remember.

## Why these surface together

Both bugs come from the same anti-pattern: **a test relies on a
piece of process-wide state staying the way it was at fixture-write
time.** For test 1, that state is the logging tree. For test 2, it's
the schema's row contents. Neither piece of state is owned by the
test. Both are mutable from elsewhere. Once Phase 31 added enough
new tests to perturb either, the latent bugs surfaced.

The fix in both cases is the same shape: **make the fixture's
guarantee explicit and idempotent.** The fixture should *reach* the
desired state, not assume it. "Disable Celery's hijack" reaches a
known logging tree. "Resurrect soft-deleted rows" reaches a known
data state.

## How to spot this class of bug

When a test fails that has nothing to do with what you just changed,
ask:

- "What process-wide state does this test depend on?"
- "Could any other test in the suite have mutated that state?"
- "Does my fixture *reach* the state I want, or *assume* it?"

If it assumes, it's a future bug. Cheaper to fix as a fixture
than as a flaky CI run six months from now.

## Operational checklist

- Every test that uses `caplog` should run in a suite alongside any
  test that triggers Celery. Don't trust solo-passes.
- Every fixture that "seeds" data should be **idempotent against
  any starting state** — empty, partially populated, soft-deleted,
  hard-deleted. Write it as a state machine, not as an insert.
- When adding a new soft-delete column or a new migration that
  mutates seed data, audit existing fixtures that seed the same
  tables. The pattern that just bit us will bite again.
