# uni-volunteer-scheduler

UCSB SciTrek volunteer scheduling app. Account-less participant signup,
quarterly CSV module-template import, three-role UX (participant, admin,
organizer). Built to replace SignupGenius for Sci Trek's volunteer
operations.

**Milestone:** v1.2-prod — production-ready by role.

## Stack

- **Backend:** FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery + Redis
- **Frontend:** React 19 + Vite 7 + Tailwind v4
- **Testing:** vitest (frontend unit), pytest (backend), Playwright (E2E,
  6-browser matrix)
- **Orchestration:** `docker-compose.yml` at repo root — db, redis, backend,
  migrate (one-shot), celery_worker, celery_beat, mailpit

## Quick boot

From the repo root:

```bash
# Fresh stack (drops volumes)
docker compose down -v
docker compose up -d

# Run migrations (one-shot)
docker compose run --rm migrate

# Frontend dev server (separate terminal)
cd frontend && npm install && npm run dev
```

The frontend serves at http://localhost:5173, backend at http://localhost:8000,
Mailpit (dev email capture) at http://localhost:8025.

## Running tests

Postgres and Redis are **NOT exposed to localhost** — they're only reachable
from inside the `uni-volunteer-scheduler_default` docker network. Backend
tests run in a one-off container on that network. See [CLAUDE.md](CLAUDE.md)
for the full setup, including first-time `CREATE DATABASE test_uvs`.

- **Backend** (docker-network pattern):
  ```bash
  docker run --rm \
    --network uni-volunteer-scheduler_default \
    -v $PWD/backend:/app -w /app \
    -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
    uni-volunteer-scheduler-backend \
    sh -c "pytest -q"
  ```
- **Frontend:** `cd frontend && npm run test -- --run`
- **Playwright E2E:** `EXPOSE_TOKENS_FOR_TESTING=1 npx playwright test`
  (6-browser matrix: Chromium, Firefox, WebKit, Pixel 5, iPhone 12, iPhone
  SE 375)

## Role tour

With the stack up and `seed_e2e.py` run (or via Playwright globalSetup):

- **Participant (account-less):** http://localhost:5173/events — browse
  events by week, open an event, pick slots, enter name + email + phone,
  confirm via magic link.
- **Admin:** http://localhost:5173/login → `admin@e2e.example.com` /
  `Admin!2345` → lands on `/admin`. Overview, Audit Logs, Users, Portals,
  Templates, Imports (quarterly CSV → LLM extraction), Exports.
- **Organizer:** http://localhost:5173/login → `organizer@e2e.example.com` /
  `Organizer!2345` → lands on `/organizer` (phone-first dashboard with
  Today / Upcoming / Past tabs and tap-to-check-in roster).

## Further reading

- [Roadmap (v1.2-prod milestone)](.planning/ROADMAP.md) — phase ledger
  14–20
- [Manual smoke checklist](docs/smoke-checklist.md) — human pass across all
  three roles in ~30 minutes
- [Collaboration contract](docs/COLLABORATION.md) — PR-only file list,
  sync cadence, tie-breaker rule
- [Project notes for Claude](CLAUDE.md) — stack quirks, Alembic conventions,
  CSV cadence rule

## Credits

Built for [UCSB SciTrek](https://scitrek.ucsb.edu/). UCSB students teaching
NGSS modules to local high schoolers.
