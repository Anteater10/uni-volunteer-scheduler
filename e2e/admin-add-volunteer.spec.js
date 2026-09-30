// e2e/admin-add-volunteer.spec.js
//
// Staff request 2026-09-30: staff add a volunteer to an event by hand from the
// admin event page, skipping the public form's orientation requirement.

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { ADMIN, getSeed, ephemeralEmail } from './fixtures.js';

async function loginAsAdmin(page) {
  // Admin content is desktop-only (see admin-smoke.spec.js).
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/login');
  await page.locator('#login-email').fill(ADMIN.email);
  await page.locator('#login-password').fill(ADMIN.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });
}

test('admin adds a volunteer to a shift without orientation', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, 'E2E seed required').toBeTruthy();
  const email = ephemeralEmail('staff-add');

  await loginAsAdmin(page);
  await page.goto(`/admin/events/${seed.event_id}`);
  await page.getByRole('button', { name: /^add volunteer$/i }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();

  // The new form must meet the same bar as the rest of the admin UI.
  const axe = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
  const serious = axe.violations.filter((v) => ['serious', 'critical'].includes(v.impact));
  expect(serious, JSON.stringify(serious.map((v) => v.id))).toEqual([]);

  await dialog.getByLabel(/first name/i).fill('Staff');
  await dialog.getByLabel(/last name/i).fill('Added');
  await dialog.getByLabel(/^email$/i).fill(email);
  // First shift only — no orientation, which the public form would refuse.
  await dialog.locator('fieldset').first().getByRole('checkbox').first().check();

  const [resp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/add-volunteer') && r.request().method() === 'POST'
    ),
    dialog.getByRole('button', { name: /^add volunteer$/i }).click(),
  ]);
  expect(resp.status()).toBe(201);
  await expect(dialog).not.toBeVisible();

  // Adding the same person to the same shift again is refused, with the
  // server's reason shown in the form.
  await page.getByRole('button', { name: /^add volunteer$/i }).click();
  await dialog.getByLabel(/first name/i).fill('Staff');
  await dialog.getByLabel(/last name/i).fill('Added');
  await dialog.getByLabel(/^email$/i).fill(email);
  await dialog.locator('fieldset').first().getByRole('checkbox').first().check();
  await dialog.getByRole('button', { name: /^add volunteer$/i }).click();
  await expect(dialog.getByText(/already on this shift/i)).toBeVisible();
});
