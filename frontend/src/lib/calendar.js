// PLACEHOLDER: minimal downloadIcs shipped by Plan 15-04 so the build resolves
// while Plan 15-02 is in flight. Plan 15-02 ships the full RFC 5545 generator
// (proper VCALENDAR/VEVENT, escape sequences, CRLF line endings).
// API (downloadIcs({event, slot, filename})) is locked by Plan 02 contract;
// the merge replaces this file with no API change.

function pad(n) {
  return String(n).padStart(2, '0')
}

function toIcsDate(input) {
  if (!input) return ''
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return ''
  // Local-time form: YYYYMMDDTHHmmss (Plan 02 will produce proper UTC + DTSTAMP)
  return (
    d.getFullYear().toString() +
    pad(d.getMonth() + 1) +
    pad(d.getDate()) +
    'T' +
    pad(d.getHours()) +
    pad(d.getMinutes()) +
    pad(d.getSeconds())
  )
}

function escapeText(s) {
  if (s == null) return ''
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

export function downloadIcs({ event, slot, filename }) {
  if (!event || !slot) return
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//UCSB SciTrek//Volunteer Scheduler//EN',
    'BEGIN:VEVENT',
    `UID:scitrek-${event.id || event.slug || 'event'}-${slot.id || 'slot'}@scitrek.ucsb.edu`,
    `SUMMARY:${escapeText(event.title || 'SciTrek Event')}`,
    `DTSTART:${toIcsDate(slot.start_time)}`,
    `DTEND:${toIcsDate(slot.end_time)}`,
  ]
  if (slot.location) lines.push(`LOCATION:${escapeText(slot.location)}`)
  if (event.description) lines.push(`DESCRIPTION:${escapeText(event.description)}`)
  lines.push('END:VEVENT', 'END:VCALENDAR')
  const ics = lines.join('\r\n')

  if (typeof document === 'undefined' || typeof URL === 'undefined') return

  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'event.ics'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export default downloadIcs
