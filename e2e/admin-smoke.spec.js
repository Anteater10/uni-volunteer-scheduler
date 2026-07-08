// e2e/admin-smoke.spec.js
//
// Admin dashboard smoke test — shallow coverage that guards against import
// crashes, route misconfigurations, and missing navigation.
// Does NOT test deep functionality — just verifies each page loads without error.

import { test, expect } from '@playwright/test';
import { ADMIN } from './fixtures.js';

async function loginAsAdmin(page) {
  // Admin content is desktop-only by design — AdminLayout swaps <Outlet/> for
  // DesktopOnlyBanner below 768px. Force a desktop viewport so the mobile
  // Playwright projects exercise the real admin UI (same pattern as
  // admin-a11y.spec.js and cross-role's ensureAdminViewport).
  await page.setViewportSize({ width: 1280, height: 800 });
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
    // Phase 16 redesign: the overview renders stat-card headings; the old
    // standalone "Admin" h1 became a breadcrumb link.
    await expect(
      page.getByRole('heading', { name: /hours this quarter/i })
    ).toBeVisible({ timeout: 8000 });
  });

  test('audit logs page loads', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/audit-logs');
    await page.waitForLoadState('networkidle');
    // AuditLogsPage renders an "Audit logs" h1 and a filter form whose
    // keyword input is #al-search (renamed from #al-q in the redesign).
    // AdminLayout renders both mobile and desktop DOM; use .first() to avoid strict violation.
    await expect(
      page.getByRole('heading', { name: /audit logs/i }).first()
    ).toBeVisible({ timeout: 8000 });
    await expect(page.locator('#al-search').first()).toBeVisible({ timeout: 8000 });
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
