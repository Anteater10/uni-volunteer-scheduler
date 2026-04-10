---
phase: 00-backend-completion-frontend-integration
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - backend/pytest.ini
  - backend/conftest.py
  - backend/tests/__init__.py
  - backend/tests/fixtures/__init__.py
  - backend/tests/fixtures/factories.py
  - backend/tests/test_harness_smoke.py
  - backend/requirements.txt
  - frontend/package.json
  - frontend/vitest.config.js
  - frontend/src/test/setup.js
  - frontend/src/lib/__tests__/api.test.js
  - playwright.config.js
  - e2e/.gitkeep
  - frontend/src/lib/api.js
  - backend/app/main.py
  - .planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md
autonomous: true
requirements:
  - AUDIT-01
  - TEST-01
  - E2E-01
  - OPEN-01
must_haves:
  truths:
    - "pytest --collect-only succeeds with real conftest + Postgres fixture"
    - "vitest run succeeds with at least one passing component/module test"
    - "npx playwright test --list enumerates zero flows without erroring"
    - "API-AUDIT.md exists covering every lib/api.js function with status column"
    - "createSignup, updateEvent, updateEventQuestion, deleteEventQuestion, listEventSignups no longer 404 against running backend"
    - "main.py reads CORS origins from settings and slowapi middleware is removed"
  artifacts:
    - path: "backend/conftest.py"
      provides: "pytest-django + TestClient + db_session + factory fixtures"
    - path: "backend/pytest.ini"
      provides: "pytest config with testpaths, addopts"
    - path: "frontend/vitest.config.js"
      provides: "vitest config with jsdom env"
    - path: "playwright.config.js"
      provides: "Playwright config with retries=2 on CI"
    - path: ".planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md"
      provides: "Written punch list covering every api.js function"
  key_links:
    - from: "frontend/src/lib/api.js::createSignup"
      to: "backend router POST /signups/"
      via: "trailing-slash normalized path"
      pattern: "'/signups/'"
    - from: "frontend/src/lib/api.js::updateEvent"
      to: "backend router PUT /events/{id}"
      via: "HTTP method PUT (not PATCH)"
      pattern: "method:\\s*['\"]PUT['\"]"
    - from: "frontend/src/lib/api.js::updateEventQuestion"
      to: "backend router /events/questions/{id}"
      via: "corrected path"
      pattern: "'/events/questions/"
---

<objective>
Bootstrap the test harness (pytest, vitest, Playwright), produce the complete `lib/api.js` vs backend router audit punch list, fix the four confirmed runtime 404s in `api.js`, and complete opportunistic cleanups (CORS from settings, remove dead slowapi middleware).

Purpose: Every subsequent plan in Phase 0 needs a working test harness and a correct frontend↔backend API surface. This plan creates the foundation.
Output: Running test harness (collect-only succeeds on all three frameworks), committed API-AUDIT.md punch list, patched api.js with zero known runtime 404s, cleaner main.py.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/00-VALIDATION.md
@.planning/codebase/ARCHITECTURE.md
@.planning/codebase/TESTING.md
@.planning/codebase/CONVENTIONS.md
@backend/app/main.py
@backend/app/routers/signups.py
@backend/app/routers/events.py
@backend/app/routers/slots.py
@backend/app/routers/auth.py
@backend/app/routers/users.py
@backend/app/routers/admin.py
@backend/app/routers/portals.py
@backend/app/routers/notifications.py
@frontend/src/lib/api.js
@frontend/package.json
@backend/requirements.txt

<interfaces>
Research confirmed 4 runtime 404/mismatch targets in api.js (see 00-RESEARCH.md "API Contract Audit (Full Punch List)" table). The backend routers listed above are the source of truth for URLs and HTTP methods. Notifications, portals, and admin routers have NOT been fully verified by research — Task 2 MUST read them to finalize the audit.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Bootstrap backend + frontend + Playwright test harness</name>
  <files>backend/pytest.ini, backend/conftest.py, backend/tests/__init__.py, backend/tests/fixtures/__init__.py, backend/tests/fixtures/factories.py, backend/tests/test_harness_smoke.py, backend/requirements.txt, frontend/package.json, frontend/vitest.config.js, frontend/src/test/setup.js, frontend/src/lib/__tests__/api.test.js, playwright.config.js, e2e/.gitkeep</files>
  <read_first>
    - backend/requirements.txt (current pinned versions)
    - backend/tests/test_smoke.py (existing placeholder — will be superseded)
    - backend/app/database.py (SessionLocal, engine imports)
    - backend/app/models.py (User, Event, Portal, Slot, Signup — for factory-boy definitions)
    - frontend/package.json (existing scripts and devDeps)
    - frontend/vite.config.js (alias + plugin config to mirror in vitest config)
    - .github/workflows/ci.yml (existing — DO NOT overwrite; this plan does not modify CI, Plan 07 does)
    - 00-RESEARCH.md sections "Standard Stack", "conftest.py pattern" (around line 294–345)
  </read_first>
  <action>
    Install and wire three test frameworks. Do NOT run the suites end-to-end — just make `--collect-only` / `--list` succeed.

    Backend:
    1. Append to `backend/requirements.txt` (keep alpha order if file uses it; otherwise append):
       ```
       pytest==8.3.3
       pytest-cov==7.1.0
       factory-boy==3.3.3
       freezegun==1.5.5
       httpx==0.27.2
       ```
       (pytest-django NOT required — this project is FastAPI, not Django. 00-VALIDATION.md is wrong on this; use plain pytest + TestClient. Note in API-AUDIT.md under "corrections".)
    2. Create `backend/pytest.ini`:
       ```
       [pytest]
       testpaths = tests
       addopts = -ra --strict-markers --tb=short
       markers =
           integration: integration tests hitting the real Postgres via TestClient
           unit: fast unit tests with no I/O
       ```
    3. Create `backend/conftest.py` with these fixtures (session-scoped engine using `TEST_DATABASE_URL` env var, function-scoped `db_session` with transactional rollback, function-scoped `client` wrapping `TestClient(app)` with `get_db` dependency override):
       ```python
       import os
       import pytest
       from fastapi.testclient import TestClient
       from sqlalchemy import create_engine
       from sqlalchemy.orm import sessionmaker
       from app.main import app
       from app.database import Base, get_db

       TEST_DATABASE_URL = os.environ.get(
           "TEST_DATABASE_URL",
           "postgresql+psycopg2://postgres:postgres@localhost:5432/test_uvs",
       )

       @pytest.fixture(scope="session")
       def engine():
           eng = create_engine(TEST_DATABASE_URL, future=True)
           Base.metadata.create_all(eng)
           yield eng
           Base.metadata.drop_all(eng)

       @pytest.fixture
       def db_session(engine):
           connection = engine.connect()
           trans = connection.begin()
           Session = sessionmaker(bind=connection, expire_on_commit=False)
           session = Session()
           try:
               yield session
           finally:
               session.close()
               trans.rollback()
               connection.close()

       @pytest.fixture
       def client(db_session):
           def override_get_db():
               try:
                   yield db_session
               finally:
                   pass
           app.dependency_overrides[get_db] = override_get_db
           with TestClient(app) as c:
               yield c
           app.dependency_overrides.clear()
       ```
    4. Create `backend/tests/__init__.py` (empty), `backend/tests/fixtures/__init__.py` (empty), and `backend/tests/fixtures/factories.py` with factory-boy factories for `User`, `Portal`, `Event`, `Slot`, `Signup` matching current `models.py` columns. Use `SQLAlchemyModelFactory` with `sqlalchemy_session_persistence = "flush"`.
    5. Create `backend/tests/test_harness_smoke.py`:
       ```python
       def test_harness_collects(client):
           r = client.get("/api/v1/health")
           assert r.status_code in (200, 404)  # route may not exist yet; collection is what we verify
       ```
    6. Delete `backend/tests/test_smoke.py` if it only contains `assert True`. Otherwise leave and note in API-AUDIT.md.

    Frontend:
    7. `cd frontend && npm install --save-dev vitest@2.1.2 @vitest/ui@2.1.2 jsdom@25.0.1 @testing-library/react@16.0.1 @testing-library/jest-dom@6.5.0 @playwright/test@1.59.1` — commit resulting `package.json` and `package-lock.json`.
    8. Create `frontend/vitest.config.js` (mirrors `vite.config.js` plugins/aliases, sets `test: { environment: 'jsdom', setupFiles: ['./src/test/setup.js'], globals: true }`).
    9. Create `frontend/src/test/setup.js` with `import '@testing-library/jest-dom'`.
    10. Create `frontend/src/lib/__tests__/api.test.js` with ONE placeholder test that imports `api` and asserts `typeof api.createSignup === 'function'`.
    11. Add to `frontend/package.json` scripts: `"test": "vitest run"`, `"test:watch": "vitest"`, `"e2e": "playwright test"`, `"e2e:install": "playwright install chromium"`.

    Playwright:
    12. Create `playwright.config.js` at repo root:
       ```js
       import { defineConfig, devices } from '@playwright/test';
       export default defineConfig({
         testDir: './e2e',
         fullyParallel: true,
         forbidOnly: !!process.env.CI,
         retries: process.env.CI ? 2 : 0,
         reporter: process.env.CI ? [['html'], ['github']] : 'list',
         use: {
           baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
           trace: 'on-first-retry',
           video: 'retain-on-failure',
         },
         projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
       });
       ```
    13. Create `e2e/.gitkeep`.
  </action>
  <verify>
    <automated>cd backend && python -m pytest --collect-only 2>&1 | tee /tmp/pytest-collect.log && grep -q "test_harness_collects" /tmp/pytest-collect.log && cd ../frontend && npx vitest run --reporter=basic 2>&1 | tee /tmp/vitest.log && grep -q "1 passed" /tmp/vitest.log && cd .. && npx playwright test --list 2>&1 | tee /tmp/pw.log && grep -qi "0 test\|no tests" /tmp/pw.log</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/pytest.ini` exists and contains `testpaths = tests`
    - File `backend/conftest.py` exists and contains `def client` and `def db_session`
    - File `backend/tests/fixtures/factories.py` exists and contains `class UserFactory`
    - `grep -q "pytest==" backend/requirements.txt` succeeds
    - `grep -q "factory-boy==3.3.3" backend/requirements.txt` succeeds
    - File `frontend/vitest.config.js` exists and contains `environment: 'jsdom'`
    - `grep -q '"@playwright/test"' frontend/package.json` succeeds
    - File `playwright.config.js` exists and contains `testDir: './e2e'`
    - File `e2e/.gitkeep` exists
    - `cd backend && python -m pytest --collect-only` exits 0
    - `cd frontend && npx vitest run` exits 0 with at least 1 passing test
  </acceptance_criteria>
  <done>Three test harnesses collect/list successfully; factories defined for all five core models; no real tests yet (those land in Plan 06/07).</done>
</task>

<task type="auto">
  <name>Task 2: Produce full API-AUDIT.md punch list and fix the four confirmed runtime 404s</name>
  <files>.planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md, frontend/src/lib/api.js</files>
  <read_first>
    - frontend/src/lib/api.js (every exported function — full file)
    - backend/app/routers/auth.py, users.py, events.py, slots.py, signups.py, portals.py, notifications.py, admin.py (full files — especially routers not verified in research: portals, notifications, admin)
    - backend/app/main.py (router mount prefixes)
    - frontend/src/pages/OrganizerEventPage.jsx (grep for `listEventSignups` call sites to decide fix strategy)
    - 00-RESEARCH.md "API Contract Audit (Full Punch List)" section (lines ~136–190)
  </read_first>
  <action>
    1. Read every router in `backend/app/routers/` and build a ground-truth table: `(router_prefix, method, path, handler_name, include_in_schema)`.
    2. Read every exported function in `frontend/src/lib/api.js` and record `(name, method, path, known_callers)`.
    3. Cross-reference. Create `.planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md` with this exact structure:
       ```markdown
       # API Contract Audit — Phase 0

       **Generated:** {date}
       **Scope:** frontend/src/lib/api.js ↔ backend/app/routers/*
       **Status:** Complete

       ## Summary
       | Total functions | Matches | Mismatches fixed | Deferred |
       |---|---|---|---|

       ## Punch List
       | # | Frontend fn | FE method | FE path | BE method | BE path | Status | Action |
       |---|---|---|---|---|---|---|---|
       | 1 | login | POST | /auth/token | POST | /auth/token | ✅ match | — |
       | 2 | createSignup | POST | /signups | POST | /signups/ | ❌ trailing slash | FIXED → /signups/ |
       | ... | (one row for EVERY api.js function) |

       ## Fixes Applied (this PR)
       1. createSignup: `/signups` → `/signups/` (line X of api.js)
       2. updateEvent: method PATCH → PUT (line X)
       3. updateEventQuestion: `/event-questions/{id}` → `/events/questions/{id}` (line X)
       4. deleteEventQuestion: `/event-questions/{id}` → `/events/questions/{id}` (line X)
       5. listEventSignups: {chosen fix — either added backend endpoint tracked as follow-up, OR rewired to `/admin/events/{eventId}/roster`}

       ## Deferred / Follow-Up
       (any mismatch that requires a backend change — file as a TODO referencing this audit)

       ## Corrections to 00-VALIDATION.md / 00-RESEARCH.md
       - pytest-django is NOT required; project uses FastAPI TestClient.
       - {any other corrections discovered}

       ## Open-Question Gate Resolution
       - SignupStatus.registered: NOT in current enum. Deferred to Phase 3 per research recommendation (Option B). Phase 0 uses `confirmed` as post-signup status.
       ```
    4. Apply the 4 confirmed fixes to `frontend/src/lib/api.js`:
       - `createSignup`: change URL to `'/signups/'` (keep trailing slash).
       - `updateEvent`: change method string from `'PATCH'` to `'PUT'`.
       - `updateEventQuestion`: change URL template to `/events/questions/${questionId}`.
       - `deleteEventQuestion`: change URL template to `/events/questions/${questionId}`.
       - `listEventSignups`: DECIDE — if a backend endpoint exists (check admin router for `/admin/events/{eventId}/roster` or similar), rewire the call. Otherwise add a TODO comment above the function `// TODO(phase0): backend endpoint missing — tracked in API-AUDIT.md` and leave the function (Plan 06 will add the backend route or Plan 05 will). Document the choice in API-AUDIT.md.
    5. If any OTHER mismatch is discovered during the full audit (expected), fix it in this task if it is a pure frontend path/method correction. If it requires backend changes, list it in "Deferred / Follow-Up" — Plan 05 (refactor) or Plan 06 (tests) picks it up.
  </action>
  <verify>
    <automated>test -f .planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md && grep -q "Punch List" .planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md && grep -q "'/signups/'" frontend/src/lib/api.js && grep -q "'/events/questions/" frontend/src/lib/api.js && ! grep -qE "method:\s*['\"]PATCH['\"].*updateEvent|updateEvent.*method:\s*['\"]PATCH['\"]" frontend/src/lib/api.js</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md` exists
    - `grep -c "^| [0-9]" API-AUDIT.md` returns ≥ 25 (one row per api.js function; current count ~30)
    - `grep -q "'/signups/'" frontend/src/lib/api.js` succeeds
    - `grep -q "'/events/questions/" frontend/src/lib/api.js` succeeds
    - `grep -q "'/event-questions/" frontend/src/lib/api.js` fails (old path removed)
    - `grep -q "SignupStatus.registered" API-AUDIT.md` succeeds (open-question resolution documented)
    - Every api.js function appears in the punch list table (verify: count exported functions in api.js === count of rows in table)
  </acceptance_criteria>
  <done>Complete audit document committed; all 4 confirmed 404s fixed; open question resolved in writing; any newly discovered issues logged.</done>
</task>

<task type="auto">
  <name>Task 3: Clean up main.py — CORS from settings, remove dead slowapi middleware</name>
  <files>backend/app/main.py</files>
  <read_first>
    - backend/app/main.py (full file — especially CORS middleware block and slowapi imports)
    - backend/app/config.py or settings.py (find where `settings` is defined and whether it already has a `cors_allowed_origins` field; add it if missing, reading from env var `CORS_ALLOWED_ORIGINS` as comma-separated)
    - 00-CONTEXT.md "Tech-debt cleanups" bullets
  </read_first>
  <action>
    1. In `backend/app/config.py` (or wherever `Settings` is defined), add a field:
       ```python
       cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000"

       @property
       def cors_origins_list(self) -> list[str]:
           return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
       ```
    2. In `backend/app/main.py`:
       - Replace the hardcoded CORS origins list (and the `# TODO` around line 30) with `allow_origins=settings.cors_origins_list`.
       - Remove ALL slowapi imports, the `Limiter` instance, the `SlowAPIMiddleware` `add_middleware` call, and the `app.state.limiter = limiter` line. The custom Redis rate limiter in `deps.py` is the real one (confirmed by research).
       - Do NOT touch any other middleware or router mounts in this task.
    3. Leave a one-line comment above the CORS middleware: `# CORS origins loaded from settings.cors_allowed_origins env var`.
  </action>
  <verify>
    <automated>cd backend && python -c "from app.main import app; print('ok')" && ! grep -q "slowapi" backend/app/main.py && grep -q "settings.cors_origins_list" backend/app/main.py && grep -q "cors_allowed_origins" backend/app/config.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "slowapi" backend/app/main.py` returns non-zero (no matches)
    - `grep -q "settings.cors_origins_list" backend/app/main.py` succeeds
    - `grep -q "cors_allowed_origins" backend/app/config.py` succeeds (or settings.py — adjust to actual path)
    - `python -c "from app.main import app"` from `backend/` exits 0
    - `grep -q "# TODO" backend/app/main.py` around the old CORS line returns non-zero (TODO removed)
  </acceptance_criteria>
  <done>main.py imports cleanly; no slowapi references anywhere in main.py; CORS origins driven by env var; TODO comment removed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → api.js → FastAPI | Untrusted user input crosses via fetch; this plan does not change validation, only paths/methods |
| CI runner → test Postgres | Test harness creates/drops tables; must not touch prod |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-01 | Tampering | frontend/src/lib/api.js path rewrites | mitigate | All path changes cross-referenced to backend routers in API-AUDIT.md; Plan 06 pytest integration tests lock the contract |
| T-00-02 | Information Disclosure | CORS wildcard via env var misconfiguration | mitigate | Default in `config.py` is localhost only; production deploy (Phase 8) must set `CORS_ALLOWED_ORIGINS` explicitly — documented in API-AUDIT.md |
| T-00-03 | Denial of Service | Removing slowapi leaves only custom Redis limiter | accept | Research confirmed slowapi was never active (middleware dead code); custom limiter in deps.py is the real enforcement point. No regression. |
| T-00-04 | Repudiation | Test harness can run against prod DB if TEST_DATABASE_URL unset | mitigate | conftest.py defaults to `test_uvs` database, never prod; verified by default value in engine fixture |
</threat_model>

<verification>
- `cd backend && python -m pytest --collect-only` exits 0
- `cd frontend && npx vitest run` exits 0
- `npx playwright test --list` exits 0
- `API-AUDIT.md` committed with complete punch list
- `grep -q "'/signups/'" frontend/src/lib/api.js` succeeds
- `python -c "from app.main import app"` from `backend/` exits 0
</verification>

<success_criteria>
Plan complete when all three test harnesses collect successfully, API-AUDIT.md exists with complete punch list and open-question resolution, the four runtime 404s are fixed in api.js, and main.py is free of slowapi dead code with CORS origins loaded from settings.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-01-SUMMARY.md`
</output>
