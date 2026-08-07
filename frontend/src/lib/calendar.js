/**
 * calendar.js
 *
 * iCalendar (RFC 5545) .ics generation for SciTrek events, plus a Google
 * Calendar "add event" URL.
 *
 * buildIcs() is pure and safe in any rendering context.
 * downloadIcs() touches the DOM (Blob + anchor click); browser-only.
 *
 * No backend calls, no dependencies.
 *
 * ## Times are absolute, written as UTC
 *
 * The API hands us instants in UTC ("2026-07-26T14:00:00Z"), and a SciTrek
 * slot is a real appointment at a real school at a fixed moment. So DTSTART
 * and DTEND are emitted as UTC DATE-TIME with the Z suffix (RFC 5545 §3.3.5
 * form 2), which every calendar client converts into whatever timezone the
 * viewer is actually in.
 *
 * This replaced floating time (no Z, no TZID), which was wrong twice over:
 * the value was derived from the *downloading device's* clock, so the same
 * slot produced a different file on a Pacific laptop than on an Eastern one;
 * and floating time is then re-interpreted in the *importing* calendar's
 * timezone, so a volunteer whose phone disagreed with the machine that made
 * the file saw the wrong hour. UTC has neither problem and needs no
 * VTIMEZONE block.
 */

const PRODID = '-//SciTrek//Volunteer Scheduler//EN'
const UID_DOMAIN = 'scitrek.ucsb.edu'

/** Escape per RFC 5545 §3.3.11: backslash, newline, comma, semicolon. */
function escapeText(s) {
  if (!s) return ''
  return (
    String(s)
      // Normalise first: a description typed into a textarea can arrive with
      // CRLF or bare CR, and a raw CR inside a property value corrupts the
      // file's line structure.
      .replace(/\r\n?/g, '\n')
      .replace(/\\/g, '\\\\')
      .replace(/\n/g, '\\n')
      .replace(/,/g, '\\,')
      .replace(/;/g, '\\;')
  )
}

/**
 * Fold a content line to 75 octets per RFC 5545 §3.1.
 *
 * Long values — a wordy description, a school name with a full address — are
 * otherwise emitted as one over-length line, which strict parsers (Outlook
 * among them) truncate or reject. Continuation lines begin with a single
 * space, which parsers strip when unfolding.
 *
 * Counts UTF-8 octets rather than characters, and never splits a multi-byte
 * character, so an em dash or an accented name can't be cut in half.
 */
function foldLine(line) {
  const encoder = new TextEncoder()
  if (encoder.encode(line).length <= 75) return line

  const parts = []
  let current = ''
  let currentBytes = 0
  // First line may use all 75 octets; continuations spend one on the leading
  // space that marks them as continuations.
  let limit = 75

  for (const ch of line) {
    const chBytes = encoder.encode(ch).length
    if (currentBytes + chBytes > limit) {
      parts.push(current)
      current = ch
      currentBytes = chBytes
      limit = 74
    } else {
      current += ch
      currentBytes += chBytes
    }
  }
  if (current) parts.push(current)
  return parts.join('\r\n ')
}

function pad(n) {
  return String(n).padStart(2, '0')
}

/**
 * RFC 5545 UTC DATE-TIME: 20260726T140000Z.
 *
 * Throws on an unparseable input rather than emitting "NaNNaNNaN", which
 * would produce a file that silently fails to import.
 */
function toUtcDt(value, field) {
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) {
    throw new Error(`Calendar export: ${field} is not a valid date (${value})`)
  }
  return (
    d.getUTCFullYear() +
    pad(d.getUTCMonth() + 1) +
    pad(d.getUTCDate()) +
    'T' +
    pad(d.getUTCHours()) +
    pad(d.getUTCMinutes()) +
    pad(d.getUTCSeconds()) +
    'Z'
  )
}

/** Canonical public page for an event — the volunteer-facing detail route. */
function eventUrl(origin, eventId) {
  return `${origin}/volunteer/events/${eventId}`
}

/** Where the volunteer should physically go, most specific source first. */
function resolveLocation(event, slot) {
  return slot.location || event.location || event.school || ''
}

/**
 * Human label for a slot, used to tell an orientation apart from a teaching
 * period when someone has both on their calendar.
 */
function slotKindLabel(slot) {
  return slot.slot_type === 'orientation' ? 'Orientation' : null
}

/**
 * Stable, unique suffix for a slot's UID.
 *
 * Slot objects reach us from several payloads and not all of them carry an
 * id. Falling back to the start instant keeps UIDs distinct — sharing one UID
 * across VEVENTs makes calendars collapse them into a single entry, silently
 * dropping sessions the volunteer signed up for.
 */
function slotUidPart(slot, index) {
  if (slot.id !== undefined && slot.id !== null && slot.id !== '') {
    return `slot-${slot.id}`
  }
  if (slot.start_time) return `at-${toUtcDt(slot.start_time, 'slot start time')}`
  return `n${index}`
}

function buildVevent({ event, slot, origin, dtstamp, index }) {
  const kind = slotKindLabel(slot)
  const summary = kind
    ? `SciTrek: ${event.title} (${kind})`
    : `SciTrek: ${event.title}`
  const url = eventUrl(origin, event.id)

  const descriptionParts = []
  if (event.description) descriptionParts.push(event.description)
  if (kind) {
    descriptionParts.push(
      'This is the orientation session — attend it before your first teaching period.',
    )
  }
  descriptionParts.push(url)

  const lines = [
    'BEGIN:VEVENT',
    // Stable per slot, so re-importing updates the entry instead of creating
    // a duplicate.
    `UID:scitrek-${event.id}-${slotUidPart(slot, index)}@${UID_DOMAIN}`,
    `DTSTAMP:${dtstamp}`,
    `DTSTART:${toUtcDt(slot.start_time, 'slot start time')}`,
    `DTEND:${toUtcDt(slot.end_time, 'slot end time')}`,
    `SUMMARY:${escapeText(summary)}`,
    `LOCATION:${escapeText(resolveLocation(event, slot))}`,
    `DESCRIPTION:${escapeText(descriptionParts.join('\n\n'))}`,
    `URL:${url}`,
    // SEQUENCE lets a client recognise a later export of the same slot as a
    // revision. STATUS/TRANSP stop clients guessing: this is a real
    // commitment and it should show the volunteer as busy.
    'SEQUENCE:0',
    'STATUS:CONFIRMED',
    'TRANSP:OPAQUE',
    // Two reminders: the night before to arrange travel, and an hour ahead to
    // actually leave. School-day starts are early enough that -PT1H alone
    // tends to fire while the volunteer is still asleep.
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    'TRIGGER:-P1D',
    'DESCRIPTION:SciTrek event tomorrow',
    'END:VALARM',
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    'TRIGGER:-PT1H',
    'DESCRIPTION:SciTrek event reminder',
    'END:VALARM',
    'END:VEVENT',
  ]
  return lines
}

/**
 * Build a VCALENDAR for one event and one or more of its slots.
 *
 * @param {object} params
 * @param {object} params.event - { id, title, description?, location?, school? }
 * @param {object} [params.slot] - single slot: { id, start_time, end_time, location?, slot_type? }
 * @param {object[]} [params.slots] - several slots, each emitted as its own VEVENT
 * @param {string} params.origin - e.g. window.location.origin
 * @returns {string} VCALENDAR document, CRLF terminated
 */
export function buildIcs({ event, slot, slots, origin }) {
  const list = (slots && slots.length ? slots : [slot]).filter(Boolean)
  if (!event) throw new Error('Calendar export: event is required')
  if (list.length === 0) {
    throw new Error('Calendar export: at least one slot is required')
  }

  // One timestamp for the whole document: every VEVENT in a single export was
  // generated at the same moment.
  const dtstamp = toUtcDt(new Date(), 'now')

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:${PRODID}`,
    'CALSCALE:GREGORIAN',
    // Required by Outlook to treat the file as a publishable calendar rather
    // than a meeting request it should RSVP to.
    'METHOD:PUBLISH',
  ]
  list.forEach((s, index) => {
    lines.push(...buildVevent({ event, slot: s, origin, dtstamp, index }))
  })
  lines.push('END:VCALENDAR')

  return lines.map(foldLine).join('\r\n') + '\r\n'
}

/**
 * Build a Google Calendar "event template" URL. Opening it lands the user on
 * a pre-filled event-creation page; they press Save.
 *
 * No OAuth, no API call. Dates are UTC, which Google interprets correctly and
 * renders in the user's own calendar timezone.
 *
 * Google's template URL carries a single event, so when a volunteer took
 * several slots this covers the one passed in — the .ics download is the route
 * that carries all of them.
 *
 * @returns {string} https://calendar.google.com/calendar/render?... URL
 */
export function buildGoogleCalendarUrl({ event, slot, origin }) {
  // Google accepts the same compact UTC form the .ics uses.
  const dates = `${toUtcDt(slot.start_time, 'slot start time')}/${toUtcDt(
    slot.end_time,
    'slot end time',
  )}`
  const url = eventUrl(origin, event.id)
  const kind = slotKindLabel(slot)
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: kind ? `SciTrek: ${event.title} (${kind})` : `SciTrek: ${event.title}`,
    dates,
    details: (event.description ? `${event.description}\n\n` : '') + url,
    location: resolveLocation(event, slot),
  })
  return `https://calendar.google.com/calendar/render?${params.toString()}`
}

/**
 * Turn arbitrary text into something every OS accepts as a filename.
 *
 * Callers were building names from raw ISO timestamps, which put colons in
 * the download — illegal on Windows, and silently rewritten on macOS.
 */
export function safeIcsFilename(name) {
  const cleaned = String(name || 'scitrek-event')
    .replace(/\.ics$/i, '')
    // Anything not alphanumeric, dash, underscore or dot becomes a dash.
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '')
    .slice(0, 120)
  return `${cleaned || 'scitrek-event'}.ics`
}

/**
 * Best readable stem for an event's filename.
 *
 * Events don't always carry a slug, and falling straight through to the id put
 * a bare UUID in the volunteer's downloads folder. The title slugified is far
 * more use to someone scanning that folder later; the id stays as a last
 * resort.
 */
function eventFilenameStem(event) {
  if (event?.slug) return event.slug
  const fromTitle = String(event?.title || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    // Long enough to identify the event, short enough to leave room for the
    // date and to stay well inside filesystem name limits.
    .slice(0, 48)
    .replace(/-+$/, '')
  return fromTitle || event?.id || 'event'
}

/**
 * Default filename for an export: scitrek-{slug|title|id}-{YYYY-MM-DD}.ics,
 * dated from the first slot so a volunteer's downloads folder stays sortable.
 */
export function icsFilenameFor({ event, slot, slots }) {
  const first = (slots && slots.length ? slots : [slot]).filter(Boolean)[0]
  const iso = first?.start_time
  let datePart = ''
  if (iso) {
    const d = new Date(iso)
    if (!Number.isNaN(d.getTime())) datePart = d.toISOString().slice(0, 10)
  }
  const slugPart = eventFilenameStem(event)
  const multi = slots && slots.length > 1 ? '-slots' : ''
  return safeIcsFilename(
    `scitrek-${slugPart}${multi}${datePart ? `-${datePart}` : ''}`,
  )
}

/**
 * Generate the .ics and trigger a browser download.
 *
 * DOM side effects: creates a Blob, appends an anchor, clicks it, revokes the
 * object URL. The filename is sanitised, and derived from the event when the
 * caller doesn't supply one.
 */
export function downloadIcs({ event, slot, slots, filename }) {
  const ics = buildIcs({ event, slot, slots, origin: window.location.origin })
  const name = filename
    ? safeIcsFilename(filename)
    : icsFilenameFor({ event, slot, slots })

  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return name
}
