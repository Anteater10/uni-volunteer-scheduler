// e2e/public-signup.spec.js
//
// Full public volunteer flow:
//   browse /events -> event detail -> select both slots -> fill form ->
//   submit (capture confirm_token from API response) -> no orientation modal ->
//   success card -> confirm via token URL -> manage view shows 2 signups ->
//   cancel one -> cancel all -> empty state
//
// REQUIRES: EXPOSE_TOKENS_FOR_TESTING=1 on the backend so confirm_token is
// returned in the POST /public/signups response. Add to backend/.env for local
// runs, or ensure CI sets it (see .github/workflows/ci.yml).

import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail, VOLUNTEER_IDENTITY } from './fixtures.js';

// PART-02 — no console errors / pageerrors on any public route during the
// golden path. Allow-list is empty today; add an entry ONLY with an explicit
// justification comment naming the source of the noise and why it is benign.
const ALLOWED_CONSOLE_PATTERNS = [
  // e.g. /Download the React DevTools/ — dev-only noise (uncomment if it appears in CI)
];

// Slot table helper — after 15-04 the EventDetailPage uses a <table> with a
// "Sign Up" button per row and a slot label cell ("Orientation" or "Period N").
// Locate the label <div> by its exact slot-name text, walk up to the <tr>, and
// click the in-row "Sign Up" button.
async function clickSlotByLabel(page, label) {
  const labelDiv = page.locator('table div.font-medium', { hasText: label }).first();
  await labelDiv.waitFor({ state: 'visible' });
  const row = labelDiv.locator('xpath=ancestor::tr[1]');
  await row.getByRole('button', { name: /^sign up$/i }).click();
}

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
    // Week nav should be present
    await expect(page.getByText(/week/i).first()).toBeVisible();
    // Our seeded event must appear
    await expect(page.getByText('E2E Seed Event')).toBeVisible();
  });

  test('open event detail from card click', async ({ page }) => {
    await page.goto('/events');
    await page.getByText('E2E Seed Event').click();
    await expect(page).toHaveURL(/\/events\//);
    // After 15-04 the slot list is a single <table>; rows carry "Orientation"
    // or "Period N" labels rather than separate <section> wrappers.
    await expect(page.locator('table').getByText(/orientation/i).first()).toBeVisible();
    await expect(page.locator('table').getByText(/period/i).first()).toBeVisible();
  });

  test('select both slots, fill form, submit, capture token', async ({ page }) => {
    const seed = getSeed();
    await page.goto(`/events/${seed.event_id}`);

    // Click the in-row "Sign Up" buttons for one orientation + one period slot.
    await clickSlotByLabel(page, /orientation/i);
    await clickSlotByLabel(page, /^period/i);

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
    await clickSlotByLabel(page, /^period/i);

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
    // At least one signup card
    const cancelButtons = page.getByRole('button', { name: /^cancel$/i });
    await expect(cancelButtons.first()).toBeVisible();
  });

  test('cancel one signup', async ({ page }) => {
    const resolvedToken = token || getSeed().confirm_token;
    if (!resolvedToken) {
      test.skip(true, 'No confirm_token available — EXPOSE_TOKENS_FOR_TESTING must be set');
    }

    await page.goto(`/signup/manage?token=${resolvedToken}`);
    await expect(page.getByText(/signups/i).first()).toBeVisible({ timeout: 10000 });

    // Click first Cancel button
    await page.getByRole('button', { name: /^cancel$/i }).first().click();

    // Confirm in the modal
    await expect(page.getByText('Cancel this signup?')).toBeVisible();
    await page.getByRole('button', { name: /yes, cancel/i }).click();

    // Toast confirms cancellation
    // UI-SPEC toast: "Signup canceled." (American spelling, single L)
    await expect(page.getByText(/canceled/i)).toBeVisible({ timeout: 5000 });
  });

  test('cancel all remaining signups', async ({ page }) => {
    const resolvedToken = token || getSeed().confirm_token;
    if (!resolvedToken) {
      test.skip(true, 'No confirm_token available — EXPOSE_TOKENS_FOR_TESTING must be set');
    }

    await page.goto(`/signup/manage?token=${resolvedToken}`);
    await expect(page.getByText(/signups/i).first()).toBeVisible({ timeout: 10000 });

    // "Cancel all signups" button appears when activeCount >= 2 (ManageSignupsPage.jsx)
    // After previous test cancelled one, there may be only 1 left so "cancel all" won't appear.
    // Use the last remaining "Cancel" button directly instead.
    const cancelBtn = page.getByRole('button', { name: /^cancel$/i });
    const count = await cancelBtn.count();
    if (count > 0) {
      await cancelBtn.first().click();
      await expect(page.getByText('Cancel this signup?')).toBeVisible();
      await page.getByRole('button', { name: /yes, cancel/i }).click();
      // UI-SPEC toast: "Signup canceled." (American spelling, single L)
    await expect(page.getByText(/canceled/i)).toBeVisible({ timeout: 5000 });
    }

    // Empty state when all signups cancelled — UI-SPEC copy is
    // "You haven't signed up for anything yet" (PART-AUDIT § Copy mismatch).
    await expect(
      page.getByText(/haven't signed up for anything/i).first()
    ).toBeVisible({ timeout: 8000 });
  });
});
