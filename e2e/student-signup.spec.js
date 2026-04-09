// Flow 1: student register -> browse portal -> sign up -> MySignups confirms.
// Uses an ephemeral student email per run so the spec is idempotent and
// parallel-safe. Relies on seed_e2e.py having created the portal + event.
import { test, expect } from '@playwright/test';
import { getSeed, ephemeralEmail } from './fixtures.js';

test('student can register, sign up for a slot, and see it in MySignups', async ({ page }) => {
  const seed = getSeed();
  expect(seed.portal_slug, 'seed did not populate portal_slug').toBeTruthy();

  const email = ephemeralEmail('signup');
  const password = 'Student!2345';

  // Register
  await page.goto('/register');
  await page.getByLabel(/full name/i).fill('Flow One');
  await page.getByLabel(/^email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /create account|register|sign ?up/i }).click();
  await expect(page).toHaveURL(/\/(events|my-signups)/);

  // Browse the seeded portal and open the seeded event
  await page.goto(`/portals/${seed.portal_slug}`);
  await expect(page.getByText(seed.event_title || /e2e/i).first()).toBeVisible();

  // Walk into event detail; prefer a link tied to the event title
  const eventLink = page.getByRole('link', { name: new RegExp(seed.event_title || 'e2e', 'i') }).first();
  if (await eventLink.count()) {
    await eventLink.click();
  } else {
    await page.getByRole('link', { name: /view|details|open/i }).first().click();
  }
  await expect(page).toHaveURL(/\/events\/[0-9a-f-]+/);

  // Sign up for the first available slot
  const signupBtn = page.getByRole('button', { name: /sign ?up|reserve|join/i }).first();
  await expect(signupBtn).toBeVisible();
  await signupBtn.click();

  // Navigate to MySignups and assert a confirmed row is visible
  await page.goto('/my-signups');
  await expect(page.getByRole('heading', { name: /my signups/i })).toBeVisible();
  await expect(page.getByText(/confirmed|waitlisted/i).first()).toBeVisible();
});
