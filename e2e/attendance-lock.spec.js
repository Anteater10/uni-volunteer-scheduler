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
// A second test (issue #189) drives the volunteer QR page across two shifts:
// staff close/reopen, a pending booking, and a staff tap before the scan.
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

// Issue #189 (Kim, 2026-10-15): students could only QR check in for the first
// shift. One QR code serves the whole event; the server picks the session
// whose window is open. Through one QR URL:
//   - staff close Shift 1 -> the QR card says "Closed by staff"; staff reopen
//     -> Quinn checks in (E1)
//   - Rowan, a PENDING booking on Shift 2, checks in (E3)
//   - staff tap Sage in first; Sage then scans and sees "Checked in ✓" with
//     no error (E2)
test('QR check-in: one QR across shifts, staff close/reopen, pending, staff tap first', async ({ page, request }) => {
  test.setTimeout(90_000);
  const tag = Math.random().toString(36).slice(2, 7);
  const admin = await login(request, ADMIN);
  const organizer = await login(request, ORGANIZER);
  const week = await call(request, 'GET', '/public/current-week');
  const now = Date.now();
  const at = (minutes) => new Date(now + minutes * 60_000).toISOString();

  // Shift 1 started 5 minutes ago, Shift 2 starts in 20: both windows
  // (30 minutes either side of the start) are open now.
  const shift = (name, start, sortOrder) => ({
    name,
    capacity: 20,
    sort_order: sortOrder,
    sessions: [{ name: 'Today', start_time: at(start), end_time: at(start + 60), location: 'Room Q', sort_order: 0 }],
  });
  const title = `E2E QR Shifts ${tag}`;
  const event = await call(request, 'POST', '/events/', {
    token: organizer,
    data: {
      title,
      description: 'attendance-lock QR e2e — safe to delete',
      location: 'E2E Hall',
      visibility: 'public',
      start_date: at(-60),
      end_date: at(180),
      quarter: week.quarter,
      year: week.year,
      week_number: week.week_number,
      module_slug: 'e2e-test',
      school: 'E2E High School',
      slots: [],
      shifts: [shift('QR Shift 1', -5, 0), shift('QR Shift 2', 20, 1)],
    },
  });
  const shifts = await call(request, 'GET', `/shifts/?event_id=${event.id}`, { token: admin });
  const byName = (name) => shifts.find((s) => s.name === name);

  const quinn = { first: 'Quinn', email: ephemeralEmail('qr-s1'), shift: 'QR Shift 1' };
  const rowan = { first: 'Rowan', email: ephemeralEmail('qr-pend'), shift: 'QR Shift 2' };
  const sage = { first: 'Sage', email: ephemeralEmail('qr-staff'), shift: 'QR Shift 2' };
  for (const s of [quinn, sage]) {
    await call(request, 'POST', `/admin/events/${event.id}/add-volunteer`, {
      token: admin,
      data: {
        first_name: s.first, last_name: tag, email: s.email, send_email: false,
        shift_ids: [byName(s.shift).id],
      },
    });
  }
  // Rowan books publicly and never confirms: pending. Credit first
  // (orientation rule), then the public signup.
  await grantOrientationCredit(rowan.email);
  await call(request, 'POST', '/public/signups', {
    data: {
      first_name: rowan.first, last_name: tag, email: rowan.email, phone: '8055550142',
      slot_ids: [], shift_ids: [byName(rowan.shift).id],
    },
  });

  // The QR code's URL, exactly as the roster's QR modal builds it.
  const roster = await call(request, 'GET', `/events/${event.id}/roster`, { token: organizer });
  expect(roster.venue_code).toMatch(/^\d{4}$/);
  const code = roster.venue_code;
  await page.goto(`/event-check-in/${event.id}?v=${code}`);
  // A cold dev server can take a while to serve the first page.
  await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 15_000 });

  const cardFor = (s) => page.locator('li button').filter({ hasText: s.shift });
  const lookUp = async (s) => {
    await page.getByLabel('Email').fill(s.email);
    await page.getByRole('button', { name: 'Find my shifts' }).click();
  };
  const startOver = () => page.getByRole('button', { name: 'Check in someone else' }).click();

  // E1. Staff close Shift 1: Quinn's card says so and can't be tapped.
  const shift1Session = byName(quinn.shift).sessions[0].id;
  await call(request, 'POST', `/slots/${shift1Session}/resolve`, {
    token: organizer, data: { attended: [], no_show: [] },
  });
  await lookUp(quinn);
  await expect(cardFor(quinn)).toContainText('Closed by staff');
  await expect(cardFor(quinn)).toBeDisabled();
  await startOver();
  // Staff reopen it; the same QR now works.
  await call(request, 'POST', `/slots/${shift1Session}/reopen`, { token: organizer });
  await lookUp(quinn);
  await expect(cardFor(quinn)).toContainText('Tap to check in');
  await cardFor(quinn).click();
  await expect(cardFor(quinn)).toContainText('Checked in ✓');
  await expect(page.getByText(/You're checked in for QR Shift 1/)).toBeVisible();
  await startOver();

  // E3. A pending booking checks in with one tap (confirmation is an RSVP).
  await lookUp(rowan);
  await expect(cardFor(rowan)).toContainText('Tap to check in');
  await cardFor(rowan).click();
  await expect(cardFor(rowan)).toContainText('Checked in ✓');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await startOver();

  // E2. Staff tap Sage in first; Sage's scan then shows checked in, no error.
  const sageLookup = await call(request, 'POST', `/events/${event.id}/check-in-lookup`, {
    data: { email: sage.email, venue_code: code },
  });
  const sageUnit = sageLookup.shifts[0];
  await call(
    request, 'POST',
    `/shift-signups/${sageUnit.shift_signup_id}/sessions/${sageUnit.slot_id}/check-in`,
    { token: organizer },
  );
  await lookUp(sage);
  await expect(cardFor(sage)).toContainText('Checked in ✓');
  await expect(page.getByRole('alert')).toHaveCount(0);

  // The server agrees for all three.
  for (const s of [quinn, rowan, sage]) {
    const lookup = await call(request, 'POST', `/events/${event.id}/check-in-lookup`, {
      data: { email: s.email, venue_code: code },
    });
    expect(lookup.shifts.map((r) => [r.shift_name, r.status])).toEqual([[s.shift, 'checked_in']]);
  }
});
