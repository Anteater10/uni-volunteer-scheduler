# Test isolation: soft-delete seeds + Alembic `fileConfig` logger kill

**Phase:** 31 — Knowledge Corpus + pgvector Ingestion
**Task:** Follow-on test-isolation fixes for PR #17

## TL;DR

Four backend tests failed in CI after the pgvector image fix
(writeup 05). Two distinct root causes:

1. **Migration 0012 soft-deletes the seed templates** that migration
   0006 inserts. `_seed_templates` ran "insert if missing" and
   left the soft-deleted rows in place; the API filters them out.
2. **`alembic/env.py` calls `logging.config.fileConfig()` without
   `disable_existing_loggers=False`.** The default for that argument
   is `True`, which disables every logger that was created before
   the call. Phase 31's corpus tests run `alembic upgrade head`
   mid-session, so they silently kill `app.emails` (and every other
   already-imported logger). `test_magic_link_email_log_redacted`
   then can't capture any records, because none are being emitted.

Both fixed at the source.

## Bug 1 — Soft-deleted seed templates

### Symptom

```
FAILED tests/test_templates_crud.py::test_list_templates_returns_seeded
FAILED tests/test_templates_crud.py::test_create_duplicate_slug_409
FAILED tests/test_templates_crud.py::test_update_template

AssertionError: 'orientation' not in []
```

### Root cause

1. `engine` fixture: `Base.metadata.create_all(engine)` → empty
   `module_templates`.
2. Phase 31 corpus tests call `alembic upgrade head` on the same DB.
3. Migration 0006 inserts five seed templates.
4. Migration 0012 sets `deleted_at = NOW()` on those rows.
5. `_seed_templates` queries by slug, finds the row, takes the
   "already there, do nothing" branch.
6. Route filters `deleted_at IS NULL` → empty list.

### Fix

`_seed_templates` reaches the desired *state* (active row), not
just "any row":

```python
existing = db_session.query(ModuleTemplate).filter_by(slug=slug).first()
if existing is None:
    db_session.add(ModuleTemplate(slug=slug, name=name))
elif existing.deleted_at is not None:
    existing.deleted_at = None
    existing.name = name
db_session.flush()
```

## Bug 2 — `fileConfig` disabled every existing logger

### Symptom

```
FAILED tests/test_emails_magic_link.py::test_magic_link_email_log_redacted
AssertionError: assert 'abc123' in ''
```

`caplog.text` was empty. A direct handler attached to `app.emails`
was also empty. Records were not being emitted at all.

### How it was found

Three wrong fixes shipped first (Celery hijack disable; direct
handler bypass of root) on plausible stories. CI stayed red. Local
bisection:

```bash
pytest tests/test_corpus_embeddings.py tests/test_emails_magic_link.py
# passes

pytest tests/test_corpus_ingest_idempotency.py tests/test_emails_magic_link.py
# fails. one corpus test is enough.
```

The corpus tests call `alembic_command` → `alembic upgrade head`. Hypothesis:
something in alembic config disables loggers. Four-line repro:

```python
import logging, app.emails
print(logging.getLogger('app.emails').disabled)  # False
from logging.config import fileConfig
fileConfig('alembic.ini')
print(logging.getLogger('app.emails').disabled)  # True
```

Confirmed.

### Root cause

`backend/alembic/env.py` line 14:

```python
fileConfig(config.config_file_name)
```

`logging.config.fileConfig`'s `disable_existing_loggers` parameter
defaults to `True`. When the function runs, it sets
`logger.disabled = True` on every logger that exists at call time
and isn't explicitly named in the config. A disabled logger drops
records at `Logger.handle()` before any handler is consulted —
`caplog`, direct handlers, root handlers all see nothing.

Test suites that didn't run `alembic upgrade head` mid-session never
noticed. Phase 31's corpus suite did, and tripped the wire.

### Fix

```python
fileConfig(config.config_file_name, disable_existing_loggers=False)
```

`fileConfig` now configures only the loggers it explicitly mentions
and leaves everything else alone.

## Files changed

| Path | Change |
|---|---|
| `backend/alembic/env.py` | Pass `disable_existing_loggers=False` to `fileConfig`. |
| `backend/tests/test_templates_crud.py` | Resurrect soft-deleted seed rows in `_seed_templates`. |
| `backend/conftest.py` | Earlier kept change: `worker_hijack_root_logger = False` (not the root cause of bug 2, but a legitimate latent issue that was worth fixing on its own). |

## Verification

1. `pytest tests/test_corpus_ingest_idempotency.py::test_ingest_idempotent_on_unchanged_repo tests/test_emails_magic_link.py::test_magic_link_email_log_redacted` → 1 passed.
2. `pytest tests/test_corpus_embeddings.py tests/test_emails_magic_link.py` → all pass.
3. Full backend CI run on PR #17 → expected green.

## Invariants this restores

- **`alembic upgrade head` is logging-neutral.** Running it mid-test
  does not silently disable loggers owned by application code.
- **Test fixtures are idempotent across all reachable starting
  states.** Soft-deleted rows are now an explicit case.
- **No test's pass/fail outcome depends on what tests ran before
  it.** Both fixes eliminate hidden cross-test coupling.

## The bigger lesson

Three fixes shipped on plausible stories before I reproduced the
bug. The actual cause (`fileConfig`'s default arg) was invisible from
the failure site and from the surrounding application code. The
four-line repro that finally found it took two minutes to write
and should have been the *first* thing I tried.

**Rule:** when a fix is based on "X probably causes Y," write the
reproduction before committing. If the reproduction doesn't print
the failure you expected, the story is wrong and the fix won't hold.

## Related files

| Path | Role |
|---|---|
| `backend/alembic/env.py` | Calls `fileConfig`. The fix lives here. |
| `backend/alembic.ini` | Contains the `[loggers]`/`[handlers]`/`[formatters]` sections that `fileConfig` reads. |
| `backend/tests/conftest.py` | Defines `alembic_command` / `alembic_engine` / `corpus_db_session` — the fixtures that re-trigger `alembic upgrade head` mid-session. |
| `backend/tests/test_corpus_ingest_idempotency.py` | First file in alphabetical order that uses `alembic_command`. |
| `backend/tests/test_emails_magic_link.py` | First file alphabetically *after* the corpus suite that depends on `app.emails` log capture. |
| `backend/app/emails.py` | Defines `logger = logging.getLogger("app.emails")` and emits the redaction-relevant log line. |

## Glossary

- **`logging.config.fileConfig`** — Python stdlib helper that loads
  a logging configuration from an INI file. Its
  `disable_existing_loggers` parameter defaults to `True`, which
  silently disables every logger that was created before the call.
  This is the well-known footgun this writeup is about.
- **`logger.disabled`** — Internal flag on every `Logger` instance.
  If true, `Logger.handle()` drops records immediately, before any
  handler runs. Cannot be undone by configuring handlers downstream;
  has to be flipped back to False directly.
- **Soft delete** — Marking a row as deleted via a timestamp column
  (`deleted_at`) and filtering it out in queries.
- **Idempotent fixture** — A fixture that reaches the same end state
  regardless of starting state. Stronger than "insert if missing."
- **Cross-test state contamination** — When test A leaves a footprint
  in shared state (database rows, logger flags, env vars,
  module-level singletons) that changes test B's behaviour.
