// Flow 3: organizer logs in, lands on dashboard, opens the seeded event,
// verifies the roster view renders.
import { test, expect } from '@playwright/test';
import { ORGANIZER, getSeed } from './fixtures.js';

test('organizer can view the roster for the seeded event', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id).toBeTruthy();

  await page.goto('/login');
  await page.getByLabel(/^email/i).fill(ORGANIZER.email);
  await page.getByLabel(/password/i).fill(ORGANIZER.password);
  await page.getByRole('button', { name: /login|sign ?in/i }).click();

  await page.goto('/organizer');
  await expect(page).toHaveURL(/\/organizer/);

  // Drill into the seeded event directly (resilient to dashboard layout changes).
  await page.goto(`/organizer/events/${seed.event_id}`);
  await expect(page).toHaveURL(new RegExp(`/organizer/events/${seed.event_id}`));

  // Roster container + at least the event title must render.
  await expect(page.getByRole('heading').first()).toBeVisible();
  // Weak but stable: the page should include the word roster, signups, or slot.
  await expect(page.getByText(/roster|signup|slot|participant/i).first()).toBeVisible();
});
