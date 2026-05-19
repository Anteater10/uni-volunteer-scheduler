# Lecture 05 — CI pgvector image alignment

## Why a follow-on lecture exists for a one-line CI fix

Phase 31's master SUMMARY claimed shipped, the migration round-trip test
was green locally, and 48 backend tests passed. PR #17 still failed CI
on the first push. That gap — local green, CI red, root cause one line
deep — is the lesson. The Phase 31 substrate is correct; the **boundary
between local and CI** drifted out of alignment with the rest of the
stack, and the boundary is exactly the kind of thing that loud unit
tests will not catch.

The fix is tiny:

```yaml
# .github/workflows/ci.yml
services:
  postgres:
    image: pgvector/pgvector:pg16   # was: postgres:16
```

The teaching is what failed to catch it and why.

## What broke

The job `phase0 backend tests + coverage` runs `alembic upgrade head` as
its first DB-touching step. With migration 0019 in the chain, that step
executes:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

CI was running plain `postgres:16`. The pgvector extension is a
Postgres extension distributed as compiled `.so` files plus a
`vector.control` registration file in
`/usr/share/postgresql/16/extension/`. The plain image doesn't ship
either. Postgres returns:

```
psycopg2.errors.FeatureNotSupported:
  extension "vector" is not available
DETAIL: Could not open extension control file
  "/usr/share/postgresql/16/extension/vector.control":
  No such file or directory.
HINT: The extension must first be installed on the system where
  PostgreSQL is running.
```

`CREATE EXTENSION` does not install code — it only registers an
already-installed extension with the current database. The binaries
have to be on disk before `CREATE EXTENSION` runs. Plain `postgres:16`
has no path to acquire them at job start; the image is read-only by
the time the service container boots.

## Why local was green

`docker-compose.yml` had already been switched to
`pgvector/pgvector:pg16` back in plan 02. Locally, `alembic upgrade
head` ran against that image, found the extension, succeeded. Tests
green. The drift was that the same swap was never made in
`.github/workflows/ci.yml`. Two configs that should mirror each other
had silently fallen out of sync over a single phase.

This is the *Twin-Stack Drift* anti-pattern: every project that runs
the same DB locally (compose) and remotely (CI service container)
maintains two image references for the same database. They must move
together. They almost never do, because:

- They live in different files (often different folders).
- Local feedback is instant; CI feedback is delayed.
- The CI file is touched far less often.

The pattern shows up identically with Redis modules, Postgres
extensions (PostGIS, TimescaleDB, pgcrypto in some distros), and even
Python base images. If you ever read "works locally, fails in CI" in
a postmortem, the first place to check is whether the *system layer*
matches.

## Why the image carries the extension at all

There are three places the extension could come from:

1. **Baked into the image** (`pgvector/pgvector:pg16`). What we use.
   One pull, ready instantly, deterministic version, no build step.
2. **Compiled at container startup** via an `initdb.d/` script. Would
   need `make`, the postgres dev headers, and a network fetch on every
   cold start. Slow, fragile.
3. **Installed via the host package manager** (`apt install
   postgresql-16-pgvector`). Possible on a real VM, but the CI service
   container has no package manager invoked between `docker pull` and
   the migration step. There is no "shell open" to install into.

Option 1 is the only one that gives CI parity with production. Once
you swap to it, the image becomes the *contract*: "this database
includes pgvector at version X built against pg16."

## How CI service containers actually work

The block under `services:` in a GitHub Actions workflow asks the
runner to `docker run` an image, expose its port, and run a
healthcheck loop until the service answers. The job's own steps then
talk to that container at `localhost:<port>` (the port is published
on the runner's network namespace).

The job step `alembic upgrade head` runs **outside** the Postgres
container, on the runner, using `DATABASE_URL=postgresql://…
@localhost:5432/uni_volunteer`. Alembic opens a regular TCP
connection. The query `CREATE EXTENSION vector` is then handled
inside the Postgres container — so whatever lives on the runner's
filesystem is irrelevant. Only the Postgres container's
`/usr/share/postgresql/16/extension/` matters.

That's the conceptual mistake that's easy to make: you might think
"I'll install pgvector on the runner." That does nothing. The
extension has to be on the database's filesystem.

## What the fix looks like in practice

The diff is a single image tag. The fallout is interesting:

- The pgvector image *is* a Postgres image. It inherits everything
  from `postgres:16` and adds two files plus a registration script in
  the data-directory init phase. Pull size goes from ~250 MB to ~290
  MB. CI cold-start cost: a couple of seconds the first time, then
  cached.
- The healthcheck (`pg_isready`) keeps working — pgvector doesn't
  change auth, ports, or socket behaviour.
- Migrations 0001–0018 run identically. Migration 0019 now finds the
  extension and registers it into the test database.

## Lessons that scale beyond this fix

1. **Twin configs must point at the same image.** Audit
   `docker-compose.yml` and `.github/workflows/*.yml` together. A
   one-line diff in the wrong file invalidates a whole phase's worth
   of testing.
2. **`alembic upgrade head` is the cheapest smoke test you have.** It
   runs every distinct DDL the project has ever shipped. If a fresh
   environment can't reach `head`, no integration test below the
   migration step is meaningful.
3. **Local green ≠ remote green when the environment is part of the
   contract.** The contract here was "Postgres has pgvector." The
   local environment satisfied it; the CI environment did not. The
   tests never told you that, because they assumed the contract held.
4. **The failure was loud, the cause was quiet.** A 100-line traceback
   pointed at the right line (`op.execute("CREATE EXTENSION IF NOT
   EXISTS vector")`). The *first* line of the error message ("extension
   vector is not available") was the answer; everything else was
   exhaust. Read the first error sentence before scrolling.

## Where this fits in the Phase 31 story

Phase 31 ships *substrate*. Substrate isn't done until everywhere it's
exercised — local dev, CI, eventually prod deploys — agrees on what
the substrate looks like. The image alignment is the last invariant
in that contract, and it's worth a lecture precisely because it's the
one that's easiest to forget.

## Operational checklist for next time

- When a phase introduces a new Postgres extension or Redis module:
  - Bump the image in `docker-compose.yml`.
  - Bump the matching `services.<svc>.image` in *every* workflow
    that runs that service.
  - Add a sanity step to the workflow that runs `SELECT
    extname FROM pg_extension;` after `alembic upgrade head` — fail
    fast if anything's missing.
- Every cross-cutting "system layer" change should land with a paired
  CI patch in the same PR. The temptation to "ship now, fix CI in a
  follow-up" is what produced this exact bug.
