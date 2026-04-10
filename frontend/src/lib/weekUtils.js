/**
 * weekUtils.js
 *
 * Pure week navigation utilities for UCSB quarter-based scheduling.
 * Quarters cycle: winter → spring → summer → fall → winter (next year).
 * Each quarter has exactly 11 teaching weeks (MAX_WEEK).
 *
 * No side effects. No network calls. Safe to use in any rendering context.
 */

const QUARTER_ORDER = ["winter", "spring", "summer", "fall"];
const MAX_WEEK = 11;

/**
 * Return the {quarter, year, week_number} for the week after the given one.
 * Rolls over quarter boundaries: week 11 advances to next quarter week 1.
 * When "fall" rolls over, year increments.
 *
 * @param {string} quarter - "winter" | "spring" | "summer" | "fall"
 * @param {number} year
 * @param {number} weekNumber - 1–11
 * @returns {{ quarter: string, year: number, week_number: number }}
 */
export function getNextWeek(quarter, year, weekNumber) {
  if (weekNumber < MAX_WEEK) {
    return { quarter, year, week_number: weekNumber + 1 };
  }
  // Roll over to next quarter
  const idx = QUARTER_ORDER.indexOf(quarter);
  const nextIdx = (idx + 1) % QUARTER_ORDER.length;
  const nextQuarter = QUARTER_ORDER[nextIdx];
  const nextYear = nextQuarter === "winter" ? year + 1 : year;
  return { quarter: nextQuarter, year: nextYear, week_number: 1 };
}

/**
 * Return the {quarter, year, week_number} for the week before the given one.
 * Rolls over quarter boundaries: week 1 goes back to previous quarter week 11.
 * When "winter" rolls back, year decrements.
 *
 * @param {string} quarter - "winter" | "spring" | "summer" | "fall"
 * @param {number} year
 * @param {number} weekNumber - 1–11
 * @returns {{ quarter: string, year: number, week_number: number }}
 */
export function getPrevWeek(quarter, year, weekNumber) {
  if (weekNumber > 1) {
    return { quarter, year, week_number: weekNumber - 1 };
  }
  // Roll back to previous quarter
  const idx = QUARTER_ORDER.indexOf(quarter);
  const prevIdx = (idx - 1 + QUARTER_ORDER.length) % QUARTER_ORDER.length;
  const prevQuarter = QUARTER_ORDER[prevIdx];
  const prevYear = quarter === "winter" ? year - 1 : year;
  return { quarter: prevQuarter, year: prevYear, week_number: MAX_WEEK };
}

/**
 * Return a human-readable week label, e.g. "Spring 2026 - Week 3".
 *
 * @param {string} quarter - "winter" | "spring" | "summer" | "fall"
 * @param {number} year
 * @param {number} weekNumber - 1–11
 * @returns {string}
 */
export function formatWeekLabel(quarter, year, weekNumber) {
  const capitalised = quarter.charAt(0).toUpperCase() + quarter.slice(1);
  return `${capitalised} ${year} - Week ${weekNumber}`;
}
