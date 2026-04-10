# Phase 13: E2E Seed + Playwright Coverage — Research

**Researched:** 2026-04-09
**Domain:** Playwright E2E testing, Python seed scripting, GitHub Actions CI wiring
**Confidence:** HIGH — all findings are from direct codebase inspection

---

## Summary

Phase 13 layers E2E coverage on top of a codebase that is already 95% wired for
Playwright but whose existing specs target the retired v1.0 flows (student accounts,
`/register`, `portal_slug`, `/my-signups`). Nearly every piece of infrastructure is
in place: `playwright.config.js` exists at the repo root, `@playwright/test` v1.59.1
is installed in both the root and frontend `package.json`, a `global-setup.js`
orchestrates `seed_e2e.py`, a `fixtures.js` provides credentials and seed accessors,
and the GitHub Actions `phase0-e2e-tests` job already spins up the full Docker stack
and runs `npx playwright test`. The work of Phase 13 is almost entirely *rewriting*
the stale specs and *rewriting* `seed_e2e.py` — not bootstrapping a new test harness.

The hardest design decision is how the Playwright test obtains a raw magic-link token
to drive the confirm and manage flows. The `POST /public/signups` response does **not**
return the token — it only returns `{volunteer_id, signup_ids, magic_link_sent: true}`.
The raw token is passed to Celery for email delivery and never echoed in an HTTP
response. The E2E seed script therefore cannot get the token through the public API.
The right pattern is: `seed_e2e.py` calls `POST /public/signups` to create the signup,
then queries the `magic_link_tokens` table directly via a DB connection to retrieve the
token hash reverse — but the token is only stored as a SHA-256 hash. This means the
seed script must either (a) use a dedicated dev-only debug endpoint that exposes the
latest token for a volunteer, (b) issue the token itself by calling into the service
layer directly, or (c) expose a narrow `GET /dev/latest-token?email=` endpoint that
only runs when a feature flag / env var is set.

**Primary recommendation:** Add a single dev-only `GET /dev/latest-token?volunteer_email=`
endpoint, guarded by `if settings.env == "dev"`, that queries `magic_link_tokens` by
`volunteer_id` and returns the *raw token from the most recent row* — which requires
storing the raw token momentarily. Because the raw token is never stored (only its hash
is), the cleanest approach is a two-step: `seed_e2e.py` calls `POST /public/signups`
then calls a seed-time helper that creates a *known* token via direct DB insert (the
seed script already imports SQLAlchemy for its factory use). This keeps the production
API unchanged and avoids a new endpoint.

---

## Existing Playwright Infrastructure

### playwright.config.js (repo root — `[VERIFIED: direct read]`)

```js
// playwright.config.js
testDir: './e2e',
globalSetup: './e2e/global-setup.js',
fullyParallel: true,
forbidOnly: !!process.env.CI,
retries: process.env.CI ? 2 : 0,
use: {
  baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
  trace: 'on-first-retry',
  video: 'retain-on-failure',
},
projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
```

Key points:
- Config is at the repo root, not inside `frontend/`. Tests run with `npx playwright test`
  from the repo root.
- `baseURL` defaults to `http://localhost:5173` (Vite dev server). No `webServer` block
  — Playwright does **not** start Vite itself. The docker stack + Vite dev server must
  already be running when `npx playwright test` is invoked.
- `globalSetup` points to `e2e/global-setup.js` which calls `seed_e2e.py`.

### e2e/global-setup.js (repo root `[VERIFIED: direct read]`)

```js
spawnSync('python3', ['backend/tests/fixtures/seed_e2e.py'], {
  env: { ...process.env, BACKEND_URL: backendUrl },
})
// Expects seed script to print a single JSON line on the last stdout line.
// Stashes result in process.env.E2E_SEED for specs to consume via getSeed().
```

The seed script is currently at `backend/tests/fixtures/seed_e2e.py`.
The ROADMAP calls for `backend/scripts/seed_e2e.py`. Two options:
1. Move the file to `backend/scripts/seed_e2e.py` and update global-setup.js.
2. Keep it at `backend/tests/fixtures/seed_e2e.py` and just rewrite it.

Option 2 avoids touching CI config and global-setup.js. Recommended.

### e2e/fixtures.js (repo root `[VERIFIED: direct read]`)

```js
export const ADMIN = { email: 'admin@e2e.test', password: 'Admin!2345' };
export const ORGANIZER = { email: 'organizer@e2e.test', password: 'Organizer!2345' };
export const STUDENT = { email: 'student@e2e.test', password: 'Student!2345' };
export function getSeed() { return JSON.parse(process.env.E2E_SEED || '{}'); }
export function ephemeralEmail(tag) { ... }
```

`STUDENT` must be removed or replaced — there is no student account in v1.1. The
`ephemeralEmail()` helper is still useful for generating unique volunteer emails per
test run. A `VOLUNTEER_IDENTITY` object (first_name, last_name, email, phone) should
replace `STUDENT`.

### Package / browser install (`[VERIFIED: direct inspection]`)

- Root `package.json`: `@playwright/test: ^1.59.1` installed. `npm ci` pulls it.
- `frontend/package.json`: also has `@playwright/test: ^1.59.1` and `@axe-core/playwright: ^4.11.1`.
- `npx playwright --version` returns `Version 1.59.1` — npm package is installed.
- Chromium binary: **NOT installed** at `node_modules/.bin/playwright`. The cached
  system install at `/Users/.../Library/Caches/ms-playwright/chromium-1217/` exists
  locally but that path will not be present in CI. The CI job already runs
  `npx playwright install --with-deps chromium` — this is correct and must be kept.

---

## Existing Specs — Status After Phase 12

All existing specs reference the v1.0 model. They must be **replaced**, not amended.

| Spec file | v1.0 assumption | What breaks in v1.1 |
|-----------|----------------|---------------------|
| `student-signup.spec.js` | `/register`, `portal_slug`, `/my-signups` | All three routes deleted |
| `student-cancel.spec.js` | `/register`, `/login` as student, `/my-signups` | Student login / my-signups deleted |
| `magic-link.spec.js` | `/signup/confirm-pending`, `/signup/confirm-failed`, `/signup/confirmed` | These routes are retired (deleted in Phase 12); spec tests for them |
| `signup-three-tap.spec.js` | `slot-signup-button` data-testid, dialog, `/register` | Registration deleted; slot button testid may still exist on the new form |
| `a11y.spec.js` | `/register`, `/my-signups`, `/profile`, student login paths | Retired routes; student login gone |
| `admin-crud.spec.js` | `/admin/portals`, `/admin/users` (portal concept) | Portals likely deleted in v1.1; admin routes may have changed |
| `organizer-roster.spec.js` | `seed.event_id`, `/organizer/events/:id` | Route structure may have changed; seed shape will change |

The `organizer-roster.spec.js` is the closest to v1.1-correct but still reads
`seed.event_id` which will be output by the new seed script.

---

## seed_e2e.py — Current State and What Needs to Change

**Location:** `backend/tests/fixtures/seed_e2e.py` (`[VERIFIED: direct read]`)

### Current script does (v1.0 design):
1. Calls `POST /auth/register` — deleted in Phase 12
2. Calls `POST /users/` (admin creates users) — this still exists
3. Creates portals via `POST /portals/` — portal concept may be retired
4. Creates events as organizer with old `title`/`description` schema
5. Returns `{event_id, slot_ids, portal_slug, admin_email, organizer_email, student_email, event_title}`

### New script must do (v1.1):
1. Upsert admin user (already exists via `docker compose run migrate` → `seed_admin.py`)
2. Upsert organizer user via `POST /users/` (admin-created, role=organizer)
3. Create a v1.1 event via `POST /events/` with `quarter`, `year`, `week_number`,
   `module_slug`, `school` fields — event must fall in the current quarter/week so
   `GET /public/events?quarter=...` returns it
4. Create one `orientation` slot + one `period` slot on the event, each with capacity ≥ 2
5. Create a pre-existing volunteer who has an `attended` orientation signup (for the
   "orientation modal skipped" test scenario)
6. Create a `pending` signup for a known volunteer email with a magic-link token —
   the raw token must be returned in the seed JSON so specs can use it directly
7. Return JSON: `{event_id, orientation_slot_id, period_slot_id, quarter, year,
   week_number, confirmed_token, manage_token, seeded_volunteer_email,
   attended_volunteer_email, organizer_email, admin_email, event_title}`

### Token retrieval problem (`[VERIFIED: direct read of service and schemas]`)

`POST /public/signups` returns `{volunteer_id, signup_ids, magic_link_sent: true}`.
The raw token is **not in the response**. The token hash is stored in `magic_link_tokens`
but hashing is one-way — you cannot reverse it.

The seed script calls the backend over HTTP (per the existing design comment: "no
direct DB / no SQLAlchemy dependency_overrides"). This creates a conflict: the script
cannot retrieve the raw token from the HTTP API.

**Resolution options:**

| Option | How | Pros | Cons |
|--------|-----|------|------|
| A. Dev-only token-echo endpoint | `GET /dev/latest-token?volunteer_id=` guarded by `settings.env != "production"` | Clean HTTP-only seed | Adds prod-guard logic; new endpoint |
| B. Seed script uses direct DB (psycopg2) | Connect to `DATABASE_URL`, `SELECT` raw token — but raw token is never stored | Doesn't work — hash is one-way |
| C. Seed script inserts known token directly via DB | Generate raw token in Python, hash it, `INSERT INTO magic_link_tokens` | No new backend code | Script needs DB access + SQLAlchemy dep in seed context |
| D. Modify PublicSignupResponse to return token in non-production | Add `confirm_token: str | None` to schema, populated when `settings.env == "dev"` | One small schema change | Minor prod/dev API surface divergence |

**Recommendation: Option D.** Add `confirm_token: str | None = None` to
`PublicSignupResponse`. When `settings.env == "dev"` (or a `EXPOSE_TOKENS_FOR_TESTING`
env var is set), populate it. The seed script calls `POST /public/signups`, reads
`confirm_token` from the response, and puts it in the seed JSON. In production the
field is absent. This is the least invasive change and keeps the seed script HTTP-only.

Alternative if Option D is not desirable: Option C (direct DB insert from seed script).
The seed script already uses the `urllib` stdlib for HTTP; adding `psycopg2` for a
targeted DB insert is straightforward. The `DATABASE_URL` env var is available in the
`backend/.env` that is already sourced by the docker stack.

---

## GitHub Actions CI — Existing E2E Job

**File:** `.github/workflows/ci.yml` (`[VERIFIED: direct read]`)

### Current `phase0-e2e-tests` job (lines 174–256):

```yaml
needs: [phase0-backend-tests, phase0-frontend-tests]
steps:
  - Writes backend/.env
  - docker compose up -d db redis
  - docker compose run --rm migrate         # alembic upgrade head + seed_admin
  - docker compose up -d backend celery_worker celery_beat
  - Polls http://localhost:8000/api/v1/healthz until backend is up (40 × 2s)
  - npm ci (root — installs Playwright)
  - npx playwright install --with-deps chromium
  - cd frontend && npm ci
  - npm run dev -- --host 0.0.0.0 --port 5173 &
  - Polls http://localhost:5173 until Vite is up (30 × 2s)
  - npx playwright test (env: E2E_BASE_URL, E2E_BACKEND_URL)
  - Upload playwright-report/ + test-results/ on failure (14 days)
  - docker compose down -v (always)
```

**Key observation:** The backend `.env` is constructed inline in the CI step with
`SEED_ADMIN_EMAIL=admin@e2e.test` and `SEED_ADMIN_PASSWORD=Admin!2345`. These match
the credentials in `fixtures.js` and `seed_e2e.py`. This is the mechanism that ensures
the admin user exists when `seed_e2e.py` tries to log in as admin.

**What Phase 13 must do to CI:**
- The existing job already runs the full stack + Playwright. No new job is needed.
- The job name `phase0-e2e-tests` is stale (it's Phase 1 onwards behavior, not just
  Phase 0). It can be renamed `e2e-tests` but this is cosmetic.
- The `needs: [phase0-backend-tests, phase0-frontend-tests]` dependency is correct —
  keep it.
- If Option D (token-echo via `EXPOSE_TOKENS_FOR_TESTING`) is chosen, add
  `EXPOSE_TOKENS_FOR_TESTING=1` to the `env:` block written to `backend/.env`.

### No missing CI infrastructure — Playwright is fully wired. (`[VERIFIED: direct read]`)

---

## Public API Surface — What Specs Need to Exercise

From `12-SUMMARY.md` handoff table and direct router inspection:

### Public (unauthenticated) endpoints needed by E2E:

| Endpoint | Route | Notes |
|----------|-------|-------|
| `GET /api/v1/public/current-week` | Used by `EventsBrowsePage` week selector | Returns `{quarter, year, week_number}` |
| `GET /api/v1/public/events?quarter=&year=&week_number=` | Browse page | Seed must plant event in this week |
| `GET /api/v1/public/events/{event_id}` | Event detail | Returns slots with `slot_type` |
| `POST /api/v1/public/signups` | Signup form submit | Returns `volunteer_id`, `signup_ids`; token via Option D |
| `POST /api/v1/public/signups/confirm?token=` | ConfirmSignupPage | Flips pending→confirmed |
| `GET /api/v1/public/signups/manage?token=` | ManageSignupsPage | Returns signup list |
| `DELETE /api/v1/public/signups/{id}?token=` | ManageSignupsPage cancel | Cancel one |
| `GET /api/v1/public/orientation-status?email=` | Called from signup form | Returns `{has_attended}` |

### Organizer endpoints needed by E2E:

| Endpoint | Route | Notes |
|----------|-------|-------|
| `POST /api/v1/auth/token` (form-body) | Login page | Returns JWT |
| `GET /api/v1/organizer/...` | Organizer dashboard | Route details depend on organizer router |

---

## Frontend Routes in v1.1

From `frontend/src/App.jsx` (inferred from Phase 12 deletions):

| Route | Component | Auth |
|-------|-----------|------|
| `/events` | `EventsBrowsePage` | None |
| `/events/:id` | `EventDetailPage` (new v1.1) | None |
| `/signup/confirm?token=` | `ConfirmSignupPage` | None |
| `/signup/manage?token=` | `ManageSignupsPage` | None |
| `/login` | `LoginPage` | None |
| `/organizer` | Organizer dashboard | organizer/admin |
| `/organizer/events/:id` | Organizer roster | organizer/admin |
| `/admin` | Admin dashboard | admin |

Deleted routes (confirmed in Phase 12): `/register`, `/my-signups`, `/profile`,
`/signup/confirm-pending`, `/signup/confirm-failed`, `/signup/confirmed`,
`/admin/portals`, `/admin/users` (if portals removed).

---

## Spec Design — What to Write

### Spec 1: Public volunteer flow (`public-volunteer-flow.spec.js`)

```
Browse /events with week selector
→ navigate to event detail
→ fill signup form (orientation + period slots both selected)
→ no orientation modal (both slots in same submission)
→ form submit → success screen
→ seed provides confirm_token from signup response
→ navigate to /signup/confirm?token={confirm_token}
→ ConfirmSignupPage shows confirmed signups
→ navigate to /signup/manage?token={confirm_token}
→ ManageSignupsPage shows two signups
→ cancel one → list updates
→ cancel-all button → list empty
```

### Spec 2: Orientation modal (`orientation-modal.spec.js`)

```
Test A (modal fires):
  Use ephemeral email with no orientation history
  Select period slot only → submit
  Orientation modal fires
  Click Yes → signup proceeds (success screen)

Test B (modal skipped):
  Use seeded "has_attended" volunteer email (from seed JSON: attended_volunteer_email)
  Select period slot only → submit
  No modal → success screen directly
```

### Spec 3: Organizer check-in regression (`organizer-checkin.spec.js`)

```
Login as organizer
→ /organizer
→ /organizer/events/{seed.event_id}
→ roster renders with at least one signup row (seed must have a confirmed signup)
→ click "Check in" / "Mark attended" on that row
→ status changes to attended/checked_in
```

This tests the Phase 03 check-in state machine that Phase 12 preserved.

---

## Seed Script Design

### What `seed_e2e.py` must plant:

```python
SEED = {
    "event_id": str,           # UUID of the seeded event
    "orientation_slot_id": str, # UUID of orientation slot
    "period_slot_id": str,     # UUID of period slot
    "quarter": str,            # e.g. "spring"
    "year": int,               # e.g. 2026
    "week_number": int,        # current week (must match /public/current-week)
    "confirm_token": str,      # raw magic-link token for a pre-seeded pending signup
    "seeded_volunteer_email": str,  # email of the pre-seeded volunteer
    "attended_volunteer_email": str, # email of volunteer with attended orientation
    "organizer_email": str,
    "admin_email": str,
    "event_title": str,
}
```

### Idempotency strategy:

- Event: look up by `(quarter, year, week_number, module_slug, school)` — if found, reuse.
- Organizer user: look up by email via `GET /users/`, create if absent.
- Pre-seeded volunteer + signup: delete existing `magic_link_tokens` + `signups` for
  the seeded volunteer on this event's slots, then re-create fresh ones. This ensures
  a valid unexpired token every run.
- "Has attended" volunteer: look up by email; ensure one `attended` signup exists for
  an orientation slot. If not, create via direct DB or an admin endpoint.

### Attended orientation signup — how to create it:

The public `POST /public/signups` creates signups in `pending` status. The attended
volunteer needs a signup in `attended` status. Options:

1. Create signup via public API → then call the organizer check-in endpoint to flip
   it to `attended`. This is the correct application path.
2. Seed script directly inserts a row with `status=attended` via DB.

Option 1 is cleanest (exercises real endpoint). The check-in endpoint is at
`POST /api/v1/check-in/{signup_id}/check-in` or similar (need to verify).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Node.js | `npx playwright test` | Yes | (system) | — |
| `@playwright/test` npm package | Test runner | Yes | 1.59.1 | — |
| Chromium browser binary | Playwright runner | Cached locally; NOT in node_modules | chromium-1217 | `npx playwright install --with-deps chromium` (CI already does this) |
| Python 3 | `seed_e2e.py` | Yes (system + docker) | 3.10 in CI | — |
| Docker stack | Backend + DB | Yes | — | — |
| Vite dev server | Playwright baseURL | Not auto-started by Playwright | — | Must `npm run dev` before `npx playwright test` |

**Browser binary note:** The npm package is installed but `node_modules/.bin/playwright`
binary is absent. Locally, chromium is cached at
`~/Library/Caches/ms-playwright/chromium-1217/`. In CI, `npx playwright install --with-deps chromium`
installs it fresh — this step already exists in the CI YAML. No action needed.

---

## Common Pitfalls

### Pitfall 1: Seed plants event in wrong quarter/week

**What goes wrong:** The browse page calls `GET /public/current-week` and filters events
by the returned quarter/year/week. If the seed plants the event for a hardcoded week
that doesn't match today, `/events` returns an empty list and specs fail.

**How to avoid:** `seed_e2e.py` must call `GET /public/current-week` first, then use
the returned `(quarter, year, week_number)` when creating the event.

**Warning sign:** Spec navigates to `/events`, week selector shows correct week, but
event list is empty.

### Pitfall 2: Magic-link token not obtainable via HTTP

**What goes wrong:** `POST /public/signups` returns `magic_link_sent: true` but no
raw token. Spec cannot navigate to `/signup/confirm?token=X` without the token.

**How to avoid:** Implement Option D (add `confirm_token` field to
`PublicSignupResponse` when `EXPOSE_TOKENS_FOR_TESTING=1`). Plan must include this
backend task explicitly.

**Warning sign:** Seed script receives `{volunteer_id, signup_ids, magic_link_sent:
true}` — no token field present.

### Pitfall 3: Old specs reference deleted routes

**What goes wrong:** Phase 12 deleted `/register`, `/my-signups`, `/signup/confirm-pending`,
`/signup/confirm-failed`, `/signup/confirmed`. All six existing spec files reference
at least one of these.

**How to avoid:** All six spec files must be rewritten from scratch, not patched.

**Warning sign:** Playwright runs but specs fail on navigation — 404s or React Router
rendering the 404 fallback.

### Pitfall 4: `serial` tests mutate shared slot capacity

**What goes wrong:** The old `student-cancel.spec.js` ran serially because two tests
filled the same slot. The new orientation-modal spec also fills slots. If `fullyParallel:
true` runs these concurrently they interfere.

**How to avoid:** Seed the orientation slot and period slot with capacity ≥ 5. Each
spec run uses a fresh ephemeral email (hence a fresh volunteer), so signups don't
collide by volunteer. Only capacity exhaustion is a risk.

**Warning sign:** Flaky 409 errors on slot full during parallel test runs.

### Pitfall 5: Rate limiter blocks seed or test traffic

**What goes wrong:** `POST /public/signups` has `rate_limit(max_requests=10, window_seconds=60)`.
If seed + specs together make > 10 calls per minute from the same IP, they hit 429.

**How to avoid:** The seed script should make one signup call for the pre-seeded
volunteer. Specs use ephemeral emails → each is a separate signup. In CI, all requests
come from localhost so it's a single IP. Keep per-spec signup calls to ≤ 1.

**Warning sign:** Intermittent 429 errors in CI.

### Pitfall 6: No `webServer` in playwright.config.js — Vite must be pre-started

**What goes wrong:** Unlike some setups, this project's `playwright.config.js` has no
`webServer` block. Playwright does not start Vite. If the dev server isn't running,
every spec fails with `ERR_CONNECTION_REFUSED`.

**How to avoid:** The CI job already starts Vite manually: `npm run dev -- --host 0.0.0.0
--port 5173 &` and polls until it's up. Locally, developers must run `npm run dev` in a
separate terminal. Document this in the README section.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Token retrieval for E2E | Custom crypto-bypass or DB side-channel | Option D: `EXPOSE_TOKENS_FOR_TESTING` env var on `PublicSignupResponse` |
| Browser install in CI | Manual download step | `npx playwright install --with-deps chromium` (already in CI) |
| Parallel test isolation | Test-level DB cleanup | Ephemeral emails + sufficient slot capacity |
| Seed idempotency | Complex diff logic | "delete and re-create" for mutable state (signups, tokens) |

---

## Architecture Patterns

### Seed script pattern (from existing `seed_e2e.py` `[VERIFIED: direct read]`)

```python
# stdlib urllib only (no extra deps)
# Idempotency: GET first, create only if absent
# Prints single JSON line on last stdout line
# Exit 0 on success, non-zero on fatal error
# global-setup.js reads the JSON via process.env.E2E_SEED
```

The existing pattern is correct and must be preserved. The new script extends it.

### Spec pattern (from existing specs `[VERIFIED: direct read]`)

```js
import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail } from './fixtures.js';

test('describe the flow', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, 'seed required').toBeTruthy();
  // navigate, fill, assert
});
```

For flows that mutate shared state (capacity), use `test.describe.serial`.

### Assertions to prefer:

- `await expect(page).toHaveURL(...)` — route navigation confirmed
- `await expect(page.getByRole(...)).toBeVisible()` — semantic HTML, not CSS selectors
- `await expect(page.getByText(...)).toBeVisible()` — content assertions
- Avoid `page.locator('.class-name')` — too brittle

---

## Validation Architecture

### Test framework

| Property | Value |
|----------|-------|
| Framework | `@playwright/test` v1.59.1 |
| Config file | `playwright.config.js` (repo root) |
| Quick run (local, headed) | `npx playwright test --project=chromium` |
| Full suite | `npx playwright test` |
| Run single spec | `npx playwright test e2e/organizer-checkin.spec.js` |

### Phase Requirements → Test Map

| Req | Behavior | Test type | File |
|-----|----------|-----------|------|
| seed idempotent | Run twice, no errors, known DB state | manual + seed exit code | `seed_e2e.py` itself |
| browse → signup → confirm → manage → cancel | Full public volunteer flow | E2E | `public-volunteer-flow.spec.js` |
| orientation modal fires for period-only + no history | Modal UX | E2E | `orientation-modal.spec.js` (Test A) |
| orientation modal skipped when history exists | Modal UX | E2E | `orientation-modal.spec.js` (Test B) |
| organizer check-in regression | Phase 03 state machine | E2E | `organizer-checkin.spec.js` |
| CI runs Playwright on PRs | CI green | CI gate | `.github/workflows/ci.yml` |

### Wave 0 gaps

- [ ] `e2e/public-volunteer-flow.spec.js` — new spec (replaces stale `student-signup.spec.js`)
- [ ] `e2e/orientation-modal.spec.js` — new spec (replaces stale `magic-link.spec.js`)
- [ ] `e2e/organizer-checkin.spec.js` — rewrite of `organizer-roster.spec.js` to also assert check-in state change
- [ ] `e2e/fixtures.js` — remove `STUDENT`, add `VOLUNTEER_IDENTITY` + `ATTENDED_VOLUNTEER_EMAIL`
- [ ] `backend/tests/fixtures/seed_e2e.py` — rewrite for v1.1 schema
- [ ] `backend/app/schemas.py` — add `confirm_token: str | None = None` to `PublicSignupResponse` (Option D)
- [ ] `backend/app/routers/public/signups.py` — populate `confirm_token` when env var set
- [ ] Delete stale specs: `student-signup.spec.js`, `student-cancel.spec.js`, `magic-link.spec.js`, `signup-three-tap.spec.js`, `a11y.spec.js`, `admin-crud.spec.js`

Note on `a11y.spec.js`: the spec itself is a good pattern, but it references
`/register`, `/my-signups`, `/profile`, student login. It needs a full rewrite for v1.1
routes before it can be useful. Deleting for now and adding back in a follow-on phase
is acceptable.

---

## Open Questions

1. **Check-in endpoint path for the organizer spec**
   - What we know: Phase 03 check-in state machine survives. `backend/app/routers/check_in.py`
     exists.
   - What's unclear: exact endpoint path and expected request body for flipping a signup
     from `confirmed` to `checked_in` or `attended`.
   - Recommendation: Read `check_in.py` at plan time to confirm path before writing the spec.

2. **Portal concept — is it still in the codebase?**
   - What we know: `admin-crud.spec.js` referenced `/admin/portals`. Phase 12 SUMMARY
     deleted `OverridesSection` but did not explicitly mention portals.
   - What's unclear: whether `Portal` model / `portals` router survived Phase 12.
   - Recommendation: `grep -r "portal" backend/app/routers/` at plan time; if portal
     routes still exist, `seed_e2e.py` may still need to attach the event to a portal
     for the organizer to see it.

3. **Signup batch-cancel endpoint**
   - What we know: `ManageSignupsPage` has a "cancel all" button. Phase 11 ROADMAP mentions
     `POST /public/signups/cancel-batch?token=`.
   - What's unclear: was this endpoint implemented in Phase 11, or is cancel-all a
     client-side sequential loop of `DELETE /public/signups/{id}?token=`.
   - Recommendation: Read `ManageSignupsPage.jsx` and `public/signups.py` at plan time
     to determine which approach was used.

4. **`EXPOSE_TOKENS_FOR_TESTING` vs direct DB insert**
   - The decision between Option D and Option C affects one backend task. Both are valid.
   - Recommendation: Planner should lock this decision in Plan 13-01.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Portal model/router still exists in v1.1 after Phase 12 | Seed script design | Seed script fails if it tries to attach event to a non-existent portal route |
| A2 | `POST /public/signups/cancel-batch` was implemented in Phase 11 (not just client-side loop) | Spec 1 design | "cancel all" spec step uses wrong mechanism |
| A3 | Organizer can see all events (not scoped to owner_id) | Spec 3 design | Seeded event created by admin; organizer may not see it in roster |

---

## Sources

### Primary (HIGH confidence — codebase direct reads)
- `playwright.config.js` — Playwright config, baseURL, globalSetup path, browser project
- `e2e/global-setup.js` — seed invocation pattern, JSON contract
- `e2e/fixtures.js` — credentials, getSeed(), ephemeralEmail()
- `e2e/` (all 8 spec files) — full inventory of stale specs
- `backend/tests/fixtures/seed_e2e.py` — current seed implementation and HTTP pattern
- `backend/tests/fixtures/factories.py` — model factories, VolunteerFactory shape
- `backend/app/routers/public/signups.py` — POST /public/signups, confirm, manage, cancel
- `backend/app/routers/public/events.py` — GET /public/events, /current-week
- `backend/app/routers/public/orientation.py` — orientation-status endpoint
- `backend/app/magic_link_service.py` — token issue/consume, hash-only storage confirmed
- `backend/app/schemas.py` — PublicSignupResponse shape (no token in response confirmed)
- `backend/app/models.py` — v1.1 schema: Volunteer, Event (quarter/week), Slot (slot_type), MagicLinkToken
- `backend/app/seed_admin.py` — admin seed pattern
- `.github/workflows/ci.yml` — full E2E job anatomy
- `docker-compose.yml` — stack services, migrate step, env var injection
- `frontend/package.json` — @playwright/test v1.59.1 present
- `package.json` (root) — @playwright/test v1.59.1 present, e2e script
- `.planning/phases/12-retirement-pass/12-SUMMARY.md` — final route inventory, endpoint list, handoff checklist

### Environment checks (HIGH confidence)
- `npx playwright --version` → 1.59.1 installed
- `npx playwright show-browsers` → chromium cached locally, not in node_modules/.bin
- `ls backend/` → no `scripts/` directory; seed lives at `backend/tests/fixtures/seed_e2e.py`

---

## Metadata

**Confidence breakdown:**
- Existing infrastructure: HIGH — all verified by direct file reads
- Token retrieval problem: HIGH — confirmed by reading schemas.py + service code
- CI wiring: HIGH — full ci.yml read
- Spec design: MEDIUM — frontend component internals (form field names, button testids) not fully surveyed; planner should read App.jsx, EventDetailPage.jsx, ManageSignupsPage.jsx before finalizing spec selectors

**Research date:** 2026-04-09
**Valid until:** Stable for this milestone — no external dependencies on moving targets
