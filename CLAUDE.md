# uni-volunteer-scheduler — project notes for Claude

UCSB SciTrek volunteer scheduling app. **v1.2-prod milestone — production-ready by role.**
Two developers are running Claude Code + GSD on this repo from their own machines:

- **Andy** — admin pillar (Phases 16, 17, 18) and organizer pillar (Phase 19); project owner
- **Hung** — participant pillar (Phase 15)
- Phase 20 (cross-role integration) is shared

Both developers use single checkout + branch switching on their own clones. Coordination
happens via push/pull/PRs against shared `main`. See `docs/COLLABORATION.md` for the full
collaboration contract (file-ownership rules, PR-only list, sync cadence, tie-breaker).

Andy prefers plain-language explanations and short replies.

## Branch awareness

Before starting any work in a session, run:

```bash
git branch --show-current
```

Then check the table below and only edit files in the matching pillar. Files on the
PR-only list in `docs/COLLABORATION.md` require explicit user permission before editing.

| Branch | Pillar | Owner |
|---|---|---|
| `feature/v1.2-participant` | participant pillar | Hung |
| `feature/v1.2-admin` | admin pillar | Andy |
| `feature/v1.2-organizer` | organizer pillar | Andy |
| `main` | integration / shared | read-only between phase merges |

**Rule:** Only edit files in the pillar that owns the current branch. The PR-only list
(in `docs/COLLABORATION.md`) covers files where concurrent edits cause hard-to-reverse
damage — those need explicit user permission regardless of which branch you are on.

**If you find yourself on `main`, do NOT make changes.** Switch to the appropriate
role branch first, or ask the user which branch they want.

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
and `remote-run.log`.

**Milestone status (v1.2-prod complete — 2026-04-17):**

- v1.0 phases 0–7 shipped (2026-04-08). Phase 8 (deployment) remains deferred
  to a later milestone.
- v1.1 phases 8–13 shipped (2026-04-10) — account-less realignment, magic-link
  infrastructure, 16-scenario Playwright baseline.
- v1.2-prod phases 14–20 shipped (2026-04-17) — production-ready by role
  (participant, admin, organizer) with cross-role Playwright integration.

Cross-role regression coverage lives in `e2e/cross-role.spec.js` (5 scenarios
× 6 browser projects). Manual smoke verification: see
[docs/smoke-checklist.md](docs/smoke-checklist.md) for the ~30-minute
three-window pass. Next milestone (deployment / v1.3 polish) TBD.

## Teaching style
Andy prefers **one concept per turn** with a check-in question at the end.
Don't dump long status reports mid-teaching. If asked a technical question,
give a short, concrete answer and wait for the follow-up.
