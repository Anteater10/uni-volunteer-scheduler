# Technology Stack

**Analysis Date:** 2026-04-08

## Languages

**Primary:**
- Python 3.10 - Backend API, workers, migrations (`backend/`)
- JavaScript (ES modules, JSX) - Frontend SPA (`frontend/src/`)

**Secondary:**
- SQL - Alembic migrations (`backend/alembic/`)
- YAML - Docker Compose orchestration (`docker-compose.yml`)

## Runtime

**Backend:**
- Python 3.10-slim (Docker base image, `backend/Dockerfile`)
- Uvicorn 0.38.0 ASGI server (with uvloop 0.22.1, httptools 0.7.1, watchfiles 1.1.1, websockets 15.0.1)

**Frontend:**
- Node.js (Vite dev server / build)
- Browser target (ES modules, `"type": "module"` in `frontend/package.json`)

**Package Managers:**
- pip (backend) - `backend/requirements.txt` with pinned versions
- npm (frontend) - `frontend/package.json` + `package-lock.json` present

## Frameworks

**Backend Core:**
- FastAPI 0.123.5 - HTTP API framework (`backend/app/main.py`)
- Starlette 0.50.0 - ASGI foundation (FastAPI dependency)
- Pydantic 2.12.5 / pydantic-settings 2.12.0 - Validation and settings (`backend/app/config.py`, `backend/app/schemas.py`)
- SQLAlchemy 2.0.44 - ORM (`backend/app/models.py`, `backend/app/database.py`)
- Alembic 1.17.2 - Database migrations (`backend/alembic/`, `backend/alembic.ini`)
- Celery 5.6.0 - Background task queue (`backend/app/celery_app.py`)
- SlowAPI 0.1.9 + limits 5.6.0 - Rate limiting

**Frontend Core:**
- React 19.2.0 + React DOM 19.2.0
- React Router DOM 7.11.0 - Client routing
- TanStack React Query 5.90.12 - Server state / data fetching
- Vite 7.2.4 + @vitejs/plugin-react 5.1.1 - Build tool and dev server

**Testing:**
- pytest 8.2.2 + pytest-asyncio 0.23.7 - Backend test runner (`backend/tests/`)
- No frontend test framework detected

**Linting / Build:**
- ESLint 9.39.1 + @eslint/js 9.39.1 (`frontend/eslint.config.js`)
- eslint-plugin-react-hooks 7.0.1, eslint-plugin-react-refresh 0.4.24
- globals 16.5.0

## Key Dependencies

**Backend - Auth & Security:**
- Authlib 1.6.5 - OIDC/SSO client
- python-jose 3.5.0 - JWT encode/decode
- passlib 1.7.4 + bcrypt 5.0.0 - Password hashing
- cryptography 46.0.3, ecdsa 0.19.1, rsa 4.9.1 - Crypto primitives
- python-multipart 0.0.20 - Form/file parsing
- email-validator 2.3.0 - Email format validation

**Backend - Database & Cache:**
- psycopg2-binary 2.9.11 - PostgreSQL driver
- redis 7.1.0 - Redis client (cache, Celery broker/result)

**Backend - Messaging / Notifications:**
- sendgrid 6.12.5 + python-http-client 3.3.7 - Email delivery
- (Twilio SDK not in requirements, but Twilio env vars configured in `backend/app/config.py`)

**Backend - HTTP & Async:**
- httpx 0.27.2 - HTTP client
- anyio 4.12.0 - Async compatibility layer

**Frontend - Runtime:**
- @tanstack/react-query 5.90.12
- react-router-dom 7.11.0
- react / react-dom 19.2.0

## Configuration

**Backend environment:**
- Loaded via pydantic-settings from `backend/.env` (see `backend/app/config.py`)
- `.env` file referenced by `docker-compose.yml` via `env_file: ./backend/.env` (existence noted; contents not read)
- Required settings: `database_url`, `jwt_secret`
- Optional: JWT config, Redis/Celery URLs, SendGrid, Twilio, OIDC SSO, rate limit tuning

**Frontend:**
- `frontend/vite.config.js` - Vite configuration
- `frontend/eslint.config.js` - Lint rules
- `frontend/index.html` - SPA entry HTML

**Infrastructure:**
- `docker-compose.yml` - Orchestrates db, redis, backend, migrate, celery_worker, celery_beat
- `backend/Dockerfile` - Python 3.10-slim image for backend + workers
- `backend/alembic.ini` - Alembic configuration

## Platform Requirements

**Development:**
- Docker + Docker Compose (primary dev path)
- Python 3.10+ and Node.js (for local non-Docker runs)
- PostgreSQL 16 and Redis 7 (provided via Compose)

**Production:**
- Container runtime capable of running the Compose services (db, redis, backend, celery_worker, celery_beat, migrate)
- Deployment target not explicitly declared in repo

---

*Stack analysis: 2026-04-08*
