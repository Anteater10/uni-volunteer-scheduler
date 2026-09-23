/**
 * weekUtils.js — issue #24, reworked for SCRUM-48.
 *
 * Quarter selectors over the admin-entered quarter rows returned by
 * GET /public/quarters (see useQuarters), plus the public browse page's
 * navigation. The public schedule combines every school level, so each
 * quarter row is one navigation position and one shareable URL.
 *
 * Navigation returns null past the ends so callers can disable arrows.
 *
 * No side effects. No network calls. Safe to use in any rendering context.
 */

function sortedByStart(quarters) {
  return [...(quarters || [])].sort((a, b) =>
    a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : 0,
  );
}

/**
 * The quarter that ended most recently before `date`.
 *
 * L4 #41: the Exports "Last quarter" preset needs the one *before* the current
 * one, which activeOrRecentQuarter cannot give — it returns the quarter you
 * are standing in whenever there is one.
 */
export function previousQuarter(quarters, date) {
  const iso = toIsoDate(date);
  const ended = sortedByStart(quarters).filter((q) => q.end_date < iso);
  return ended.length ? ended[ended.length - 1] : null;
}

/** Non-archived rows, ordered by start date. */
export function activeQuarters(quarters) {
  return sortedByStart(quarters).filter((q) => !q.archived_at);
}

/** Archived rows, ordered by start date (issue #33 archived browsing). */
export function archivedQuarters(quarters) {
  return sortedByStart(quarters).filter((q) => q.archived_at);
}

export function findQuarterById(quarters, quarterId) {
  return (quarters || []).find((q) => q.id === quarterId) || null;
}

/**
 * The active quarter after quarterId. Archived deep links are clamped to their
 * row and cannot roll into the live schedule.
 */
export function getNextQuarter(quarters, quarterId) {
  const row = findQuarterById(quarters, quarterId);
  if (!row) return null;
  if (row.archived_at) return null;
  const list = activeQuarters(quarters);
  const next = list[list.findIndex((q) => q.id === quarterId) + 1];
  return next ? { quarter_id: next.id } : null;
}

/**
 * The active quarter before quarterId. Clamped inside archived rows, mirroring
 * getNextQuarter.
 */
export function getPrevQuarter(quarters, quarterId) {
  const row = findQuarterById(quarters, quarterId);
  if (!row) return null;
  if (row.archived_at) return null;
  const list = activeQuarters(quarters);
  const prev = list[list.findIndex((q) => q.id === quarterId) - 1];
  return prev ? { quarter_id: prev.id } : null;
}

/**
 * Resolve a legacy ?quarter=&year= link onto a quarter row.
 *
 * SCRUM-48: these links used to carry &week=N too. The week is now ignored
 * rather than rejected — an old bookmark or emailed link lands on the same
 * quarter's combined schedule instead of erroring, which is the whole point
 * of keeping this function. `week` is still accepted in the argument object
 * so callers need not strip it.
 */
export function resolveLegacyParams(quarters, { quarter, year }) {
  const match = sortedByStart(quarters).find(
    (q) => q.season === quarter && Number(q.year) === Number(year),
  );
  if (!match) return null;
  return { quarter_id: match.id };
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
