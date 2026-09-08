// e2e/public-signup.spec.js
//
// Full public volunteer flow:
//   browse /events -> event detail -> select both slots -> fill form ->
//   submit (capture confirm_token from API response) -> no orientation modal ->
//   success card -> confirm via token URL -> manage view shows the signup
//   list plus the read-only contact-notice card.
//
// 2026-08-02 read-only signups: the public self-cancel/self-swap endpoints
// and every cancel/move control on the magic-link manage page were deleted
// — staff perform all signup changes now. This file (scoped to the public
// volunteer surface) no longer exercises cancel flows; see
// e2e/cross-role.spec.js Scenario 4 for the staff-cancel path (admin roster
// -> `admin_signup_cancel` audit action) and the volunteer-side read-only
// assertions this file's "manage view shows signups" test mirrors.
//
// REQUIRES: EXPOSE_TOKENS_FOR_TESTING=1 on the backend so confirm_token is
// returned in the POST /public/signups response. Add to backend/.env for local
// runs, or ensure CI sets it (see .github/workflows/ci.yml).

import { test, expect } from '@playwright/test';
import {
  getSeed,
  ephemeralEmail,
  VOLUNTEER_IDENTITY,
  clickSlotByLabel,
  clickShiftById,
  slotLabel,
} from './fixtures.js';

// PART-02 — no console errors / pageerrors on any public route during the
// golden path. Allow-list is empty today; add an entry ONLY with an explicit
// justification comment naming the source of the noise and why it is benign.
const ALLOWED_CONSOLE_PATTERNS = [
  // e.g. /Download the React DevTools/ — dev-only noise (uncomment if it appears in CI)
];

test.describe.serial('public volunteer flow', () => {
  let token;
  const email = ephemeralEmail('pub');

  // PART-02: capture pageerror + console.error per-test (testInfo bag avoids
  // cross-test bleed when `fullyParallel: true` is enabled in playwright.config.js).
  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.errors = [];
    page.on('pageerror', (err) => {
      testInfo.errors.push(`pageerror: ${err.message}`);
    });
    page.on('console', (msg) => {
      if (msg.type() !== 'error') return;
      // msg.text() collapses structured args to "[object Object]". Walk msg.args()
      // and grab JSHandle previews so the failure message names the real culprit.
      const argPreviews = msg.args().map((a) => {
        try { return a.toString(); } catch { return '<unprintable>'; }
      });
      const text = `${msg.text()}${argPreviews.length ? ` | args=${argPreviews.join(' / ')}` : ''}`;
      if (ALLOWED_CONSOLE_PATTERNS.some((re) => re.test(text))) return;
      testInfo.errors.push(`console.error[${msg.location().url || 'inline'}:${msg.location().lineNumber || '?'}]: ${text}`);
    });
  });

  test.afterEach(async ({}, testInfo) => {
    const errors = testInfo.errors || [];
    if (errors.length > 0) {
      throw new Error(
        `PART-02 violation — ${errors.length} error(s) captured during "${testInfo.title}":\n${errors.join('\n')}`,
      );
    }
  });

  test('browse /events shows seed event', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed is required — run seed_e2e.py first').toBeTruthy();

    await page.goto('/events');
    // SCRUM-48: the nav label is now "<quarter> — <school level>".
    await expect(page.getByText(/middle school|high school/i).first()).toBeVisible();
    // Our seeded event must appear
    await expect(page.getByText('E2E Seed Event')).toBeVisible();
  });

  test('open event detail from card click', async ({ page }) => {
    const seed = getSeed();
    await page.goto('/events');
    await page.getByText('E2E Seed Event').click();
    await expect(page).toHaveURL(/\/events\//);
    // Orientation slot labels render in the desktop <table> (md+) or the
    // mobile card list (<md) — slotLabel resolves whichever is visible.
    await expect(slotLabel(page, /orientation/i)).toBeVisible();
    // 2026-08-05 shifts: classroom work is no longer a "Period N" row of its
    // own — it is a shift card carrying its sessions.
    await expect(page.getByTestId(`shift-${seed.shift_id}`)).toBeVisible();
  });

  test('select both slots, fill form, submit, capture token', async ({ page }) => {
    const seed = getSeed();
    await page.goto(`/events/${seed.event_id}`);

    // Click "Sign Up" for one orientation slot (table row on desktop, card on
    // mobile — see fixtures.js) plus the shift that carries the classroom work.
    await clickSlotByLabel(page, /orientation/i);
    await clickShiftById(page, seed.shift_id);

    // Identity form should appear
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill form fields using label IDs from EventDetailPage.jsx
    await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
    await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
    await page.locator('#email').fill(email);
    await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);

    // Submit button is the bottom-of-form CTA labelled "Sign up" (lower-case "u").
    // Disambiguate from per-row "Sign Up" buttons by scoping to the form.
    const submitBtn = page.locator('form').getByRole('button', { name: /sign up/i }).last();

    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/public/signups') && resp.request().method() === 'POST'
      ),
      submitBtn.click(),
    ]);

    const body = await response.json();
    expect(
      body.confirm_token,
      'confirm_token missing — EXPOSE_TOKENS_FOR_TESTING=1 must be set on the backend'
    ).toBeTruthy();
    token = body.confirm_token;

    // Store token in test shared state via global scope
    // (serial block runs in same worker, token variable is shared)
  });

  test('no orientation modal when both slots selected', async ({ page }) => {
    const seed = getSeed();
    await page.goto(`/events/${seed.event_id}`);

    await clickSlotByLabel(page, /orientation/i);
    await clickShiftById(page, seed.shift_id);

    await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
    await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
    await page.locator('#email').fill(ephemeralEmail('nmod'));
    await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);

    const submitBtn = page.locator('form').getByRole('button', { name: /sign up/i }).last();
    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/public/signups') && resp.request().method() === 'POST'
      ),
      submitBtn.click(),
    ]);

    // Orientation modal must NOT appear when an orientation slot is selected.
    // Per 15-06 the modal copy is "Have you done a Sci Trek orientation?".
    await expect(
      page.getByText(/have you done a sci trek orientation/i)
    ).not.toBeVisible();

    // Success response captured.
    const body = await response.json();
    expect(response.ok()).toBeTruthy();
    token = body.confirm_token || token; // capture if available
  });

  test('confirm via token URL shows confirmation', async ({ page }) => {
    // Use seed confirm_token if per-test token is unavailable
    const resolvedToken = token || getSeed().confirm_token;
    if (!resolvedToken) {
      test.skip(true, 'No confirm_token available — EXPOSE_TOKENS_FOR_TESTING must be set');
    }

    await page.goto(`/signup/confirm?token=${resolvedToken}`);
    // ConfirmSignupPage shows green confirmation banner
    await expect(page.getByText(/your signup is confirmed/i)).toBeVisible({ timeout: 10000 });
  });

  test('manage view shows signups', async ({ page }) => {
    const resolvedToken = token || getSeed().confirm_token;
    if (!resolvedToken) {
      test.skip(true, 'No confirm_token available — EXPOSE_TOKENS_FOR_TESTING must be set');
    }

    await page.goto(`/signup/manage?token=${resolvedToken}`);
    // Page header renders "Your signups" (UI-SPEC) or "Signups for {name}" when
    // the backend resolves the volunteer — accept either via the shared /signups/i.
    await expect(page.getByText(/signups/i).first()).toBeVisible({ timeout: 10000 });
    // 2026-08-02 read-only signups: no self-service cancel/move affordance —
    // the organizer contact-notice card replaces it (mirrors the volunteer-
    // side checks in cross-role.spec.js Scenario 4).
    await expect(page.getByTestId('contact-notice')).toBeVisible();
    await expect(
      page.getByRole('button', { name: /cancel|move/i }),
    ).toHaveCount(0);
  });
});
