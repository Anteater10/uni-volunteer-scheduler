# Test isolation: soft-delete seeds + Celery logger hijack

**Phase:** 31 — Knowledge Corpus + pgvector Ingestion
**Task:** Follow-on test-isolation fixes for PR #17

## TL;DR

Four backend tests failed in CI after the pgvector image fix (writeup 05).
Two distinct root causes, both about cross-test state contamination:

1. **Celery hijacked the root logger** at eager-mode boot, stealing
   records from `caplog` and breaking
   `test_magic_link_email_log_redacted`.
2. **Migration 0012 soft-deletes the seed templates** that migration
   0006 inserts. Test fixtures that ran "insert if missing" left
   soft-deleted rows in place; the API filters them out, and
   `test_templates_crud.py` saw an empty list.

Both fixed at the fixture layer.

## Bug 1 — Celery `worker_hijack_root_logger`

### Symptom

```
FAILED tests/test_auth_magic_link.py::test_magic_link_email_log_redacted
AssertionError: 'magic_link_dispatched' not in ''
```

`caplog.text` was empty even though the route emitted the structured
log line.

### Root cause

Celery's default `worker_hijack_root_logger=True` walks the logging
tree on first worker boot and replaces handlers on any logger that
propagates to root. With Celery in eager mode (set by the
`_celery_eager_mode` session fixture), the first `.delay()` call from
any test triggers worker boot.

Pytest's `caplog` attaches `LogCaptureHandler` to root and relies on
application loggers propagating up. After Celery's hijack, those
records get routed to Celery's own handler and never reach `caplog`.

Test order matters: when the magic-link test runs first in a process,
Celery hasn't booted yet and `caplog` works. In CI's full-suite run,
corpus + admin tests boot Celery first; by the time the magic-link
test runs, the root logger is already hijacked.

### Fix (two layers)

**Layer 1 — disable Celery's hijack** in
`backend/conftest.py` `_celery_eager_mode` fixture:

```python
celery.conf.worker_hijack_root_logger = False
```

**Layer 2 — attach a handler directly** in the failing test
(`test_emails_magic_link.py::test_magic_link_email_log_redacted`).
`caplog` routes via the root logger and is fragile to any library
that mutates root-logger state (Celery, sentence-transformers'
`logging.basicConfig` on first model load, etc). The test now binds
its handler directly to `app.emails`:

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
log_output = buf.getvalue()
```

Layer 1 is the right ceiling fix (keeps `caplog` working for the
~10 other tests that use it). Layer 2 makes this specific test
indifferent to global-logger state set by any other test that ran
before it.

## Bug 2 — Soft-deleted seed templates

### Symptom

```
FAILED tests/test_templates_crud.py::test_list_templates_returns_seeded
FAILED tests/test_templates_crud.py::test_create_duplicate_slug_409
FAILED tests/test_templates_crud.py::test_update_template

AssertionError: 'orientation' not in []
```

The `_seed_templates` fixture appeared to do nothing. The API
returned an empty list.

### Root cause

State chain across the test database:

1. `engine` fixture: `Base.metadata.create_all(engine)` → empty
   `module_templates`.
2. Phase 31 corpus tests run `alembic upgrade head` on the same DB.
3. Migration 0006 inserts five seed templates (`orientation`,
   `intro-bio`, `intro-chem`, `intro-physics`, `intro-astro`).
4. Migration 0012 sets `deleted_at = NOW()` on those same five rows.
5. After corpus tests finish, the rows persist as
   *soft-deleted* in `test_uvs`.
6. A later test calls `_seed_templates`, which uses an "insert if
   missing" pattern. Each `query(...).filter_by(slug=slug).first()`
   returns the soft-deleted row, so the insert branch is skipped.
7. The route filters `deleted_at IS NULL`, so the list endpoint
   returns `[]`.

### Fix

`_seed_templates` must reach the desired *state*, not just check
existence:

```python
existing = db_session.query(ModuleTemplate).filter_by(slug=slug).first()
if existing is None:
    db_session.add(ModuleTemplate(slug=slug, name=name))
elif existing.deleted_at is not None:
    existing.deleted_at = None
    existing.name = name
db_session.flush()
```

Now the fixture is idempotent against three starting states: empty
table, active row present, soft-deleted row present.

## Files changed

| Path | Change |
|---|---|
| `backend/conftest.py` | Add `celery.conf.worker_hijack_root_logger = False` |
| `backend/tests/test_templates_crud.py` | Resurrect soft-deleted rows in `_seed_templates`; add docstring explaining cross-test state chain |

## Verification

1. `pytest backend/tests/test_auth_magic_link.py::test_magic_link_email_log_redacted` passes when run after the corpus suite.
2. `pytest backend/tests/test_templates_crud.py -v` passes after corpus migrations have run against the same DB.
3. Full backend pytest suite in CI completes with 0 failures on PR #17.

## Invariants this restores

- **`caplog` works regardless of test order.** Celery no longer
  silently rewires logging on first worker boot.
- **Test fixtures are idempotent across all reachable starting
  states.** "Insert if missing" is upgraded to "reach desired state."
- **No test's pass/fail outcome depends on what tests ran before
  it.** Both fixes eliminate hidden cross-test coupling.

## Related files

| Path | Role |
|---|---|
| `backend/conftest.py` | Session fixtures: engine, Celery eager mode, transactional session. |
| `backend/tests/test_templates_crud.py` | Module-template CRUD integration tests. |
| `backend/alembic/versions/0006_*` | Inserts the five seed templates. |
| `backend/alembic/versions/0012_*` | Soft-deletes those rows. |
| `backend/app/celery_app.py` | Celery configuration; eager mode is set in tests, not here. |

## Why these are paired in one writeup

Both bugs are instances of the same anti-pattern: **a test depends
on process-wide state remaining as it was at fixture-write time**.
For Bug 1 that state is the logging tree; for Bug 2 it is the row
contents of `module_templates`. Phase 31 added enough new tests to
disturb both pieces of state, surfacing latent bugs that had been
sitting in the codebase since at least Phase 12.

The fix-shape is identical in both cases: **fixtures should reach
the desired state, not assume it.**

## Glossary

- **Logger hijack** — replacing the handlers on a logger that you
  do not own, typically by walking the logger tree. Common in
  libraries that want their formatting to "win" (Celery, Sentry,
  loguru). It is a well-known anti-pattern but ships enabled by
  default in several popular packages.
- **Soft delete** — marking a row as deleted via a timestamp column
  (`deleted_at`) and filtering it out in queries, rather than
  removing it physically. Preserves history at the cost of every
  query needing a `WHERE deleted_at IS NULL` filter.
- **Idempotent fixture** — a fixture that reaches the same end state
  regardless of starting state. Stronger than "insert if missing";
  the gold standard for test isolation.
- **Cross-test state contamination** — when test A leaves a footprint
  in shared state (database, logger tree, env vars, module-level
  singletons) that changes test B's behaviour. The most common cause
  of "passes alone, fails in suite" flakes.
