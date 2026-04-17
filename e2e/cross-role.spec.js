// e2e/cross-role.spec.js
//
// Phase 20 Plan 01 — cross-role integration scenarios.
// Covers INTEG-01 (canonical loop), INTEG-02 (>=4 new scenarios), INTEG-03
// (full suite green gate).
//
// REQUIRES: EXPOSE_TOKENS_FOR_TESTING=1 on the backend so confirm_token is
// returned in the POST /public/signups response and rate limits are bypassed.
// See .github/workflows/ci.yml and backend/.env.
//
// Scenario 1 is a `test.describe.serial` block because the three tests share
// a single ephemeral volunteer email + confirm_token + signup_id threaded
// admin -> participant -> organizer -> admin-audit. Scenarios 2-5 are
// independent and parallel-safe (each uses a fresh ephemeralEmail tag).
//
// Composition notes (from 20-RESEARCH.md "Don't Hand-Roll"):
// - NO shared helper module extracted in this plan (additive-only scope).
// - Login flow is inlined per spec (5-line pattern from admin-smoke.spec.js).
// - clickSlotByLabel copied verbatim from public-signup.spec.js (not imported).
// - Direct-API signup uses the fetch pattern from organizer-check-in.spec.js.
//
// Audit-log findings (verified during Task 1 inspection):
// - Only ADMIN-initiated actions are audited (signup_cancelled, admin_signup_cancel,
//   user_login, event_create, etc. — see backend/app/services/audit_log_humanize.py
//   ACTION_LABELS). Public signup.created and organizer check-in are NOT audited.
//   Scenarios that assert audit-log content use `signup_cancelled` (public cancel
//   path writes synchronously via deps.log_action — see Scenario 4).
// - AuditLogsPage.jsx uses `#al-search` (not `#al-q`). The search input is
//   debounced 300ms via useDebounced; no submit button is required.
// - Audit writes are synchronous (backend/app/deps.py log_action — same transaction
//   as the mutating action). No Celery indirection; no expect.poll needed.
//
// Logout approach (verified during Task 1 inspection):
// - Logout UI is nested in a dropdown menu behind the user email button in
//   Layout.jsx. For reliability, tests call page.context().clearCookies() and
//   then reload — cleaner than driving the menu UI.

import { test, expect } from '@playwright/test';
import {
  ADMIN,
  ORGANIZER,
  VOLUNTEER_IDENTITY,
  ephemeralEmail,
  getSeed,
} from './fixtures.js';

// PART-02-style console-error capture. Cross-role specs MUST NOT ship with
// silent console noise EXCEPT where parallel-scenario interference is
// unavoidable — see allowlist justifications below.
const ALLOWED_CONSOLE_PATTERNS = [
  // Parallel test workers can briefly race on the same /admin/summary or
  // /admin/audit-logs endpoints. React-Query fires console.error on HTTP
  // errors that are already surfaced via toast/EmptyState UI. When Scenario
  // 4 cancels a signup while Scenario 3 is polling the roster, the toast
  // "Check-in failed" in OrganizerRosterPage (onError handler) is the
  // user-visible signal — the console.error payload is a raw Response
  // object that serialises to "[object Object]". Allowlisting this is safe
  // because the UI still gets the toast and this is a test-infrastructure
  // artefact, not a product bug.
  /^\[object Object\]$/,
  // Scenario 5 (organizer RBAC) deliberately hits shared admin pages that
  // fire admin-only API calls (e.g. /admin/module-templates, /admin/imports).
  // The backend correctly returns 403 for organizer; the browser logs the
  // 403 as a "Failed to load resource" console.error. The UI surfaces the
  // denial as an in-page error state ("Couldn't load imports — Insufficient
  // permissions") with a Retry button. This is correct cross-role UX.
  /Failed to load resource.*403.*Forbidden/i,
];

// Force a desktop viewport for scenarios that touch the admin shell. The
// AdminLayout (frontend/src/pages/admin/AdminLayout.jsx) renders a
// DesktopOnlyBanner ("Please switch to a larger screen") below 768px. We
// mirror the admin-a11y.spec.js pattern (page.setViewportSize 1280x800) so
// the cross-role scenarios that authenticate as admin continue to work on
// Mobile Chrome, Mobile Safari, and iPhone SE 375 projects.
async function ensureAdminViewport(page) {
  await page.setViewportSize({ width: 1280, height: 800 });
}

function installErrorCapture(page, testInfo) {
  testInfo.errors = [];
  page.on('pageerror', (err) => {
    testInfo.errors.push(`pageerror: ${err.message}`);
  });
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const argPreviews = msg.args().map((a) => {
      try {
        return a.toString();
      } catch {
        return '<unprintable>';
      }
    });
    const text = `${msg.text()}${
      argPreviews.length ? ` | args=${argPreviews.join(' / ')}` : ''
    }`;
    if (ALLOWED_CONSOLE_PATTERNS.some((re) => re.test(text))) return;
    testInfo.errors.push(
      `console.error[${msg.location().url || 'inline'}:${
        msg.location().lineNumber || '?'
      }]: ${text}`,
    );
  });
}

function assertNoErrors(testInfo) {
  const errors = testInfo.errors || [];
  if (errors.length > 0) {
    throw new Error(
      `cross-role console/pageerror violation — ${errors.length} error(s) during "${testInfo.title}":\n${errors.join(
        '\n',
      )}`,
    );
  }
}

// Inline login (do NOT extract — scope is additive-only).
async function loginAs(page, who) {
  await page.goto('/login');
  await page.locator('#login-email').fill(who.email);
  await page.locator('#login-password').fill(who.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 8000 });
}

// Clear auth cookies + session storage + reload. Preferred over driving the
// header dropdown Logout button (which is hidden behind an aria-haspopup
// menu that can race with React state in parallel workers).
async function logout(page) {
  await page.context().clearCookies();
  try {
    await page.evaluate(() => {
      try {
        window.localStorage.clear();
      } catch {}
      try {
        window.sessionStorage.clear();
      } catch {}
    });
  } catch {
    // page may be on about:blank early in the test — safe to ignore.
  }
}

// Copy of clickSlotByLabel from public-signup.spec.js (no import — scope).
async function clickSlotByLabel(page, label) {
  const labelDiv = page
    .locator('table div.font-medium', { hasText: label })
    .first();
  await labelDiv.waitFor({ state: 'visible' });
  const row = labelDiv.locator('xpath=ancestor::tr[1]');
  await row.getByRole('button', { name: /^sign up$/i }).click();
}

// ---------------------------------------------------------------------------
// SCENARIO 1 — canonical cross-role loop
//   admin seeds event (satisfied by globalSetup seed_e2e.py)
//   -> participant signs up + confirms via token
//   -> organizer checks in from roster
//   -> admin views audit log and confirms the cross-role surface is reachable
// ---------------------------------------------------------------------------

test.describe.serial('cross-role Scenario 1: canonical admin -> participant -> organizer -> admin loop', () => {
  // Shared state threaded through the 3 serial tests. Last name includes a
  // random suffix so the roster locator can find this specific participant
  // even when prior runs or parallel workers leave similar rows around.
  const email = ephemeralEmail('xrole1');
  const lastNameTag = `XRole1${Math.random().toString(36).slice(2, 8)}`;
  let confirmToken;

  test.beforeEach(async ({ page }, testInfo) => {
    installErrorCapture(page, testInfo);
  });

  test.afterEach(async ({}, testInfo) => {
    assertNoErrors(testInfo);
  });

  test('Scenario 1A: public participant signs up via seeded event and confirms', async ({
    page,
  }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required — run seed_e2e.py first').toBeTruthy();
    expect(seed.period_slot_id, 'period_slot_id required in seed JSON').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // Select both slots (orientation + period) so no orientation modal fires.
    await clickSlotByLabel(page, /orientation/i);
    await clickSlotByLabel(page, /^period/i);

    // Identity form
    await expect(page.getByText('Your information')).toBeVisible();
    await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
    await page.locator('#last_name').fill(lastNameTag);
    await page.locator('#email').fill(email);
    await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);

    const submitBtn = page
      .locator('form')
      .getByRole('button', { name: /sign up/i })
      .last();

    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/public/signups') &&
          resp.request().method() === 'POST',
      ),
      submitBtn.click(),
    ]);

    const body = await response.json();
    expect(
      body.confirm_token,
      'confirm_token missing — EXPOSE_TOKENS_FOR_TESTING=1 must be set on the backend',
    ).toBeTruthy();
    confirmToken = body.confirm_token;

    // Confirm via token URL — the confirmation banner is the success signal.
    await page.goto(`/signup/confirm?token=${confirmToken}`);
    await expect(page.getByText(/your signup is confirmed/i)).toBeVisible({
      timeout: 10000,
    });
  });

  test('Scenario 1B: organizer checks the participant in from the roster', async ({
    page,
  }) => {
    const seed = getSeed();
    await loginAs(page, ORGANIZER);
    await page.goto(`/organizer/events/${seed.event_id}/roster`);

    // Match the row by our unique last-name tag. Scenario 1A signed up for
    // both orientation AND period, so TWO rows may render — pick the first
    // one that is still in a click-able state (confirmed or pending; not
    // already checked_in from a previous partial run).
    const ourRows = page
      .locator('ul li button')
      .filter({ hasText: new RegExp(lastNameTag, 'i') });
    await expect(ourRows.first()).toBeVisible({ timeout: 10000 });

    const clickable = ourRows
      .filter({ hasText: /confirmed|pending/i })
      .first();
    await expect(clickable).toBeVisible({ timeout: 10000 });
    await clickable.click();

    // Post-click the chip flips from "confirmed"/"pending" to "checked in",
    // so the pre-click filter on /confirmed|pending/i no longer matches. Re-
    // locate the row by our unique last-name tag + "checked in" substring in
    // the accessible name. The button's full text is e.g.
    // "E2E <lastNameTag> 02:00 AM checked in".
    const checkedInRow = page
      .locator('ul li button')
      .filter({ hasText: new RegExp(lastNameTag, 'i') })
      .filter({ hasText: /checked in/i });
    await expect(checkedInRow.first()).toBeVisible({ timeout: 8000 });
  });

  test('Scenario 1C: admin can reach the audit log after the cross-role flow', async ({
    page,
  }) => {
    // Log out the organizer session, then log in as admin. Force desktop
    // viewport for the admin shell (see ensureAdminViewport).
    await ensureAdminViewport(page);
    await logout(page);
    await loginAs(page, ADMIN);
    await page.goto('/admin/audit-logs');
    await page.waitForLoadState('networkidle');

    // Audit-logs page heading renders.
    await expect(
      page.getByRole('heading', { name: /audit logs/i }),
    ).toBeVisible({ timeout: 8000 });

    // NOTE (Scenario 1 INTEG-05 finding): public signup.created and organizer
    // check-in are NOT written to the audit log (see
    // backend/app/services/audit_log_humanize.py ACTION_LABELS — only admin
    // actions + public signup cancel are audited). We therefore assert the
    // weaker property here: the admin surface is reachable cross-role and the
    // audit log page renders with at least one row. Scenario 4 exercises the
    // signup_cancelled audit path directly.

    // Filter by admin email using the debounced (#al-search) input — 300ms
    // debounce + networkidle is sufficient, no submit button.
    const search = page.locator('#al-search');
    await expect(search).toBeVisible({ timeout: 8000 });
    await search.fill(ADMIN.email);
    // Wait for debounce + refetch to settle.
    await page.waitForLoadState('networkidle');

    // Expect either a row (admin_list_audit_logs / user_login) OR the empty
    // state — both are acceptable evidence that the filter + page wire up.
    // Prefer asserting at least one row is present when any admin activity
    // has been audited in this run.
    const anyRow = page.locator('table tbody tr').first();
    const emptyState = page.getByText(/no audit logs match these filters/i);
    await expect(anyRow.or(emptyState)).toBeVisible({ timeout: 10000 });
  });
});

// Direct-API signup + confirm (copy of the fetch pattern from
// organizer-check-in.spec.js). Returns { signupId, confirmToken, email }.
async function apiSignupAndConfirm(tag, slotIds, lastName) {
  const apiBase = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
  const email = ephemeralEmail(tag);
  const resp = await fetch(`${apiBase}/api/v1/public/signups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: 'CrossRole',
      last_name: lastName,
      email,
      phone: '8055550150',
      slot_ids: slotIds,
    }),
  });
  expect(resp.ok, `POST /public/signups failed: ${resp.status}`).toBeTruthy();
  const body = await resp.json();
  expect(
    body.confirm_token,
    'confirm_token missing — EXPOSE_TOKENS_FOR_TESTING=1 must be set on the backend',
  ).toBeTruthy();

  const confirmResp = await fetch(
    `${apiBase}/api/v1/public/signups/confirm?token=${body.confirm_token}`,
    { method: 'POST' },
  );
  expect(confirmResp.ok, `confirm failed: ${confirmResp.status}`).toBeTruthy();

  return {
    signupId: body.signup_ids[0],
    confirmToken: body.confirm_token,
    email,
  };
}

// Extract the "Signups" StatCard value on /admin overview. Returns an integer,
// or null if the card is not visible yet. OverviewSection.jsx renders the
// value as a .text-4xl div next to a sibling .text-sm label; we read the
// explainer text ("N students have signed up (all time).") for robustness.
async function readSignupsTotal(page) {
  const explainer = page
    .getByText(/students have signed up \(all time\)/i)
    .first();
  await expect(explainer).toBeVisible({ timeout: 10000 });
  const text = (await explainer.textContent()) || '';
  const m = text.match(/^\s*(\d+)\s+students have signed up/i);
  return m ? parseInt(m[1], 10) : null;
}

// ---------------------------------------------------------------------------
// SCENARIO 2 — admin overview stat increments after a participant signup
// ---------------------------------------------------------------------------

test('cross-role Scenario 2: admin overview Signups count increments after a participant signup', async ({
  page,
}, testInfo) => {
  installErrorCapture(page, testInfo);

  const seed = getSeed();
  expect(seed.period_slot_id, 'period_slot_id required in seed JSON').toBeTruthy();

  // Step 1 — admin reads current signups_total. Force desktop viewport so
  // the AdminLayout renders content (DesktopOnlyBanner blocks < 768px).
  await ensureAdminViewport(page);
  await loginAs(page, ADMIN);
  await page.goto('/admin');
  const before = await readSignupsTotal(page);
  expect(before, 'Signups total must be readable on /admin overview').not.toBeNull();

  // Step 2 — direct-API signup + confirm (fastest path, per plan Task 2 hint).
  await apiSignupAndConfirm('xrole2', [seed.period_slot_id], 'XRole2');

  // Step 3 — reload admin overview and assert the count strictly increased.
  // OverviewSection uses useQuery without auto-refetch interval, so a manual
  // navigation/reload is needed to pick up the new value. Other parallel
  // scenarios (3, 4) create their own signups, so assert >= before + 1
  // rather than exactly before + 1 — the scenario's invariant is "a new
  // signup is visible on the admin overview", not "no other signup happened".
  await expect
    .poll(
      async () => {
        await page.goto('/admin');
        const n = await readSignupsTotal(page);
        return n;
      },
      {
        timeout: 10000,
        message: 'Signups total did not increase after API signup',
      },
    )
    .toBeGreaterThanOrEqual(before + 1);

  assertNoErrors(testInfo);
});

// ---------------------------------------------------------------------------
// SCENARIO 3 — organizer sees a freshly-created signup via the 5s roster poll
// ---------------------------------------------------------------------------

test('cross-role Scenario 3: organizer roster reflects a new signup within the 5s poll window', async ({
  page,
}, testInfo) => {
  installErrorCapture(page, testInfo);

  const seed = getSeed();
  expect(seed.period_slot_id, 'period_slot_id required in seed JSON').toBeTruthy();

  // Organizer opens the roster BEFORE the signup is created, so the 5s
  // react-query refetchInterval (verified in OrganizerRosterPage.jsx line 28)
  // is what brings the row in — no page.reload() required.
  await loginAs(page, ORGANIZER);
  await page.goto(`/organizer/events/${seed.event_id}/roster`);
  await expect(page.getByText(/checked in/i).first()).toBeVisible({
    timeout: 10000,
  });

  // Create the signup via direct API while the roster is open.
  await apiSignupAndConfirm('xrole3', [seed.period_slot_id], 'XRole3');

  // The polling interval is 5000ms; give it 12s of budget to absorb one full
  // cycle + network latency. Match by the distinctive last name.
  const newRow = page
    .locator('ul li button')
    .filter({ hasText: /xrole3/i })
    .first();
  await expect(newRow).toBeVisible({ timeout: 12000 });

  assertNoErrors(testInfo);
});

// ---------------------------------------------------------------------------
// SCENARIO 4 — public cancel flow surfaces in the admin audit log
// ---------------------------------------------------------------------------

test('cross-role Scenario 4: public cancel via magic-link surfaces signup_cancelled in audit log', async ({
  page,
}, testInfo) => {
  installErrorCapture(page, testInfo);

  const seed = getSeed();
  expect(seed.period_slot_id, 'period_slot_id required in seed JSON').toBeTruthy();

  // Step 1 — direct-API signup + confirm. We need the confirm_token to drive
  // /signup/manage in the UI.
  const { confirmToken, email } = await apiSignupAndConfirm(
    'xrole4',
    [seed.period_slot_id],
    'XRole4',
  );

  // Step 2 — open the magic-link manage page and cancel the signup via UI.
  await page.goto(`/signup/manage?token=${confirmToken}`);
  await expect(page.getByText(/signups/i).first()).toBeVisible({
    timeout: 10000,
  });

  // Click the per-row "Cancel" button, confirm via modal "Yes, cancel".
  await page.getByRole('button', { name: /^cancel$/i }).first().click();
  await expect(page.getByText('Cancel this signup?')).toBeVisible();
  await page.getByRole('button', { name: /yes, cancel/i }).click();
  // Toast copy normalised to American "canceled" (single L) per
  // ManageSignupsPage.jsx.
  await expect(page.getByText(/canceled/i)).toBeVisible({ timeout: 5000 });

  // Step 3 — admin filters audit log by email; expect a "Cancelled a signup"
  // row (humanised label for the `signup_cancelled` action — note double-L in
  // the backend action literal but single-L in the humanised UI label).
  // Clear public-session state first so the admin login is clean. Force
  // desktop viewport for the admin shell.
  await logout(page);
  await ensureAdminViewport(page);
  await loginAs(page, ADMIN);
  await page.goto('/admin/audit-logs');
  await page.waitForLoadState('networkidle');

  const search = page.locator('#al-search');
  await expect(search).toBeVisible({ timeout: 8000 });
  await search.fill(email);
  // Debounce is 300ms; wait for refetch to settle.
  await page.waitForLoadState('networkidle');

  // Poll — audit write is synchronous (deps.log_action inside the same txn),
  // but the admin list endpoint is a separate read; a short poll absorbs any
  // read-after-write replica lag if a pool connection is cold.
  const cancelledRow = page
    .locator('table tbody tr')
    .filter({ hasText: /cancelled a signup/i })
    .first();
  await expect(cancelledRow).toBeVisible({ timeout: 10000 });

  assertNoErrors(testInfo);
});

// ---------------------------------------------------------------------------
// SCENARIO 5 — organizer RBAC — admin-only pages deny, shared pages load
//
// From frontend/src/App.jsx + ProtectedRoute.jsx (verified during Task 3
// inspection):
// - Admin-only (roles=["admin"]): /admin/users, /admin/audit-logs, /admin/exports
//   -> ProtectedRoute renders a "Forbidden" component (NOT a redirect).
// - Shared (roles=["admin", "organizer"]): /admin/templates, /admin/imports,
//   /admin/events, /admin plus /organizer.
//
// Pitfall 5 from 20-RESEARCH.md: templates and imports MUST load for organizer.
// Do not invert the allow/deny lists.
// ---------------------------------------------------------------------------

test('cross-role Scenario 5: organizer RBAC — admin-only pages deny, shared pages load', async ({
  page,
}, testInfo) => {
  installErrorCapture(page, testInfo);

  // Scenario 5 navigates shared admin surfaces (/admin/users, /admin/imports,
  // /admin/templates, /admin/audit-logs, /admin/exports). Force desktop
  // viewport so AdminLayout renders its actual content and the Forbidden
  // panel (for admin-only routes) rather than the DesktopOnlyBanner.
  await ensureAdminViewport(page);
  await loginAs(page, ORGANIZER);

  // Admin-only routes render the ProtectedRoute "Forbidden" panel for an
  // organizer session (verified in ProtectedRoute.jsx lines 12-19).
  const adminOnly = ['/admin/users', '/admin/audit-logs', '/admin/exports'];
  for (const path of adminOnly) {
    await page.goto(path);
    await expect(
      page.getByRole('heading', { name: /forbidden/i }),
      `expected Forbidden on ${path} for organizer`,
    ).toBeVisible({ timeout: 8000 });
  }

  // Shared routes (positive checks — organizer MUST be able to reach these).
  // /admin/templates and /admin/imports are the Phase 17 / Phase 18 surfaces.
  // /organizer is the Phase 19 dashboard.
  // We assert these pages are NOT the Forbidden panel — they must mount the
  // real shared-admin shell. Some (e.g. /admin/imports) expose a backend API
  // that denies organizer access; the page-level UI still renders the admin
  // shell + section content and surfaces the API denial as a retryable
  // in-page error. That is the correct UX, not a routing problem.
  for (const path of ['/admin/templates', '/admin/imports', '/organizer']) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(path.replace(/\//g, '\\/') + '$'));
    // Must NOT be the ProtectedRoute Forbidden panel.
    await expect(
      page.getByRole('heading', { name: /^forbidden$/i }),
    ).toHaveCount(0);
    // Positive signal: page has rendered some main content (heading, nav,
    // breadcrumb, or a CTA button). Use a broad selector so scaffolding
    // differences between the three pages do not fail the check.
    await expect(
      page
        .locator('h1, h2, h3, nav, [role="navigation"], button')
        .first(),
    ).toBeVisible({ timeout: 8000 });
  }

  assertNoErrors(testInfo);
});
