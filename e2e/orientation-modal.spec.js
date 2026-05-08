// e2e/orientation-modal.spec.js
//
// Tests orientation warning modal behavior:
//   Test A: Modal fires when volunteer picks period-only slot + no orientation history
//   Test B: Modal skipped when volunteer has prior attended orientation
//
// From OrientationWarningModal.jsx:
//   title: "Have you done a Sci Trek orientation?"
//   Primary button: "I've done orientation — continue"
//   Secondary button: "I haven't — show me orientation events"

import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail, VOLUNTEER_IDENTITY } from './fixtures.js';

async function fillIdentityForm(page, email) {
  await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
  await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
  await page.locator('#email').fill(email);
  await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);
}

// Slot table helper — after 15-04 the EventDetailPage uses a <table>; locate
// the slot-label <div> (which has class "font-medium") then walk up to the row.
async function clickSlotByLabel(page, label) {
  const labelDiv = page.locator('table div.font-medium', { hasText: label }).first();
  await labelDiv.waitFor({ state: 'visible' });
  const row = labelDiv.locator('xpath=ancestor::tr[1]');
  await row.getByRole('button', { name: /^sign up$/i }).click();
}

// Submit the identity form — must be the form's "Sign up" CTA, not a row button.
async function submitForm(page) {
  await page.locator('form').getByRole('button', { name: /sign up/i }).last().click();
}

test.describe('orientation modal', () => {
  test('Test A: modal fires when period-only + no orientation history', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // Select ONLY the period slot (not orientation)
    await clickSlotByLabel(page, /^period/i);

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with fresh email (no orientation history)
    const email = ephemeralEmail('modal-a');
    await fillIdentityForm(page, email);

    // Submit form
    await submitForm(page);

    // The orientation modal MUST fire because:
    // - Only period slot selected (no orientation slot)
    // - Email has no prior orientation history
    await expect(
      page.getByText('Have you done a Sci Trek orientation?')
    ).toBeVisible({ timeout: 8000 });

    // Click "I've done orientation — continue"
    await page.getByRole('button', { name: /i've done orientation/i }).click();

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
    await clickSlotByLabel(page, /^period/i);

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with the seeded "has attended orientation" email
    // The backend's GET /public/orientation-status?email= will return {has_attended_orientation: true}
    // causing the modal to be skipped
    await page.locator('#first_name').fill('Attended');
    await page.locator('#last_name').fill('Volunteer');
    await page.locator('#email').fill(seed.attended_volunteer_email);
    await page.locator('#phone').fill('805-555-0100');

    // Submit — wait for the orientation-status API call to confirm the check happened.
    const [orientResp] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/orientation-status') && resp.request().method() === 'GET'
      ),
      page.locator('form').getByRole('button', { name: /sign up/i }).last().click(),
    ]);

    // The orientation-status response must say has_attended_orientation: true
    const orientBody = await orientResp.json();
    expect(
      orientBody.has_attended_orientation,
      'attended volunteer should have has_attended_orientation=true'
    ).toBe(true);

    // Orientation modal must NOT appear (suppressed because has_attended_orientation=true)
    await page.waitForTimeout(500);
    await expect(
      page.getByText('Have you done a Sci Trek orientation?')
    ).not.toBeVisible();
  });
});
