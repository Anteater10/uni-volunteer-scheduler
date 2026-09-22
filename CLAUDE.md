# uni-volunteer-scheduler — project notes for Claude

UCSB SciTrek volunteer scheduling app. Current milestone: **L — Launch**
(live, verified, handed to Rafael). Where things stand is in
`.planning/STATE.md`; what is left is in `.planning/ROADMAP.md`, the single
source of truth.

**Who works here (updated 2026-09-21, roadmap #172):**

- **Andy** does all backlog work and owns the project. He commits as both
  "Andy" and "Siddhant Subramanian". He prefers plain-language explanations
  and short replies.
- **Rafael** (`rsolorzano-ucsb`) does deployment only. Nothing in the backlog is
  a handoff to him.
- **Hung** built the participant pillar in v1.2. His last commit on `main` was
  2026-08-03.

The v1.2 setup (two developers, long-lived `feature/v1.2-*` role branches,
pillar ownership) is over. `docs/COLLABORATION.md` describes that setup and
is kept for history. Only its PR-only list still applies.

## How work flows

1. **Start of a session:** run `git branch --show-current`. If you are on
   `main`, do not edit anything. Create a short-lived branch off an up-to-date
   `main`, named after the roadmap phase: `chore/S-ci-honesty`,
   `feature/L4-quick-fixes`, `docs/L4-followups-...`.
2. **One PR per small piece of work.** It merges to `main` once CI is green and
   Andy says so. Delete the branch after the merge.
   The dev containers **do not mount the code**: after backend changes merge,
   run `docker compose up -d --build backend celery_worker celery_beat`, or the
   local stack keeps running the old image (found 2026-09-21: it was a day behind).
3. **Every PR fully tests the files it touches.** Coverage floors only go up
   (roadmap #163/#168). The hard 100% gate, for backend *and* frontend, lands
   after L5.
4. **Keep the three trackers in step, in the same PR:** the roadmap row
   (`.planning/ROADMAP.md`), its Jira ticket (project `SCRUM`, tagged
   `[SCRUM-N]` on the row), and, for GitHub issues, the "KanBan Board" project
   (#2).
5. **A phase is done only when every row is.** Every row ✅ with a merged PR,
   its Jira ticket at Done, and STATE.md updated. Report "N of M rows done",
   never "phase done". This is roadmap structural rule 4, added because L3 was
   once reported done at 2 of 6.

**PR-only files** need Andy's explicit OK before any edit: `.planning/ROADMAP.md`,
`.planning/STATE.md`, `CLAUDE.md`, `.github/workflows/*`,
`backend/app/models.py`, `backend/alembic/versions/*`, `docker-compose.yml`, the
Dockerfiles, and the shared frontend contract files listed in
`docs/COLLABORATION.md`.

**No Claude attribution** in commit messages or PR bodies: no footer, no
co-author trailer.

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

## CSV import pipeline — removed
The Phase 5/18 CSV module-import pipeline (frontend surface, `/admin/imports`
endpoints, `csv_imports` table, Celery task) was deleted in PR #51. Modules are
created and edited by hand in the admin UI. Events previously committed by an
import are ordinary events and were untouched.

## Planning harness
This project uses the **GSD (get-shit-done)** harness. Project state lives in
`.planning/` — `ROADMAP.md`, `STATE.md`, per-phase `PLAN.md` / `SUMMARY.md`,
and `remote-run.log`.

Milestone history: v1.0 (phases 0–7), v1.1 (8–13) and v1.2-prod (14–20)
shipped by 2026-04-17, and v1.4 added the copilot. Since 2026-09 the work has
been organised as the Launch roadmap (Gate 0, then phases L0–L8, P, D and X)
in `.planning/ROADMAP.md`. Cross-role regression coverage lives in
`e2e/cross-role.spec.js`. For manual smoke verification, see
[docs/smoke-checklist.md](docs/smoke-checklist.md).

## Teaching style
Andy prefers **one concept per turn** with a check-in question at the end.
Don't dump long status reports mid-teaching. If asked a technical question,
give a short, concrete answer and wait for the follow-up.
