# Alembic Migrations — Reference

Reference companion to `docs/learning/concepts/alembic-migrations.md`.
Use this page when you need to look up the CLI, the file structure,
the codebase's conventions, or operational rules of thumb.

## TL;DR

- Alembic stores migrations as a DAG of revisions; each file declares
  `revision` and `down_revision`.
- The `alembic_version` table holds the current head(s).
- This project uses **descriptive slug revision ids**
  (`0009_phase08_v1_1_schema_realignment`) and widens
  `alembic_version.version_num` to `VARCHAR(128)` in
  `backend/alembic/env.py` because Alembic's 32-char default
  overflows.
- Postgres-only quirks live in the migrations: enum-value additions
  must use `with op.get_context().autocommit_block():` because
  `ALTER TYPE ... ADD VALUE` cannot run inside a transaction.
- Known latent bug, per CLAUDE.md: several `downgrade()` functions
  create enum types in `upgrade()` but do not `DROP TYPE` on the way
  down. Fresh upgrades work; downgrade→upgrade fails with
  `DuplicateObject`.

## API surface

### CLI commands

| Command | Purpose |
|---|---|
| `alembic init <dir>` | Scaffold a new alembic directory. |
| `alembic revision -m "..."` | Create an empty migration file. |
| `alembic revision --autogenerate -m "..."` | Diff metadata vs DB, write a migration. |
| `alembic upgrade head` | Apply all unapplied migrations to the tip. |
| `alembic upgrade +1` | Apply the next single migration. |
| `alembic upgrade <rev>` | Apply up to a specific revision. |
| `alembic downgrade -1` | Reverse the most recent migration. |
| `alembic downgrade <rev>` | Reverse down to a specific revision. |
| `alembic current` | Print the currently applied revision(s). |
| `alembic history` | Print the revision graph. |
| `alembic heads` | List head revisions (more than one = needs merge). |
| `alembic merge -m "..." h1 h2` | Create a merge revision joining two heads. |
| `alembic show <rev>` | Print one revision's metadata. |
| `alembic stamp <rev>` | Set the `alembic_version` row without running SQL. |

### Operations (`op`) API used in this codebase

| Op | Notes |
|---|---|
| `op.create_table(name, *columns)` | Create a table. |
| `op.drop_table(name)` | Drop a table. |
| `op.add_column(table, column)` | Add a column. |
| `op.drop_column(table, name)` | Drop a column. |
| `op.alter_column(table, name, ...)` | Rename, retype, nullable change. |
| `op.create_index(name, table, cols)` | Create an index. |
| `op.drop_index(name, table_name=...)` | Drop an index. |
| `op.create_foreign_key(name, src, dst, ...)` | Add an FK. |
| `op.drop_constraint(name, table, type_=...)` | Drop FK/UNIQUE/CHECK. |
| `op.create_unique_constraint(name, table, cols)` | Add a UNIQUE. |
| `op.execute("SQL ...")` | Raw SQL — dialect-specific. |
| `op.get_context().autocommit_block()` | Run statements outside the migration's transaction. |
| `op.get_bind()` | Get the SQLAlchemy `Connection` for direct queries. |

### Revision file structure

```python
"""<docstring describing change>"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0009_phase08_v1_1_schema_realignment"
down_revision = "0008_phase7_user_deleted_at"   # str | tuple | None
branch_labels = None
depends_on = None

def upgrade() -> None:
    ...

def downgrade() -> None:
    ...
```

## Mental model

### The graph

Migrations are nodes in a DAG. Each has one or more parents
(`down_revision` as a string or tuple) and zero-or-more children.
"Head" = leaf. "Base" = root (no parent). Multiple heads happen when
parallel branches add migrations without merging.

### `alembic_version`

A single-column table storing the currently-applied revision id.
With multiple heads applied, it stores multiple rows.

This project's `env.py` widens the column to `VARCHAR(128)` to fit
slug ids and runs that widen at startup so the system is self-healing
on a fresh DB.

### Online migration strategies

| Strategy | When to use |
|---|---|
| Single-step transactional migration | Small tables, low traffic, brief downtime acceptable. |
| Expand-backfill-contract | Large tables, no downtime allowed. Three deploys. |
| Background backfill job | Backfill is too long to run inside any migration. |
| Tool-assisted (gh-ost, pt-osc) | Very large tables with strict no-lock budget. |

### Idempotency

Hand-written migrations should be idempotent when possible. Patterns:
`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` (PG 9.6+),
`ADD VALUE IF NOT EXISTS` for enums, `checkfirst=True` on
`enum.create()`. Idempotency makes retries safe.

## Usage in this codebase

### Layout

```
backend/
  alembic.ini
  alembic/
    env.py           # widens version_num column on every run
    script.py.mako   # template for new revisions
    versions/        # one .py per migration
```

### Revision id convention

Hex (Alembic default) for the two oldest files:

- `2465a60b9dbc_initial_schema.py`
- `b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py`

Slug ids tied to phase numbers for everything from Phase 0 onward:

- `0002_phase0_schema_hardening`
- `0003_add_pending_status_and_magic_link_tokens`
- `0004_phase3_check_in_state_machine_schema`
- ...
- `0018_copilot_sessions_and_messages`

The CLAUDE.md note states: "**Revision IDs use descriptive slug form**
(e.g. `0003_add_pending_status_and_magic_link_tokens`), not short
hex." `env.py` widens `alembic_version.version_num` to `VARCHAR(128)`
to accommodate them.

### `env.py` startup widen

```python
connection.execute(text(
    "CREATE TABLE IF NOT EXISTS alembic_version ("
    "version_num VARCHAR(128) NOT NULL, "
    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
))
connection.execute(text(
    "ALTER TABLE alembic_version "
    "ALTER COLUMN version_num TYPE VARCHAR(128)"
))
connection.commit()
```

This block is safe to run every time (no-op when already widened) and
"Do not remove" per CLAUDE.md.

### Enum-add pattern (Phase 02)

```python
def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'pending'")
```

The `autocommit_block` wraps any statements that cannot run in a
transaction (enum value adds, `CREATE INDEX CONCURRENTLY`).

### Enum-create pattern (Phase 08)

```python
quarter_enum = postgresql.ENUM(
    "winter", "spring", "summer", "fall",
    name="quarter",
    create_type=False,
)
quarter_enum.create(op.get_bind(), checkfirst=True)
```

The `create_type=False` avoids SQLAlchemy auto-creating the type when
columns of this type are added later in the same migration; the
explicit `.create(..., checkfirst=True)` is idempotent.

### Running migrations

In docker-compose:

```
db        # Postgres 16
migrate   # one-shot: alembic upgrade head, then exits
backend   # depends_on: migrate (does not start until migrations done)
```

Manually (from the repo root) to create a new revision:

```bash
docker compose run --rm backend \
  alembic revision --autogenerate -m "phase X foo"
```

To apply pending migrations against the running `db`:

```bash
docker compose run --rm migrate alembic upgrade head
```

## Operational concerns

### Lock-wait timeouts

Postgres' `lock_timeout` defaults to 0 (wait forever). Set it inside a
migration to fail fast instead of wedging the DB:

```python
op.execute("SET lock_timeout = '5s'")
```

Pair with `statement_timeout` if your migration does a backfill UPDATE.

### Avoiding rewrites

Operations that rewrite the whole table — `ALTER COLUMN TYPE` (most
cases), adding `NOT NULL` to a populated column on PG < 12, adding a
column with a volatile default — should be split using
expand-backfill-contract.

### Index builds

`CREATE INDEX` takes a `SHARE` lock; writers block. Use
`CREATE INDEX CONCURRENTLY` inside an `autocommit_block` for hot
tables:

```python
with op.get_context().autocommit_block():
    op.execute(
        "CREATE INDEX CONCURRENTLY ix_signups_volunteer_id "
        "ON signups (volunteer_id)"
    )
```

`CONCURRENTLY` is slower wall-clock but does not block writes.

### Connection pools and migrations

If you use PgBouncer in transaction-pooling mode, run migrations
through a direct DB connection — DDL needs session affinity for
session-scoped settings like `SET LOCAL` and for advisory locks.

### Multi-head merges in PRs

When two PRs branch from the same head, the second to merge will
break `alembic upgrade head`. Convention: the second author runs
`alembic merge -m "merge phaseX + phaseY" headA headB` and commits
the merge revision in their PR.

### Downgrades in production

This project does not run downgrades in production. The CLAUDE.md
note documents that several existing `downgrade()` functions are
incomplete (enum types not dropped), so even local downgrade→upgrade
round-trips fail. For production rollback, the policy is
forward-fix migrations.

### Stamping after manual changes

If the DB has been hand-edited or restored from backup, use
`alembic stamp <rev>` to align `alembic_version` with the actual
schema without running any SQL.

### CI

Best practice (deferred in this project): in CI, run
`alembic upgrade head` then `alembic downgrade base` then
`alembic upgrade head` to verify both directions. Currently fails
in this repo due to the documented `DROP TYPE` issue.

## Glossary

- **Alembic** — SQLAlchemy's migration tool.
- **`alembic_version`** — Single-column table storing applied head(s).
- **`autocommit_block`** — Context manager that runs SQL outside the
  migration's transaction, required for statements like
  `ALTER TYPE ... ADD VALUE` and `CREATE INDEX CONCURRENTLY`.
- **Autogenerate** — Alembic's diff-based migration generator
  (`alembic revision --autogenerate`). Good starting point, must be
  reviewed.
- **Backfill** — Populating new columns or tables with data derived
  from existing rows, often in chunks.
- **Branch label** — Optional name attached to a revision for grouping
  / addressing it in commands.
- **Contract** — Final step of expand-backfill-contract; removes the
  old shape.
- **Down revision** — The parent revision in the DAG; declared as
  `down_revision` in the file.
- **Expand** — First step of expand-backfill-contract; additive
  changes that both old and new code can coexist with.
- **Forward-only migrations** — Style where migrations have no
  `downgrade()` and rollback is done by writing new forward
  migrations.
- **Head** — A leaf of the migration DAG. Multiple heads mean parallel
  branches that need a merge revision.
- **Merge revision** — Empty migration whose `down_revision` is a
  tuple, used to rejoin parallel branches into a single head.
- **Online migration** — Schema change done with no service downtime,
  typically via expand-backfill-contract.
- **Revision** — A single migration file with `upgrade()` /
  `downgrade()`.
- **Slug id** — Descriptive revision id (e.g.
  `0003_add_pending_status_and_magic_link_tokens`); contrast with
  Alembic's default 12-char hex.
- **Stamp** — `alembic stamp <rev>` updates `alembic_version` without
  running SQL.
- **`target_metadata`** — The SQLAlchemy `MetaData` object autogenerate
  compares the live DB against (this project: `Base.metadata`).
- **Transactional DDL** — Postgres's ability to run most DDL inside a
  transaction. Exceptions are why `autocommit_block` exists.
