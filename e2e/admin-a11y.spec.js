// e2e/admin-a11y.spec.js
//
// First admin a11y coverage (Phase 16, Plan 07, Task 2 — ADMIN-25 + ADMIN-26).
//
// Runs @axe-core/playwright against every in-scope Phase 16 admin route at a
// desktop viewport (1280x800, per D-08/D-09 WCAG AA at desktop widths) and fails
// the build if any serious or critical WCAG 2.1 AA violations are found.
//
// Deviation from plan (Rule 3): the plan spec says `frontend/e2e/admin-a11y.spec.js`
// but e2e tests in this repo actually live at the repo root `e2e/` directory per
// `playwright.config.js`. File placed at the real location.

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { ADMIN } from './fixtures.js';

// Static admin routes covered by the a11y sweep. /admin/events/:eventId is
// exercised in a separate test below because the eventId has to be discovered
// from the Overview page at runtime.
const ROUTES = [
  { label: 'Overview', path: '/admin' },
  { label: 'Users', path: '/admin/users' },
  { label: 'Portals', path: '/admin/portals' },
  { label: 'Audit Logs', path: '/admin/audit-logs' },
  { label: 'Exports', path: '/admin/exports' },
  { label: 'Help', path: '/admin/help' },
];

// Shared admin-login helper — copied from admin-smoke.spec.js to avoid
// introducing a new helper module in this plan (keeps PR footprint small; the
// doc sweep in Phase 20 can extract a shared e2e/helpers/ module).
async function loginAsAdmin(page) {
  await page.goto('/login');
  await page.locator('#login-email').fill(ADMIN.email);
  await page.locator('#login-password').fill(ADMIN.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });
}

function seriousOrCritical(violations) {
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
}

function formatViolations(violations) {
  return violations
    .map((v) => {
      const nodes = v.nodes
        .map((n) => `      - ${n.target.join(' ')}\n        ${n.failureSummary || ''}`)
        .join('\n');
      return `  [${v.impact}] ${v.id}: ${v.help}\n    ${v.helpUrl}\n${nodes}`;
    })
    .join('\n\n');
}

test.describe('Admin a11y (WCAG 2.1 AA, desktop 1280x800)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loginAsAdmin(page);
  });

  for (const { label, path } of ROUTES) {
    test(`${label} (${path}) has no serious or critical a11y violations`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState('networkidle');

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const bad = seriousOrCritical(results.violations);
      if (bad.length > 0) {
        console.log(`\nA11y violations on ${label} (${path}):\n${formatViolations(bad)}`);
      }
      expect(bad, `Serious/critical a11y violations on ${label}`).toEqual([]);
    });
  }

  test('Event detail (/admin/events/:eventId) has no serious or critical a11y violations', async ({
    page,
  }) => {
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');

    const eventLink = page.locator('a[href*="/admin/events/"]').first();
    const count = await eventLink.count();
    test.skip(count === 0, 'No events seeded — skipping event detail a11y check');

    await eventLink.click();
    await page.waitForLoadState('networkidle');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const bad = seriousOrCritical(results.violations);
    if (bad.length > 0) {
      console.log(`\nA11y violations on Event detail:\n${formatViolations(bad)}`);
    }
    expect(bad, 'Serious/critical a11y violations on Event detail').toEqual([]);
  });
});
