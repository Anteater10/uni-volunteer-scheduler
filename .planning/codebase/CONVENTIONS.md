# Coding Conventions

**Analysis Date:** 2026-04-08

The project is a monorepo with two distinct codebases: a Python/FastAPI backend (`backend/`) and a React/Vite frontend (`frontend/`). Each has its own conventions.

## Naming Patterns

**Backend files (`backend/app/`):**
- Python modules use `snake_case.py`: `main.py`, `models.py`, `schemas.py`, `database.py`, `deps.py`, `celery_app.py`, `seed_admin.py`
- Routers live in `backend/app/routers/` as single-purpose modules named after the resource: `auth.py`, `users.py`, `events.py`, `slots.py`, `signups.py`, `notifications.py`, `admin.py`, `portals.py`
- Alembic migrations in `backend/alembic/`

**Frontend files (`frontend/src/`):**
- React components and pages use `PascalCase.jsx`: `EventsPage.jsx`, `AdminDashboardPage.jsx`, `Layout.jsx`, `ProtectedRoute.jsx`
- Page components suffixed with `Page` and live in `frontend/src/pages/`
- Reusable components live in `frontend/src/components/`
- Plain JS helpers use `camelCase.js` and live in `frontend/src/lib/`: `api.js`, `authStorage.js`, `datetime.js`
- Context providers live in `frontend/src/state/` as `camelCase.jsx`: `authContext.jsx`
- Entry points: `frontend/src/main.jsx`, `frontend/src/App.jsx`

**Functions:**
- Backend: `snake_case` for all functions (`create_event`, `_to_naive_utc`, `_validate_event_dates`). Leading underscore marks module-private helpers.
- Frontend: `camelCase` for functions (`buildQuery`, `safeReadJson`, `extractErrorMessage`, `formatApiDateTimeLocal`). React components are `PascalCase`.

**Variables:**
- Backend: `snake_case` (`current_user`, `signup_open_at`, `start_date`)
- Frontend: `camelCase` (`isLoading`, `queryKey`); module-level constants are `SCREAMING_SNAKE_CASE` (`RAW_BASE`, `API_BASE`)

**Types / Schemas:**
- Backend Pydantic schemas are `PascalCase` in `backend/app/schemas.py` (`Token`, `TokenData`, `ORMBase`, `EventCreate`, `EventRead`)
- SQLAlchemy models are `PascalCase` in `backend/app/models.py` (`User`, `Event`)
- Enum values use lowercase (`UserRole.admin`, `UserRole.organizer`)

## Code Style

**Backend (Python):**
- No formatter or linter config detected (no `.ruff.toml`, `pyproject.toml`, `.flake8`, `black` config). Style is ad hoc but consistent: 4-space indent, double quotes, type hints on function signatures, Pydantic v2 with `from_attributes=True`.
- Type hints used liberally: `def _to_naive_utc(dt: datetime) -> datetime:`, `def create_event(event_in: schemas.EventCreate, db: Session = Depends(get_db), ...)`.
- File header comments: most backend files open with a path comment, e.g. `# backend/app/routers/events.py`.

**Frontend (JavaScript/JSX):**
- ESLint 9 flat config at `frontend/eslint.config.js` extending `js.configs.recommended`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`.
- Key rule: `'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }]` — unused vars starting with uppercase or underscore are allowed.
- No Prettier config; de facto style is double quotes, 2-space indent, semicolons, trailing commas where natural.
- `dist/` is globally ignored.
- JSX files use `.jsx` extension (not `.js`) for anything containing JSX.

## Import Organization

**Backend (`backend/app/routers/events.py`):**
1. Standard library: `from datetime import timedelta, datetime, timezone`
2. Typing helpers: `from typing import List`
3. Third-party: `from fastapi import APIRouter, Depends, HTTPException`, `from sqlalchemy.orm import Session`
4. Local relative imports: `from .. import models, schemas`, `from ..database import get_db`, `from ..deps import require_role, log_action`

Relative imports (`from ..`) are the norm inside the `app/` package.

**Frontend (`frontend/src/pages/EventsPage.jsx`):**
1. React / framework: `import React from "react";`
2. Third-party: `import { useQuery } from "@tanstack/react-query";`, `import { Link } from "react-router-dom";`
3. Local relative: `import { api } from "../lib/api";`, `import { formatApiDateTimeLocal } from "../lib/datetime";`

No path aliases configured — all local imports use relative paths.

## Error Handling

**Backend:**
- Raise `HTTPException(status_code=..., detail="...")` from FastAPI for user-facing errors. Examples in `backend/app/routers/events.py`:
  - `raise HTTPException(status_code=400, detail="end_date must be after start_date")`
  - `raise HTTPException(status_code=403, detail="Not allowed to modify this event")`
- Validation is factored into private helper functions prefixed with `_validate_` or `_ensure_` (e.g. `_validate_event_dates`, `_ensure_event_owner_or_admin`).
- Rate-limit errors are handled globally in `backend/app/main.py` via `_rate_limit_exceeded_handler`.

**Frontend:**
- `frontend/src/lib/api.js` centralizes HTTP error parsing with `safeReadJson` and `extractErrorMessage`. Non-OK responses throw an `Error` whose `message` field is derived from FastAPI's `detail` (string, list of validation errors, or `message`).
- Components render errors inline, e.g. `if (error) return <div style={{ color: "crimson" }}>Failed: {error.message}</div>;` in `frontend/src/pages/EventsPage.jsx`.
- React Query (`useQuery`) manages async state: `{ data, isLoading, error }`.

## Logging / Audit

- No logger framework on the backend. Auditing uses an explicit `log_action` dependency imported from `backend/app/deps.py` and wired into route handlers for admin actions.
- Frontend uses plain `console` only where needed — no logging library.

## Function Design

**Backend:**
- Private helpers (`_to_naive_utc`, `_validate_event_dates`, `_validate_slot_range_within_event`) keep route handlers focused. Handlers orchestrate; helpers validate and normalize.
- Datetimes are normalized to naive UTC before comparison via `_to_naive_utc` — this is a project-wide convention.
- Route handlers take Pydantic input schemas, a `db: Session = Depends(get_db)` dependency, and a `current_user` from `require_role(...)`.

**Frontend:**
- Page components are default-exported functions: `export default function EventsPage() { ... }`.
- Data fetching via `useQuery({ queryKey: [...], queryFn: api.<resource>.<action> })`. Keys are arrays starting with the resource name (`["events"]`).
- API calls are grouped under a single `api` object exported from `frontend/src/lib/api.js` and accessed as `api.events.list`, `api.auth.login`, etc.

## Module Design

**Backend:**
- `backend/app/main.py` registers routers with `app.include_router(...)`.
- Each router module defines `router = APIRouter(prefix="/<resource>", tags=["<resource>"])` and attaches handlers with `@router.post("/", ...)` etc. See `backend/app/routers/events.py:12`.
- Shared DB/auth dependencies live in `backend/app/deps.py` (`get_db`, `require_role`, `limiter`, `log_action`).
- `backend/app/schemas.py` groups Pydantic schemas with clear section comment banners (`# ===== USER SCHEMAS =====`).
- A base `ORMBase(BaseModel)` with `model_config = ConfigDict(from_attributes=True)` is inherited by read schemas for SQLAlchemy compatibility.

**Frontend:**
- `frontend/src/lib/api.js` exports a single `api` namespace object — do not add fetch calls scattered across components.
- Auth token storage is isolated in `frontend/src/lib/authStorage.js`.
- Datetime formatting centralized in `frontend/src/lib/datetime.js` (`formatApiDateTimeLocal`).
- Global auth state lives in `frontend/src/state/authContext.jsx` (React Context).
- Route protection via `frontend/src/components/ProtectedRoute.jsx` wrapper.

## Configuration

- Backend config: `backend/app/config.py` uses `pydantic-settings` (inferred from `requirements.txt`). Environment loaded via `python-dotenv`.
- Frontend config: Vite env vars prefixed `VITE_` (e.g. `VITE_API_URL`). Read from `import.meta.env`.
- CORS origins hardcoded in `backend/app/main.py` with a TODO for production.

## Comments

- Backend uses docstrings for non-trivial helpers: `"""Normalize datetimes so comparisons are safe across aware/naive values."""` in `backend/app/routers/events.py:16`.
- Path-header comments are common (`# backend/app/routers/events.py`, `# src/lib/api.js`).
- Inline `# TODO:` markers are used sparingly (see CORS origins in `backend/app/main.py`).

---

*Convention analysis: 2026-04-08*
