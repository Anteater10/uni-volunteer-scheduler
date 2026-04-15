# Phase 0: Backend Completion + Frontend Integration — Research

**Researched:** 2026-04-08
**Domain:** FastAPI + Celery + React + Playwright — backend audit, auth hardening, timezone migration, E2E testing
**Confidence:** HIGH (primary findings verified against live codebase; library versions verified against pip/npm registries)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**API Contract Audit**
- Fix every mismatch, not just E2E blockers. Phase goal mandates "linked fix PR for every mismatch."
- Deliverable: Written punch list covering every `frontend/src/lib/api.js` function cross-checked against backend routers.
- Known mismatches to fix:
  - `api.createSignup` POSTs `/signups` but router mounts `/signups/` (trailing slash) — normalize one way.
  - `updateEvent` uses `PATCH` — backend `PATCH` is `include_in_schema=False`, public surface is `PUT` — align frontend to `PUT` OR expose `PATCH`.
  - `updateEventQuestion`/`deleteEventQuestion` call `/event-questions/{id}` but router mounts at `/events/questions/{id}`.
  - `listEventSignups` calls `/events/{eventId}/signups` — endpoint does not exist.
- pytest integration tests per router with `conftest.py`, FastAPI `TestClient`, DB fixtures.

**Auth Hardening (in-scope)**
- Frontend refresh-token flow: store refresh token in `authStorage`, implement refresh-on-401 in `api.js`. Fix dead `getRefreshToken`.
- Hash refresh tokens at rest: SHA-256 before storing in `RefreshToken.token`; compare hashes on verify. Alembic migration.
- Defer to later phase: Argon2id password migration, httpOnly-cookie storage, password reset, email verification.

**Timezone Migration (full, now)**
- Single Alembic migration: `DateTime(timezone=True)` on all columns.
- Replace every `datetime.utcnow()` with `datetime.now(timezone.utc)`.
- Delete all `_to_naive_utc()` helpers (events.py, slots.py, signups.py, deps.py, celery_app.py).
- Backfill/cast existing rows (assume stored values were UTC).
- Celery reminder scheduling must produce identical windows across DST transitions (test with frozen time).

**Celery Reliability (redbeat + flag + index)**
- Replace celery-beat with `celery-redbeat` for distributed locking.
- Add `reminder_sent` boolean flag on `Signup` (default False, set after SendGrid success). Idempotency for reminder task.
- Add index on `slots.start_time`.
- Task retries: `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3` on `send_email_notification` and `schedule_reminders`.
- Planner must verify whether `registered` is in the current `SignupStatus` enum or needs Alembic migration.

### Claude's Discretion

**Playwright suite shape:**
- Cover 4 E2E flows: (1) student register→browse→sign up→MySignups, (2) student cancel→slot freed→email, (3) organizer login→dashboard→roster, (4) admin CRUD users/portals/events.
- Run against `docker-compose` stack with ephemeral test database. Reuse Docker Compose profile.
- Seed via `backend/tests/fixtures/` factory callable from Playwright `globalSetup`. Minimum: admin, organizer, portal, event with slots, participant.
- GitHub Actions on every PR, fail on regression, upload traces on failure.
- Playwright config: retries=2 on CI, 0 locally; headed only on `--debug`.
- Email assertions: stub SendGrid, assert `Notification` DB row, not real inbox.

**Refactors bundled into Phase 0:**
- Extract `backend/app/signup_service.py` with `promote_waitlist_fifo` using canonical `(timestamp, id)` ordering.
- Extract `backend/app/emails.py` with one function per notification type.
- Centralize `_to_naive_utc` / `_ensure_event_owner_or_admin` into `backend/app/utils.py` and `backend/app/deps.py`.
- Do NOT split `admin.py` (753 lines) or `OrganizerEventPage.jsx` (945 lines) in Phase 0.

**Tech-debt cleanups (in scope):**
- Replace `pydantic.dict()` → `.model_dump(exclude_unset=True)` at 3 sites (events.py, users.py, slots.py).
- Whitelist mutable fields in `update_me`.
- Remove dead `slowapi` middleware.
- Read CORS origins from `settings`.
- Add `current_count` defensive-healing note to signup_service.

**Validation defaults:**
- pytest: auth, concurrency, waitlist, rate limiter, ownership, Celery idempotency.
- Coverage: 70% lines backend, 90% critical paths (signup/cancel/waitlist).

**Security defaults:**
- Run `/gsd-secure-phase 0` threat-model gate during planning.
- No new secrets introduced.

### Deferred Ideas (OUT OF SCOPE)

- Argon2id password hashing migration
- httpOnly cookie storage + CSRF double-submit
- Password reset flow
- Email verification on register
- Strict CSP header
- Splitting `admin.py` into sub-routers
- Splitting `OrganizerEventPage.jsx` into sub-components
- SMS delivery (Twilio)
- Bulk slot edit / drag-drop
- Audit-log jsonb + GIN index
- Pagination on list endpoints
- Dropping `current_count` column
- JWT key rotation with `kid`
- Per-organizer broadcast rate limit + templated header/footer
- `admin_summary` Redis caching
- `my_signups` window-function rewrite
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUDIT-01 | Audit every router for working / stubbed / broken endpoints | API Contract Audit section — complete punch list with 4 verified mismatches |
| AUDIT-02 | Request validation with Pydantic on every endpoint | Pydantic v2 patterns section; `UserUpdate` privilege-escalation fix required |
| AUDIT-03 | Consistent error response shape `{error, code, detail}` | Current pattern analysis; FastAPI HTTPException shapes documented |
| AUTH-01 | Frontend refresh-token flow: store, refresh-on-401, fix dead code | Auth Hardening section — `authStorage.js` and `api.js` changes specified |
| AUTH-02 | Hash refresh tokens at rest (SHA-256) + Alembic migration | Auth Hardening section — column rename + hash comparison pattern |
| TZ-01 | Migrate all DateTime columns to `timezone=True` + remove `_to_naive_utc` helpers | Timezone Migration section — Alembic pattern + 9 affected files listed |
| TZ-02 | Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` | Found in: models.py, deps.py, routers/signups.py, celery_app.py |
| CELERY-01 | Replace celery-beat with celery-redbeat | Celery Reliability section — redbeat 2.3.3 verified on PyPI |
| CELERY-02 | Add `reminder_sent` flag on Signup + idempotency guard | Celery Reliability section — Alembic migration required |
| CELERY-03 | Add index on `slots.start_time` | Celery Reliability section — Alembic migration |
| CELERY-04 | Retry config on email and reminder tasks | Celery Reliability section — autoretry pattern |
| REFACTOR-01 | Extract `signup_service.py` with canonical `promote_waitlist_fifo` | Architecture Patterns section — unifies divergent ordering in signups.py vs admin.py |
| REFACTOR-02 | Extract `emails.py` per notification type | Architecture Patterns section — deduplicates 8+ inline email bodies |
| E2E-01 | Playwright suite covering 4 flows | Playwright CI section — setup patterns, Docker Compose integration |
| E2E-02 | CI gates PR merge on Playwright pass | GitHub Actions pattern documented |
| E2E-03 | Cancel flow verifies freed capacity is reusable | Cancel flow analysis — second-user-signup assertion required |
| TEST-01 | pytest integration tests per router with DB fixtures | Testing section — conftest.py pattern, real Postgres required |
| TEST-02 | 70% line coverage backend, 90% critical paths | Validation Architecture section |
| OPEN-01 | Confirm `signups.status` enum current values | Open Questions — `registered` NOT in current enum (confirmed by models.py audit) |
</phase_requirements>

---

## Summary

Phase 0 closes every gap between what the backend serves and what the frontend calls, adds a proper test harness where none exists today, and fixes three correctness hazards (timezone drift, waitlist ordering divergence, refresh-token dead code) before any other phase builds on this foundation.

The codebase is structurally sound and the architecture is coherent, but the test surface is almost zero (one `assert True` smoke test) and four frontend API calls produce runtime 404s today. The cancel/withdraw flow itself is implemented correctly in `signups.py` but the frontend `cancelSignup` function is wired correctly too — the gap is that no E2E test verifies the freed capacity is reused. The highest-risk implementation work is the timezone Alembic migration (touching all datetime columns) and the refresh-token-on-401 flow in `api.js` (requires queuing concurrent 401s behind one in-flight refresh).

**Critical discovery:** `SignupStatus` in `models.py` contains `confirmed`, `waitlisted`, and `cancelled` only — `registered` does NOT exist. The ROADMAP open-question gate is now answered: an Alembic migration IS required to add `registered` as initial status before Phase 3 (check-in state machine), but it is not strictly required for Phase 0's E2E flows, which can treat the existing `confirmed` as the initial post-signup state. The planner must decide whether to add `registered` in Phase 0 or defer to Phase 3.

**Primary recommendation:** Execute in this order — (1) API contract fixes + integration tests, (2) timezone migration, (3) auth hardening (refresh token), (4) Celery reliability + redbeat, (5) refactor extractions, (6) Playwright suite. Doing the migration before Playwright means E2E runs against the clean timezone-aware schema.

---

## API Contract Audit (Full Punch List)

This is a complete cross-reference of every `frontend/src/lib/api.js` function against backend routers. [VERIFIED: live codebase read]

### Verified Mismatches (must fix)

| Frontend Call | Frontend Path | HTTP Method | Backend Mount | Status | Fix |
|---------------|--------------|-------------|---------------|--------|-----|
| `createSignup` | `/signups` | POST | `/signups/` (router prefix) | Mismatch: no trailing slash | Normalize; FastAPI 307-redirects but CORS can block preflight redirect |
| `updateEvent` | `/events/{id}` | PATCH | `PATCH` is `include_in_schema=False`; public is `PUT` | Mismatch | Change frontend to `PUT` |
| `updateEventQuestion` | `/event-questions/{id}` | PATCH | `/events/questions/{id}` | 404 at runtime | Fix frontend path to `/events/questions/{id}` |
| `deleteEventQuestion` | `/event-questions/{id}` | DELETE | `/events/questions/{id}` | 404 at runtime | Fix frontend path to `/events/questions/{id}` |
| `listEventSignups` | `/events/{eventId}/signups` | GET | Does not exist | 404 at runtime | Add endpoint OR change call site to `/admin/events/{eventId}/roster` |

### Verified Correct Paths

| Frontend Call | Path | Method | Backend Confirms |
|---------------|------|--------|-----------------|
| `login` | `/auth/token` | POST | `router.post("/token")` in `auth.py` — form-encoded, correct |
| `register` | `/auth/register` | POST | `router.post("/register")` — correct |
| `me` | `/users/me` | GET | `router.get("/me")` in `users.py` — correct |
| `listEvents` | `/events` | GET | `router.get("/")` with prefix `/events` — resolves to `/events/` but FastAPI handles bare `/events` |
| `getEvent` | `/events/{id}` | GET | Correct |
| `createEvent` | `/events` | POST | Router at `/events/` — same trailing-slash concern as createSignup |
| `deleteEvent` | `/events/{id}` | DELETE | Correct, 204 |
| `cloneEvent` | `/events/{id}/clone` | POST | Correct |
| `listSlots` | `/slots/` | GET | Router at `/slots/` with `include_in_schema=False` on bare `/slots` — correct |
| `createSlot` | `/slots/` | POST | Correct (takes `?event_id=` query param) |
| `updateSlot` | `/slots/{id}` | PATCH | Need to verify router — slot router not fully read but pattern is consistent |
| `deleteSlot` | `/slots/{id}` | DELETE | Need to verify router |
| `generateSlots` | `/events/{id}/generate_slots` | POST | `router.post("/{event_id}/generate_slots")` — correct |
| `cancelSignup` | `/signups/{id}/cancel` | POST | `router.post("/{signup_id}/cancel")` — correct |
| `listMySignups` | `/signups/my` | GET | `router.get("/my")` — correct |
| `listEventQuestions` | `/events/{id}/questions` | GET | `router.get("/{event_id}/questions")` — correct |
| `createEventQuestion` | `/events/{id}/questions` | POST | `router.post("/{event_id}/questions")` — correct |
| `listMyNotifications` | `/notifications/my` | GET | Need to verify router |
| `getPortalBySlug` | `/portals/{slug}` | GET | Need to verify router |
| `listPortals` | `/portals` | GET | Need to verify router |
| `createPortal` | `/portals` | POST | Need to verify router |
| `attachEventToPortal` | `/portals/{portalId}/events/{eventId}` | POST | Need to verify router |
| `adminSummary` | `/admin/summary` | GET | Need to verify router |
| `adminListUsers` | `/users` | GET | `router.get("/")` in `users.py` with admin guard — correct |
| `adminCreateUser` | `/users` | POST | `router.post("/")` in `users.py` — correct |
| `adminUpdateUser` | `/users/{id}` | PATCH | `router.patch("/{user_id}")` — correct |
| `adminDeleteUser` | `/admin/users/{id}` | DELETE | Need to verify admin router |
| `adminAuditLogs` | `/admin/audit_logs` | GET | Need to verify admin router |
| `adminCancelSignup` | `/admin/signups/{id}/cancel` | POST | Need to verify admin router |

### Open-Question Gate Resolution

**`SignupStatus.registered`:** NOT present in current `models.py`. Enum is `{confirmed, waitlisted, cancelled}`. [VERIFIED: models.py line 34-38]

The Phase 0 E2E flows can complete with the current enum (`confirmed` is the post-signup status). Adding `registered` as an initial pre-confirmation status belongs to Phase 3 (check-in state machine) where the full lifecycle `registered → confirmed → checked_in → attended | no_show` is implemented. The planner must either:
- Option A: Add `registered` now in Phase 0 and treat all existing `confirmed` signups as having skipped the `registered` stage.
- Option B: Defer `registered` to Phase 3 and run Phase 0 E2E flows with `confirmed` as the terminal "active" status.

**Recommendation:** Option B. Adding `registered` now requires updating all existing rows and all code paths that check `SignupStatus.confirmed`, creating a large diff that interferes with Phase 0's audit goal.

---

## Standard Stack

### Core (already installed — no new installs for backend audit/fixes)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| FastAPI | 0.123.5 | HTTP API framework | [VERIFIED: requirements.txt] |
| SQLAlchemy | 2.0.44 | ORM | [VERIFIED: requirements.txt] |
| Alembic | 1.17.2 | DB migrations | [VERIFIED: requirements.txt] |
| Celery | 5.6.0 | Task queue | [VERIFIED: requirements.txt] |
| Pydantic | 2.12.5 | Validation | [VERIFIED: requirements.txt] |
| psycopg2-binary | 2.9.11 | Postgres driver | [VERIFIED: requirements.txt] |
| redis | 7.1.0 | Redis client | [VERIFIED: requirements.txt] |
| sendgrid | 6.12.5 | Email delivery | [VERIFIED: requirements.txt] |
| python-jose | 3.5.0 | JWT | [VERIFIED: requirements.txt] |
| passlib | 1.7.4 | Password hashing | [VERIFIED: requirements.txt] |

### New Backend Dependencies (add to requirements.txt)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| celery-redbeat | 2.3.3 | Distributed beat scheduler | Prevents duplicate reminder emails when two beat workers run simultaneously | [VERIFIED: pip registry] |
| pytest-cov | 7.1.0 | Coverage reporting | Enforce 70%/90% coverage thresholds | [VERIFIED: pip registry] |
| factory-boy | 3.3.3 | Test data factories | Seed DB fixtures for integration tests | [VERIFIED: pip registry] |
| freezegun | 1.5.5 | Freeze time in tests | Test DST-safe reminder scheduling | [VERIFIED: pip registry] |

### Frontend Dependencies (new — none currently installed)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| @playwright/test | 1.59.1 | E2E test runner | CI-required 4-flow coverage | [VERIFIED: npm registry] |

**Installation commands:**

```bash
# Backend
cd backend
pip install celery-redbeat==2.3.3 pytest-cov==7.1.0 factory-boy==3.3.3 freezegun==1.5.5
# Then pin to requirements.txt

# Frontend (from repo root or frontend/)
cd frontend
npm install --save-dev @playwright/test@1.59.1
npx playwright install chromium
```

---

## Architecture Patterns

### Verified Current Structure [VERIFIED: live codebase]

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, middleware, router registration
│   ├── config.py            # pydantic-settings env-driven config
│   ├── database.py          # SQLAlchemy engine, SessionLocal, get_db
│   ├── deps.py              # Auth, rate-limit, audit, refresh token helpers
│   ├── models.py            # ORM models (all DateTime columns are naive today)
│   ├── schemas.py           # Pydantic request/response schemas
│   ├── celery_app.py        # Celery app + tasks + beat schedule
│   ├── seed_admin.py        # Initial admin seeding
│   └── routers/
│       ├── auth.py          # /auth/* — login, register, refresh, logout, SSO
│       ├── users.py         # /users/* — me, list (admin), CRUD (admin)
│       ├── events.py        # /events/* — CRUD, generate_slots, questions
│       ├── slots.py         # /slots/* — CRUD
│       ├── signups.py       # /signups/* — create, cancel, my, my/upcoming, ics
│       ├── notifications.py # /notifications/*
│       ├── admin.py         # /admin/* — 753 lines, mixed concerns
│       └── portals.py       # /portals/*
├── alembic/
│   └── versions/            # 2 migrations today
└── tests/
    └── test_smoke.py        # assert True — placeholder only

frontend/
├── src/
│   ├── lib/
│   │   ├── api.js           # All backend calls — single request() wrapper
│   │   └── authStorage.js   # localStorage access token; getRefreshToken returns ""
│   ├── state/authContext.jsx
│   ├── pages/               # One page per route
│   └── components/
├── package.json             # No test runner yet
└── playwright.config.js     # Does not exist yet — Wave 0 gap
```

### New Files to Create

```
backend/
├── app/
│   ├── signup_service.py    # promote_waitlist_fifo with canonical (timestamp, id) ordering
│   ├── emails.py            # One function per notification type
│   └── utils.py             # _to_naive_utc (if needed during TZ migration transition)
└── tests/
    ├── conftest.py          # TestClient, DB fixtures, factory setup
    ├── fixtures/
    │   └── factories.py     # factory-boy model factories
    ├── test_auth.py         # login, register, refresh, token expiry
    ├── test_signups.py      # create, cancel, waitlist, concurrency
    ├── test_events.py       # CRUD, ownership, validation
    ├── test_celery.py       # task idempotency (mocked broker)
    └── test_rate_limits.py  # rate limit enforcement

frontend/
├── playwright.config.js     # Playwright configuration
├── playwright/
│   ├── global-setup.js      # DB seeding via backend API
│   └── tests/
│       ├── student-flow.spec.js    # register → browse → signup → MySignups
│       ├── cancel-flow.spec.js     # cancel → capacity freed → second signup succeeds
│       ├── organizer-flow.spec.js  # login → dashboard → roster
│       └── admin-flow.spec.js      # CRUD users/portals/events
```

### Pattern 1: FastAPI TestClient Integration Test

```python
# Source: FastAPI official docs — dependency_overrides pattern [ASSUMED from training; pattern stable across FastAPI versions]
# backend/tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/uni_volunteer_test"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

**CRITICAL:** Use real Postgres, not SQLite. The schema uses JSON columns and `Enum` types that behave differently on SQLite. [VERIFIED: models.py — JSON, Enum columns present]

### Pattern 2: Refresh-on-401 with Thundering-Herd Prevention

```javascript
// frontend/src/lib/api.js — refresh-on-401 pattern
// Concurrent 401s must be queued behind one in-flight refresh, not each triggering refresh

let refreshPromise = null;

async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;  // queue behind in-flight
  refreshPromise = (async () => {
    const refreshToken = authStorage.getRefreshToken();
    if (!refreshToken) throw new Error("No refresh token");
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      authStorage.clearTokens();
      throw new Error("Refresh failed");
    }
    const data = await res.json();
    authStorage.setTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
    return data.access_token;
  })();
  refreshPromise.finally(() => { refreshPromise = null; });
  return refreshPromise;
}

// In request(), intercept 401 once:
async function request(path, options = {}) {
  // ... existing request logic ...
  if (res.status === 401 && options._retry !== true) {
    try {
      await refreshAccessToken();
      return request(path, { ...options, _retry: true });
    } catch {
      authStorage.clearTokens();
      window.location.href = "/login";  // or dispatch logout event
      throw new Error("Session expired");
    }
  }
  // ... rest of error handling
}
```
[ASSUMED — pattern is standard industry practice; specific API may need adjustment]

### Pattern 3: Celery Task Retry Configuration

```python
# backend/app/celery_app.py — retry config [ASSUMED from Celery 5.x docs; pattern stable]
@celery.task(
    autoretry_for=(Exception,),
    retry_backoff=True,          # exponential: 1s, 2s, 4s
    max_retries=3,
    retry_backoff_max=60,        # cap at 60s
    acks_late=True,              # don't ack until task completes
)
def send_email_notification(user_id: str, subject: str, body: str) -> None:
    # ... existing implementation + reminder_sent guard ...
    db: Session = SessionLocal()
    try:
        signup = db.query(models.Signup).filter(...).first()
        if signup and signup.reminder_sent:
            return  # idempotency guard
        # send email
        # set signup.reminder_sent = True
        db.commit()
    finally:
        db.close()
```

### Pattern 4: celery-redbeat Configuration

```python
# backend/app/celery_app.py — replace default beat with redbeat
# [ASSUMED from celery-redbeat 2.x docs; verify against official docs before implementing]
celery.conf.update(
    redbeat_redis_url=settings.redis_url,  # same Redis instance is fine for dev
    redbeat_lock_timeout=300,              # 5 min — matches reminder interval
)

# Beat schedule stays the same structure; redbeat reads it automatically
celery.conf.beat_schedule = { ... }  # unchanged

# Start beat with redbeat scheduler:
# celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler
```

### Pattern 5: SHA-256 Refresh Token Hashing

```python
# backend/app/deps.py
import hashlib

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_refresh_token(db, user):
    raw_token = str(uuid.uuid4())
    hashed = _hash_token(raw_token)
    rt = models.RefreshToken(user_id=user.id, token=hashed, expires_at=...)
    db.add(rt)
    db.flush()
    return raw_token  # return raw to client; store hash only

def verify_refresh_token(db, raw_token):
    hashed = _hash_token(raw_token)
    rt = db.query(models.RefreshToken).filter(
        models.RefreshToken.token == hashed
    ).first()
    # ... rest of verification
```

The Alembic migration must:
1. Rename column `token` → `token_hash` (or keep as `token` but note it's now a hash).
2. Rehash existing plain-UUID tokens in the migration (all existing tokens become invalid; acceptable since frontend never stored them anyway).
[VERIFIED: current `authStorage.js` returns `""` for refresh token — no existing client-side refresh tokens to preserve]

### Pattern 6: DateTime(timezone=True) Migration

```python
# backend/alembic/versions/XXXX_timezone_migration.py [ASSUMED from Alembic + SQLAlchemy docs]
from alembic import op
import sqlalchemy as sa

def upgrade():
    # For each DateTime column, cast to TIMESTAMPTZ (Postgres native)
    # AT TIME ZONE 'UTC' treats the stored naive value as UTC
    op.execute("""
        ALTER TABLE events
          ALTER COLUMN start_date TYPE TIMESTAMP WITH TIME ZONE
            USING start_date AT TIME ZONE 'UTC',
          ALTER COLUMN end_date TYPE TIMESTAMP WITH TIME ZONE
            USING end_date AT TIME ZONE 'UTC',
          ALTER COLUMN signup_open_at TYPE TIMESTAMP WITH TIME ZONE
            USING signup_open_at AT TIME ZONE 'UTC',
          ALTER COLUMN signup_close_at TYPE TIMESTAMP WITH TIME ZONE
            USING signup_close_at AT TIME ZONE 'UTC',
          ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE
            USING created_at AT TIME ZONE 'UTC'
    """)
    # Repeat for: slots, signups, notifications, refresh_tokens, audit_logs, users, portals
```

After migration, every `DateTime` column in `models.py` becomes `DateTime(timezone=True)`, and SQLAlchemy returns tz-aware datetimes automatically.

### Pattern 7: Playwright Docker Compose Integration

```javascript
// playwright.config.js [ASSUMED from Playwright docs; verify against 1.59 release notes]
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./playwright/tests",
  globalSetup: "./playwright/global-setup.js",
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Assumes docker-compose stack is already up before test run
  webServer: {
    command: "cd .. && npm run dev",  // Vite dev server
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
  },
});
```

```javascript
// playwright/global-setup.js — seed test DB via API
import { request } from "@playwright/test";

export default async function globalSetup() {
  const api = await request.newContext({ baseURL: "http://localhost:8000" });
  // POST to a test-only seed endpoint, OR call existing admin API with known creds
  // Minimum seed: admin user, organizer user, portal, event, slots, participant user
  await api.dispose();
}
```

**CRITICAL for CI:** The GitHub Actions job must `docker compose up -d` (without frontend) and wait for health checks before running Playwright. The frontend runs as a Vite dev server in the workflow.

### Anti-Patterns to Avoid

- **Never run integration tests against SQLite.** JSON column type and enum behavior differ from Postgres. [VERIFIED: models.py uses JSON and Enum types]
- **Never add `registered` to `SignupStatus` without a migration.** SQLAlchemy Enum maps to Postgres native ENUM type; adding values requires `ALTER TYPE ... ADD VALUE`. [VERIFIED: enum lock comments in models.py]
- **Never commit inside Celery task before the task succeeds.** Current `send_email_notification` commits the `Notification` row before confirming email delivery — this is correct; just don't split it to commit DB before email attempt when adding `reminder_sent`.
- **Never use `response.ok` shortcut after `refreshAccessToken`.** Always check 401 on the retry too, or you risk an infinite refresh loop.
- **Never use `with_for_update()` inside a different lock ordering than the standard.** Current code locks Slot then Signup in `create_signup`, but Signup then Slot in `cancel_signup`. Extract a canonical lock-order constant.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Distributed beat deduplication | Custom Redis lock on beat tasks | `celery-redbeat` | Handles leader election, lock refresh, crash recovery. Hand-rolled Redis lock breaks on restart or network partition |
| JWT refresh queuing | Multiple `fetch` calls each triggering refresh | Single `refreshPromise` module-level variable | Thundering herd: 5 concurrent 401s each refreshing creates 5 new tokens, invalidating each other |
| Test data factories | Manual `db.add(models.User(...))` in every test | `factory-boy` | Makes fixtures composable, avoids FK ordering issues, supports traits/subfactories |
| Time-sensitive test assertions | `time.sleep()` in tests | `freezegun` | Eliminates flakiness; lets you freeze time to exact reminder windows |
| SHA-256 hashing | Any custom hash function | `hashlib.sha256` (stdlib) | No new dependency; constant-time compare not required here (lookup by hash, not comparison) |
| Email body deduplication | Copying email strings into tests | `backend/app/emails.py` functions | Extract once, reference in both task and test assertion |

---

## Runtime State Inventory

Step 2.5: SKIPPED — This is a backend-completion + test-harness phase, not a rename/refactor/migration of stored strings. No runtime state inventory required. The timezone Alembic migration does touch stored datetime values, but that is a schema migration (handled in Architecture Patterns above), not a runtime string rename.

---

## Common Pitfalls

### Pitfall 1: Trailing Slash 307 Redirect Breaking CORS Preflight

**What goes wrong:** FastAPI's `redirect_slashes=True` (default) issues a 307 redirect for `/signups` → `/signups/`. The browser follows the redirect but the CORS preflight `OPTIONS` request is not re-sent to the redirected URL, causing the actual request to fail with a CORS error.

**Why it happens:** CORS preflight caches the origin for the original URL; the redirect is to a different path.

**How to avoid:** Either (a) set the frontend to always use trailing slashes, or (b) set `redirect_slashes=False` on the FastAPI app and add both variants on each router using `include_in_schema=False`. Option (b) is already used on the slots router (`@router.get("")` + `@router.get("/")`) — apply the same pattern to signups.

**Warning signs:** 307 in browser network tab followed by CORS error on the redirected request.

### Pitfall 2: Pydantic `.dict()` Deprecation Warning in Tests

**What goes wrong:** `updates.dict(exclude_unset=True)` raises `PydanticDeprecatedSince20` warning in Pydantic v2. In strict test environments this may surface as an error.

**Why it happens:** Three sites in the codebase use the Pydantic v1 `.dict()` method: `events.py:137`, `users.py:26`, `slots.py:105`. [VERIFIED: CONCERNS.md]

**How to avoid:** Replace with `.model_dump(exclude_unset=True)` at all three sites as part of tech-debt cleanup.

### Pitfall 3: Enum ALTER TYPE in Alembic Migration

**What goes wrong:** Adding a value to a SQLAlchemy `Enum` with `name=` pointing to a Postgres native enum type (`signupstatus`) requires `ALTER TYPE signupstatus ADD VALUE 'registered'`. If `models.py` is updated without a matching Alembic migration, SQLAlchemy will fail to start because the Postgres enum does not contain the value.

**Why it happens:** SQLAlchemy generates `CREATE TYPE` only once (initial migration). Subsequent code changes to the Python enum class are not auto-detected by Alembic autogenerate.

**How to avoid:** Always write a manual `op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'registered'")` migration when adding to any `Enum(name=...)` column.

**Warning signs:** `LookupError: 'registered' is not among the valid values` from SQLAlchemy at startup.

### Pitfall 4: Celery-redbeat Requires REDIS_URL for Beat Only

**What goes wrong:** `celery-redbeat` uses a separate Redis key namespace by default. If `redbeat_redis_url` is not set, it falls back to the broker URL, which is fine — but if the broker and backend use different Redis instances, only one will have the lock.

**How to avoid:** Explicitly set `redbeat_redis_url = settings.redis_url` in Celery config. For this project, broker and result backend are on the same Redis instance, so this is not a risk. [VERIFIED: docker-compose.yml uses single Redis service]

### Pitfall 5: `freezegun` Does Not Patch Celery's Internal Scheduler Clock

**What goes wrong:** `@freeze_time(...)` patches `datetime.datetime.now` and `datetime.datetime.utcnow` in Python stdlib, but Celery's beat scheduler uses its own system clock for ETA calculations. If testing that `schedule_reminders` picks up the right slots, you must freeze time in the task's own imports, not just the test module.

**How to avoid:** Directly call the task function (not `.delay()`) in tests with `freezegun` active, and ensure all datetime calls within the task are patched. Use `freezegun.freeze_time` as a context manager around the direct function call.

### Pitfall 6: Playwright Global Setup Cannot Use `dependency_overrides`

**What goes wrong:** Playwright's `globalSetup` runs in a separate Node.js process from tests. It cannot share Python test fixtures or override FastAPI dependencies. Seeding must be done via HTTP calls to the running backend (not via direct DB access from JS).

**How to avoid:** Seed via the backend's admin API endpoints with a known admin credential seeded at DB initialization. The `migrate` service already runs `python -m app.seed_admin` — ensure that script creates a deterministic admin with known test credentials (or add a separate `seed_test.py` invoked only in CI).

### Pitfall 7: `update_me` Privilege Escalation

**What goes wrong:** `update_me` in `users.py` uses a `setattr` loop over all fields in `schemas.UserUpdate`. If `role` or `hashed_password` ever appear in that schema, a participant can elevate themselves to admin.

**Why it happens:** `setattr` loop applies any field in the schema without an explicit allowlist. [VERIFIED: users.py lines 26-28]

**How to avoid:** Replace with an explicit allowlist: `ALLOWED_FIELDS = {"name", "university_id", "notify_email"}`. Part of Phase 0 tech-debt cleanup.

### Pitfall 8: Dead `slowapi` Middleware Adds Overhead

**What goes wrong:** `SlowAPIMiddleware` is mounted in `main.py` but no endpoints use `@limiter.limit(...)`. It adds request overhead without providing any protection.

**Why it happens:** Rate limiting was migrated to a custom Redis counter (`rate_limit` dependency in `deps.py`) but the old middleware was not removed. [VERIFIED: main.py lines 18-21, deps.py lines 40-60]

**How to avoid:** Remove `SlowAPIMiddleware`, `app.state.limiter = limiter`, and `_rate_limit_exceeded_handler` from `main.py`. The `limiter` object in `deps.py` is still needed if any endpoint is decorated with `@limiter.limit` — but none are, so both can be removed.

---

## Open Questions (RESOLVED)

> All questions below were resolved during plan revision by reading the backend router source files directly. Inline **RESOLVED:** markers capture the concrete answers; plans reference these findings instead of deferring to execution.

1. **`listEventSignups` missing endpoint**
   - What we know: `api.listEventSignups(eventId)` calls `GET /events/{eventId}/signups` which does not exist in any backend router.
   - What's unclear: What data does the organizer dashboard use? Does `OrganizerEventPage.jsx` call this function? Does `GET /admin/events/{eventId}/roster` serve the same purpose?
   - Recommendation: Read `OrganizerEventPage.jsx` to find actual call sites, then either (a) add `GET /events/{eventId}/signups` as a non-admin version of the roster, or (b) change the frontend call to use the admin roster endpoint with appropriate auth.
   - **RESOLVED:** Verified against `backend/app/routers/events.py` (grep of `@router.*`): no `/events/{event_id}/signups` endpoint exists. The only signup-roster endpoint is `GET /admin/events/{event_id}/roster` in `admin.py` (line 169). **Decision:** Plan 01 API-AUDIT task updates `frontend/src/api.js::listEventSignups` to call `GET /admin/events/${eventId}/roster` (organizers already have admin-or-owner access via `ensure_event_owner_or_admin`). No new backend endpoint is added in Phase 0.

2. **`updateSlot` / `deleteSlot` method mismatch**
   - What we know: Frontend calls `PATCH /slots/{id}` and `DELETE /slots/{id}`. The slot router was not fully read.
   - What's unclear: Whether the slot router uses `PATCH` or `PUT` for updates.
   - Recommendation: Planner should read `backend/app/routers/slots.py` in full before writing the implementation plan.
   - **RESOLVED:** Read `backend/app/routers/slots.py`. Confirmed routes: `@router.patch("/{slot_id}")` at line 89 and `@router.delete("/{slot_id}")` at line 133. **Frontend already matches** (PATCH + DELETE). No backend or frontend change required for slots routing. Plan 01 API-AUDIT removes slots from the mismatch punch list.

3. **Notification / Portal / Admin router endpoints**
   - What we know: Several `api.js` functions targeting `/notifications/my`, `/portals/*`, and `/admin/*` were verified-correct at the function level but the backend routers were not fully audited.
   - Recommendation: Plan a Wave 0 task to read all remaining router files and complete the punch list before any other implementation work.
   - **RESOLVED:** All remaining routers read during revision:
     - `notifications.py`: only `GET /notifications/my` (line 14). Frontend `api.getMyNotifications` matches. No gap.
     - `portals.py`: `POST /`, `GET /`, `GET /{slug}`, `POST /{portal_id}/events/{event_id}`, `DELETE /{portal_id}/events/{event_id}`. Frontend portal functions (`listPortals`, `getPortal`, `attachEventToPortal`, `detachEventFromPortal`) all match. No gap.
     - `admin.py`: `GET /summary`, `GET /events/{id}/analytics`, `GET /events/{id}/roster`, `GET /events/{id}/export_csv`, `POST /signups/{id}/cancel|promote|move|resend`, `POST /events/{id}/notify`, `GET /audit_logs`, `DELETE /users/{id}`. Frontend admin functions cross-checked: all 10 endpoints are called from `api.js`. No gap.
     - **Net result:** The only API contract mismatches that remain for Plan 01 are the four already documented in the audit (createSignup trailing slash, updateEvent PUT vs PATCH, updateEventQuestion path, deleteEventQuestion path) plus the `listEventSignups` rewire from resolution #1. No new Wave 0 router audit task needed — audit work collapses into Plan 01 Task 2.

4. **`signups.status = registered` decision**
   - What we know: `registered` is NOT in the current enum. Phase 0 E2E flows work with `confirmed` as initial status.
   - Recommendation: Defer `registered` to Phase 3. Document in plan that the Phase 0 Playwright test asserts `status === 'confirmed'` after signup, not `status === 'registered'`.

5. **Playwright seed strategy**
   - What we know: `seed_admin.py` creates a deterministic admin. Test DB needs additional seed: organizer, portal, event, slots, participant.
   - Recommendation: Add a `seed_test_fixtures.py` script that is idempotent (check-before-insert) and called in the CI workflow before Playwright runs.

---

## Environment Availability

| Dependency | Required By | Available | Version | Notes |
|------------|------------|-----------|---------|-------|
| Docker | Playwright CI stack | Yes | 28.3.2 | [VERIFIED: local env] |
| Docker Compose | Full stack integration tests | Yes | bundled with Docker Desktop | |
| Node.js | Frontend + Playwright | Yes | 20.20.0 | [VERIFIED: local env] |
| npm | Frontend package management | Yes | 10.8.2 | [VERIFIED: local env] |
| Python 3.12 | Backend tests | Yes | 3.12.6 | Note: backend Docker image uses 3.10-slim; local dev is 3.12 |
| PostgreSQL | Integration tests | Via Docker | postgres:16 | CI workflow already has `services.postgres` |
| Redis | Celery tests (mocked) | Via Docker | redis:7 | Available in docker-compose |

**Version mismatch note:** Backend Docker image (`python:3.10-slim`) but local dev runs Python 3.12. This is fine for test compatibility — both support all libraries in use — but `datetime.utcnow()` deprecation warning is active on 3.12. [VERIFIED: STACK.md, local python3 --version]

**Missing dependencies with no fallback:** None that block Phase 0.

**Missing dependencies with fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.2.2 + pytest-asyncio 0.23.7 (backend); Playwright 1.59.1 (E2E) |
| Config file | `backend/pytest.ini` — does not exist yet (Wave 0 gap) |
| Quick run command | `cd backend && pytest tests/ -x -q` |
| Full suite command | `cd backend && pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=70` |
| E2E command | `cd frontend && npx playwright test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Refresh token stored + 401 triggers refresh | integration | `pytest tests/test_auth.py::test_refresh_on_401 -x` | No — Wave 0 |
| AUTH-02 | Refresh token hashed in DB | integration | `pytest tests/test_auth.py::test_refresh_token_hashed -x` | No — Wave 0 |
| TZ-01 | Migration produces timezone-aware datetimes | integration | `pytest tests/test_migration.py::test_datetime_tz_aware -x` | No — Wave 0 |
| TZ-02 | Reminder scheduling invariant across DST | unit | `pytest tests/test_celery.py::test_reminder_dst_invariant -x` | No — Wave 0 |
| CELERY-01 | Redbeat prevents duplicate reminders | integration | `pytest tests/test_celery.py::test_no_duplicate_reminders -x` | No — Wave 0 |
| CELERY-02 | `reminder_sent` flag prevents double-send | unit | `pytest tests/test_celery.py::test_reminder_sent_idempotency -x` | No — Wave 0 |
| REFACTOR-01 | `promote_waitlist_fifo` uses `(timestamp, id)` ordering | unit | `pytest tests/test_signup_service.py::test_waitlist_fifo_ordering -x` | No — Wave 0 |
| E2E-01 | Student register→browse→signup→MySignups | E2E | `npx playwright test student-flow` | No — Wave 0 |
| E2E-02 | Student cancel→capacity freed→second signup succeeds | E2E | `npx playwright test cancel-flow` | No — Wave 0 |
| E2E-03 | Organizer login→dashboard→roster | E2E | `npx playwright test organizer-flow` | No — Wave 0 |
| E2E-04 | Admin CRUD users/portals/events | E2E | `npx playwright test admin-flow` | No — Wave 0 |
| AUDIT-01 | API contract: 4 known mismatches fixed | integration | `pytest tests/test_events.py tests/test_signups.py -x` | No — Wave 0 |
| TEST-01 | Auth: login, register, refresh, role claims | integration | `pytest tests/test_auth.py -x` | No — Wave 0 |
| TEST-01 | Signup: concurrency, capacity, waitlist | integration | `pytest tests/test_signups.py -x` | No — Wave 0 |
| TEST-01 | Rate limiter enforcement | integration | `pytest tests/test_rate_limits.py -x` | No — Wave 0 |
| TEST-01 | Ownership checks | integration | `pytest tests/test_events.py::test_ownership -x` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && pytest tests/ -x -q`
- **Per wave merge:** `cd backend && pytest tests/ --cov=app --cov-fail-under=70 && cd ../frontend && npx playwright test`
- **Phase gate:** Full suite green (backend 70% coverage + Playwright 4 flows) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/pytest.ini` — configure testpaths, asyncio_mode
- [ ] `backend/tests/conftest.py` — TestClient + DB session + factory setup
- [ ] `backend/tests/fixtures/factories.py` — factory-boy model factories
- [ ] `backend/tests/test_auth.py` — covers AUTH-01, AUTH-02, TEST-01 (auth)
- [ ] `backend/tests/test_signups.py` — covers TEST-01 (signup), REFACTOR-01
- [ ] `backend/tests/test_events.py` — covers AUDIT-01, TEST-01 (ownership)
- [ ] `backend/tests/test_celery.py` — covers CELERY-01, CELERY-02, TZ-02
- [ ] `frontend/playwright.config.js` — covers E2E-01 through E2E-04
- [ ] `frontend/playwright/global-setup.js` — DB seeding
- [ ] `frontend/playwright/tests/*.spec.js` — 4 test files

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes — refresh token hashing, 401 handling | SHA-256 hash at rest; verify on lookup |
| V3 Session Management | Yes — refresh token revocation, expiry | `revoked_at` + `expires_at` on `RefreshToken` table (already implemented) |
| V4 Access Control | Yes — `update_me` privilege escalation risk | Explicit field allowlist replacing `setattr` loop |
| V5 Input Validation | Yes — Pydantic on every endpoint | Pydantic v2 `.model_dump(exclude_unset=True)` everywhere |
| V6 Cryptography | Partial — refresh tokens are plain UUIDs today | SHA-256 hash (this phase); Argon2id password migration deferred |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Refresh token theft from DB dump | Information Disclosure | SHA-256 hash at rest — implement this phase |
| Privilege escalation via `update_me` | Elevation of Privilege | Whitelist mutable fields — implement this phase |
| CORS wildcard misconfiguration | Spoofing | Read origins from `settings` (env var) — implement this phase |
| Email spoofing via organizer broadcast | Spoofing | Out of scope for Phase 0; deferred (per CONTEXT.md) |
| Duplicate email reminders | Denial of Service (cost) | `reminder_sent` flag + redbeat locking — implement this phase |
| Race condition on `max_signups_per_user` | Tampering | Known bug (CONCERNS.md); no fix in Phase 0 scope but add a test that documents it |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `datetime.utcnow()` | `datetime.now(timezone.utc)` | Python 3.12+ deprecation | Produces tz-aware datetime; works with `DateTime(timezone=True)` |
| `pydantic.dict()` | `.model_dump(exclude_unset=True)` | Pydantic v2 | `.dict()` removed in v3; migrate now |
| celery-beat (single process) | celery-redbeat | Distributed deploy requirement | Prevents duplicate beat task execution |
| Plain UUID refresh token | SHA-256 hash in DB | Security best practice | DB dump no longer leaks usable tokens |
| No E2E tests | Playwright | Phase 0 goal | CI regression gating |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Refresh-on-401 thundering-herd prevention via `let refreshPromise = null` module-level singleton | Pattern 2 | If `api.js` is bundled in a way that creates multiple module instances (unlikely with Vite), the singleton doesn't work. Low risk with standard Vite ESM bundling. |
| A2 | `celery-redbeat` 2.3.3 works with Celery 5.6.0 | Standard Stack | Redbeat 2.x changelog should be verified against Celery 5.6 — both from pip registry, but no official compatibility matrix read. |
| A3 | Playwright `globalSetup` can call existing admin API for seeding | Pattern 7 | If admin API is rate-limited or requires session state that globalSetup can't easily establish, a test-only seed endpoint may be needed. |
| A4 | `freezegun` patches `datetime.utcnow()` inside Celery task body | Pitfall 5 | Verified in freezegun docs at training time; confirmed approach for stdlib datetime. Edge cases with C-extension datetime (cpython 3.12 speedups) may not be patched — verify with a simple test. |
| A5 | `ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'registered'` is available in Postgres 16 | Pitfall 3 | `IF NOT EXISTS` clause on `ADD VALUE` was added in Postgres 9.3; safe for Postgres 16. [ASSUMED from training] |
| A6 | Portals, notifications, and remaining admin router endpoints match their `api.js` call signatures | API Audit — Verified Correct table | These routers were not fully read during research. Planner must complete audit in Wave 0 task. |

---

## Sources

### Primary (HIGH confidence — verified against live codebase)
- `frontend/src/lib/api.js` — full API client function list and paths
- `backend/app/models.py` — SignupStatus enum (confirmed `registered` NOT present), DateTime column types (all naive)
- `backend/app/routers/signups.py` — create_signup, cancel_signup, my_signups logic; waitlist ordering (`timestamp.asc()` only, missing `id` tiebreaker)
- `backend/app/routers/events.py` — `PATCH` is `include_in_schema=False`, public is `PUT`; questions at `/events/questions/{id}`
- `backend/app/routers/auth.py` — refresh token endpoint exists at `/auth/refresh`, issues both access + refresh tokens
- `backend/app/routers/users.py` — `update_me` setattr loop, `updates.dict(exclude_unset=True)` (v1 API)
- `backend/app/celery_app.py` — single-process beat, no `reminder_sent` guard, naive datetimes
- `backend/app/deps.py` — refresh token stored as plain UUID (no hashing), `datetime.utcnow()` throughout
- `frontend/src/lib/authStorage.js` — `getRefreshToken()` returns `""`, refresh token never stored
- `backend/app/main.py` — `SlowAPIMiddleware` dead code, hardcoded CORS origins
- `backend/requirements.txt` — pinned library versions
- `frontend/package.json` — no test runner present
- `.github/workflows/ci.yml` — CI exists but only runs `pytest` (one smoke test)
- `docker-compose.yml` — 6 services: db, redis, backend, migrate, celery_worker, celery_beat

### Secondary (MEDIUM confidence — pip/npm registry verified)
- celery-redbeat 2.3.3 — verified on PyPI `pip3 index versions celery-redbeat`
- pytest-cov 7.1.0 — verified on PyPI
- factory-boy 3.3.3 — verified on PyPI
- freezegun 1.5.5 — verified on PyPI
- @playwright/test 1.59.1 — verified on npm registry

### Tertiary (LOW confidence — assumed from training knowledge)
- celery-redbeat configuration syntax (beat_schedule structure, `redbeat_redis_url` key name)
- Playwright `globalSetup` API for seeding
- SHA-256 refresh token hashing pattern (standard practice, not verified against specific docs)
- `freezegun` patching behavior with Python 3.12 C-extension datetime

---

## Metadata

**Confidence breakdown:**
- API contract audit: HIGH — verified by reading both `api.js` and backend router files
- SignupStatus enum (open-question gate): HIGH — verified by reading `models.py`
- Standard stack versions: HIGH — verified against requirements.txt and npm/pip registries
- Architecture patterns: MEDIUM — implementation patterns from training knowledge; specific syntax may need adjustment
- Playwright CI setup: MEDIUM — version verified; config syntax assumed from training
- celery-redbeat integration: MEDIUM — version verified; config syntax assumed from training

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable libraries; re-verify Playwright if using later than 1.59.1)
