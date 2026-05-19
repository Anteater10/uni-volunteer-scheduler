# Lecture 06 — Test isolation: soft-deleted seeds and Alembic's silent logger massacre

## Why this lecture exists

After CI got pgvector wired up (lecture 05), four backend tests still failed.
None of them were touching anything new. They failed because Phase 31
exercised parts of the test infrastructure that had silent bugs nobody had
been forced to notice. Two distinct root causes, both about cross-test
state contamination — the kind of failure where the symptom and the cause
sit in different files and don't reference each other.

The two bugs:

1. `test_templates_crud.py` (3 tests) — the `_seed_templates` fixture
   thought the rows were already seeded, but the API returned an empty
   list.
2. `test_magic_link_email_log_redacted` — `caplog.text` was empty. So
   was a direct handler attached straight to the `app.emails` logger.
   Records were not being emitted at all.

Bug 2 is the interesting one and it took three wrong fixes before I
stopped guessing and actually reproduced it.

## Bug 1 — Migration-inserted seed rows get soft-deleted across tests

(Same as before — included here for completeness.)

### Symptom

```python
def test_list_templates_returns_seeded(client, admin_headers):
    resp = client.get("/api/v1/admin/module-templates", headers=admin_headers)
    slugs = [t["slug"] for t in resp.json()]
    assert "orientation" in slugs  # FAILS — slugs is []
```

### Root cause

Chain of state across tests:

1. `engine` fixture: `Base.metadata.create_all` → empty `module_templates`.
2. Phase 31 corpus tests call `alembic upgrade head`.
3. Migration 0006 inserts five seed templates.
4. Migration 0012 soft-deletes them.
5. `_seed_templates` does "insert if missing" and skips because the
   row exists (just soft-deleted).
6. The list endpoint filters `deleted_at IS NULL` → `[]`.

### Fix

Fixture must reach the desired *state*, not just "row exists":

```python
existing = db_session.query(ModuleTemplate).filter_by(slug=slug).first()
if existing is None:
    db_session.add(ModuleTemplate(slug=slug, name=name))
elif existing.deleted_at is not None:
    existing.deleted_at = None
    existing.name = name
db_session.flush()
```

### Pattern

**Test fixtures should be idempotent against any reachable starting
state, not just "fresh DB."** "Slug exists" is not the same as "slug
exists and is active." Migrations add new reachable states the
fixtures never anticipated.

## Bug 2 — Alembic disabled every existing logger

This is the one worth reading the lecture for.

### Symptom

```python
def test_magic_link_email_log_redacted(caplog):
    with caplog.at_level(logging.INFO, logger="app.emails"):
        send_magic_link(...)
    assert "abc123" in caplog.text  # FAILS — caplog.text is ''
```

`caplog.text` was empty. Strange enough that I tried three increasingly
wrong fixes before debugging properly.

### The three wrong fixes (worth the embarrassment)

**Wrong fix 1 — disable Celery's worker_hijack_root_logger.** Celery
hijacks the root logger on worker boot when this is true. In eager
mode the hijack still fires the first time a `.delay()` is invoked.
Plausible! `worker_hijack_root_logger = False` in the test fixture.
**CI still red.**

**Wrong fix 2 — blame sentence-transformers.** The corpus tests load
`sentence_transformers`, which may call `logging.basicConfig()`. That
adds a root handler but doesn't directly suppress capture. Plausible
again. I made the test resilient by attaching a `StreamHandler`
directly to `app.emails`, bypassing root entirely. **CI still red.**

That last one is what broke me out of guessing. A direct handler on
`app.emails` not capturing anything means the logger *itself* is
silent. Records aren't being filtered downstream — they're not being
generated at all.

### The actual debug

Bisect locally with progressively narrower test selections:

```bash
pytest tests/test_corpus_embeddings.py tests/test_emails_magic_link.py
# → passes

pytest tests/test_corpus_ingest_idempotency.py tests/test_emails_magic_link.py
# → fails

pytest tests/test_corpus_ingest_idempotency.py::test_ingest_idempotent_on_unchanged_repo \
       tests/test_emails_magic_link.py::test_magic_link_email_log_redacted
# → still fails. one corpus test is enough.
```

The corpus test errored (its own fixture issue) but it still ran far
enough to break the next test's logger. What does it do before
erroring? It calls `alembic_command`, which calls `alembic upgrade head`.

So I ran the obvious experiment:

```python
import logging, app.emails
print(logging.getLogger('app.emails').disabled)   # False
from logging.config import fileConfig
fileConfig('alembic.ini')
print(logging.getLogger('app.emails').disabled)   # True
```

There it is.

### Root cause

`backend/alembic/env.py` line 14:

```python
fileConfig(config.config_file_name)
```

`logging.config.fileConfig`'s `disable_existing_loggers` parameter
**defaults to `True`**. When the function runs, it walks the logger
tree and sets `logger.disabled = True` on every existing logger that
isn't explicitly named in the config file. `app.emails`,
`app.celery_app`, the rest — all disabled. A disabled logger silently
drops every record at `Logger.handle()` before any handler is
consulted. `caplog` sees nothing. A direct handler sees nothing.
`logger.info(...)` is effectively a no-op.

The bug had been latent for years. Test suites that don't run
`alembic upgrade head` mid-session never noticed. Phase 31's corpus
suite is the first place we do exactly that, in the same process as
the rest of the tests. It tripped a wire that had been sitting there
since the very first migration shipped.

### The fix

One argument:

```python
fileConfig(config.config_file_name, disable_existing_loggers=False)
```

Now `fileConfig` only configures the loggers it explicitly mentions
and leaves everything else untouched. `app.emails` stays alive,
records get emitted, `caplog` works again.

### Pattern

**`logging.config.fileConfig` is a footgun.** It is one of the very
few Python stdlib functions where the documented default actively
mutates global state owned by other code. Anything you import that
calls `fileConfig` (Alembic, Django, plenty of internal tools) can
silently disable every logger the rest of your process owns. The
mutation is invisible at the call site and invisible at the read
site — you only notice when log assertions or live-logging tests
fail with no records.

Two defenses:

1. **In your own code, always pass `disable_existing_loggers=False`.**
   The default is almost never what you want.
2. **In libraries you control, switch to `logging.config.dictConfig`**
   (it has the same parameter but the explicit form is harder to
   miss) or build the config programmatically.

If you ever see "the logger silently stopped working halfway through
the suite," `fileConfig` is your prime suspect.

## Why I went down three wrong roads first

Worth saying out loud, because it's the lesson behind the lesson:

- **Celery's hijack is famous.** It is the canonical "logger
  silently stops working" cause in the Python web world. So when
  caplog returned empty, my brain leapt to it without checking.
- **Sentence-transformers loading is exotic and recent.** Plausible
  story = plausible-looking fix.
- **I didn't reproduce locally before committing.** Both fixes shipped
  on a story, not on evidence.

The actual cause — `fileConfig`'s default arg — wasn't on my radar
because it's a piece of API ergonomics, not a library behavior. The
moment I ran the four-line repro (`import emails → fileConfig →
print disabled`), the answer was obvious. The cost of running that
first instead of fourth was about thirty minutes and three CI cycles.

**Rule:** when a fix is based on a plausible story rather than a
reproduction, write the reproduction first. "I think X causes Y"
should always be cheaper to verify than to fix.

## How these surface together

Both bugs are instances of "fixture or env code mutates global state
the rest of the suite assumed was stable." For Bug 1, it's
schema-level row state mutated by migrations. For Bug 2, it's
process-level logger state mutated by `fileConfig`. Both fixes share
the same shape: **make the mutation stop happening, or make the
consumer immune to it.** Here both fixes are at the source: don't
seed-skip soft-deleted rows; don't let `fileConfig` disable
unrelated loggers.

## Operational checklist

- Audit every call to `logging.config.fileConfig` in your codebase
  and any vendored library. If `disable_existing_loggers` is not
  explicitly `False`, it's a latent bug.
- When a caplog/log-capture test fails with empty records, *first*
  check `logging.getLogger(name).disabled`. It's a one-line test that
  rules out an entire class of cause.
- Fixtures that "seed" data should be idempotent against any
  starting state — fresh, present, soft-deleted, hard-deleted.
- When a plausible story explains a bug, write the four-line
  reproduction *before* committing the fix. If the reproduction
  doesn't print the failure you expected, the story is wrong.
