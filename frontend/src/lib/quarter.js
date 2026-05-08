// Mirrors backend/app/services/quarter.py. MUST stay in sync — see that file.
// Anchor: Spring 2026 week 1 start (Monday 2026-03-30), confirmed by user 2026-04-15.
// Note: JS Date month is 0-indexed, so March = month 2.
export const QUARTER_ANCHOR = new Date(Date.UTC(2026, 2, 30));
export const WEEKS_PER_QUARTER = 11;

const MS_PER_DAY = 24 * 3600 * 1000;
const MS_PER_WEEK = 7 * MS_PER_DAY;
const MS_PER_QUARTER = WEEKS_PER_QUARTER * MS_PER_WEEK;

function weeksSinceAnchor(now = new Date()) {
  const ms = now.getTime() - QUARTER_ANCHOR.getTime();
  return Math.floor(ms / MS_PER_WEEK);
}

export function quarterIndex(now = new Date()) {
  return Math.floor(weeksSinceAnchor(now) / WEEKS_PER_QUARTER);
}

export function currentQuarter(now = new Date()) {
  const idx = quarterIndex(now);
  const start = new Date(QUARTER_ANCHOR.getTime() + idx * MS_PER_QUARTER);
  const end = new Date(start.getTime() + MS_PER_QUARTER);
  return { start, end };
}

export function previousQuarter(now = new Date()) {
  const idx = quarterIndex(now) - 1;
  const start = new Date(QUARTER_ANCHOR.getTime() + idx * MS_PER_QUARTER);
  const end = new Date(start.getTime() + MS_PER_QUARTER);
  return { start, end };
}

export function quarterProgress(now = new Date()) {
  const { start } = currentQuarter(now);
  const days = Math.max(0, Math.floor((now.getTime() - start.getTime()) / MS_PER_DAY));
  const week = Math.min(WEEKS_PER_QUARTER, 1 + Math.floor(days / 7));
  return {
    week,
    of: WEEKS_PER_QUARTER,
    pct: Math.round((week / WEEKS_PER_QUARTER) * 100) / 100,
  };
}
