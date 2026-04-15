// e2e/admin-smoke.spec.js
//
// Admin dashboard smoke test — shallow coverage that guards against import
// crashes, route misconfigurations, and missing navigation.
// Does NOT test deep functionality — just verifies each page loads without error.

import { test, expect } from '@playwright/test';
import { ADMIN } from './fixtures.js';

async function loginAsAdmin(page) {
  // LoginPage.jsx uses id="login-email" and id="login-password"
  await page.goto('/login');
  await page.locator('#login-email').fill(ADMIN.email);
  await page.locator('#login-password').fill(ADMIN.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  // Wait for redirect away from /login
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });
}

test.describe('admin dashboard smoke', () => {
  test('admin can log in', async ({ page }) => {
    await loginAsAdmin(page);
    // After login, redirected to somewhere other than /login
    await expect(page).not.toHaveURL('/login');
  });

  test('admin overview page loads', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/admin');
    // AdminLayout renders heading "Admin" (from AdminLayout.jsx or OverviewSection)
    await expect(page.getByRole('heading', { name: 'Admin' })).toBeVisible({ timeout: 8000 });
  });

  test('audit logs page loads', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/audit-logs');
    await page.waitForLoadState('networkidle');
    // AuditLogsPage renders a filter form — look for the Keyword Search input.
    // AdminLayout renders both mobile and desktop DOM; use .first() to avoid strict violation.
    await expect(page.locator('#al-q').first()).toBeVisible({ timeout: 8000 });
  });

  test('templates page loads', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/templates');
    // Wait for page to load — any heading is fine
    await page.waitForLoadState('networkidle');
    // Templates section renders a heading or table
    await expect(page.locator('h1, h2, h3').first()).toBeVisible({ timeout: 8000 });
  });

  test('exports page loads', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/exports');
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    // ExportsSection renders some content
    await expect(page.locator('h1, h2, h3, button, table').first()).toBeVisible({ timeout: 8000 });
  });
});
