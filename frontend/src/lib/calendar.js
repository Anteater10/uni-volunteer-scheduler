/**
 * calendar.js
 *
 * iCalendar (RFC 5545) .ics file generation for SciTrek events.
 * buildIcs() is pure and safe for any rendering context.
 * downloadIcs() has a DOM side effect (Blob + anchor click); browser-only.
 *
 * No backend calls. No external dependencies. Floating-time DTSTART per
 * RFC 5545 §3.3.5 (event shows at venue's local time across timezones).
 */

/** Escape per RFC 5545 §3.3.11. Newlines, commas, semicolons, backslashes. */
function escapeText(s) {
  if (!s) return ''
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

/** RFC 5545 DATE-TIME floating form: 20260422T090000 (no Z, no TZID). */
function toFloatingDt(iso) {
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return (
    d.getFullYear() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    'T' +
    pad(d.getHours()) +
    pad(d.getMinutes()) +
    pad(d.getSeconds())
  )
}

/** UTC DTSTAMP per §3.8.7.2. Required. Must be UTC DATE-TIME with Z suffix. */
function toUtcDtStamp(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return (
    date.getUTCFullYear() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    'T' +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds()) +
    'Z'
  )
}

/**
 * Build VCALENDAR for one event + one slot. CRLF line endings per §3.1.
 *
 * @param {object} params
 * @param {object} params.event - { id, title, description?, school?, slug? }
 * @param {object} params.slot - { id, start_time, end_time, location? }
 * @param {string} params.origin - e.g. window.location.origin (URL DESCRIPTION anchor)
 * @returns {string} Full VCALENDAR document (CRLF terminated)
 */
export function buildIcs({ event, slot, origin }) {
  const uid = `scitrek-${event.id}-slot-${slot.id}@scitrek.ucsb.edu`
  const url = `${origin}/events/${event.id}`
  const summary = `Sci Trek: ${event.title}`
  const location = slot.location || event.school || ''
  const description = (event.description || '') + (event.description ? '\n' : '') + url

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//SciTrek//Volunteer Scheduler//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${toUtcDtStamp()}`,
    `DTSTART:${toFloatingDt(slot.start_time)}`,
    `DTEND:${toFloatingDt(slot.end_time)}`,
    `SUMMARY:${escapeText(summary)}`,
    `LOCATION:${escapeText(location)}`,
    `DESCRIPTION:${escapeText(description)}`,
    `URL:${url}`,
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    'TRIGGER:-PT1H',
    'DESCRIPTION:Sci Trek event reminder',
    'END:VALARM',
    'END:VEVENT',
    'END:VCALENDAR',
  ]
  return lines.join('\r\n') + '\r\n'
}

/**
 * Generate .ics for {event, slot} and trigger a download in the browser.
 * DOM side effects: creates Blob, anchor element, clicks it, revokes object URL.
 *
 * @param {object} params
 * @param {object} params.event
 * @param {object} params.slot
 * @param {string} params.filename - e.g. "scitrek-{event-slug}-{yyyy-mm-dd}.ics"
 */
export function downloadIcs({ event, slot, filename }) {
  const ics = buildIcs({ event, slot, origin: window.location.origin })
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
