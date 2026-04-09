---
phase: 00-backend-completion-frontend-integration
plan: 07
type: execute
wave: 5
depends_on: [01, 02, 03, 04, 05, 06]
files_modified:
  - e2e/global-setup.js
  - e2e/fixtures.js
  - e2e/student-signup.spec.js
  - e2e/student-cancel.spec.js
  - e2e/organizer-roster.spec.js
  - e2e/admin-crud.spec.js
  - backend/tests/fixtures/seed_e2e.py
  - .github/workflows/ci.yml
  - docker-compose.yml
autonomous: true
requirements:
  - E2E-01
  - E2E-02
  - E2E-03
  - CELERY-01
must_haves:
  truths:
    - "Playwright suite runs 4 flow files end-to-end against docker-compose stack"
    - "Student signup flow: register → browse → sign up → MySignups (no curl)"
    - "Student cancel flow: cancel → slot freed → second student signs up successfully → cancellation Notification row exists"
    - "Organizer roster flow: login → dashboard → view roster"
    - "Admin CRUD flow: login → create/edit/delete user + portal + event"
    - "CI runs pytest + vitest + playwright on every PR and fails on any red"
    - "Playwright trace artifacts upload on failure"
    - "docker-compose beat service uses redbeat scheduler"
  artifacts:
    - path: "e2e/student-signup.spec.js"
      provides: "Flow 1 E2E"
    - path: "e2e/student-cancel.spec.js"
      provides: "Flow 2 E2E with freed-capacity assertion"
    - path: "e2e/organizer-roster.spec.js"
      provides: "Flow 3 E2E"
    - path: "e2e/admin-crud.spec.js"
      provides: "Flow 4 E2E"
    - path: ".github/workflows/ci.yml"
      provides: "Extended job matrix: pytest, vitest, playwright"
    - path: "backend/tests/fixtures/seed_e2e.py"
      provides: "Idempotent HTTP-based fixture seeder callable from Playwright globalSetup"
  key_links:
    - from: "e2e/global-setup.js"
      to: "backend/tests/fixtures/seed_e2e.py"
      via: "spawn python script against running backend"
      pattern: "seed_e2e"
    - from: ".github/workflows/ci.yml"
      to: "playwright test"
      via: "job step"
      pattern: "playwright"
---

<objective>
Stand up the Playwright E2E suite covering the four flows named in ROADMAP success criteria, extend the existing CI workflow to run pytest + vitest + Playwright on every PR with failure gating and trace artifact upload, and finalize the docker-compose stack so beat uses redbeat.

Purpose: This is the phase goal's final check: a human-equivalent script must complete every flow through the browser with no curl. CI must gate PR merges.
Output: 4 passing Playwright specs, CI workflow green on a clean tree, trace uploads on failure, docker-compose beat command updated.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/API-AUDIT.md
@.planning/phases/00-backend-completion-frontend-integration/00-01-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-06-SUMMARY.md
@playwright.config.js
@.github/workflows/ci.yml
@docker-compose.yml
@frontend/src/pages/MySignupsPage.jsx
@frontend/src/pages/OrganizerEventPage.jsx
@frontend/src/pages/LoginPage.jsx
@frontend/src/pages/RegisterPage.jsx
</context>

<tasks>

<task type="auto">
  <name>Task 1: Seed fixture script + Playwright globalSetup + shared fixtures file</name>
  <files>backend/tests/fixtures/seed_e2e.py, e2e/global-setup.js, e2e/fixtures.js</files>
  <read_first>
    - backend/app/routers/auth.py (register/login payload shapes)
    - backend/app/routers/portals.py + events.py + slots.py (admin CRUD shapes)
    - backend/tests/fixtures/factories.py (do NOT reuse — factories are in-process only; research "Pitfall 6: Playwright globalSetup cannot use dependency_overrides")
    - playwright.config.js (from Plan 01)
    - 00-CONTEXT.md "Playwright suite shape" — fixtures requirement
  </read_first>
  <action>
    1. Create `backend/tests/fixtures/seed_e2e.py` — a standalone Python script (NOT a pytest fixture) that makes HTTP calls against `BACKEND_URL=http://localhost:8000` to create an idempotent baseline:
       - admin user: `admin@e2e.test` / `Admin!2345`
       - organizer user: `organizer@e2e.test` / `Organizer!2345`
       - participant user: `student@e2e.test` / `Student!2345`
       - one portal: slug `e2e-portal`
       - one event owned by organizer, attached to portal
       - three slots on that event, start_time = now+25h (outside reminder window), capacity=2 each
       - Idempotency: each create is wrapped in "check existing by unique key first, skip if found"
       - Entry point: `if __name__ == "__main__": sys.exit(main())`
       - Prints a JSON blob to stdout with the created IDs for Playwright to consume: `{"event_id": ..., "slot_ids": [...], "portal_slug": "e2e-portal", "admin_email": ..., ...}`
    2. Create `e2e/global-setup.js`:
       ```js
       import { spawnSync } from 'node:child_process';
       export default async function globalSetup() {
         const res = spawnSync('python', ['backend/tests/fixtures/seed_e2e.py'], {
           env: { ...process.env, BACKEND_URL: process.env.E2E_BACKEND_URL || 'http://localhost:8000' },
           encoding: 'utf-8',
         });
         if (res.status !== 0) {
           console.error('seed_e2e.py failed:', res.stderr);
           throw new Error('E2E seed failed');
         }
         const data = JSON.parse(res.stdout.trim().split('\n').pop());
         process.env.E2E_SEED = JSON.stringify(data);
       }
       ```
       Add `globalSetup: './e2e/global-setup.js'` to `playwright.config.js`.
    3. Create `e2e/fixtures.js` exporting credential constants and a helper to read `E2E_SEED`:
       ```js
       export const ADMIN = { email: 'admin@e2e.test', password: 'Admin!2345' };
       export const ORGANIZER = { email: 'organizer@e2e.test', password: 'Organizer!2345' };
       export const STUDENT = { email: 'student@e2e.test', password: 'Student!2345' };
       export function getSeed() { return JSON.parse(process.env.E2E_SEED || '{}'); }
       ```
  </action>
  <verify>
    <automated>test -f backend/tests/fixtures/seed_e2e.py && test -f e2e/global-setup.js && test -f e2e/fixtures.js && grep -q "globalSetup" playwright.config.js && python -c "import ast; ast.parse(open('backend/tests/fixtures/seed_e2e.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/tests/fixtures/seed_e2e.py` exists and is valid Python (ast.parse succeeds)
    - `grep -q "def main" backend/tests/fixtures/seed_e2e.py` succeeds
    - `grep -q "admin@e2e.test" backend/tests/fixtures/seed_e2e.py` succeeds
    - File `e2e/global-setup.js` exists
    - File `e2e/fixtures.js` exists with `ADMIN`, `ORGANIZER`, `STUDENT` exports
    - `grep -q "globalSetup" playwright.config.js` succeeds
    - `grep -q "ORGANIZER" e2e/fixtures.js` succeeds
  </acceptance_criteria>
  <done>Idempotent seed script runnable standalone; Playwright globalSetup invokes it; fixtures module exports credentials.</done>
</task>

<task type="auto">
  <name>Task 2: Four Playwright spec files — student signup, cancel, organizer roster, admin CRUD</name>
  <files>e2e/student-signup.spec.js, e2e/student-cancel.spec.js, e2e/organizer-roster.spec.js, e2e/admin-crud.spec.js</files>
  <read_first>
    - frontend/src/pages/RegisterPage.jsx (form field names, submit button label)
    - frontend/src/pages/LoginPage.jsx
    - frontend/src/pages/MySignupsPage.jsx (how signups render — list items, cancel button)
    - frontend/src/pages/OrganizerEventPage.jsx (roster table structure)
    - frontend/src/App.jsx (routes)
    - 00-CONTEXT.md specific: "cancel E2E test MUST verify the freed capacity is reusable: a second user signs up into the same slot after the cancel and succeeds"
  </read_first>
  <action>
    Write four Playwright test specs. Prefer semantic selectors (`getByRole`, `getByLabel`, `getByText`) over CSS classes. Use `{ STUDENT, ORGANIZER, ADMIN, getSeed }` from `./fixtures.js`.

    1. `e2e/student-signup.spec.js`:
       ```js
       import { test, expect } from '@playwright/test';
       import { STUDENT, getSeed } from './fixtures';
       test('student can register, sign up, and see MySignups', async ({ page }) => {
         const seed = getSeed();
         // Fresh student per run — generate unique email to avoid seed collision
         const email = `student-${Date.now()}@e2e.test`;
         await page.goto('/register');
         await page.getByLabel(/name/i).fill('Flow One');
         await page.getByLabel(/email/i).fill(email);
         await page.getByLabel(/password/i).fill('Student!2345');
         await page.getByRole('button', { name: /register|sign up/i }).click();
         await expect(page).toHaveURL(/\/(events|dashboard|my)/i);
         await page.goto(`/portals/${seed.portal_slug}`);
         await page.getByRole('link', { name: /view|details/i }).first().click();
         await page.getByRole('button', { name: /sign ?up|reserve/i }).first().click();
         await page.goto('/my-signups');
         await expect(page.getByText(/confirmed/i)).toBeVisible();
       });
       ```
    2. `e2e/student-cancel.spec.js`:
       - Seed has one slot with capacity=2 — sign up TWO ephemeral students (A and B), fill capacity.
       - Log in as student A, navigate to MySignups, click cancel on the signup, confirm modal.
       - Assert the signup is no longer visible (or shows cancelled state).
       - Register a THIRD ephemeral student C and sign up for the SAME slot.
       - Assert C's signup is confirmed (capacity was freed).
       - Poll `/api/v1/admin/notifications` (or an equivalent endpoint accessible to admin — or use a direct DB query via a helper HTTP endpoint if one exists; otherwise skip the Notification assertion and note it in SUMMARY as a manual verification item from 00-VALIDATION.md).
    3. `e2e/organizer-roster.spec.js`:
       - Log in as ORGANIZER.
       - Navigate to organizer dashboard (infer URL from App.jsx).
       - Click into the seeded event.
       - Assert roster section renders (at least the table/list container is visible).
       - Assert at least one signup row is visible (from the cancel spec or a pre-seeded signup).
    4. `e2e/admin-crud.spec.js`:
       - Log in as ADMIN.
       - Navigate to admin users page; create a new user via UI; assert row appears.
       - Edit the new user (change name); assert updated.
       - Delete the new user; assert row gone.
       - Navigate to portals page; create portal; delete portal.
       - Navigate to events page; create event (with minimum required fields); delete event.

    Test independence: each spec assumes seed_e2e baseline but creates its own ephemeral records so specs can run in parallel without interfering. If a flow cannot avoid mutating shared state, use `test.describe.serial`.
  </action>
  <verify>
    <automated>ls e2e/*.spec.js | wc -l | grep -q "^4$" && npx playwright test --list 2>&1 | tee /tmp/pw-list.log && grep -q "student-signup" /tmp/pw-list.log && grep -q "student-cancel" /tmp/pw-list.log && grep -q "organizer-roster" /tmp/pw-list.log && grep -q "admin-crud" /tmp/pw-list.log</automated>
  </verify>
  <acceptance_criteria>
    - Four files exist under `e2e/*.spec.js`: student-signup, student-cancel, organizer-roster, admin-crud
    - `grep -q "getSeed" e2e/student-signup.spec.js` succeeds
    - `grep -q "capacity" e2e/student-cancel.spec.js` OR `grep -q "freed" e2e/student-cancel.spec.js` succeeds (freed-capacity intent encoded)
    - `grep -q "cancel" e2e/student-cancel.spec.js` succeeds
    - `grep -q "ORGANIZER" e2e/organizer-roster.spec.js` succeeds
    - `grep -q "ADMIN" e2e/admin-crud.spec.js` succeeds
    - `grep -cE "await expect" e2e/*.spec.js | awk -F: '{s+=$2} END {exit !(s>=12)}'` (≥ 12 expects across 4 files)
    - `npx playwright test --list` enumerates 4 tests
  </acceptance_criteria>
  <done>Four specs list cleanly; each encodes its flow's critical assertions; cancel spec verifies freed capacity.</done>
</task>

<task type="auto">
  <name>Task 3: Extend CI workflow + update docker-compose beat command</name>
  <files>.github/workflows/ci.yml, docker-compose.yml</files>
  <read_first>
    - .github/workflows/ci.yml (current jobs — DO NOT rewrite; extend)
    - docker-compose.yml (find beat service command)
    - 00-CONTEXT.md "Playwright suite shape" — CI requirement
  </read_first>
  <action>
    1. `docker-compose.yml`: find the `beat` service (or celery beat command). Change its command from the default beat invocation to:
       `celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler`
       Do NOT change the worker service, db service, or backend service beyond this one line.
    2. `.github/workflows/ci.yml`: ADD (do not overwrite) jobs/steps so the workflow runs on every PR and push to main:
       - Job `backend-tests`: sets up Postgres + Redis services, installs Python deps from `backend/requirements.txt`, runs `alembic upgrade head`, runs `pytest` from `backend/` (inherits 70% coverage gate from pytest.ini).
       - Job `frontend-tests`: sets up Node, installs frontend deps, runs `npm run test` (vitest) from `frontend/`.
       - Job `e2e-tests`: `needs: [backend-tests, frontend-tests]`. Spins up the docker-compose stack (`docker compose up -d`), waits for backend health, runs `npx playwright install --with-deps chromium`, runs `npx playwright test`. On failure, uploads `playwright-report/` and `test-results/` as artifacts.
       - Job `critical-path-coverage`: `needs: backend-tests`. Runs `pytest --cov=app --cov-report=json` from `backend/`, then a shell script that parses `coverage.json` and asserts ≥ 90% line coverage for `app/signup_service.py`, `app/routers/signups.py`, `app/celery_app.py`. Fails the workflow if any falls below.
       - All jobs must run on `pull_request` and `push` to `main`. Branch protection/merge gating is a GitHub setting noted in SUMMARY as a manual post-plan step.
    3. Do NOT touch any existing jobs in ci.yml beyond adding the new ones. If the existing workflow already has a `backend-tests` job, rename the new ones with a `phase0-` prefix to avoid collision, and note in SUMMARY.
  </action>
  <verify>
    <automated>grep -q "redbeat.RedBeatScheduler" docker-compose.yml && grep -q "playwright" .github/workflows/ci.yml && grep -q "alembic upgrade head" .github/workflows/ci.yml && grep -q "coverage.json\|--cov-report=json" .github/workflows/ci.yml && grep -q "upload-artifact" .github/workflows/ci.yml && grep -q "signup_service.py" .github/workflows/ci.yml && grep -qE '0\.90|fail-under=90|"90"' .github/workflows/ci.yml</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "redbeat.RedBeatScheduler" docker-compose.yml` succeeds
    - `grep -q "playwright test\|playwright" .github/workflows/ci.yml` succeeds
    - `grep -q "pytest" .github/workflows/ci.yml` succeeds
    - `grep -q "vitest\|npm run test" .github/workflows/ci.yml` succeeds
    - `grep -q "alembic upgrade" .github/workflows/ci.yml` succeeds
    - `grep -q "upload-artifact" .github/workflows/ci.yml` succeeds (trace uploads on failure)
    - `grep -qE 'signup_service.*(90|0\.90)|(90|0\.90).*signup_service|cov.*fail.*90|fail-under.*90' .github/workflows/ci.yml` succeeds (actual 0.90 threshold literal must appear alongside signup_service or a cov fail-under directive)
    - `grep -q "signup_service.py" .github/workflows/ci.yml` succeeds (critical path file named)
    - `grep -qE '0\.90|"90"|fail-under=90|>= 90' .github/workflows/ci.yml` succeeds (90% threshold literal present)
    - `grep -q "pull_request" .github/workflows/ci.yml` succeeds
  </acceptance_criteria>
  <done>CI runs all three test layers on PR; docker-compose beat uses redbeat; failure gates merges.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CI runner → docker-compose stack | Ephemeral; no prod secrets loaded |
| seed_e2e.py → running backend | HTTP-only, uses dev credentials from env |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-26 | Repudiation | PRs merging with broken E2E flows | mitigate | CI workflow gates on Playwright failure; trace artifacts uploaded for post-mortem |
| T-00-27 | Information Disclosure | Seed credentials hardcoded in fixtures | accept | Dev-only credentials, never run against prod; documented in SUMMARY |
| T-00-28 | Denial of Service | Playwright test parallelism flooding dev DB | accept | Playwright `fullyParallel: true` bounded by worker count; ephemeral docker-compose stack |
| T-00-29 | Tampering | seed_e2e.py not idempotent could leave residual state | mitigate | Each create checks-before-insert; idempotent by unique key (email, slug) |
| T-00-30 | Denial of Service | Redbeat requiring Redis — beat crash on Redis loss | accept | Research documented the single-Redis assumption; Phase 8 infra deploy adds Redis HA |
</threat_model>

<verification>
- `npx playwright test --list` enumerates 4 tests
- `grep -q "redbeat.RedBeatScheduler" docker-compose.yml` succeeds
- CI workflow contains pytest, vitest, and playwright steps with artifact upload
- 90% critical-path coverage gate present
</verification>

<success_criteria>
Phase 0 closes: 4 Playwright flows executable, CI gates PR merges, docker-compose beat uses redbeat, critical-path coverage enforced. A human can sign up, cancel, organize, and admin entirely through the browser — no curl.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-07-SUMMARY.md`
</output>
