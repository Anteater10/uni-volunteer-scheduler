/**
 * duplicateEvent.js — shift math + prefill builder for the duplicate flow.
 *
 * Duplicating an event means prefilling the ordinary create form from a
 * source event, with every date shifted so it lands in the chosen week of
 * the chosen target quarter. The shifted values are suggestions — the admin
 * edits anything (rooms move, days change) before creating.
 *
 * Week math mirrors backend quarter_service: week N of a quarter starts
 * (N-1) whole weeks after the row's start_date. Day arithmetic on plain
 * dates runs at UTC noon so DST transitions can't skew a day.
 */

import { activeQuarters } from "./weekUtils";

const DAY_MS = 24 * 60 * 60 * 1000;

function isoDateToUtcNoon(isoDate) {
  const [y, m, d] = String(isoDate).slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d, 12);
}

function utcMsToIsoDate(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

/** "2026-03-30" + 14 → "2026-04-13". Negative days allowed. */
export function addDaysIso(isoDate, days) {
  return utcMsToIsoDate(isoDateToUtcNoon(isoDate) + days * DAY_MS);
}

function daysBetweenIso(fromIsoDate, toIsoDate) {
  return Math.round(
    (isoDateToUtcNoon(toIsoDate) - isoDateToUtcNoon(fromIsoDate)) / DAY_MS,
  );
}

/** The calendar date week `weekNumber` of `quarterRow` starts on. */
export function weekStartIso(quarterRow, weekNumber) {
  return addDaysIso(quarterRow.start_date, (weekNumber - 1) * 7);
}

/** "Oct 12 – Oct 18" for the week-picker options. */
export function weekRangeLabel(quarterRow, weekNumber) {
  const startIso = weekStartIso(quarterRow, weekNumber);
  const fmt = (isoDate) =>
    new Date(isoDateToUtcNoon(isoDate)).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
  return `${fmt(startIso)} – ${fmt(addDaysIso(startIso, 6))}`;
}

/** Local calendar date of an ISO datetime — matches what the form shows. */
function localDateIso(isoDateTime) {
  const d = new Date(isoDateTime);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Whole-day shift that moves the source event into `targetWeek` of
 * `targetRow`, preserving weekday-within-week and times.
 *
 * Anchors on the source's own week start when its quarter row is known;
 * legacy events without a resolvable row anchor on their start date, which
 * puts the (editable) suggested start on the target week's first day.
 */
export function computeShiftDays({ sourceEvent, sourceRow, targetRow, targetWeek }) {
  const targetAnchor = weekStartIso(targetRow, targetWeek);
  const sourceAnchor =
    sourceRow && sourceEvent?.week_number
      ? weekStartIso(sourceRow, sourceEvent.week_number)
      : localDateIso(sourceEvent.start_date);
  return daysBetweenIso(sourceAnchor, targetAnchor);
}

/** Shift an ISO datetime by whole days, preserving local wall-clock time. */
function shiftIsoDateTime(isoDateTime, days) {
  const d = new Date(isoDateTime);
  d.setDate(d.getDate() + days);
  return d.toISOString();
}

/**
 * The `initial` object for EventForm (mode="create"): the source event with
 * all datetimes shifted, ids and signup counts stripped, slots sorted by
 * start time.
 *
 * 2026-08-02 shifts: the classroom work now lives in `sourceEvent.shifts`, so
 * a copy that only carried `slots` would silently drop it — and could not be
 * saved anyway, since a period slot without a shift violates
 * ck_slots_shift_membership_matches_type. Shifts are copied whole (name,
 * capacity, ordered sessions), which is the point of the feature: the bundle
 * an admin built once is the thing worth duplicating.
 *
 * Ids and counts are stripped from both levels. Copying a shift id would make
 * EventForm treat the copy as an existing row, and copying `current_count`
 * would gate deletion on signups that belong to the *source* event.
 */
export function buildDuplicateInitial(sourceEvent, shiftDays) {
  const slots = (sourceEvent.slots || [])
    .slice()
    .sort((a, b) => new Date(a.start_time) - new Date(b.start_time))
    .map((s) => ({
      slot_type: s.slot_type || "period",
      start_time: shiftIsoDateTime(s.start_time, shiftDays),
      end_time: shiftIsoDateTime(s.end_time, shiftDays),
      capacity: s.capacity,
      location: s.location || "",
    }));

  // Session order is the organizer's, so `sort_order` leads and start time
  // only breaks ties — the same precedence the shift builder and the
  // volunteer-facing cards use.
  const shifts = (sourceEvent.shifts || [])
    .slice()
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    .map((shift, shiftIndex) => ({
      name: shift.name || "",
      capacity: shift.capacity,
      current_count: 0,
      sort_order: shiftIndex,
      sessions: [...(shift.sessions || [])]
        .sort(
          (a, b) =>
            (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
            new Date(a.start_time) - new Date(b.start_time),
        )
        .map((s, sessionIndex) => ({
          name: s.name || "",
          start_time: shiftIsoDateTime(s.start_time, shiftDays),
          end_time: shiftIsoDateTime(s.end_time, shiftDays),
          location: s.location || "",
          sort_order: sessionIndex,
        })),
    }));

  return {
    shifts,
    title: sourceEvent.title || "",
    description: sourceEvent.description || "",
    location: sourceEvent.location || "",
    school: sourceEvent.school || "",
    visibility: sourceEvent.visibility || "public",
    max_signups_per_user: sourceEvent.max_signups_per_user ?? "",
    module_slug: sourceEvent.module_slug || "",
    start_date: shiftIsoDateTime(sourceEvent.start_date, shiftDays),
    end_date: shiftIsoDateTime(sourceEvent.end_date, shiftDays),
    slots,
  };
}

/**
 * Default duplication target: the active quarter containing today, else the
 * next upcoming one, else the most recent active row. Null with no rows.
 */
export function defaultTargetQuarterId(quarters, todayIso) {
  const rows = activeQuarters(quarters || []);
  if (rows.length === 0) return null;
  const containing = rows.find(
    (q) => q.start_date <= todayIso && q.end_date >= todayIso,
  );
  if (containing) return containing.id;
  const upcoming = rows.find((q) => q.start_date > todayIso);
  if (upcoming) return upcoming.id;
  return rows[rows.length - 1].id;
}

function clampWeek(week, targetRow) {
  return Math.max(1, Math.min(targetRow.weeks_in_quarter, week));
}

/**
 * Default target week. Cross-quarter copies mirror the source's week number
 * ("week 3 of spring" → "week 3 of fall"); same-quarter copies bump to the
 * next week, since re-creating the same week is never the intent.
 */
export function defaultTargetWeek({ sourceEvent, sourceRow, targetRow }) {
  const sourceWeek = sourceEvent?.week_number || 1;
  if (sourceRow && sourceRow.id === targetRow.id) {
    return clampWeek(sourceWeek + 1, targetRow);
  }
  return clampWeek(sourceWeek, targetRow);
}
