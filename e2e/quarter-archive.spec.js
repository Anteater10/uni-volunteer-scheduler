// e2e/quarter-archive.spec.js
//
// Issue #33 — quarter archiving round trip:
// admin archives a past quarter → the public browse page lists it under
// "Archived quarters" → clicking in shows the archived banner with week nav.
//
// Setup goes through the API (idempotent per run); the archive action and
// the public verification go through the real UI.

import { test, expect } from '@playwright/test';
import { ADMIN } from './fixtures.js';

const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
const API = `${BACKEND_URL}/api/v1`;

// Each Playwright project gets its own past-quarter row (distinct year →
// distinct (season, year) key AND non-overlapping dates), so the six
// browser projects can run this spec in parallel without racing. The
// backend accepts years >= 2020 only, and winter of these years ended
// long before any plausible "today".
const PROJECT_YEARS = {
  chromium: 2020,
  firefox: 2021,
  webkit: 2022,
  'Mobile Chrome': 2023,
  'Mobile Safari': 2024,
  'iPhone SE 375': 2025,
};

async function adminToken(request) {
  const resp = await request.post(`${API}/auth/token`, {
    form: { username: ADMIN.email, password: ADMIN.password },
  });
  expect(resp.ok(), `admin login failed: ${resp.status()}`).toBeTruthy();
  return (await resp.json()).access_token;
}

/**
 * Ensure a winter-{year} quarter row exists and is NOT archived, so the
 * UI Archive button is available. Returns the row.
 */
async function ensurePastQuarter(request, token, year) {
  const headers = { Authorization: `Bearer ${token}` };

  const list = await request.get(`${API}/admin/quarters`, { headers });
  expect(list.ok()).toBeTruthy();
  let row = (await list.json()).find(
    (q) => q.season === 'winter' && q.year === year && q.label === '',
  );

  if (!row) {
    const created = await request.post(`${API}/admin/quarters`, {
      headers,
      data: {
        season: 'winter',
        year,
        label: '',
        start_date: `${year}-01-10`,
        end_date: `${year}-03-15`,
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    row = (await created.json()).quarter;
  }

  if (row.archived_at) {
    const restored = await request.post(`${API}/admin/quarters/${row.id}/restore`, { headers });
    expect(restored.ok()).toBeTruthy();
    row = await restored.json();
  }
  return row;
}

async function loginAsAdmin(page) {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/login');
  await page.locator('#login-email').fill(ADMIN.email);
  await page.locator('#login-password').fill(ADMIN.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });
}

test('admin archives a past quarter; public browses it under Archived quarters', async ({
  page,
  request,
}, testInfo) => {
  const year = PROJECT_YEARS[testInfo.project.name];
  test.skip(year === undefined, 'no reserved past-quarter year for this Playwright project');
  const token = await adminToken(request);
  const row = await ensurePastQuarter(request, token, year);
  const displayName = `Winter ${year}`;

  // ---- Admin: archive through the Quarters page ----
  await loginAsAdmin(page);
  await page.goto('/admin/quarters');
  await page.getByTestId(`archive-${row.id}`).click();
  await page.getByTestId('confirm-archive').click();
  // The row flips to its archived state: Restore replaces Archive.
  await expect(page.getByTestId(`restore-${row.id}`)).toBeVisible({ timeout: 8000 });

  // ---- Public: the archived quarter is reachable from the browse page ----
  await page.goto('/volunteer');
  await page.getByText('Archived quarters').click();
  await page.getByRole('button', { name: displayName }).click();

  // SCRUM-48: the browse page steps quarter × school level, not weeks.
  await expect(page.getByText(`${displayName} — Middle School`)).toBeVisible({
    timeout: 8000,
  });
  const banner = page.getByRole('status').filter({ hasText: /archived/i });
  await expect(banner).toContainText(displayName);

  // Nav is clamped inside the archived quarter: on the first level prev is
  // disabled, while next still moves to the other level within the row.
  await expect(
    page.getByRole('button', { name: 'Previous quarter or school level', exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Next quarter or school level', exact: true }),
  ).toBeEnabled();
});
