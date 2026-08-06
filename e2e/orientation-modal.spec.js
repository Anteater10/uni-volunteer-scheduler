// e2e/orientation-modal.spec.js
//
// Tests orientation requirement behavior (server-enforced at signup create):
//   Test A: Un-oriented volunteer picking period-only is steered to add an
//           orientation session (required modal — no bypass), adds one, and
//           the signup succeeds with both slots.
//   Test B: Modal skipped when volunteer has prior attended orientation
//
// From OrientationWarningModal.jsx (required variant — the seed event
// offers an orientation slot, so the advisory click-through never applies):
//   title: "Orientation is part of your first signup"
//   Primary button: "Pick an orientation session"

import { test, expect } from '@playwright/test';
import {
  getSeed,
  ephemeralEmail,
  VOLUNTEER_IDENTITY,
  clickSlotByLabel,
  clickShiftById,
} from './fixtures.js';

async function fillIdentityForm(page, email) {
  await page.locator('#first_name').fill(VOLUNTEER_IDENTITY.first_name);
  await page.locator('#last_name').fill(VOLUNTEER_IDENTITY.last_name);
  await page.locator('#email').fill(email);
  await page.locator('#phone').fill(VOLUNTEER_IDENTITY.phone);
}

// Submit the identity form — must be the form's "Sign up" CTA, not a row button.
async function submitForm(page) {
  await page.locator('form').getByRole('button', { name: /sign up/i }).last().click();
}

test.describe('orientation modal', () => {
  test('Test A: period-only without history is steered to add an orientation session', async ({ page }) => {
    const seed = getSeed();
    expect(seed.event_id, 'E2E seed required').toBeTruthy();
    expect(seed.shift_id, 'shift_id required in seed JSON').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // 2026-08-05 shifts: classroom work is a shift now, so "period-only" means
    // booking the shift and no orientation slot.
    await clickShiftById(page, seed.shift_id);

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with fresh email (no orientation history)
    const email = ephemeralEmail('modal-a');
    await fillIdentityForm(page, email);

    // Submit form
    await submitForm(page);

    // The required modal MUST fire (no bypass offered) because:
    // - Only period slot selected (no orientation slot)
    // - Email has no prior orientation history
    // - The seed event offers an orientation slot
    await expect(
      page.getByText('Orientation is part of your first signup')
    ).toBeVisible({ timeout: 8000 });
    await expect(
      page.getByRole('button', { name: /i've done orientation/i })
    ).not.toBeVisible();

    // Steer back to the schedule and add the orientation session. The period
    // selection and identity fields persist.
    await page.getByRole('button', { name: /pick an orientation session/i }).click();
    await clickSlotByLabel(page, /^orientation/i);

    await expect(page.getByText('Your information')).toBeVisible();
    await submitForm(page);

    // With the orientation slot included, the signup succeeds.
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
    expect(seed.shift_id, 'shift_id required in seed JSON').toBeTruthy();

    await page.goto(`/events/${seed.event_id}`);

    // Select ONLY the shift — no orientation slot.
    await clickShiftById(page, seed.shift_id);

    // Identity form appears
    await expect(page.getByText('Your information')).toBeVisible();

    // Fill with the seeded "has attended orientation" email
    // The frontend calls GET /public/orientation-check?email=&event_id= (Phase 21
    // credit engine); it returns {has_credit: true} so the modal is skipped.
    await page.locator('#first_name').fill('Attended');
    await page.locator('#last_name').fill('Volunteer');
    await page.locator('#email').fill(seed.attended_volunteer_email);
    await page.locator('#phone').fill('805-555-0100');

    // Submit — wait for the orientation-check API call to confirm the check happened.
    const [orientResp] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/orientation-check') && resp.request().method() === 'GET'
      ),
      page.locator('form').getByRole('button', { name: /sign up/i }).last().click(),
    ]);

    // The orientation-check response must say has_credit: true — the field the
    // modal decision actually reads (EventDetailPage.jsx falls back to
    // has_attended_orientation only for legacy responses).
    const orientBody = await orientResp.json();
    expect(
      orientBody.has_credit,
      'attended volunteer should have has_credit=true'
    ).toBe(true);

    // Orientation modal must NOT appear (suppressed because has_credit=true)
    await page.waitForTimeout(500);
    await expect(
      page.getByText('Have you done a Sci Trek orientation?')
    ).not.toBeVisible();
  });
});
