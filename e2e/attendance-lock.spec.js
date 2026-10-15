// e2e/attendance-lock.spec.js
//
// 2026-10-13 (Kim's report): attendance closes per slot, by a person, and can
// always be reopened. This walks the roster the way staff use it:
//
//   1. pending and confirmed both read "not checked in"; a tap checks in, a
//      second tap undoes it
//   2. "End orientation" closes the slot with a pending person in it (Cancel
//      first changes nothing); a closed slot is read-only
//   3. "Reopen orientation" puts attended back to checked in and no-show back
//      to not checked in, a mistake can be fixed, and the slot closes again
//   4. "End event" closes only sessions that have started — the session two
//      days out is not offered and stays open with nobody marked
//
// Setup is API-only and builds a fresh event per run (unique title and
// emails), so the six browser projects can run it in parallel. Times are
// relative to now: the orientation and the "Today" session have started, the
// "Later" session is two days away. Everything checked happens in the UI.

import { test, expect } from '@playwright/test';
import { ADMIN, ORGANIZER, ephemeralEmail, grantOrientationCredit } from './fixtures.js';

const BACKEND_URL = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
const API = `${BACKEND_URL}/api/v1`;

async function call(request, method, path, { token, data, form } = {}) {
  const resp = await request.fetch(`${API}${path}`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    data,
    form,
  });
  const body = await resp.json().catch(() => null);
  expect(resp.ok(), `${method} ${path} -> ${resp.status()} ${JSON.stringify(body)}`).toBeTruthy();
  return body;
}

async function login(request, who) {
  const body = await call(request, 'POST', '/auth/token', {
    form: { username: who.email, password: who.password },
  });
  return body.access_token;
}

/** Build the event and its bookings. Returns names the test looks for. */
async function seedLockEvent(request, tag) {
  const admin = await login(request, ADMIN);
  const organizer = await login(request, ORGANIZER);
  const week = await call(request, 'GET', '/public/current-week');

  const now = Date.now();
  const at = (minutes) => new Date(now + minutes * 60_000).toISOString();
  const event = await call(request, 'POST', '/events/', {
    token: organizer,
    data: {
      title: `E2E Slot Lock ${tag}`,
      description: 'attendance-lock e2e — safe to delete',
      location: 'E2E Hall',
      visibility: 'public',
      start_date: at(-60),
      end_date: at(2 * 24 * 60 + 120),
      quarter: week.quarter,
      year: week.year,
      week_number: week.week_number,
      module_slug: 'e2e-test',
      school: 'E2E High School',
      slots: [
        {
          slot_type: 'orientation',
          start_time: at(-10),
          end_time: at(50),
          capacity: 50,
          location: 'E2E Hall Room A',
        },
      ],
      shifts: [
        {
          name: 'Lock Shift',
          capacity: 50,
          sort_order: 0,
          sessions: [
            { name: 'Today', start_time: at(-5), end_time: at(60), location: 'Room B', sort_order: 0 },
            { name: 'Later', start_time: at(2 * 24 * 60), end_time: at(2 * 24 * 60 + 60), location: 'Room B', sort_order: 1 },
          ],
        },
      ],
    },
  });

  const slots = await call(request, 'GET', `/slots/?event_id=${event.id}`, { token: admin });
  const orientationId = slots.find((s) => s.slot_type === 'orientation').id;
  const shifts = await call(request, 'GET', `/shifts/?event_id=${event.id}`, { token: admin });
  const shiftId = shifts[0].id;

  const names = {
    pendingOrient: `Penny ${tag}`,
    confirmedOrient: `Connie ${tag}`,
    alpha: `Alpha ${tag}`,
    bravo: `Bravo ${tag}`,
    pendingShift: `Pablo ${tag}`,
  };
  const phone = '8055550142';

  // Public signup never confirmed -> pending.
  await call(request, 'POST', '/public/signups', {
    data: {
      first_name: 'Penny', last_name: tag, email: ephemeralEmail('lock-pend'), phone,
      slot_ids: [orientationId], shift_ids: [],
    },
  });
  // Staff add -> confirmed.
  const addVolunteer = (first, body) =>
    call(request, 'POST', `/admin/events/${event.id}/add-volunteer`, {
      token: admin,
      data: { first_name: first, last_name: tag, email: ephemeralEmail('lock'), send_email: false, ...body },
    });
  await addVolunteer('Connie', { slot_ids: [orientationId] });
  await addVolunteer('Alpha', { shift_ids: [shiftId] });
  await addVolunteer('Bravo', { shift_ids: [shiftId] });
  // A pending shift booking: credit first (orientation rule), then public signup.
  const pabloEmail = ephemeralEmail('lock-pshift');
  await grantOrientationCredit(pabloEmail);
  await call(request, 'POST', '/public/signups', {
    data: { first_name: 'Pablo', last_name: tag, email: pabloEmail, phone, slot_ids: [], shift_ids: [shiftId] },
  });

  return { eventId: event.id, names };
}

const card = (section, name) => section.locator('li button').filter({ hasText: name });
const chip = (section, name) => card(section, name).locator('span').last();

test('slot lock: tap/undo, close with pending, read-only, reopen + fix, End event skips future', async ({ page, request }) => {
  // One long walk through every state: well past the 30s default.
  test.setTimeout(120_000);
  const tag = Math.random().toString(36).slice(2, 7);
  const { eventId, names } = await seedLockEvent(request, tag);

  await page.goto('/login');
  await page.locator('#login-email').fill(ORGANIZER.email);
  await page.locator('#login-password').fill(ORGANIZER.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: 10000 });
  // The organizer roster route works at every width (/admin/* is desktop-only).
  await page.goto(`/organizer/events/${eventId}/roster`);

  const orientation = page.locator('section').filter({ has: page.getByText('Orientation', { exact: true }) });
  const today = page.locator('section').filter({ hasText: 'Lock Shift · Today' });
  const later = page.locator('section').filter({ hasText: 'Lock Shift · Later' });
  const dialog = page.getByRole('dialog');
  const orientationAction = orientation.getByRole('button', { name: /End orientation|Reopen orientation/ });

  // 1. pending == confirmed on an open slot; tap checks in, tap again undoes.
  await expect(chip(orientation, names.pendingOrient)).toHaveText('not checked in');
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('not checked in');
  await card(orientation, names.confirmedOrient).click();
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('checked in');
  await expect(card(orientation, names.confirmedOrient)).toContainText('tap again to undo');
  await card(orientation, names.confirmedOrient).click();
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('not checked in');
  // A pending person checks in with one tap too.
  await card(orientation, names.pendingOrient).click();
  await expect(chip(orientation, names.pendingOrient)).toHaveText('checked in');
  await expect(orientation).toContainText('1/2 checked in');

  // 2. Close with Cancel first (nothing changes), then for real.
  await orientationAction.click();
  await expect(dialog).toContainText(names.pendingOrient);
  await expect(dialog).toContainText(names.confirmedOrient);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(orientation).toContainText('1/2 checked in');

  await orientationAction.click();
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(orientation).toContainText(/closed/i);
  await expect(orientation).toContainText('1 attended · 1 no show');
  await expect(chip(orientation, names.pendingOrient)).toHaveText('attended');
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('no show');
  // Closed is read-only.
  await expect(card(orientation, names.confirmedOrient)).toBeDisabled();
  await expect(card(orientation, names.pendingOrient)).toBeDisabled();
  await expect(orientationAction).toHaveText('Reopen orientation');

  // 3. Reopen keeps the results as checked in / not checked in; fix; re-close.
  await orientationAction.click();
  await expect(orientationAction).toHaveText('End orientation');
  await expect(chip(orientation, names.pendingOrient)).toHaveText('checked in');
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('not checked in');
  await card(orientation, names.confirmedOrient).click();
  await expect(chip(orientation, names.confirmedOrient)).toHaveText('checked in');
  await orientationAction.click();
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(orientation).toContainText('2 attended · 0 no show');

  // 4. End event: only the started session is offered; "Later" is untouched.
  await card(today, names.alpha).click();
  await expect(chip(today, names.alpha)).toHaveText('checked in');
  await expect(chip(today, names.pendingShift)).toHaveText('not checked in');
  await page.getByRole('button', { name: 'End event' }).click();
  await expect(dialog).toContainText(names.alpha);
  await expect(dialog).toContainText(names.bravo);
  await expect(dialog).toContainText(names.pendingShift);
  await expect(dialog).toContainText('Lock Shift · Today');
  await expect(dialog).not.toContainText('Later');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toHaveCount(0);

  await expect(today).toContainText('1 attended · 2 no show');
  await expect(chip(today, names.pendingShift)).toHaveText('no show');
  await expect(later).toContainText('0/3 checked in');
  // It can't be ended early either: the button waits for the start time.
  await expect(later.getByRole('button', { name: /^End slot/ })).toBeDisabled();
  for (const n of [names.alpha, names.bravo, names.pendingShift]) {
    await expect(chip(later, n)).toHaveText('not checked in');
  }
  // Something is still open, so the event is not complete.
  await expect(page.getByTestId('event-complete-banner')).toHaveCount(0);

  // Nothing started is left open: End event now says so.
  await page.getByRole('button', { name: 'End event' }).click();
  await expect(dialog).toContainText('Nothing to close yet');
  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).toHaveCount(0);
});
