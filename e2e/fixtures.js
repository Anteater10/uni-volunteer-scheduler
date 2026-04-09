// Shared credentials + seed accessor for Playwright specs.
// Credentials must match backend/tests/fixtures/seed_e2e.py.

export const ADMIN = { email: 'admin@e2e.test', password: 'Admin!2345' };
export const ORGANIZER = { email: 'organizer@e2e.test', password: 'Organizer!2345' };
export const STUDENT = { email: 'student@e2e.test', password: 'Student!2345' };

export function getSeed() {
  try {
    return JSON.parse(process.env.E2E_SEED || '{}');
  } catch {
    return {};
  }
}

// Generate a collision-free ephemeral student email for specs that need a
// fresh account (so they can run in parallel and/or re-run without cleanup).
export function ephemeralEmail(tag = 'student') {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${tag}-${Date.now()}-${rand}@e2e.test`;
}
