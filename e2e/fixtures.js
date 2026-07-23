// Shared credentials + seed accessor for Playwright specs.
// Credentials must match backend/tests/fixtures/seed_e2e.py.

export const ADMIN = { email: 'admin@e2e.example.com', password: 'Admin!2345' };
export const ORGANIZER = { email: 'organizer@e2e.example.com', password: 'Organizer!2345' };

// v1.1: no student accounts — volunteers are account-less.
// Use VOLUNTEER_IDENTITY + ephemeralEmail() for signup form tests.
export const VOLUNTEER_IDENTITY = {
  first_name: 'E2E',
  last_name: 'Volunteer',
  phone: '805-555-0199',
};

export function getSeed() {
  try {
    return JSON.parse(process.env.E2E_SEED || '{}');
  } catch {
    return {};
  }
}

// Generate a collision-free ephemeral volunteer email for specs that need a
// fresh identity (so they can run in parallel and/or re-run without cleanup).
export function ephemeralEmail(tag = 'vol') {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${tag}-${Date.now()}-${rand}@e2e.example.com`;
}

// EventDetailPage renders two mutually exclusive slot layouts split at the
// Tailwind `md` (768px) breakpoint:
//   desktop (md+): a <table> whose label cells are div.font-medium ("Orientation",
//                  "Period N") with an in-row "Sign Up" button
//   mobile (<md):  a card list (div.rounded-xl) whose labels are p.font-medium
//                  with an in-card "Sign up" button
// slotLabel resolves the label element in whichever layout is visible at the
// current viewport, so specs exercise the real mobile UI on mobile projects.
export function slotLabel(page, label) {
  return page
    .locator(
      'table div.font-medium:visible, div.rounded-xl p.font-medium:visible',
      { hasText: label }
    )
    .first();
}

// Click the "Sign Up"/"Sign up" button for the slot with the given label, in
// whichever layout (desktop table row or mobile card) is currently visible.
export async function clickSlotByLabel(page, label) {
  const labelEl = slotLabel(page, label);
  await labelEl.waitFor({ state: 'visible' });
  // Nearest clickable container: <tr> on desktop, rounded-xl card on mobile.
  const container = labelEl.locator(
    'xpath=ancestor::*[self::tr or contains(@class, "rounded-xl")][1]'
  );
  await container.getByRole('button', { name: /^sign up$/i }).click();
}

// Server-enforced orientation requirement: period-only signups from fresh
// emails 422 with ORIENTATION_REQUIRED unless the email holds orientation
// credit for the event's module family. Specs that need a bare period-only
// signup (roster/check-in/swap flows) grant credit first via the admin API.
// 'e2e-test' matches the seed module template (family_key defaults to slug).
export async function grantOrientationCredit(email, familyKey = 'e2e-test') {
  const apiBase = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
  const loginResp = await fetch(`${apiBase}/api/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: ADMIN.email, password: ADMIN.password }),
  });
  if (!loginResp.ok) {
    throw new Error(`admin login for credit grant failed: ${loginResp.status}`);
  }
  const { access_token: token } = await loginResp.json();
  const grantResp = await fetch(`${apiBase}/api/v1/admin/orientation-credits`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      volunteer_email: email,
      family_key: familyKey,
      notes: 'e2e fixture grant (period-only signup helper)',
    }),
  });
  if (!grantResp.ok) {
    throw new Error(`orientation credit grant failed: ${grantResp.status}`);
  }
}
