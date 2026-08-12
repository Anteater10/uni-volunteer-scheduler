// Every date and time in this app is the venue's wall clock at UCSB.
//
// The server stores instants in UTC, which is correct, and the browser will
// happily render them in whatever timezone the laptop happens to be set to,
// which is not. An event whose last session ends Friday at 3pm is stored as
// ending Friday 23:59 Pacific — 06:59 UTC on Saturday — so a browser an hour
// or more east of Pacific printed "Sat, Aug 29" for an event that finishes on
// Friday the 28th. Nothing about that looks like a bug; it looks like a date.
//
// The public event page had already worked this out and kept its own
// VENUE_TZ constant. The admin pages each grew their own copy of the same
// formatter with `undefined` where the timezone belongs, and inherited the
// browser's. This module is the one copy, so there is nowhere left to get it
// wrong.
export const VENUE_TZ = "America/Los_Angeles";

function toDate(iso) {
  if (!iso) return null;
  const raw = String(iso);
  // A date-only value is a calendar day, not an instant, and it has to
  // survive being rendered in Pacific from a browser anywhere. Midnight is
  // the worst possible anchor for that in either direction: UTC midnight is
  // the previous afternoon in Pacific, and local midnight is the previous
  // day in Pacific for any browser east of it. Noon UTC is mid-morning
  // Pacific and stays on the stated day from every timezone on earth.
  const d = new Date(raw.includes("T") ? raw : `${raw}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "Aug 17, 2026 at 5:00 PM" in venue time. */
export function fmtVenueDateTime(iso, fallback = "—") {
  const d = toDate(iso);
  if (!d) return fallback;
  return d.toLocaleString("en-US", {
    timeZone: VENUE_TZ,
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** "Mon, Aug 17" in venue time. */
export function fmtVenueDate(iso, fallback = "") {
  const d = toDate(iso);
  if (!d) return fallback;
  return d.toLocaleDateString("en-US", {
    timeZone: VENUE_TZ,
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/** "Monday" in venue time. */
export function fmtVenueWeekday(iso, fallback = "") {
  const d = toDate(iso);
  if (!d) return fallback;
  return d.toLocaleDateString("en-US", {
    timeZone: VENUE_TZ,
    weekday: "long",
  });
}
