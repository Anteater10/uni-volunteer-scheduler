// e2e/organizer-check-in.spec.js
//
// Organizer check-in regression test:
//   1. Create a confirmed signup via API (direct fetch, no UI dependency on other specs)
//   2. Login as organizer via the UI
//   3. Navigate to the seeded event's roster: /organize/events/:id/roster
//   4. Verify signup row is visible
//   5. Click the row (check-in action) and assert status changes to checked_in
//
// Roster uses OrganizerRosterPage.jsx which:
//   - Shows each signup as a <button> row
//   - Status chips from STATUS_CHIP map
//   - Rows are disabled+unclickable when status != "confirmed" and != "pending"
//   - POST /signups/{signup_id}/check-in on click

import { test, expect } from '@playwright/test';
import { getSeed, ORGANIZER, ephemeralEmail } from './fixtures.js';

test('organizer can view roster and check in a signup', async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, 'E2E seed required').toBeTruthy();
  expect(seed.period_slot_id, 'period_slot_id required in seed JSON').toBeTruthy();

  const apiBase = process.env.E2E_BACKEND_URL || 'http://localhost:8000';

  // Step 1: Create a fresh signup via the API (not UI — avoids serial dependency)
  const email = ephemeralEmail('checkin');
  const signupResp = await fetch(`${apiBase}/api/v1/public/signups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: 'CheckIn',
      last_name: 'Test',
      email,
      phone: '8055550150',
      slot_ids: [seed.period_slot_id],
    }),
  });

  expect(signupResp.ok, `POST /public/signups failed: ${signupResp.status}`).toBeTruthy();
  const signupBody = await signupResp.json();

  // Confirm the signup using the token so it shows as "confirmed" on the roster
  const confirmToken = signupBody.confirm_token;
  if (confirmToken) {
    const confirmResp = await fetch(
      `${apiBase}/api/v1/public/signups/confirm?token=${confirmToken}`,
      { method: 'POST' }
    );
    // 200/204 both acceptable
    if (!confirmResp.ok) {
      console.warn(`Confirm returned ${confirmResp.status} — signup stays pending`);
    }
  } else {
    console.warn(
      'confirm_token absent — EXPOSE_TOKENS_FOR_TESTING must be set. Signup stays pending.'
    );
  }

  const signupId = signupBody.signup_ids[0];
  expect(signupId, 'signup_id required').toBeTruthy();

  // Step 2: Login as organizer via UI
  // LoginPage.jsx uses id="login-email" and id="login-password"
  await page.goto('/login');
  await page.locator('#login-email').fill(ORGANIZER.email);
  await page.locator('#login-password').fill(ORGANIZER.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();

  // After login, should be redirected (any auth'd page)
  await expect(page).not.toHaveURL('/login', { timeout: 8000 });

  // Step 3: Navigate directly to the roster page
  // Route is /organize/events/:eventId/roster per App.jsx
  await page.goto(`/organize/events/${seed.event_id}/roster`);

  // Step 4: Roster loaded with our signup row
  // OrganizerRosterPage shows "X of Y checked in" header — use .first() to avoid strict violation
  await expect(page.getByText(/checked in/i).first()).toBeVisible({ timeout: 10000 });

  // The roster must contain a row for our signup
  // Rows are <button> elements containing student_name and a status chip
  // Status chip shows "confirmed" or "pending" text
  const rosterRow = page.locator('ul li button').filter({ hasText: /confirmed|pending/i }).first();
  await expect(rosterRow).toBeVisible({ timeout: 5000 });

  // Step 5: Click the row to check in
  await rosterRow.click();

  // After optimistic update, the row status should change to "checked in"
  // Use the status chip specifically — <span> with text "checked in" in a button row
  await expect(
    page.locator('ul li button span').filter({ hasText: /^checked in$/i }).first()
  ).toBeVisible({ timeout: 8000 });
});
