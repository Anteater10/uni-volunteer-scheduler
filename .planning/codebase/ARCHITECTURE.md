# Architecture

**Analysis Date:** 2026-04-08

## Pattern Overview

**Overall:** Classic two-tier web application with a Python FastAPI REST backend, a React SPA frontend, and an asynchronous task worker. All services are orchestrated via Docker Compose.

**Key Characteristics:**
- Monorepo with cleanly separated `backend/` (FastAPI + SQLAlchemy) and `frontend/` (React + Vite) applications
- REST API versioned under `/api/v1`, consumed by SPA via a single fetch wrapper (`frontend/src/lib/api.js`)
- Stateless JWT-based authentication (access token + DB-tracked refresh tokens), role-based authorization (admin / organizer / participant)
- Asynchronous notifications (email, reminders, weekly digest) via Celery with Redis broker and Celery Beat scheduler
- Postgres as the system of record; Alembic-managed schema migrations
- Rate limiting backed by Redis (slowapi + custom Redis counter)

## Layers

**HTTP / API layer (FastAPI routers):**
- Purpose: HTTP entry points, request validation, auth/role enforcement, audit logging, task dispatch
- Location: `backend/app/routers/`
- Contains: One router per domain resource — `auth.py`, `users.py`, `events.py`, `slots.py`, `signups.py`, `notifications.py`, `admin.py`, `portals.py`
- Depends on: `deps.py` (auth, rate-limiting, audit), `schemas.py` (Pydantic I/O models), `models.py` (ORM), `celery_app` (task enqueue)
- Used by: Registered in `backend/app/main.py` via `app.include_router(..., prefix="/api/v1")`

**Application/shared layer:**
- Purpose: Cross-cutting concerns — config, DB session, security primitives, audit logging, Celery tasks
- Location: `backend/app/`
- Key files:
  - `backend/app/main.py` — FastAPI app assembly, CORS, security headers, rate-limit middleware, router registration, `/api/v1/health` endpoint
  - `backend/app/config.py` — Pydantic settings (env-driven)
  - `backend/app/deps.py` — OAuth2/JWT, password hashing (PBKDF2-SHA256), Redis rate limiter, `get_current_user`, `require_role`, `log_action`, refresh token helpers
  - `backend/app/database.py` — SQLAlchemy engine, `SessionLocal`, `get_db` generator; forces `SET TIME ZONE 'UTC'` per connection
  - `backend/app/celery_app.py` — Celery app, SendGrid email helper, `send_email_notification`, `schedule_reminders`, `weekly_digest`, beat schedule

**Data / ORM layer:**
- Purpose: Persistence model and schema contract
- Location: `backend/app/models.py`, `backend/app/schemas.py`
- Contains: SQLAlchemy ORM models (`User`, `Event`, `Slot`, `Signup`, `CustomQuestion`, `CustomAnswer`, `Notification`, `RefreshToken`, `AuditLog`, `SiteSettings`, `Portal`, `PortalEvent`) and Pydantic request/response schemas
- Enums: `UserRole`, `SignupStatus`, `NotificationType`, `PrivacyMode`
- Used by: Routers and Celery tasks

**Migrations:**
- Location: `backend/alembic/` with `backend/alembic.ini`
- Versions: `backend/alembic/versions/2465a60b9dbc_initial_schema.py`, `backend/alembic/versions/b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py`
- Applied automatically by the `migrate` service in `docker-compose.yml` (`alembic upgrade head && python -m app.seed_admin`)

**Async worker layer:**
- Purpose: Deferred side-effects — transactional emails, scheduled reminders, weekly digest
- Location: `backend/app/celery_app.py`
- Runs as two Docker services: `celery_worker` and `celery_beat`
- Broker/result backend: Redis (`settings.celery_broker_url`, `settings.celery_result_backend`)
- Scheduled tasks: `schedule_reminders` every 5 minutes; `weekly_digest` Mondays 08:00

**Frontend shell / routing layer:**
- Purpose: App bootstrap, routing, global providers
- Location:
  - `frontend/src/main.jsx` — React 18 root, wraps app in `QueryClientProvider` (TanStack Query), `BrowserRouter`, and `AuthProvider`
  - `frontend/src/App.jsx` — `react-router-dom` route tree wrapped in `Layout`; public, authed, organizer/admin, and admin-only route groups guarded by `ProtectedRoute`
- Components: `frontend/src/components/Layout.jsx`, `frontend/src/components/ProtectedRoute.jsx`

**Frontend state layer:**
- Auth context: `frontend/src/state/authContext.jsx` — exposes `user`, `isAuthed`, `role`, `login`, `register`, `logout`, `reloadMe`; hydrates via `GET /users/me` when a token is present
- Server state: TanStack Query (`@tanstack/react-query`) created in `frontend/src/main.jsx`
- Auth storage: `frontend/src/lib/authStorage.js`

**Frontend API client layer:**
- Location: `frontend/src/lib/api.js`
- Single `request()` helper wraps `fetch`, attaches `Authorization: Bearer <token>`, safely parses JSON errors, and supports query params and body serialization
- Also exposes `downloadBlob()` for CSV/ICS downloads
- Exports a bundled `api` object with both flat (`api.listEvents`) and nested (`api.signups.my`) aliases for backwards compatibility across pages
- Base URL resolved from `import.meta.env.VITE_API_URL` with `/api/v1` appended

**Frontend pages (view layer):**
- Location: `frontend/src/pages/`
- One page component per route — public (`EventsPage`, `EventDetailPage`, `PortalPage`, `LoginPage`, `RegisterPage`), participant (`MySignupsPage`, `NotificationsPage`), organizer (`OrganizerDashboardPage`, `OrganizerEventPage`), admin (`AdminDashboardPage`, `AdminEventPage`, `UsersAdminPage`, `PortalsAdminPage`, `AuditLogsPage`), and `NotFoundPage`
- Pages call the shared `api` client and use TanStack Query for caching

## Data Flow

**Signup creation flow (`POST /api/v1/signups`):**

1. Frontend page (e.g. `EventDetailPage.jsx`) calls `api.signups.create(payload)` → `request()` in `frontend/src/lib/api.js` adds Bearer token
2. FastAPI routes to `backend/app/routers/signups.py::create_signup`
3. `get_current_user` dependency decodes JWT and loads the user row
4. Handler locks the target `Slot` row with `SELECT ... FOR UPDATE` to serialize capacity checks
5. Validates signup window (`signup_open_at`/`signup_close_at`), past-slot guard, per-user event limit, and duplicate signup
6. Confirms if `current_count < capacity`, otherwise waitlists; persists custom answers
7. Writes `AuditLog` row via `log_action` (same transaction), then `db.commit()`
8. Enqueues `send_email_notification.delay(...)` on Celery
9. Celery worker sends email via SendGrid (if configured) and inserts a `Notification` row
10. Response returned to frontend; TanStack Query invalidates related caches

**Cancel + waitlist promotion flow (`POST /api/v1/signups/{id}/cancel`):**

1. Locks signup row, then slot row
2. Heals `slot.current_count` from actual confirmed count (defensive)
3. Marks signup cancelled, decrements count
4. FIFO-promotes waitlisted signups until capacity is filled (each also `SELECT ... FOR UPDATE`)
5. Commits, then dispatches cancellation email to the user and promotion emails to promoted users

**Auth flow:**

1. `LoginPage` calls `api.login(email, password)` which `POST`s `application/x-www-form-urlencoded` to `/api/v1/auth/token` (FastAPI `OAuth2PasswordRequestForm`)
2. Backend verifies password via `verify_password` (PBKDF2-SHA256), issues JWT with `sub` + `role` claims and a DB-persisted refresh token
3. Frontend stores access token via `authStorage.setToken`
4. `AuthProvider` calls `api.me()` → `GET /users/me` to hydrate user on load
5. `ProtectedRoute` checks `isAuthed` and optional `roles` prop against context

**Scheduled notification flow:**

1. `celery_beat` fires `schedule_reminders` every 300s
2. Task queries slots starting in ~24h or ~2h and dispatches `send_email_notification` per confirmed signup
3. `weekly_digest` fires Mondays 08:00 UTC, groups upcoming confirmed signups per user

**State Management:**
- Backend: per-request SQLAlchemy session via `get_db` dependency; handlers control commit/rollback explicitly (helpers like `log_action`, `create_refresh_token`, `revoke_refresh_token` never commit)
- Frontend: TanStack Query for server state; React context (`AuthContext`) for auth/session; localStorage-backed `authStorage` for the access token

## Key Abstractions

**Event → Slot → Signup hierarchy:**
- `Event` has many `Slot`s (cascade delete). `Slot` has many `Signup`s. `Signup` has many `CustomAnswer`s tied to the event's `CustomQuestion`s.
- Capacity is enforced at the `Slot` level via `capacity` and a denormalized `current_count` (confirmed-only, self-healing on write).

**Portal:**
- A named, slug-addressable collection of events joined via `PortalEvent`. Rendered publicly at `/portals/:slug`.

**RefreshToken:**
- DB-persisted long-lived token (vs. stateless access JWT) enabling revocation. Helpers in `backend/app/deps.py`.

**AuditLog:**
- Append-only record written in-transaction via `deps.log_action(db, actor, action, entity_type, entity_id, extra)` for every mutating operation. Surfaced via `AuditLogsPage` → `/admin/audit_logs`.

**Role-based dependency:**
- `require_role(*roles)` factory returns a FastAPI dependency that 403s on mismatch. Used by routers to gate organizer/admin endpoints.

## Entry Points

**Backend HTTP:**
- Location: `backend/app/main.py`
- Triggers: Uvicorn serving the FastAPI `app` (container exposes port 8000)
- Responsibilities: Middleware (CORS, `SlowAPIMiddleware`, security headers), rate-limit exception handler, `/api/v1/health`, router registration

**Backend worker:**
- Location: `backend/app/celery_app.py` (`celery` app)
- Triggers: `celery -A app.celery_app.celery worker -l info` and `celery ... beat ...` (see `docker-compose.yml`)

**Backend migrations/seed:**
- Location: `backend/alembic/env.py`, `backend/app/seed_admin.py`
- Triggers: `migrate` one-shot service in `docker-compose.yml`

**Frontend:**
- Location: `frontend/index.html` → `frontend/src/main.jsx` → `frontend/src/App.jsx`
- Triggers: Vite dev server or built static assets

## Error Handling

**Strategy:** FastAPI `HTTPException` for expected failures (400/401/403/404/429); JWT decode errors mapped to 401 in `get_current_user`; rate-limit breaches return 429 via `_rate_limit_exceeded_handler`.

**Patterns:**
- Concurrency-critical writes wrap ORM access in `with_for_update()` row locks (e.g. `backend/app/routers/signups.py`)
- Helpers like `log_action` never commit so callers control transaction boundaries
- Frontend `request()` in `frontend/src/lib/api.js` normalizes FastAPI error shapes (`detail` string, `detail[].msg` list, generic `message`) into `Error` messages

## Cross-Cutting Concerns

**Logging:** Audit trail via `AuditLog` table (`deps.log_action`). No structured application logger wired in code reviewed.

**Validation:** Pydantic schemas in `backend/app/schemas.py` enforce request/response shapes. Router-level validators for event/slot date ranges (`_validate_event_dates`, `_validate_slot_range_within_event` in `backend/app/routers/events.py`).

**Authentication:** JWT Bearer tokens via `OAuth2PasswordBearer` (`tokenUrl="/api/v1/auth/token"`). PBKDF2-SHA256 password hashing via passlib. Refresh tokens stored server-side for revocation.

**Authorization:** `require_role(...)` dependency + handler-level ownership checks (`_ensure_event_owner_or_admin`).

**Rate limiting:** Two layers — `slowapi` middleware (decorator-driven) and a custom Redis counter factory `rate_limit(max_requests, window_seconds)` in `backend/app/deps.py`.

**Timezones:** DB connection forced to UTC in `backend/app/database.py`; handlers normalize aware/naive datetimes with `_to_naive_utc` helpers before comparisons.

**Security headers:** Custom middleware in `backend/app/main.py` sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`. CSP is intentionally omitted (comment notes Swagger UI CDN compatibility).

---

*Architecture analysis: 2026-04-08*
