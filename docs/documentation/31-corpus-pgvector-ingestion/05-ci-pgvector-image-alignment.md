# CI pgvector image alignment

**Phase:** 31 — Knowledge Corpus + pgvector Ingestion
**Task:** Follow-on CI patch for PR #17

## TL;DR

The CI `phase0 backend tests + coverage` job ran `alembic upgrade head`
against the Postgres service container, which was on plain
`postgres:16`. Migration 0019 (Phase 31) executes
`CREATE EXTENSION IF NOT EXISTS vector`. The extension was not
installed on the CI image, so the migration failed before any test
ran. Fix: align the CI Postgres service image with the dev/prod image
declared in `docker-compose.yml`.

## Symptom

```
INFO  [alembic.runtime.migration] Running upgrade
  0018_copilot_sessions_and_messages -> 0019_enable_pgvector_corpus_tables,
  Phase 31 (v1.4): enable pgvector + corpus tables.

sqlalchemy.exc.NotSupportedError:
  (psycopg2.errors.FeatureNotSupported) extension "vector" is not available
DETAIL: Could not open extension control file
  "/usr/share/postgresql/16/extension/vector.control":
  No such file or directory.
HINT: The extension must first be installed on the system where
  PostgreSQL is running.

[SQL: CREATE EXTENSION IF NOT EXISTS vector]
##[error]Process completed with exit code 1.
```

## Root cause

`CREATE EXTENSION <name>` does **not** install code; it only registers
an already-installed extension binary with the current database.
pgvector's binary (`vector.so`) and registration file (`vector.control`)
must exist on the Postgres container's filesystem under
`/usr/share/postgresql/16/extension/` before the SQL runs.

The local dev stack already swapped to `pgvector/pgvector:pg16` in plan
02 of Phase 31. The CI workflow `.github/workflows/ci.yml` was not
updated at the same time. Local green / CI red is the predictable
consequence.

## Fix

```yaml
# .github/workflows/ci.yml
services:
  postgres:
    image: pgvector/pgvector:pg16   # was: postgres:16
    env:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: uni_volunteer
    ports:
      - "5432:5432"
    options: >-
      --health-cmd="pg_isready -U postgres"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=20
```

The image is API-compatible with `postgres:16` — same port, same
healthcheck, same auth semantics — so no other CI knob has to change.

## Verification

1. `alembic upgrade head` succeeds in CI (passes 0001..0019 clean).
2. `SELECT extname FROM pg_extension;` includes `vector` in the
   resulting test database.
3. Downstream tests in `backend/tests/test_corpus_*.py` (esp.
   `test_corpus_migration_round_trip.py` and
   `test_corpus_hnsw_index.py`) run as designed.

## Invariants this restores

- **Image parity invariant.** Every Postgres service in
  `docker-compose.yml` and every Postgres service in
  `.github/workflows/*.yml` references the same image tag. Updates
  ship in one PR.
- **`alembic upgrade head` is the gate.** Any environment that cannot
  reach `head` on a clean DB is non-conforming. Tests below the
  migration are not meaningful in such an environment.
- **`CREATE EXTENSION` requires pre-installed binaries.** Workflows
  that introduce a new extension must update the image, not the
  application code.

## Related files

| Path | Role |
|---|---|
| `.github/workflows/ci.yml` | CI workflow, contains the `services.postgres.image` key. |
| `docker-compose.yml` | Dev/prod compose stack, already on `pgvector/pgvector:pg16` since plan 02. |
| `backend/alembic/versions/0019_enable_pgvector_corpus_tables.py` | The migration that triggers the requirement. |
| `backend/app/corpus/ingest.py` (`build_hnsw_index`) | Downstream consumer — depends on the extension being registered. |

## Suggested guard for next time

Add a one-line probe to the CI job immediately after `alembic upgrade
head` so a regression fails fast with a clear message rather than a
cascade of opaque test errors:

```bash
psql "$DATABASE_URL" -tAc \
  "SELECT 1 FROM pg_extension WHERE extname = 'vector';" \
  | grep -q '^1$' \
  || { echo "::error::pgvector extension missing in CI Postgres"; exit 1; }
```

## Glossary

- **Postgres extension** — a packaged unit of SQL + (often) compiled
  code that augments the server. Registered per-database via
  `CREATE EXTENSION`. Binaries live on the server's filesystem; the
  extension is not "installed" by the SQL statement, only registered.
- **Service container** — GitHub Actions' `services:` block runs an
  image alongside the job's main runner. Steps connect over
  `localhost:<exposed-port>`. The runner's filesystem is *not* the
  service's filesystem.
- **`vector.control`** — pgvector's extension registration file. Its
  presence is what `CREATE EXTENSION vector` actually checks.
- **Twin-stack drift** — informal term for two environment
  declarations (local + CI, or staging + prod) silently falling out
  of sync because there is no cross-file invariant check.
