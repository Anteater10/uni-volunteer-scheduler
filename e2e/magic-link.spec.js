// Flow: magic-link confirmation pages render correctly.
// Tests navigation to confirm-pending, confirm-failed, and confirmed pages
// with query parameters. Does NOT require a real magic-link token endpoint
// (pages are server-state-free except for the resend form).
import { test, expect } from '@playwright/test';

test.describe('magic-link confirmation pages', () => {
  test('confirm-pending page shows check-your-inbox message', async ({ page }) => {
    await page.goto('/signup/confirm-pending?email=test@example.com&event=abc');
    await expect(
      page.getByRole('heading', { name: /check your inbox/i }),
    ).toBeVisible();
    await expect(page.getByText(/test@example.com/)).toBeVisible();
    await expect(page.getByText(/15 minutes/)).toBeVisible();
    await expect(
      page.getByRole('button', { name: /resend email/i }),
    ).toBeVisible();
  });

  test('confirm-failed page with reason=expired shows expired message', async ({ page }) => {
    await page.goto('/signup/confirm-failed?reason=expired');
    await expect(
      page.getByRole('heading', { name: /confirmation failed/i }),
    ).toBeVisible();
    await expect(page.getByText(/link has expired/i)).toBeVisible();
    await expect(
      page.getByRole('button', { name: /resend confirmation link/i }),
    ).toBeVisible();
  });

  test('confirm-failed page with reason=used shows already-used message', async ({ page }) => {
    await page.goto('/signup/confirm-failed?reason=used');
    await expect(page.getByText(/already been used/i)).toBeVisible();
  });

  test('confirm-failed page with reason=not_found shows not-found message', async ({ page }) => {
    await page.goto('/signup/confirm-failed?reason=not_found');
    await expect(page.getByText(/couldn.*find/i)).toBeVisible();
  });

  test('confirmed page shows success state', async ({ page }) => {
    await page.goto('/signup/confirmed?event=some-event-id');
    await expect(
      page.getByRole('heading', { name: /signup confirmed/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /view my signups/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /back to event/i }),
    ).toBeVisible();
  });

  test('confirmed page without event param hides back-to-event link', async ({ page }) => {
    await page.goto('/signup/confirmed');
    await expect(
      page.getByRole('heading', { name: /signup confirmed/i }),
    ).toBeVisible();
    // "Back to event" link should not be present
    await expect(
      page.getByRole('link', { name: /back to event/i }),
    ).toHaveCount(0);
  });
});
