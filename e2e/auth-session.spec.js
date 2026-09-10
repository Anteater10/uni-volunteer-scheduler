// e2e/auth-session.spec.js
//
// Phase L3 regression suite: the session survives a page reload.
//
// This file exists because of a bug that shipped past a green backend suite
// (2100+ tests), a green frontend suite (633 tests) AND a passing curl check.
// The refresh token moved to an HttpOnly cookie and the access token moved
// into memory, which means an access token no longer survives a reload — the
// app re-mints one on boot by POSTing /auth/refresh, and that call needs an
// X-CSRF-Token header whose value is read from a JS-readable cookie.
//
// Both cookies were initially given Path=/api/v1/auth. A browser only exposes
// a cookie to document.cookie when its Path prefix-matches THE CURRENT PAGE,
// and the SPA's pages are /, /login, /admin/... — so the csrf cookie was
// invisible, no header was sent, every refresh 403'd, and every reload logged
// the user out.
//
// Nothing below jsdom could see it: the vitest test set document.cookie
// itself (defaulting to Path=/, a cookie the server never sends), and curl
// matches cookies against the REQUEST url (/api/v1/auth/refresh, which does
// match). Only a real browser sitting on a real app route can tell.
//
// So: assert the browser-observable facts, not the implementation.
import { test, expect } from '@playwright/test';
import { ADMIN } from './fixtures.js';

// The API is a different ORIGIN from the SPA in dev (5173 vs 8000) but the
// same SITE — cookies ignore port, which is why the cookie flow works across
// the two at all. Target it absolutely; a relative /api/... would hit the
// vite dev server instead.
const API_ORIGIN = process.env.E2E_BACKEND_URL || 'http://localhost:8000';

async function loginAsAdmin(page) {
  // Admin content is desktop-only by design (AdminLayout swaps in
  // DesktopOnlyBanner below 768px), so force a desktop viewport for the
  // mobile projects too — same pattern as admin-smoke.spec.js.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/login');
  await page.locator('#login-email').fill(ADMIN.email);
  await page.locator('#login-password').fill(ADMIN.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 8000 });
}

test.describe('Phase L3 — cookie-based session', () => {
  test('staff session survives a page reload', async ({ page }) => {
    await loginAsAdmin(page);
    const afterLogin = page.url();

    // The actual regression. With the csrf cookie unreadable this reload
    // ends up back on /login.
    await page.reload();
    await expect(page).not.toHaveURL(/\/login$/, { timeout: 8000 });
    expect(page.url()).toBe(afterLogin);
  });

  test('session survives a fresh navigation to a deep admin route', async ({ page }) => {
    await loginAsAdmin(page);

    // A bookmark / address-bar hit is a full document load, so it takes the
    // same boot-refresh path as a reload but from a different Path — which
    // is exactly what the cookie Path bug was sensitive to.
    await page.goto('/admin');
    await expect(page).not.toHaveURL(/\/login$/, { timeout: 8000 });
  });

  test('the csrf cookie is readable from an app route and the refresh cookie is not', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto('/admin');

    const visible = await page.evaluate(() => document.cookie);
    expect(visible, 'csrf_token must be readable by JS from an app route').toMatch(
      /(?:^|;\s*)csrf_token=/,
    );
    expect(
      visible,
      'the refresh token must NEVER be readable by JS — that is the point of the phase',
    ).not.toMatch(/refresh_token=/);

    // And the jar-level view confirms the refresh cookie exists but is HttpOnly.
    const cookies = await page.context().cookies();
    const refresh = cookies.find((c) => c.name === 'refresh_token');
    expect(refresh, 'refresh_token cookie should exist').toBeTruthy();
    expect(refresh.httpOnly).toBe(true);

    const csrf = cookies.find((c) => c.name === 'csrf_token');
    expect(csrf.httpOnly).toBe(false);
    expect(csrf.path).toBe('/');
  });

  test('no token is left in localStorage', async ({ page }) => {
    await loginAsAdmin(page);

    const stored = await page.evaluate(() => {
      const out = {};
      for (let i = 0; i < localStorage.length; i += 1) {
        const k = localStorage.key(i);
        out[k] = localStorage.getItem(k);
      }
      return out;
    });

    // The whole purpose of L3: an XSS reading localStorage finds no session.
    expect(Object.keys(stored)).not.toContain('uvse_access_token');
    expect(Object.keys(stored)).not.toContain('uvse_refresh_token');
    const blob = JSON.stringify(stored);
    expect(blob).not.toMatch(/eyJ[A-Za-z0-9_-]{10,}/); // no JWT anywhere
  });

  test('logging out clears the cookies and a reload does not restore the session', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto('/admin');

    // Drive the real logout path rather than clearing cookies by hand — the
    // point is that the server revokes and clears, not that Playwright can
    // delete a cookie.
    const logoutStatus = await page.evaluate(async (apiOrigin) => {
      const csrf = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
      const res = await fetch(`${apiOrigin}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf[1]) } : {},
      });
      return res.status;
    }, API_ORIGIN);
    expect(logoutStatus).toBe(200);

    const cookies = await page.context().cookies();
    expect(cookies.find((c) => c.name === 'refresh_token')).toBeFalsy();

    await page.goto('/admin');
    await expect(page).toHaveURL(/\/login/, { timeout: 8000 });
  });
});
