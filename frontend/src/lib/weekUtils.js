/**
 * weekUtils.js — issue #24.
 *
 * Week navigation and quarter selectors over the admin-entered quarter rows
 * returned by GET /public/quarters (see useQuarters). Each row carries its
 * real length (weeks_in_quarter) — 6-week summer sessions and 11-week
 * regular quarters need no special casing, and navigation returns null past
 * the ends so callers can disable arrows.
 *
 * No side effects. No network calls. Safe to use in any rendering context.
 */

function sortedByStart(quarters) {
  return [...(quarters || [])].sort((a, b) =>
    a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : 0,
  );
}

/** Non-archived rows, ordered by start date. */
export function activeQuarters(quarters) {
  return sortedByStart(quarters).filter((q) => !q.archived_at);
}

export function findQuarterById(quarters, quarterId) {
  return (quarters || []).find((q) => q.id === quarterId) || null;
}

/**
 * The week after {quarterId, weekNumber}, rolling into the next entered
 * (non-archived) row. Null past the last entered week.
 */
export function getNextWeek(quarters, quarterId, weekNumber) {
  const list = activeQuarters(quarters);
  const idx = list.findIndex((q) => q.id === quarterId);
  if (idx === -1) return null;
  if (weekNumber < list[idx].weeks_in_quarter) {
    return { quarter_id: quarterId, week_number: weekNumber + 1 };
  }
  const next = list[idx + 1];
  return next ? { quarter_id: next.id, week_number: 1 } : null;
}

/**
 * The week before {quarterId, weekNumber}, rolling back into the previous
 * entered (non-archived) row's final week. Null before the first entered week.
 */
export function getPrevWeek(quarters, quarterId, weekNumber) {
  const list = activeQuarters(quarters);
  const idx = list.findIndex((q) => q.id === quarterId);
  if (idx === -1) return null;
  if (weekNumber > 1) {
    return { quarter_id: quarterId, week_number: weekNumber - 1 };
  }
  const prev = list[idx - 1];
  return prev ? { quarter_id: prev.id, week_number: prev.weeks_in_quarter } : null;
}

/** "Summer 2026 · Session A — Week 2" */
export function formatWeekLabel(quarterRow, weekNumber) {
  if (!quarterRow) return `Week ${weekNumber}`;
  return `${quarterRow.display_name} — Week ${weekNumber}`;
}

/**
 * Resolve a legacy ?quarter=&year=&week= link onto a quarter row.
 * Summer links are ambiguous between sessions — the first session wins.
 */
export function resolveLegacyParams(quarters, { quarter, year, week }) {
  const match = sortedByStart(quarters).find(
    (q) => q.season === quarter && Number(q.year) === Number(year),
  );
  if (!match) return null;
  return { quarter_id: match.id, week_number: Number(week) };
}

function toIsoDate(d) {
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10);
}

/** The row whose inclusive [start_date, end_date] covers the given date. */
export function quarterContaining(quarters, date) {
  const iso = toIsoDate(date);
  return (
    (quarters || []).find((q) => q.start_date <= iso && q.end_date >= iso) || null
  );
}

/**
 * The row covering the date, else the most recently ended one (gaps) —
 * mirrors the backend dashboard semantics. Null before all entered quarters.
 */
export function activeOrRecentQuarter(quarters, date) {
  const active = quarterContaining(quarters, date);
  if (active) return active;
  const iso = toIsoDate(date);
  const past = sortedByStart(quarters).filter((q) => q.end_date < iso);
  return past.length ? past[past.length - 1] : null;
}
