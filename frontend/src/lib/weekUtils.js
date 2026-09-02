/**
 * weekUtils.js — issue #24, reworked for SCRUM-48.
 *
 * Quarter selectors over the admin-entered quarter rows returned by
 * GET /public/quarters (see useQuarters), plus the public browse page's
 * navigation.
 *
 * SCRUM-48: that navigation used to step one week at a time. Volunteers don't
 * think in weeks — they want a whole quarter for the level they teach — so it
 * now steps through (quarter × school level) pairs instead. The control is the
 * same pair of arrows; only what it walks changed. Two levels per quarter
 * means three quarters gives six positions.
 *
 * Navigation returns null past the ends so callers can disable arrows.
 *
 * No side effects. No network calls. Safe to use in any rendering context.
 */

/**
 * The school levels a volunteer browses by, in stepper order.
 *
 * `both` is deliberately absent: it is a property a *module* can have, not a
 * tab a volunteer picks. A `both` module's events surface under either level
 * (the backend's filter includes them in each), so giving it its own position
 * would add a tab nobody needs and hide those events from the two that matter.
 */
export const SCHOOL_BRANCHES = ["middle_school", "high_school"];

const SCHOOL_BRANCH_LABELS = {
  middle_school: "Middle School",
  high_school: "High School",
};

/** The level a quarter opens on when none is specified. */
export const DEFAULT_SCHOOL_BRANCH = SCHOOL_BRANCHES[0];

export function isSchoolBranch(value) {
  return SCHOOL_BRANCHES.includes(value);
}

function sortedByStart(quarters) {
  return [...(quarters || [])].sort((a, b) =>
    a.start_date < b.start_date ? -1 : a.start_date > b.start_date ? 1 : 0,
  );
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
 * The position after {quarterId, schoolBranch}.
 *
 * Walks levels within a quarter first, then rolls into the next entered
 * (non-archived) row at its first level. Null past the last position. Inside
 * an archived row (deep link, issue #33) navigation clamps to that row — it
 * never rolls out into the live schedule.
 */
export function getNextQuarterLevel(quarters, quarterId, schoolBranch) {
  const row = findQuarterById(quarters, quarterId);
  if (!row) return null;
  const levelIndex = SCHOOL_BRANCHES.indexOf(schoolBranch);
  if (levelIndex === -1) return null;
  if (levelIndex < SCHOOL_BRANCHES.length - 1) {
    return {
      quarter_id: quarterId,
      school_branch: SCHOOL_BRANCHES[levelIndex + 1],
    };
  }
  if (row.archived_at) return null;
  const list = activeQuarters(quarters);
  const next = list[list.findIndex((q) => q.id === quarterId) + 1];
  return next
    ? { quarter_id: next.id, school_branch: SCHOOL_BRANCHES[0] }
    : null;
}

/**
 * The position before {quarterId, schoolBranch}, rolling back into the
 * previous entered (non-archived) row's last level. Null before the first
 * position. Clamped inside archived rows, mirroring getNextQuarterLevel.
 */
export function getPrevQuarterLevel(quarters, quarterId, schoolBranch) {
  const row = findQuarterById(quarters, quarterId);
  if (!row) return null;
  const levelIndex = SCHOOL_BRANCHES.indexOf(schoolBranch);
  if (levelIndex === -1) return null;
  if (levelIndex > 0) {
    return {
      quarter_id: quarterId,
      school_branch: SCHOOL_BRANCHES[levelIndex - 1],
    };
  }
  if (row.archived_at) return null;
  const list = activeQuarters(quarters);
  const prev = list[list.findIndex((q) => q.id === quarterId) - 1];
  return prev
    ? {
        quarter_id: prev.id,
        school_branch: SCHOOL_BRANCHES[SCHOOL_BRANCHES.length - 1],
      }
    : null;
}

/** "Summer 2026 · Session A — Middle School" */
export function formatQuarterLevelLabel(quarterRow, schoolBranch) {
  const level = SCHOOL_BRANCH_LABELS[schoolBranch] || "";
  if (!quarterRow) return level;
  return level ? `${quarterRow.display_name} — ${level}` : quarterRow.display_name;
}

/**
 * Resolve a legacy ?quarter=&year= link onto a quarter row.
 *
 * SCRUM-48: these links used to carry &week=N too. The week is now ignored
 * rather than rejected — an old bookmark or emailed link lands on the same
 * quarter's default level instead of erroring, which is the whole point of
 * keeping this function. `week` is still accepted in the argument object so
 * callers need not strip it.
 */
export function resolveLegacyParams(quarters, { quarter, year }) {
  const match = sortedByStart(quarters).find(
    (q) => q.season === quarter && Number(q.year) === Number(year),
  );
  if (!match) return null;
  return { quarter_id: match.id, school_branch: DEFAULT_SCHOOL_BRANCH };
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
