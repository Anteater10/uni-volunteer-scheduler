# Testing Patterns

**Analysis Date:** 2026-04-08

## Overview

Testing in this project is **minimal and aspirational**. Only the backend has any test scaffolding at all, and it consists of a single smoke test. The frontend has no test framework installed. This is a significant gap — see `CONCERNS.md` for follow-up.

## Backend Testing

### Framework

- **Runner:** `pytest` 8.2.2 (pinned in `backend/requirements.txt`)
- **Async support:** `pytest-asyncio` 0.23.7 (installed but not yet used)
- **HTTP client for tests:** `httpx` 0.27.2 (available for FastAPI `TestClient` or async client testing)
- **Config:** No `pytest.ini`, `pyproject.toml`, or `conftest.py` detected. Pytest runs with defaults.

### Test Location

- All backend tests live in `backend/tests/`.
- Current contents:
  - `backend/tests/test_smoke.py` — a single placeholder test.

```python
# backend/tests/test_smoke.py
def test_smoke():
    assert True
```

### Naming

- Test files: `test_*.py`
- Test functions: `test_*`
- No test classes currently used.

### Run Commands

From the `backend/` directory (or inside the backend Docker container):

```bash
pytest                          # Run all tests
pytest tests/test_smoke.py      # Run a specific file
pytest -k smoke                 # Run by keyword
pytest -v                       # Verbose
```

No npm / make / compose wrapper exists for running tests — invoke `pytest` directly. There is no CI workflow detected that runs tests automatically.

### Fixtures

- **No `conftest.py` exists yet.** When tests grow, add one at `backend/tests/conftest.py` for shared fixtures (DB session, FastAPI `TestClient`, authenticated user factory).
- There are no factory libraries installed (no `factory_boy`, `faker`).

### Mocking

- No mocking is currently in use. For future tests, `unittest.mock` is the standard library default; `pytest-asyncio` is already available for async route tests.

### What to Test (recommended scope)

Routers in `backend/app/routers/` contain most of the business logic and are the natural target for integration tests using FastAPI's `TestClient`:

- `backend/app/routers/auth.py` — login, registration, token refresh, role claims
- `backend/app/routers/events.py` — event CRUD, date validation helpers (`_validate_event_dates`, `_validate_slot_range_within_event`)
- `backend/app/routers/signups.py` — signup lifecycle, capacity, status transitions
- `backend/app/routers/slots.py` — slot creation and validation against parent event
- `backend/app/routers/admin.py` — admin-only endpoints and audit logging via `log_action`

Pure helper functions in `backend/app/routers/events.py` (`_to_naive_utc`, `_validate_event_dates`) are good unit-test candidates since they have no DB dependency.

### Database for Tests

- App uses PostgreSQL via SQLAlchemy 2.0 (`backend/app/database.py`).
- Alembic manages migrations (`backend/alembic/`, `backend/alembic.ini`).
- No test database setup exists yet. Recommended pattern: a `conftest.py` fixture that creates a SQLite in-memory or ephemeral Postgres schema per test session and overrides the `get_db` dependency via `app.dependency_overrides`.

### Coverage

- No coverage tool installed (`coverage.py`, `pytest-cov` not in `requirements.txt`).
- No coverage thresholds enforced.

## Frontend Testing

### Framework

- **None installed.** `frontend/package.json` has no test runner (no Vitest, Jest, Playwright, Cypress, React Testing Library).
- The only quality gate is ESLint: `npm run lint` (configured in `frontend/eslint.config.js`).
- `frontend/package.json` scripts: `dev`, `build`, `lint`, `preview` — there is no `test` script.

### Run Commands

```bash
cd frontend
npm run lint        # ESLint only — no tests to run
```

### Recommended Setup

Given this is a React 19 + Vite project, the natural additions would be:

- **Unit / component tests:** Vitest + `@testing-library/react` + `@testing-library/jest-dom`
- **E2E tests:** Playwright (preferred for Vite projects)
- **Config location:** Extend `frontend/vite.config.js` with a `test` block for Vitest.

Target files for initial coverage:

- `frontend/src/lib/api.js` — `buildQuery`, `safeReadJson`, `extractErrorMessage` are pure functions and trivial to unit test.
- `frontend/src/lib/datetime.js` — `formatApiDateTimeLocal` date-formatting helper.
- `frontend/src/lib/authStorage.js` — token persistence.
- `frontend/src/components/ProtectedRoute.jsx` — auth-gate logic.
- Page components using React Query (`EventsPage.jsx`, `MySignupsPage.jsx`) — test via `@testing-library/react` with a mocked `api` module or MSW.

## Integration / E2E

- No integration, contract, or E2E testing exists across frontend + backend.
- `docker-compose.yml` at the repo root could be leveraged to spin a full stack for E2E runs.

## CI

- No `.github/workflows/` or other CI configuration detected in the explored tree. Tests are not run automatically on push or PR.

## Summary of Gaps

1. Backend has only a smoke test — zero real coverage of routers, auth, or signup logic.
2. Frontend has no test framework at all.
3. No `conftest.py` or test DB fixtures on the backend.
4. No coverage tooling or thresholds.
5. No CI pipeline to run whatever tests do exist.

Anyone adding tests should start by (a) creating `backend/tests/conftest.py` with a `TestClient` + override-`get_db` fixture, and (b) installing Vitest + React Testing Library on the frontend and adding a `test` npm script.

---

*Testing analysis: 2026-04-08*
