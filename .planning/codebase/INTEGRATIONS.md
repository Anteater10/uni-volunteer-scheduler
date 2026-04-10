# External Integrations

**Analysis Date:** 2026-04-08

## APIs & External Services

**Email:**
- SendGrid - Transactional email delivery
  - SDK: `sendgrid` 6.12.5 (`backend/requirements.txt`)
  - Auth: `SENDGRID_API_KEY` env var (`backend/app/config.py`)
  - From address: `EMAIL_FROM_ADDRESS` env var

**SMS:**
- Twilio - SMS notifications (configured, SDK not pinned in requirements)
  - Auth: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` env vars
  - Sender: `TWILIO_FROM_NUMBER` env var
  - Config location: `backend/app/config.py`

**Notifications router:** `backend/app/routers/notifications.py`

## Data Storage

**Primary Database:**
- PostgreSQL 16 (`docker-compose.yml` - `db` service, image `postgres:16`)
  - Database name: `uni_volunteer`
  - User: `postgres`
  - Connection: `DATABASE_URL` env var (`backend/app/config.py`)
  - Client: SQLAlchemy 2.0.44 + psycopg2-binary 2.9.11
  - Session/engine setup: `backend/app/database.py`
  - Models: `backend/app/models.py`
  - Migrations: Alembic, `backend/alembic/`
  - Persistence: Docker volume `pgdata`

**Cache / Broker:**
- Redis 7 (`docker-compose.yml` - `redis` service, image `redis:7`, `--appendonly yes`)
  - Client: `redis` 7.1.0 Python package
  - Uses:
    - General cache / rate limiting: `REDIS_URL` (default `redis://redis:6379/0`)
    - Celery broker: `CELERY_BROKER_URL` (default `redis://redis:6379/1`)
    - Celery result backend: `CELERY_RESULT_BACKEND` (default `redis://redis:6379/2`)

**File Storage:**
- None detected (no S3, GCS, or object storage SDK in dependencies)

## Authentication & Identity

**Local Auth:**
- Email + password with bcrypt hashing (passlib 1.7.4 + bcrypt 5.0.0)
- JWT access + refresh tokens via python-jose 3.5.0
  - `JWT_SECRET`, `JWT_ALGORITHM` (default HS256)
  - `ACCESS_TOKEN_EXPIRES_MINUTES` (default 60)
  - `REFRESH_TOKEN_EXPIRES_DAYS` (default 14)
- Implementation: `backend/app/routers/auth.py`, `backend/app/deps.py`

**SSO (OIDC/SAML):**
- Authlib 1.6.5 - OIDC client
- Env config: `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER`, `OIDC_REDIRECT_URI`
- Supports generic IdPs (e.g., Google Accounts, institutional IdP)
- Callback: configured via `OIDC_REDIRECT_URI` (e.g., `/api/v1/auth/sso/callback`)

**Admin bootstrap:**
- `backend/app/seed_admin.py` - Invoked by `migrate` service on container start

## Background Jobs

**Celery workers:**
- `celery_worker` service - runs `celery -A app.celery_app.celery worker`
- `celery_beat` service - runs `celery -A app.celery_app.celery beat` (scheduled tasks)
- App module: `backend/app/celery_app.py`
- Broker + backend: Redis (see above)

## Rate Limiting

**SlowAPI 0.1.9:**
- Configurable via `RATE_LIMIT_WINDOW_SECONDS` (default 60) and `RATE_LIMIT_MAX_REQUESTS` (default 100)
- Backed by Redis via `limits` package

## Monitoring & Observability

**Error Tracking:** None detected (no Sentry, Datadog, or similar SDK)

**Logs:** Uvicorn/Celery stdout logging; no structured logging framework detected

## CI/CD & Deployment

**Hosting:** Not declared in repo

**CI Pipeline:** No `.github/workflows`, `.gitlab-ci.yml`, or CircleCI config detected at repo root

**Container build:** `backend/Dockerfile` (Python 3.10-slim). Frontend has no Dockerfile at time of analysis.

## Environment Configuration

**Required env vars (backend/.env):**
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET` - JWT signing secret
- `POSTGRES_PASSWORD` - Referenced in `docker-compose.yml`

**Optional env vars:**
- `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRES_MINUTES`, `REFRESH_TOKEN_EXPIRES_DAYS`
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `SENDGRID_API_KEY`, `EMAIL_FROM_ADDRESS`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER`, `OIDC_REDIRECT_URI`
- `RATE_LIMIT_WINDOW_SECONDS`, `RATE_LIMIT_MAX_REQUESTS`

**Secrets location:**
- `backend/.env` file (existence noted; contents never read). Loaded by pydantic-settings and passed to containers via `env_file` in `docker-compose.yml`.

## Webhooks & Callbacks

**Incoming:**
- OIDC SSO callback endpoint (configured via `OIDC_REDIRECT_URI`) in `backend/app/routers/auth.py`

**Outgoing:**
- SendGrid API calls (email send)
- Twilio API calls (SMS send, when configured)

## API Routers (internal surface)

Located at `backend/app/routers/`:
- `auth.py` - Authentication, SSO
- `users.py` - User management
- `events.py` - Events
- `slots.py` - Event time slots
- `signups.py` - Volunteer signups
- `portals.py` - Portal/tenant views
- `notifications.py` - Email/SMS notification triggers
- `admin.py` - Admin tooling

---

*Integration audit: 2026-04-08*
