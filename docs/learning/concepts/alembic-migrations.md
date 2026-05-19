# Alembic Migrations — Lecture Notes

Interview-prep material on schema migrations for backend roles. Alembic
is the migration tool in the SQLAlchemy ecosystem; the same concepts —
revision graph, online/expand-contract migrations, enum hazards, multi-
head merges — show up under different names in Django migrations,
Flyway, Liquibase, golang-migrate, and node's typeORM.

## Why this matters

Schema change is where most production outages start. A naive `ALTER
TABLE` on a busy Postgres table can lock writers for minutes, take
down the API, and roll back a deploy. Migrations also sit at the
intersection of two teams working on the same database — if both add a
revision and you do not handle the divergence, you ship a broken
deploy. Senior interview questions almost always include "how would
you add this non-null column to a table with 100M rows without taking
the service down?"

## The design choice

There are three rough families of migration tools:

1. **State-based** — the source of truth is a desired schema (an SQL
   file or an ORM model); the tool diffs against the live DB and emits
   the delta on deploy. Examples: Microsoft's SSDT, some ORMs' "sync"
   modes. Convenient; bad on production because you do not control
   *how* the delta is applied.
2. **Revision-based / forward-only** — each change is a numbered
   migration file; the tool records which have been applied. Examples:
   Flyway (SQL-only), golang-migrate, Rails migrations, Django
   migrations, Alembic. This is the dominant style.
3. **Revision-based with up/down** — same as above, but each migration
   declares how to undo itself. Alembic and Django offer this. Down
   migrations are debated — you should not run them in production, but
   they are valuable for local development.

This project uses Alembic with up/down. The CLAUDE.md file explicitly
notes that several `downgrade()` functions in this repo do not drop
their enum types on the way down, which would fail
downgrade→upgrade round-trips on a single instance. Fresh upgrades
are fine; the bug is documented and deferred.

### Pros / cons

| Approach | Pro | Con |
|---|---|---|
| State-based | One file = one schema | Loses intent; risky deltas; hard to backfill |
| Revision-based, forward-only | Simple, easy to reason about | No clean rollback path in dev |
| Revision-based, up/down | Local dev rollback works | Downgrades rot; rarely tested |

### Alembic vs Django migrations vs Flyway

| Trait | Alembic | Django migrations | Flyway |
|---|---|---|---|
| Authoring language | Python | Python | SQL (or Java) |
| Autogenerate from models | Yes (`alembic revision --autogenerate`) | Yes (`makemigrations`) | No |
| Up/down | Yes | Yes | Only with Pro |
| Multi-head merges | First-class (`alembic merge`) | First-class | Avoided by linear naming |
| Branch labels | Yes | Yes | No |
| Ecosystem | SQLAlchemy | Django ORM | Any DB |

Alembic's autogenerate is good but not perfect — it misses some things
(server defaults, check constraints, custom types) and adds noise
(operation reordering). The discipline is to always read the generated
file before committing.

### Why version the schema in code at all?

- Every environment (dev, CI, staging, prod) converges to the same
  schema.
- The schema lives next to the code that uses it, in git history.
- Rollback is reproducible.
- Two devs can work in parallel and merge.

## How it works under the hood

### The revision graph

Alembic does not store linear version numbers; it stores a directed
acyclic graph (DAG) of revisions. Each migration file declares:

```python
revision = "0009_phase08_v1_1_schema_realignment"
down_revision = "0008_phase7_user_deleted_at"
```

This forms a chain: 0008 -> 0009. If two devs branch from 0008 and
each add a new revision, you get two *heads*:

```
0008 -> 0009a
0008 -> 0009b
```

`alembic merge -m "merge" 0009a 0009b` creates a third revision whose
`down_revision` is the tuple `("0009a", "0009b")`. After that the
graph has a single head again.

### The `alembic_version` table

Alembic stores the currently-applied revision id(s) in a table called
`alembic_version`. On `alembic upgrade head` it walks the graph from
the current row to the head, executing each `upgrade()` in order. On
`alembic downgrade <rev>` it walks backwards executing `downgrade()`.

This codebase has a wrinkle: revision ids are descriptive slugs
(`0009_phase08_v1_1_schema_realignment`, up to ~60 chars) rather than
Alembic's default 12-char hex. Postgres' default
`alembic_version.version_num` column is `VARCHAR(32)`, which overflows.
`backend/alembic/env.py` widens the column to `VARCHAR(128)` on every
startup before running migrations:

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

The CLAUDE.md note "do not remove" is there because deleting this
block causes Alembic to error on first run with a value-too-long
error for any slug id.

### File anatomy

A real Alembic file from this repo
(`backend/alembic/versions/0003_add_pending_status_and_magic_link_tokens.py`):

```python
"""Add pending status and magic_link_tokens table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_add_pending_status_and_magic_link_tokens"
down_revision = "0002_phase0_schema_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add 'pending' to the signupstatus enum (must be outside transaction)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'pending'")

    # 2. Create the magic_link_tokens table
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "signup_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_magic_link_tokens_email_created_at",
        "magic_link_tokens",
        ["email", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("magic_link_tokens")
    # Note: removing enum value 'pending' from signupstatus is not supported
    # by Postgres; intentionally skipped.
```

Three things to note for interviews:

1. The enum-add uses `autocommit_block()` because `ALTER TYPE ... ADD
   VALUE` cannot run inside a transaction in Postgres.
2. The downgrade explicitly does not remove the enum value, because
   Postgres has no `ALTER TYPE ... DROP VALUE` statement at all.
3. The index is composite (`email` + `created_at DESC`), encoding the
   query pattern for rate-limit lookups.

### Autogenerate vs hand-written

`alembic revision --autogenerate -m "..."` diffs `target_metadata`
(the SQLAlchemy `Base.metadata`) against the live DB and writes a
file. It is good at: new tables, new columns, new indexes, dropped
columns. It is bad at: server defaults, check constraints, enum
changes, data migrations, anything custom.

Best practice: autogenerate the skeleton, then **read every line**,
delete spurious operations, add data backfill steps, and add comments
explaining anything non-obvious.

### Online schema change — expand / backfill / contract

The classic three-deploy pattern for zero-downtime changes:

1. **Expand** — add the new column / table / index as nullable or
   additive. Both old and new code can run against it.
2. **Backfill** — populate the new column from existing data, either
   in the migration (if fast) or in a background job (if slow).
3. **Contract** — switch reads to the new column, then a later
   migration removes the old column / makes the new column NOT NULL.

You almost never do all three in one deploy on a busy table. A
non-null column added in a single step on Postgres before 11 rewrites
the whole table; on 11+ a default value is fast as long as it does not
involve a volatile expression.

### Lock escalation hazards on Postgres

- `ALTER TABLE ... ADD COLUMN nullable` — fast, brief
  `ACCESS EXCLUSIVE` lock to update catalogs.
- `ALTER TABLE ... ADD COLUMN NOT NULL DEFAULT 'x'` — fast on PG 11+ if
  the default is non-volatile, slow on older versions.
- `ALTER TABLE ... ADD COLUMN NOT NULL` (no default) — fast catalog
  change, but a separate scan if you want to enforce.
- `CREATE INDEX` — holds `SHARE` lock, blocks writes. Use
  `CREATE INDEX CONCURRENTLY` outside a transaction.
- `ALTER TABLE ... ALTER COLUMN TYPE` — usually a full table rewrite.
  Avoid; create a new column, backfill, swap.

`ACCESS EXCLUSIVE` blocks readers too. Take it briefly or schedule.

## How this codebase uses it

### Layout

```
backend/
  alembic.ini                # CLI config
  alembic/
    env.py                   # runtime: widens version_num, runs migrations
    versions/
      2465a60b9dbc_initial_schema.py
      b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py
      0002_phase0_schema_hardening.py
      0003_add_pending_status_and_magic_link_tokens.py
      ...
      0018_copilot_sessions_and_messages.py
```

The first two files use Alembic's default 12-char hex ids (carry-over
from before the project switched naming convention). From 0002 onward
revision ids are descriptive slugs tied to phase numbers — this makes
the `alembic_version` table self-documenting (`SELECT version_num` tells
you what phase you are on) but requires the widened column described
above.

### Running migrations

The `migrate` service in `docker-compose.yml` runs as a one-shot
container that executes `alembic upgrade head` against the `db`
service, then exits. The API service depends on `migrate` so it does
not start serving traffic until the schema is current.

Locally, you can author a new migration with:

```bash
docker compose run --rm backend alembic revision --autogenerate -m "phase X foo"
```

and apply:

```bash
docker compose run --rm migrate alembic upgrade head
```

### Connecting models to migrations

`backend/alembic/env.py` imports the SQLAlchemy `Base` and the
project's models so that autogenerate sees the full schema:

```python
from app.database import Base
from app import models  # ensures models are imported
target_metadata = Base.metadata
```

If you forget the `app import models`, autogenerate produces a file
that drops every table — because as far as the metadata knows, nothing
is declared.

### Enum-add migration pattern

Whenever a Phase adds a new value to an existing Postgres enum, the
pattern is the one shown in 0003: `autocommit_block()` plus `ALTER
TYPE ... ADD VALUE IF NOT EXISTS`. Idempotent and safe to re-run.

## Common pitfalls

### Forgetting `DROP TYPE` in downgrade

The CLAUDE.md note documents this as a latent bug in several
migrations: `upgrade()` calls `quarter_enum.create(...)` but the
matching `downgrade()` does not call `quarter_enum.drop(...)`. Effect:
on a single database, run upgrade → downgrade → upgrade and the
second upgrade fails with `DuplicateObject: type "quarter" already
exists`. Fresh upgrades on a clean DB are fine, which is why this
slipped through CI. The fix is to add `enum_t.drop(op.get_bind(),
checkfirst=True)` to every downgrade that creates an enum.

### Multi-head merges from parallel development

Two devs both branch from revision N, each commit M and M'. The
resulting `alembic upgrade head` fails with "Multiple heads detected".
Fix: `alembic merge -m "merge phases X+Y" M M'` to create a merge
revision, commit it.

### Autogenerate noise

Autogenerate sometimes emits drop+create pairs for things that did not
change semantically — index reordering, enum sort order, server
defaults that round-trip differently. Always diff, prune, and write a
docstring explaining the intent.

### Data migrations inside DDL transactions

If your migration does both DDL (add column) and a slow `UPDATE` to
backfill, the table is held under lock for the whole transaction. Two
options: chunk the backfill into a background job (preferred for large
tables) or split into multiple deploys.

### Enum changes in Postgres

- Adding a value: `ALTER TYPE x ADD VALUE 'new'` — must be outside a
  transaction, so use `autocommit_block()`.
- Removing a value: impossible. You have to create a new type, swap
  columns, drop the old type.
- Renaming a value (PG 10+): `ALTER TYPE x RENAME VALUE 'a' TO 'b'`.
  Inside transactions, fine.

### Online migration deadlocks

`ALTER TABLE` takes `ACCESS EXCLUSIVE` even for "fast" catalog
changes. If long-running readers hold a row lock, the ALTER queues
behind them, and meanwhile every other transaction queues behind the
ALTER — a single deploy stalls the whole DB. Mitigation:

```python
op.execute("SET lock_timeout = '5s'")
op.execute("ALTER TABLE ...")
```

If the ALTER cannot grab the lock in 5s, the deploy fails fast and
you retry later, rather than wedging everything.

### Forgetting `import models` in env.py

Autogenerate produces a migration that drops every table because the
metadata is empty. Always import your models module.

### Running migrations from the API container

Race condition: two API replicas start, both run `alembic upgrade
head`, both try to acquire the schema lock. One wins, one fails.
Better: a separate one-shot `migrate` service (this project) or a
deploy script that runs migrations before scaling up.

### Mixing `op` and raw SQL

`op.create_table(...)` is portable across dialects; `op.execute("SQL
text")` is not. For Postgres-only features (`UUID` columns, partial
indexes, `JSONB`) raw SQL is fine, but be honest that you are
foreclosing portability.

## Interview Q&A

**Q1 (junior).** What is the difference between
`alembic upgrade head` and `alembic upgrade +1`?
**A.** `head` runs every unapplied migration up to the current tip of
the graph. `+1` runs exactly the next one. `head` is what deploys
should run; `+1` is for stepping through during debugging.

**Q2 (junior).** Why does an Alembic migration file have both
`upgrade()` and `downgrade()`?
**A.** `upgrade()` applies the change going forward. `downgrade()`
undoes it for local development or, in rare cases, an emergency
rollback. Downgrades are not run in production by most teams — once a
new app version is live against the new schema, rolling the schema
back would break the old app's expectations.

**Q3 (mid).** How does Alembic know which migrations have been
applied?
**A.** A `alembic_version` table in the database stores the current
revision id (or ids, for multiple heads). On startup Alembic reads
that row, walks the revision graph from there to the requested
target, and runs each migration's `upgrade()` in order.

**Q4 (mid).** Walk me through adding a non-null column to a 100M-row
table without downtime.
**A.** Expand-backfill-contract. Deploy 1: add the column as nullable
(fast catalog change). Deploy 2: backfill in chunks, either in a
background job or in a separate, throttled SQL job. Deploy 3: switch
application code to read/write the new column; add a NOT NULL
constraint (PG 12+ supports `NOT VALID` then `VALIDATE CONSTRAINT` to
avoid a long lock). Optionally Deploy 4: drop the old column.

**Q5 (mid).** Two devs both branch a migration off the same parent
and merge to main. What happens, and how do you fix it?
**A.** Alembic detects two heads and refuses to upgrade. Resolution
is `alembic merge -m "..." headA headB`, which writes a no-op
migration whose `down_revision` is the tuple `(headA, headB)`. After
that the graph has a single head and `upgrade head` works.

**Q6 (senior).** Postgres enums — what are the gotchas in migrations?
**A.** Three: adding a value must run outside a transaction
(`ALTER TYPE ... ADD VALUE`), so wrap it in
`autocommit_block()`. Removing a value is not supported by Postgres
at all; the workaround is type-swap. And on downgrade, if `upgrade()`
created the enum type but `downgrade()` does not drop it, the second
upgrade fails with `DuplicateObject`. This codebase has that latent
bug, documented in CLAUDE.md.

**Q7 (senior).** Your team's CI passes a migration, but production
deploy hangs for 20 minutes and you have to roll back. What's the
likely cause and the prevention?
**A.** Likely cause: the migration's `ALTER TABLE` is waiting for
`ACCESS EXCLUSIVE` on a hot table because long-running readers or
writers hold conflicting locks. Every queued transaction lines up
behind the ALTER, taking the API down. Prevention: set a small
`lock_timeout` at the start of the migration so it fails fast instead
of blocking; review for any operation that rewrites the table
(`ALTER COLUMN TYPE`, adding `NOT NULL` to a populated column on old
PG); run migrations during low-traffic windows; consider a separate
maintenance role with `statement_timeout` configured.

**Q8 (senior).** What is your stance on running `downgrade` in
production?
**A.** Don't. Once new app code is deployed against new schema, the
schema is the contract. Rolling the schema back without rolling the
app back is a recipe for `UndefinedColumn` errors. If you must
recover, the safer path is a forward-fix migration that restores the
old shape (or runs an expand-contract back). Downgrades are valuable
for local dev and for stepping during testing.

## Further reading

- Alembic tutorial — https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Alembic "Working with Branches" — multi-head merges, branch labels.
- The "Strong Migrations" gem (Ruby) docs — best general checklist of
  unsafe operations in Postgres and MySQL, regardless of language.
  https://github.com/ankane/strong_migrations
- "Online schema changes" — gh-ost (GitHub), pt-online-schema-change
  (Percona). Even if you do not use them, the docs explain what makes
  an `ALTER` unsafe.
- PostgreSQL docs on `ALTER TABLE` — explicit lock levels per
  subcommand. https://www.postgresql.org/docs/current/sql-altertable.html
- Heroku's "Maintaining your PostgreSQL database" — production
  experience with locks and migrations.
- This repo: `backend/alembic/env.py`,
  `backend/alembic/versions/0003_add_pending_status_and_magic_link_tokens.py`,
  `backend/alembic/versions/0009_phase08_v1_1_schema_realignment.py`,
  and the CLAUDE.md notes on slug ids and downgrade `DROP TYPE`.
