# uni-volunteer-scheduler

UCSB SciTrek volunteer scheduling app. Account-less participant signup,
quarterly CSV module-template import, three-role UX (participant, admin,
organizer). Built to replace SignupGenius for Sci Trek's volunteer
operations.

**Milestone:** v1.3-check — v1.2-prod base + v1.3 feature integration.

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

## v1.3 features being integrated onto v1.2-prod

Phases 21–29 from the v1.3 branch are being cherry-picked onto this
branch. **Phases 27 (SMS) and 28 (v1.3 QR model) are excluded** — see
`docs/superpowers/specs/2026-04-17-v1.3-integration-design.md` for the
full integration plan.

- **Orientation credit (Phase 21)** — cross-week / cross-module credit so
  a week-4 orientation counts for the whole module family. Organizer
  override + audit, admin page at `/admin/orientation-credits`. See
  `backend/app/services/orientation_service.py`.
- **Custom form fields (Phase 22)** — organizer-editable signup
  questions per event (with module-template defaults). Responses stored
  in `signup_responses`; roster + CSV export include them.
  `backend/app/services/form_schema_service.py`.
- **Recurring event duplication (Phase 23)** — admin "Duplicate to weeks
  …" action preserves slots + form schema + window. Conflict detection +
  atomic commit. `backend/app/services/event_duplication_service.py`.
- **Scheduled reminder emails (Phase 24)** — Celery Beat schedules:
  weekly kickoff, 24h-pre, 2h-pre. Per-volunteer opt-out + quiet hours
  21:00–07:00 PT + `(signup_id, kind)` idempotency.
  `backend/app/services/reminder_service.py`.
- **Waitlist + auto-promote (Phase 25)** — at-capacity signups go to
  `waitlisted`. Cancellation auto-promotes the FIFO head. Organizer
  manual promote + admin waitlist reorder.
  `backend/app/signup_service.py::promote_waitlist_fifo`.
- **Broadcast messages (Phase 26)** — organizer / admin → email all
  confirmed signups for an event. Rate-limited 5/hr per event. Audit +
  preview. `backend/app/services/broadcast_service.py`.
- **Slot swap (Phase 29, SWAP-01..04)** — atomic move of a signup to a
  different slot in the same event. Hard-fail on target full (409),
  auto-promote source waitlist, audit.
  `backend/app/services/swap_service.py`.
- **Signup window lock (Phase 29, LOCK-01/02)** — event-level
  `signup_open_at` / `signup_close_at` gates the public signup path with
  PT-localized copy. Organizer/admin paths always bypass.
- **Hide past events (Phase 29, HIDE-01)** — `site_settings` singleton
  gets `hide_past_events_from_public` (default true). Filters
  `/public/events` by last-slot-end. Admin toggle on `/admin` overview.

QR check-in with the event-level organizer-display model is planned as a
post-integration phase on this branch (not the v1.3 per-volunteer-email
model).

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

- [v1.3 integration design](docs/superpowers/specs/2026-04-17-v1.3-integration-design.md)
  — the spec driving this branch
- [Manual smoke checklist](docs/smoke-checklist.md) — human pass across all
  three roles in ~30 minutes
- [Collaboration contract](docs/COLLABORATION.md) — PR-only file list,
  sync cadence, tie-breaker rule
- [Project notes for Claude](CLAUDE.md) — stack quirks, Alembic conventions,
  CSV cadence rule

Planning artifacts (GSD harness) live in `.planning/`:
- `ROADMAP.md`, `STATE.md` — milestone + current state.
- `REQUIREMENTS-v1.3.md` — v1.3 requirement IDs (SWAP, LOCK, HIDE, INTEG, …).
- `phases/<N>-*/` — per-phase `PLAN.md`, `SUMMARY.md`, `CONTEXT.md`.

## Credits

Built for [UCSB SciTrek](https://scitrek.ucsb.edu/). UCSB students teaching
NGSS modules to local high schoolers.
