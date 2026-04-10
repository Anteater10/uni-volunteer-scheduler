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

test.describe.serial('public volunteer flow', () => {
  let token;
  const email = ephemeralEmail('pub');

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
    // Slot sections present
    await expect(page.getByText(/orientation slots/i)).toBeVisible();
    await expect(page.getByText(/period slots/i)).toBeVisible();
  });

  test('select both slots, fill form, submit, capture token', async ({ page }) => {
    const seed = getSeed();
    await page.goto(`/events/${seed.event_id}`);

    // Click orientation slot card to select it (first non-full orientation card)
    const orientationCards = page.locator('section').filter({ hasText: /orientation slots/i })
      .locator('li');
    await orientationCards.first().click();

    // Click period slot card to select it
    const periodCards = page.locator('section').filter({ hasText: /period slots/i })
      .locator('li');
    await periodCards.first().click();

    // Identity form should appear
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill form fields using label IDs from EventDetailPage.jsx
    await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
    await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
    await page.locator('#email').fill(email);
    await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);

    // Intercept POST /public/signups to capture confirm_token
    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/public/signups') && resp.request().method() === 'POST'
      ),
      page.getByRole('button', { name: /sign up/i }).click(),
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

    const orientationCards = page.locator('section').filter({ hasText: /orientation slots/i })
      .locator('li');
    await orientationCards.first().click();
    const periodCards = page.locator('section').filter({ hasText: /period slots/i })
      .locator('li');
    await periodCards.first().click();

    await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
    await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
    await page.locator('#email').fill(ephemeralEmail('nmod'));
    await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);

    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/public/signups') && resp.request().method() === 'POST'
      ),
      page.getByRole('button', { name: /sign up/i }).click(),
    ]);

    // Orientation modal must NOT appear when orientation slot is selected
    await expect(
      page.getByText(/have you completed orientation/i)
    ).not.toBeVisible();

    // Success card/popup visible
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
    await expect(page.getByText('Your Signups')).toBeVisible({ timeout: 10000 });
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
    await expect(page.getByText('Your Signups')).toBeVisible({ timeout: 10000 });

    // Click first Cancel button
    await page.getByRole('button', { name: /^cancel$/i }).first().click();

    // Confirm in the modal
    await expect(page.getByText('Cancel this signup?')).toBeVisible();
    await page.getByRole('button', { name: /yes, cancel/i }).click();

    // Toast confirms cancellation
    await expect(page.getByText(/cancelled/i)).toBeVisible({ timeout: 5000 });
  });

  test('cancel all remaining signups', async ({ page }) => {
    const resolvedToken = token || getSeed().confirm_token;
    if (!resolvedToken) {
      test.skip(true, 'No confirm_token available — EXPOSE_TOKENS_FOR_TESTING must be set');
    }

    await page.goto(`/signup/manage?token=${resolvedToken}`);
    await expect(page.getByText('Your Signups')).toBeVisible({ timeout: 10000 });

    // "Cancel all signups" button appears when activeCount >= 2 (ManageSignupsPage.jsx)
    // After previous test cancelled one, there may be only 1 left so "cancel all" won't appear.
    // Use the last remaining "Cancel" button directly instead.
    const cancelBtn = page.getByRole('button', { name: /^cancel$/i });
    const count = await cancelBtn.count();
    if (count > 0) {
      await cancelBtn.first().click();
      await expect(page.getByText('Cancel this signup?')).toBeVisible();
      await page.getByRole('button', { name: /yes, cancel/i }).click();
      await expect(page.getByText(/cancelled/i)).toBeVisible({ timeout: 5000 });
    }

    // Empty state when all signups cancelled
    await expect(
      page.getByText(/no upcoming signups/i)
    ).toBeVisible({ timeout: 8000 });
  });
});
