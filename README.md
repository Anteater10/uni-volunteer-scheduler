# uni-volunteer-scheduler

UCSB SciTrek volunteer scheduling app. Replaces SignUpGenius for
orientation + teaching-module volunteer coordination.

- **Backend:** FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery + Redis
- **Frontend:** React 19 + Vite 7 + Tailwind v4 + vitest

## Quick start

```bash
docker compose up -d  # db, redis, backend, celery_worker, celery_beat, migrate
cd frontend && npm install && npm run dev
```

Backend: http://localhost:8000 · Frontend: http://localhost:5173 ·
Mailpit (dev email): http://localhost:8025

## v1.3 features (SciTrek parity)

Shipped between Phase 21 and Phase 29 (2026-04-17).

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
- **SMS reminders (Phase 27)** — AWS SNS behind `SMS_ENABLED` flag. TCPA
  opt-in on signup form, 2h-pre SMS, 30-min-after no-show nudge,
  STOP/HELP footer. `backend/app/services/sms_service.py`.
- **QR check-in (Phase 28)** — confirmation email embeds an inline PNG
  QR encoding the existing SIGNUP_MANAGE magic-link URL. Organizer
  scanner at roster page (camera + text-input fallback). No new secret
  surface. `backend/app/services/qr_service.py`.
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

## Docs

- [`docs/COLLABORATION.md`](docs/COLLABORATION.md) — two-developer contract
  (Andy / Hung), file ownership, PR-only list.
- [`docs/smoke-checklist.md`](docs/smoke-checklist.md) — manual smoke
  steps for every v1.3 surface.
- [`docs/ADMIN-AUDIT.md`](docs/ADMIN-AUDIT.md) — admin audit log
  conventions.
- [`docs/ccpa-policy.md`](docs/ccpa-policy.md) — user-data policy.

Planning artifacts (GSD harness) live in `.planning/`:
- `ROADMAP.md`, `STATE.md` — milestone + current state.
- `REQUIREMENTS-v1.3.md` — v1.3 requirement IDs (SWAP, LOCK, HIDE, INTEG, …).
- `phases/<N>-*/` — per-phase `PLAN.md`, `SUMMARY.md`, `CONTEXT.md`.

## Running tests

**Backend** (Postgres + Redis only reachable from the docker network):

```bash
docker exec uni-volunteer-scheduler-db-1 \
  psql -U postgres -c "CREATE DATABASE test_uvs;"   # first time only
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

**Frontend:**

```bash
cd frontend && npm run test -- --run
```

Current known-baseline failures (do not regress):
- Backend: 2 (`tests/test_import_pipeline.py`).
- Frontend: 6 (AdminTopBar ×2, AdminLayout ×1, ExportsSection ×1, ImportsSection ×2).

## Alembic notes

- Revision IDs use descriptive slug form (e.g. `0017_site_settings_hide_past_events`).
- `alembic/env.py` pre-widens `alembic_version.version_num` to VARCHAR(128).
- CSV module-template import cadence is **once per quarter / every 11 weeks**.
