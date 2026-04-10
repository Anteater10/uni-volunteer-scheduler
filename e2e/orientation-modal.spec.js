// e2e/orientation-modal.spec.js
//
// Tests orientation warning modal behavior:
//   Test A: Modal fires when volunteer picks period-only slot + no orientation history
//   Test B: Modal skipped when volunteer has prior attended orientation
//
// From OrientationWarningModal.jsx:
//   title: "Have you completed orientation?"
//   Yes button: "Yes, I have completed orientation"
//   No button: "No — show me orientation slots"

import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail, VOLUNTEER_IDENTITY } from './fixtures.js';

async function fillIdentityForm(page, email) {
  await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
  await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
  await page.locator('#email').fill(email);
  await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);
}

test.describe('orientation modal', () => {
  test('Test A: modal fires when period-only + no orientation history', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // Select ONLY the period slot (not orientation)
    const periodCards = page.locator('section').filter({ hasText: /period slots/i }).locator('li');
    await expect(periodCards.first()).toBeVisible();
    await periodCards.first().click();

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with fresh email (no orientation history)
    const email = ephemeralEmail('modal-a');
    await fillIdentityForm(page, email);

    // Submit form
    await page.getByRole('button', { name: /sign up/i }).click();

    // The orientation modal MUST fire because:
    // - Only period slot selected (no orientation slot)
    // - Email has no prior orientation history
    await expect(
      page.getByText('Have you completed orientation?')
    ).toBeVisible({ timeout: 8000 });

    // Click "Yes, I have completed orientation"
    await page.getByRole('button', { name: /yes, i have completed orientation/i }).click();

    // Signup should proceed — success response (API call happens after modal confirm)
    // Wait for the POST /public/signups to complete
    await expect(page.getByText(/check your email|success|sign.?up.*received/i)).toBeVisible({
      timeout: 10000,
    });
  });

  test('Test B: modal skipped when volunteer has attended orientation', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required').toBeTruthy();
    expect(
      seed.attended_volunteer_email,
      'attended_volunteer_email required in seed JSON'
    ).toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // Select ONLY the period slot
    const periodCards = page.locator('section').filter({ hasText: /period slots/i }).locator('li');
    await expect(periodCards.first()).toBeVisible();
    await periodCards.first().click();

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with the seeded "has attended orientation" email
    // The backend's GET /public/orientation-status?email= will return {has_attended_orientation: true}
    // causing the modal to be skipped
    await page.locator('#first_name').fill('Attended');
    await page.locator('#last_name').fill('Volunteer');
    await page.locator('#email').fill(seed.attended_volunteer_email);
    await page.locator('#phone').fill('805-555-0100');

    // Submit
    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes('/public/signups') && resp.request().method() === 'POST'
      ),
      page.getByRole('button', { name: /sign up/i }).click(),
    ]);

    // Orientation modal must NOT appear
    // Wait briefly to confirm modal doesn't show up
    await page.waitForTimeout(1000);
    await expect(
      page.getByText('Have you completed orientation?')
    ).not.toBeVisible();

    // Response should be success (201/200) — signup proceeded directly
    expect(
      response.ok(),
      `Expected signup success but got ${response.status()}: ${await response.text()}`
    ).toBeTruthy();
  });
});
