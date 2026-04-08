# Phase 0: Backend Completion + Frontend Integration — Context

**Gathered:** 2026-04-08
**Status:** Ready for planning
**Source:** /gsd-discuss-phase 0

<domain>
## Phase Boundary

Close all gaps in the existing backend and frontend so every feature works end-to-end through the browser — no curl required. This means a full API contract audit (backend vs `lib/api.js`), auth hardening, Celery reliability fixes, a timezone-correctness migration, and a Playwright suite that gates the build on the 4 critical E2E flows (student signup, student cancel, organizer roster, admin CRUD).

This phase is the strict prerequisite for every other phase. If Phase 0 is not green, no other phase starts.

**Out of scope:** New features, UCSB infrastructure deploy (Phase 8), bulk slot edit / drag-drop (backlog), SMS delivery (backlog), notification templating beyond what's needed to dedupe current inline bodies.

</domain>

<decisions>
## Implementation Decisions

### API Contract Audit & Fixes
- **Scope:** Fix every mismatch, not just E2E blockers. Phase goal mandates "linked fix PR for every mismatch."
- **Deliverable:** Written punch list covering every `frontend/src/lib/api.js` function (URL, HTTP method, response shape) cross-checked against backend routers.
- **Known mismatches to fix:**
  - `api.createSignup` POSTs `/signups` but backend mounts `/signups/` (trailing slash); normalize one way.
  - `updateEvent` uses `PATCH` — backend only exposes `PUT` publicly (`PATCH` is `include_in_schema=False`). Align frontend to `PUT` OR expose `PATCH`; pick one.
  - `updateEventQuestion` / `deleteEventQuestion` call `/event-questions/{id}` but backend mounts `/events/questions/{id}`. Fix frontend paths.
  - `listEventSignups` calls `/events/{eventId}/signups` — endpoint does not exist. Either add the endpoint or change the frontend call site.
- **Testing:** Add pytest integration tests per router (new `backend/tests/` structure with `conftest.py`, FastAPI `TestClient`, DB fixtures) to prevent regressions.

### Auth Hardening (in-scope)
- **Frontend refresh-token flow:** Store refresh token in `authStorage`, implement refresh-on-401 in `api.js` request helper. Fix stale `getRefreshToken` dead code. This unblocks real E2E testing (60-min access token expiry currently forces logout mid-test).
- **Hash refresh tokens at rest:** SHA-256 the token before storing in `RefreshToken.token`; compare hashes on verify. Keep `unique=True` on the hash column. Alembic migration to rename/rehash column.
- **Defer to later phase:** Argon2id password migration, httpOnly-cookie storage, password reset endpoint, email verification. These are separate risk/UX changes that don't block the Phase 0 goal.

### Timezone Migration (full, now)
- **Do it now** with a single Alembic migration. Tolerate one painful PR rather than leaving DST bugs and deprecation warnings throughout the codebase.
- **Changes:**
  - Migrate all `DateTime` columns in `backend/app/models.py` to `DateTime(timezone=True)`.
  - Replace every `datetime.utcnow()` with `datetime.now(timezone.utc)`.
  - Delete all `_to_naive_utc()` helpers (events.py, slots.py, signups.py, deps.py, celery_app.py).
  - Backfill/cast existing rows in the Alembic migration (assume stored values were UTC).
- **Validation:** Celery reminder scheduling must produce identical windows across DST transitions (test with frozen time).

### Celery Reliability (redbeat + flag + index)
- **Replace celery-beat with `celery-redbeat`** for distributed locking. Prevents duplicate reminders if two beats ever run (HA scenario, deploys).
- **Add `reminder_sent` boolean flag on `Signup`** (default `False`, set by the task after SendGrid success). Idempotency for reminder task.
- **Add index on `slots.start_time`** to speed the 5-minute scan window.
- **Task retries:** Configure `autoretry_for=(Exception,)`, `retry_backoff=True`, `max_retries=3` on `send_email_notification` and `schedule_reminders`.
- **Signups.status enum gate (open question from ROADMAP):** Planner must verify whether `registered` is in the current enum or needs an Alembic migration — block plan otherwise.

### Claude's Discretion

**Playwright suite shape:**
- Cover the 4 E2E flows named in ROADMAP success criteria: (1) student register→browse→sign up→see in MySignups, (2) student cancel→slot capacity freed→confirmation email, (3) organizer login→dashboard→roster, (4) admin CRUD users/portals/events.
- Run against `docker-compose` stack (db/redis/backend already orchestrated there) with an ephemeral test database spun up per run. Reuse Docker Compose profile rather than standing up a second stack.
- Seed fixtures via a `backend/tests/fixtures/` factory callable from a Playwright `globalSetup`. Minimum: one admin, one organizer, one portal, one event with slots, one participant user.
- CI: GitHub Actions workflow that runs on every PR, fails the build on regression, uploads trace artifacts on failure.
- Playwright config: retries=2 on CI, 0 locally; headed only on local `--debug`.
- Email assertions: stub SendGrid in test env and assert the `Notification` DB row rather than a real inbox.

**Refactors bundled into Phase 0:**
- **Extract `backend/app/signup_service.py`** with a single `promote_waitlist_fifo` using canonical `(timestamp, id)` ordering. Required because the waitlist-ordering divergence is a latent correctness bug that the cancel E2E test will expose.
- **Extract `backend/app/emails.py`** with one function per transactional notification type. Required to dedupe inline email bodies before adding Playwright assertions against them.
- **Centralize `_to_naive_utc` / `_ensure_event_owner_or_admin`** into `backend/app/utils.py` and `backend/app/deps.py` respectively (the TZ migration already rewrites these files).
- **Do NOT split** `admin.py` (753 lines) or `OrganizerEventPage.jsx` (945 lines) in Phase 0 — pure ergonomics, no correctness impact, high diff noise. Defer to a dedicated refactor phase.

**Tech-debt cleanups (in scope, opportunistic):**
- Replace `pydantic.dict()` → `.model_dump(exclude_unset=True)` at the 3 cited sites (events.py, users.py, slots.py).
- Whitelist mutable fields in `update_me` (users.py) explicitly — eliminates the setattr privilege-escalation risk. Required before auth hardening lands.
- Remove dead `slowapi` middleware from `main.py` (custom Redis rate limiter is the real one).
- Read CORS allowed origins from `settings` (env var), remove the TODO in `main.py:30`.
- Add `current_count` defensive-healing note to signup_service extraction — do NOT drop the column in Phase 0 (too risky), but document the invariant.

**Validation / observability defaults:**
- pytest integration tests cover: auth (login/register/refresh), signup concurrency, waitlist promotion ordering, rate limiter, ownership checks, Celery task idempotency (mocked broker).
- Minimum coverage target: backend 70% lines, critical paths (signup/cancel/waitlist) 90%.
- No new logging infra — use existing `logger` calls, just ensure every new try/except includes `logger.exception`.

**Security defaults:**
- Run `/gsd-secure-phase 0` threat-model gate during planning; block on High severity.
- No new secrets introduced (reuse existing JWT secret, SendGrid key, Redis URL).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project planning
- `.planning/PROJECT.md` — Vision, principles, non-negotiables
- `.planning/REQUIREMENTS.md` — Acceptance criteria and constraints
- `.planning/ROADMAP.md` — Phase 0 section with success criteria and open-question gate
- `.planning/STATE.md` — Current project state

### Codebase intel (already generated)
- `.planning/codebase/ARCHITECTURE.md` — Layer boundaries, auth flow, notification flow
- `.planning/codebase/CONCERNS.md` — Authoritative list of every issue this phase addresses (tech debt, bugs, security, performance, fragility, test gaps)
- `.planning/codebase/CONVENTIONS.md` — Code style and naming conventions to follow
- `.planning/codebase/INTEGRATIONS.md` — SendGrid, Redis, Celery, OIDC integration points
- `.planning/codebase/STACK.md` — Exact library versions in use
- `.planning/codebase/STRUCTURE.md` — Directory layout
- `.planning/codebase/TESTING.md` — Current test gaps; planner will extend this

### Backend files central to the phase
- `backend/app/main.py` — CORS, middleware, slowapi dead code
- `backend/app/models.py` — All ORM columns requiring TZ migration
- `backend/app/deps.py` — Auth, rate limit, refresh token helpers
- `backend/app/celery_app.py` — Beat schedule, reminder scan, SendGrid helper
- `backend/app/routers/signups.py` — Waitlist logic, concurrency, current_count healing
- `backend/app/routers/admin.py` — Duplicate waitlist logic, email broadcast vector, N+1
- `backend/app/routers/events.py`, `slots.py`, `auth.py`, `users.py` — API contract audit targets
- `backend/tests/test_smoke.py` — Placeholder; planner must establish real test harness here

### Frontend files central to the phase
- `frontend/src/lib/api.js` — Every function audited against backend routes
- `frontend/src/lib/authStorage.js` — Refresh token dead code to fix
- `frontend/src/pages/OrganizerEventPage.jsx` — Do NOT split; touch only for API contract fixes
- `frontend/package.json` — Add Playwright + test runner

### External docs (for researcher)
- celery-redbeat docs — distributed beat replacement
- passlib argon2 migration docs — (if later phase picks it up; just for researcher awareness)
- Playwright CI recipes for Vite + docker-compose
- Alembic + `DateTime(timezone=True)` migration patterns

</canonical_refs>

<specifics>
## Specific Ideas

- The cancel E2E test MUST verify the freed capacity is reusable: a second user signs up into the same slot after the cancel and succeeds. This exercises `current_count`, waitlist promotion, and email dispatch in one path.
- Integration tests should use a real Postgres (not SQLite) — the schema uses JSON columns and timezone-aware timestamps that behave differently on SQLite.
- Refresh-on-401 flow must queue concurrent 401s behind a single in-flight refresh to avoid thundering-herd token refresh.

</specifics>

<deferred>
## Deferred Ideas

**Moved to later phases / backlog:**
- Argon2id password hashing migration
- httpOnly cookie storage for access tokens + CSRF double-submit
- Password reset flow (`/auth/forgot-password`, `/auth/reset-password`)
- Email verification on register
- Strict CSP header (relaxed only for `/docs`)
- Splitting `admin.py` into `admin_analytics.py` / `admin_signups.py` / `admin_users.py` / `admin_audit.py`
- Splitting `OrganizerEventPage.jsx` into `frontend/src/pages/organizer/*`
- SMS delivery via Twilio
- Bulk slot edit / drag-drop (IDEAS.md)
- Audit-log `jsonb` + GIN index optimization
- Pagination on `list_users` / `list_events` / `list_portals` / `list_audit_logs`
- Dropping the `current_count` column in favor of dynamic count or DB trigger
- JWT key rotation with `kid` header
- Per-organizer broadcast rate limit + templated header/footer for `EventNotifyRequest`
- `admin_summary` Redis caching
- `my_signups` window-function rewrite

**Open-question gate (must resolve before phase closes):**
- UCSB infrastructure contact confirmed via IT ticket (feeds Phase 8).
- `signups.status` enum: verify whether `registered` is the initial status today or if an Alembic migration is required.

</deferred>

---

*Phase: 00-backend-completion-frontend-integration*
*Context gathered: 2026-04-08 via /gsd-discuss-phase*
