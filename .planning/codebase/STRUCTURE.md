# Codebase Structure

**Analysis Date:** 2026-04-08

## Directory Layout

```
uni-volunteer-scheduler/
├── backend/                        # FastAPI + SQLAlchemy + Celery service
│   ├── Dockerfile                  # Image for API, worker, beat, migrate services
│   ├── Readme                      # Backend notes
│   ├── requirements.txt            # Python dependencies
│   ├── alembic.ini                 # Alembic config
│   ├── alembic/                    # DB migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   ├── README
│   │   └── versions/
│   │       ├── 2465a60b9dbc_initial_schema.py
│   │       └── b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py
│   ├── app/                        # Application package
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point (app, middleware, routers)
│   │   ├── config.py               # Pydantic settings loaded from env
│   │   ├── database.py             # SQLAlchemy engine, SessionLocal, get_db
│   │   ├── deps.py                 # Auth, hashing, JWT, rate limiting, audit helpers
│   │   ├── models.py               # SQLAlchemy ORM models + enums
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── celery_app.py           # Celery app, tasks, beat schedule
│   │   ├── seed_admin.py           # Bootstrap admin user
│   │   └── routers/                # HTTP route modules (one per resource)
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── events.py
│   │       ├── slots.py
│   │       ├── signups.py
│   │       ├── notifications.py
│   │       ├── portals.py
│   │       └── admin.py
│   └── tests/
│       └── test_smoke.py
├── frontend/                       # React + Vite SPA
│   ├── index.html                  # Vite HTML shell
│   ├── vite.config.js              # Vite config
│   ├── eslint.config.js            # Flat ESLint config
│   ├── package.json                # npm manifest
│   ├── package-lock.json
│   ├── public/                     # Static assets served verbatim
│   │   └── vite.svg
│   └── src/
│       ├── main.jsx                # React root, providers, router bootstrap
│       ├── App.jsx                 # Route tree
│       ├── App.css
│       ├── index.css
│       ├── assets/                 # Imported static assets (e.g. react.svg)
│       ├── components/             # Shared layout + guards
│       │   ├── Layout.jsx
│       │   └── ProtectedRoute.jsx
│       ├── lib/                    # Non-React utilities
│       │   ├── api.js              # Fetch wrapper + bundled API client
│       │   ├── authStorage.js      # localStorage token helpers
│       │   └── datetime.js         # Date/time formatting helpers
│       ├── state/                  # React context providers
│       │   └── authContext.jsx
│       └── pages/                  # Route-level page components
│           ├── EventsPage.jsx
│           ├── EventDetailPage.jsx
│           ├── PortalPage.jsx
│           ├── LoginPage.jsx
│           ├── RegisterPage.jsx
│           ├── MySignupsPage.jsx
│           ├── NotificationsPage.jsx
│           ├── OrganizerDashboardPage.jsx
│           ├── OrganizerEventPage.jsx
│           ├── AdminDashboardPage.jsx
│           ├── AdminEventPage.jsx
│           ├── UsersAdminPage.jsx
│           ├── PortalsAdminPage.jsx
│           ├── AuditLogsPage.jsx
│           └── NotFoundPage.jsx
├── scripts/
│   └── smoke_test.sh               # End-to-end smoke test script
├── docker-compose.yml              # db, redis, backend, migrate, celery_worker, celery_beat
├── .github/                        # GitHub workflows / config
├── .planning/                      # GSD planning workspace (not application code)
├── IDEAS.md                        # Product/engineering brainstorming notes
├── LICENSE
└── README.md
```

## Directory Purposes

**`backend/app/`:**
- Purpose: The FastAPI application package — all runtime Python code lives here
- Contains: Entry point, config, DB wiring, ORM models, Pydantic schemas, shared dependencies, Celery app, per-resource routers
- Key files: `main.py`, `deps.py`, `models.py`, `schemas.py`, `celery_app.py`

**`backend/app/routers/`:**
- Purpose: HTTP layer, one module per domain resource
- Contains: `APIRouter` instances with `prefix=/<resource>` and `tags=["<resource>"]`; registered in `backend/app/main.py` with `/api/v1` prefix
- Key files: `events.py`, `signups.py`, `admin.py`, `portals.py`

**`backend/alembic/`:**
- Purpose: Schema migration history
- Contains: Alembic environment (`env.py`), templated script generator, and `versions/` with one file per migration
- Generated: Partially (`versions/` files are hand-edited after autogenerate)
- Committed: Yes

**`backend/tests/`:**
- Purpose: Backend test suite
- Contains: `test_smoke.py`
- Committed: Yes

**`frontend/src/pages/`:**
- Purpose: One component per route; handles data fetching and composition for that screen
- Naming: `PascalCasePage.jsx`

**`frontend/src/components/`:**
- Purpose: Shared/reusable components used across pages
- Current contents: `Layout.jsx` (app chrome/nav), `ProtectedRoute.jsx` (auth + role gate)

**`frontend/src/lib/`:**
- Purpose: Framework-agnostic utilities and the API client
- Key files: `api.js` (central fetch wrapper), `authStorage.js`, `datetime.js`

**`frontend/src/state/`:**
- Purpose: React context providers for global client state
- Current contents: `authContext.jsx` (`AuthProvider`, `useAuth` hook)

**`frontend/public/`:**
- Purpose: Static files served as-is by Vite at the site root
- Generated: No
- Committed: Yes

**`scripts/`:**
- Purpose: Repo-level operational scripts
- Contents: `smoke_test.sh`

**`.github/`:**
- Purpose: GitHub metadata (Actions workflows, templates)

## Key File Locations

**Entry Points:**
- `backend/app/main.py` — FastAPI application (`app`)
- `backend/app/celery_app.py` — Celery application (`celery`)
- `frontend/src/main.jsx` — React root; wraps `<App/>` with `QueryClientProvider`, `BrowserRouter`, `AuthProvider`
- `frontend/index.html` — Vite HTML entry
- `docker-compose.yml` — Orchestrates all runtime services

**Configuration:**
- `backend/app/config.py` — Pydantic `Settings` (reads `backend/.env`)
- `backend/alembic.ini` — Alembic runtime config
- `frontend/vite.config.js` — Vite build/dev config
- `frontend/eslint.config.js` — ESLint flat config
- `frontend/package.json` — npm scripts and dependencies
- `backend/requirements.txt` — Python dependencies

**Core Logic:**
- `backend/app/routers/signups.py` — Signup creation, cancel, waitlist promotion, ICS export
- `backend/app/routers/events.py` — Event CRUD, slot generation, custom questions, clone
- `backend/app/routers/admin.py` — Admin-only operations (summary, audit logs, signup moderation)
- `backend/app/routers/auth.py` — Login, register, token refresh, SSO hooks
- `backend/app/celery_app.py` — `send_email_notification`, `schedule_reminders`, `weekly_digest`
- `backend/app/deps.py` — `get_current_user`, `require_role`, `log_action`, JWT/refresh helpers
- `backend/app/models.py` — All ORM models
- `frontend/src/lib/api.js` — The single API client used by every page
- `frontend/src/state/authContext.jsx` — Auth session state

**Testing:**
- `backend/tests/test_smoke.py` — Backend smoke test
- `scripts/smoke_test.sh` — End-to-end smoke test script

**Migrations:**
- `backend/alembic/versions/2465a60b9dbc_initial_schema.py` — Initial schema
- `backend/alembic/versions/b8f0c2e41a9d_add_unique_constraints_portal_events_and_signups.py` — Unique constraints

## Naming Conventions

**Backend files:**
- `snake_case.py` for all Python modules (e.g. `celery_app.py`, `seed_admin.py`)
- Router modules named by resource plural: `events.py`, `signups.py`

**Frontend files:**
- Page and component files: `PascalCase.jsx` (e.g. `EventDetailPage.jsx`, `ProtectedRoute.jsx`)
- Pages suffixed `Page` (e.g. `MySignupsPage.jsx`)
- Utility/lib modules: `camelCase.js` (e.g. `authStorage.js`, `datetime.js`)
- Context providers: `camelCaseContext.jsx` (e.g. `authContext.jsx`)

**Directories:**
- All lowercase (`routers`, `pages`, `components`, `lib`, `state`)

**Routes:**
- API: `/api/v1/<resource>` with sub-paths like `/signups/my`, `/events/{id}/clone`
- Frontend: kebab/lowercase (`/my-signups`, `/admin/audit-logs`)

## Where to Add New Code

**New API endpoint for an existing resource:**
- Add handler to the matching router in `backend/app/routers/<resource>.py`
- Use `Depends(get_current_user)` or `Depends(require_role(...))` for auth
- Add/extend Pydantic schemas in `backend/app/schemas.py`
- Call `log_action(db, current_user, "<action>", "<Entity>", str(id))` before `db.commit()` for mutating endpoints
- Add a corresponding client method in `frontend/src/lib/api.js` (both flat and nested alias if the pattern is used in that area)

**New resource/domain:**
- Create `backend/app/routers/<resource>.py` with an `APIRouter(prefix="/<resource>", tags=["<resource>"])`
- Register it in `backend/app/main.py` with `app.include_router(<resource>.router, prefix="/api/v1")`
- Add ORM model(s) to `backend/app/models.py` and relationships on related models
- Create an Alembic revision under `backend/alembic/versions/`
- Add schemas to `backend/app/schemas.py`

**New frontend page / route:**
- Create `frontend/src/pages/<Name>Page.jsx`
- Import and register it in `frontend/src/App.jsx`, placing it inside the correct `<ProtectedRoute>` group (public / authed / organizer+admin / admin-only)
- Access server data through `api` from `frontend/src/lib/api.js`, preferably via TanStack Query hooks

**New shared React component:**
- Place in `frontend/src/components/<Name>.jsx`

**New utility / helper:**
- Backend: a new module in `backend/app/` or extend `backend/app/deps.py` for auth/security helpers
- Frontend: add a module to `frontend/src/lib/`

**New scheduled / async job:**
- Add a `@celery.task` function in `backend/app/celery_app.py`
- Register it in `celery.conf.beat_schedule` if periodic
- Dispatch from routers with `<task>.delay(...)` after `db.commit()`

**New migration:**
- Generate under `backend/alembic/versions/` (`alembic revision --autogenerate -m "..."`)
- Applied automatically by the `migrate` docker-compose service on startup

## Special Directories

**`.planning/`:**
- Purpose: GSD planning state and generated codebase docs (this file lives here)
- Generated: Yes (by GSD tooling)
- Committed: No (should be gitignored per project conventions)

**`backend/alembic/versions/`:**
- Purpose: Migration history
- Generated: Partially (scaffolded, then edited)
- Committed: Yes

**`frontend/public/`:**
- Purpose: Verbatim static assets
- Generated: No
- Committed: Yes

**Build artifacts (not present in tree, typically gitignored):**
- `frontend/node_modules/`, `frontend/dist/`
- `backend/__pycache__/`, `backend/.venv/`

---

*Structure analysis: 2026-04-08*
