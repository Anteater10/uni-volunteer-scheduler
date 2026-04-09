// Playwright globalSetup — runs the idempotent seed_e2e.py script against the
// already-running backend and stashes the resulting ID blob in process.env for
// spec files to read via ./fixtures.js getSeed().
import { spawnSync } from 'node:child_process';

export default async function globalSetup() {
  const backendUrl = process.env.E2E_BACKEND_URL || 'http://localhost:8000';
  const res = spawnSync('python3', ['backend/tests/fixtures/seed_e2e.py'], {
    env: { ...process.env, BACKEND_URL: backendUrl },
    encoding: 'utf-8',
  });
  if (res.status !== 0) {
    console.error('[e2e] seed_e2e.py stdout:', res.stdout);
    console.error('[e2e] seed_e2e.py stderr:', res.stderr);
    throw new Error(`E2E seed failed (exit ${res.status})`);
  }
  // seed script prints a single JSON line on the last non-empty stdout line
  const lines = (res.stdout || '').trim().split('\n').filter(Boolean);
  const last = lines[lines.length - 1] || '{}';
  try {
    const data = JSON.parse(last);
    process.env.E2E_SEED = JSON.stringify(data);
    console.log('[e2e] seed ok:', data.event_title, 'slots:', data.slot_ids?.length);
  } catch (e) {
    throw new Error(`E2E seed produced invalid JSON: ${last}`);
  }
}
