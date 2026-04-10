# uni-volunteer-scheduler — project notes for Claude

UCSB SciTrek volunteer scheduling app. Sole developer: Andy. First-time Claude
Code user — prefer plain-language explanations and short replies.

## Stack
- **Backend:** FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery + Redis
- **Frontend:** React 19 + Vite 7 + Tailwind v4 + vitest + Playwright
- **Orchestration:** `docker-compose.yml` at repo root runs db, redis, backend,
  migrate (one-shot), celery_worker, celery_beat

## Running tests
Postgres and Redis are **NOT exposed to localhost** — they're only reachable
from inside the `uni-volunteer-scheduler_default` docker network. To run
backend tests:

```bash
# First time only: create the test database
docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"

# Run pytest in a one-off container on the network with code mounted
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

Frontend tests run normally: `cd frontend && npm run test -- --run`.

## Alembic conventions
- **Revision IDs use descriptive slug form** (e.g. `0003_add_pending_status_and_magic_link_tokens`), not short hex.
- `alembic/env.py` pre-widens `alembic_version.version_num` to `VARCHAR(128)` on every startup because the default 32-char column overflows our slug IDs. Do not remove.
- **Known latent bug:** several `downgrade()` functions create enum types in `upgrade()` but don't `DROP TYPE` on the way down. Fresh upgrades work fine; downgrade→upgrade round-trips fail with `DuplicateObject`. Cleanup deferred.

## CSV import cadence
Module template CSV import (Phase 5) runs **once per quarter — every 11 weeks**. Not yearly. Any UI copy, email text, or doc that says "yearly" is wrong.

## Planning harness
This project uses the **GSD (get-shit-done)** harness. Project state lives in
`.planning/` — `ROADMAP.md`, `STATE.md`, per-phase `PLAN.md` / `SUMMARY.md`,
and `remote-run.log`. Phases 0–7 are code-complete. Phase 8 (deployment) is
deferred. A product pivot (account-less signup, week-based schedule, orientation
as soft warning) is coming in the next milestone.

## Teaching style
Andy prefers **one concept per turn** with a check-in question at the end.
Don't dump long status reports mid-teaching. If asked a technical question,
give a short, concrete answer and wait for the follow-up.
