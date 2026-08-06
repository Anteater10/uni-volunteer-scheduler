/**
 * calendar.test.js
 *
 * Tests for RFC 5545 iCalendar (.ics) generation, the Google Calendar template
 * URL, and the download util.
 *
 * Note on times: the API returns UTC instants ("2026-07-26T14:00:00Z") and the
 * exporter emits UTC DATE-TIME. The suite previously asserted floating time,
 * which was wrong — floating values were derived from the downloading device's
 * clock, so the same slot produced a different file per machine and was then
 * re-read in the importing calendar's timezone. Those assertions are now
 * inverted deliberately, and `is identical regardless of the generating
 * machine's timezone` guards the regression.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  buildIcs,
  buildGoogleCalendarUrl,
  downloadIcs,
  safeIcsFilename,
  icsFilenameFor,
} from '../calendar'

const FIXTURE_EVENT = {
  id: 42,
  title: 'Rocket Physics @ Goleta Valley JH',
  description: 'Hands-on rocket lab for 7th graders',
  school: 'Goleta Valley JH',
  slug: 'rocket-physics',
  start_date: '2026-04-22T16:00:00Z',
}
const FIXTURE_SLOT = {
  id: 7,
  slot_type: 'period',
  start_time: '2026-04-22T16:00:00Z',
  end_time: '2026-04-22T18:00:00Z',
  location: 'Goleta Valley JH Room 12',
}
const SECOND_SLOT = {
  id: 8,
  slot_type: 'period',
  start_time: '2026-04-23T16:00:00Z',
  end_time: '2026-04-23T18:00:00Z',
  location: 'Goleta Valley JH Room 12',
}
const ORIGIN = 'https://scitrek.test'

const build = (over = {}) =>
  buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN, ...over })

/** Undo RFC 5545 folding so assertions can match whole property values. */
const unfold = (ics) => ics.replace(/\r\n /g, '')

describe('buildIcs — envelope', () => {
  it('contains the required calendar properties', () => {
    const out = build()
    expect(out).toContain('BEGIN:VCALENDAR')
    expect(out).toContain('VERSION:2.0')
    expect(out).toContain('PRODID:-//SciTrek//Volunteer Scheduler//EN')
    expect(out).toContain('CALSCALE:GREGORIAN')
    expect(out).toContain('END:VCALENDAR')
  })

  it('declares METHOD:PUBLISH so Outlook treats it as a calendar, not an RSVP', () => {
    expect(build()).toContain('METHOD:PUBLISH')
  })
})

describe('buildIcs — times are absolute UTC', () => {
  it('DTSTART and DTEND carry the Z suffix', () => {
    const out = build()
    expect(out).toContain('DTSTART:20260422T160000Z')
    expect(out).toContain('DTEND:20260422T180000Z')
  })

  it('DTSTAMP is UTC form with Z suffix', () => {
    expect(build()).toMatch(/DTSTAMP:\d{8}T\d{6}Z/)
  })

  it('reads the instant in UTC, not the local clock', () => {
    // The regression that motivated the rewrite: the old exporter read the
    // instant through the *downloading device's* clock, so one slot produced a
    // different file on a Pacific laptop than on an Eastern one. Feeding the
    // same instant in three notations must give one answer — a local-clock
    // reader would return three different ones on any machine outside UTC.
    const dtstartOf = (ics) => /DTSTART:[^\r\n]+/.exec(ics)[0]
    const sameInstant = [
      '2026-04-22T16:00:00Z',
      '2026-04-22T09:00:00-07:00',
      '2026-04-22T18:00:00+02:00',
    ]
    const seen = new Set(
      sameInstant.map((start_time) =>
        dtstartOf(build({ slot: { ...FIXTURE_SLOT, start_time } })),
      ),
    )
    expect([...seen]).toEqual(['DTSTART:20260422T160000Z'])
  })

  it('throws a clear error rather than emitting NaN for a bad date', () => {
    expect(() =>
      build({ slot: { ...FIXTURE_SLOT, start_time: 'not-a-date' } }),
    ).toThrow(/not a valid date/i)
  })
})

describe('buildIcs — required VEVENT fields', () => {
  it('UID is stable and namespaced per slot', () => {
    expect(build()).toContain('UID:scitrek-42-slot-7@scitrek.ucsb.edu')
  })

  it('falls back to the start instant when a slot has no id', () => {
    // Some payloads hand us slots without ids; two such slots must not share
    // a UID, or calendars collapse them into one entry.
    const a = { ...FIXTURE_SLOT, id: undefined }
    const b = { ...SECOND_SLOT, id: undefined }
    const out = build({ slot: undefined, slots: [a, b] })
    const uids = [...out.matchAll(/UID:([^\r\n]+)/g)].map((m) => m[1])
    expect(uids).toHaveLength(2)
    expect(new Set(uids).size).toBe(2)
  })

  it('marks the entry confirmed, busy, and at sequence 0', () => {
    const out = build()
    expect(out).toContain('STATUS:CONFIRMED')
    expect(out).toContain('TRANSP:OPAQUE')
    expect(out).toContain('SEQUENCE:0')
  })
})

describe('buildIcs — escaping (RFC 5545 §3.3.11)', () => {
  it('escapes commas, semicolons, backslashes and newlines', () => {
    const event = { ...FIXTURE_EVENT, description: 'Line1, part;two\\slash\nline2' }
    const out = unfold(build({ event }))
    expect(out).toContain('Line1\\, part\\;two\\\\slash\\nline2')
  })

  it('escapes the same characters in SUMMARY', () => {
    const event = { ...FIXTURE_EVENT, title: 'Ev,ent;One\\Two' }
    expect(unfold(build({ event }))).toContain(
      'SUMMARY:SciTrek: Ev\\,ent\\;One\\\\Two',
    )
  })

  it('normalises CRLF in input so no raw CR lands inside a value', () => {
    const event = { ...FIXTURE_EVENT, description: 'first\r\nsecond\rthird' }
    const out = build({ event })
    expect(unfold(out)).toContain('first\\nsecond\\nthird')
    // Every CR in the document must be part of a CRLF line ending.
    expect(out.replace(/\r\n/g, '')).not.toContain('\r')
  })
})

describe('buildIcs — line folding (RFC 5545 §3.1)', () => {
  it('folds content lines longer than 75 octets', () => {
    const event = { ...FIXTURE_EVENT, description: 'x'.repeat(400) }
    const out = build({ event })
    const overLong = out
      .split('\r\n')
      .filter((l) => new TextEncoder().encode(l).length > 75)
    expect(overLong).toEqual([])
  })

  it('folds so the value survives unfolding intact', () => {
    const long = 'y'.repeat(300)
    const out = build({ event: { ...FIXTURE_EVENT, description: long } })
    expect(unfold(out)).toContain(`DESCRIPTION:${long}`)
  })

  it('never splits a multi-byte character across a fold', () => {
    // Em dashes are 3 octets each; a naive character-count fold corrupts them.
    const event = { ...FIXTURE_EVENT, description: '—'.repeat(120) }
    const out = build({ event })
    expect(unfold(out)).toContain('—'.repeat(120))
    expect(out).not.toContain('�')
  })
})

describe('buildIcs — SUMMARY / LOCATION / URL', () => {
  it('SUMMARY prefixes "SciTrek: "', () => {
    expect(build()).toContain('SUMMARY:SciTrek: Rocket Physics @ Goleta Valley JH')
  })

  it('flags an orientation slot in the SUMMARY', () => {
    const out = build({ slot: { ...FIXTURE_SLOT, slot_type: 'orientation' } })
    expect(out).toContain('(Orientation)')
  })

  it('LOCATION prefers slot.location', () => {
    expect(build()).toContain('LOCATION:Goleta Valley JH Room 12')
  })

  it('LOCATION falls back to event.location then event.school', () => {
    const slot = { ...FIXTURE_SLOT, location: '' }
    expect(
      build({ slot, event: { ...FIXTURE_EVENT, location: 'Main Campus' } }),
    ).toContain('LOCATION:Main Campus')
    expect(build({ slot })).toContain('LOCATION:Goleta Valley JH')
  })

  it('links to the canonical volunteer detail route', () => {
    // /events/:id only works because a redirect catches it; point straight at
    // the real page so the link in someone's calendar never depends on that.
    const out = unfold(build())
    expect(out).toContain('URL:https://scitrek.test/volunteer/events/42')
    expect(out).toContain('https://scitrek.test/volunteer/events/42')
  })
})

describe('buildIcs — reminders', () => {
  it('sets a day-before and an hour-before alarm', () => {
    const out = build()
    expect(out).toContain('TRIGGER:-P1D')
    expect(out).toContain('TRIGGER:-PT1H')
    expect((out.match(/BEGIN:VALARM/g) || []).length).toBe(2)
  })
})

describe('buildIcs — multiple slots', () => {
  it('emits one VEVENT per slot in a single file', () => {
    const out = build({ slot: undefined, slots: [FIXTURE_SLOT, SECOND_SLOT] })
    expect((out.match(/BEGIN:VEVENT/g) || []).length).toBe(2)
    expect((out.match(/BEGIN:VCALENDAR/g) || []).length).toBe(1)
    expect(out).toContain('DTSTART:20260422T160000Z')
    expect(out).toContain('DTSTART:20260423T160000Z')
  })

  it('requires at least one slot', () => {
    expect(() => build({ slot: undefined, slots: [] })).toThrow(/at least one slot/i)
  })
})

describe('buildIcs — line endings', () => {
  it('uses CRLF throughout and ends with one', () => {
    const out = build()
    expect((out.match(/(?<!\r)\n/g) || []).length).toBe(0)
    expect(out.endsWith('\r\n')).toBe(true)
  })
})

describe('buildGoogleCalendarUrl', () => {
  it('uses compact UTC dates', () => {
    const url = buildGoogleCalendarUrl({
      event: FIXTURE_EVENT,
      slot: FIXTURE_SLOT,
      origin: ORIGIN,
    })
    expect(url).toContain('dates=20260422T160000Z%2F20260422T180000Z')
  })

  it('carries title, location and the canonical link', () => {
    const url = buildGoogleCalendarUrl({
      event: FIXTURE_EVENT,
      slot: FIXTURE_SLOT,
      origin: ORIGIN,
    })
    const parsed = new URL(url)
    expect(parsed.searchParams.get('text')).toBe(
      'SciTrek: Rocket Physics @ Goleta Valley JH',
    )
    expect(parsed.searchParams.get('location')).toBe('Goleta Valley JH Room 12')
    expect(parsed.searchParams.get('details')).toContain(
      'https://scitrek.test/volunteer/events/42',
    )
  })
})

describe('safeIcsFilename / icsFilenameFor', () => {
  it('strips characters Windows rejects in a filename', () => {
    // The old call sites interpolated a raw ISO timestamp, colons included.
    expect(safeIcsFilename('scitrek-x-2026-04-22T09:00:00Z')).toBe(
      'scitrek-x-2026-04-22T09-00-00Z.ics',
    )
  })

  it('does not double the extension', () => {
    expect(safeIcsFilename('already.ics')).toBe('already.ics')
  })

  it('falls back to a usable name for empty input', () => {
    expect(safeIcsFilename('')).toBe('scitrek-event.ics')
    expect(safeIcsFilename('///')).toBe('scitrek-event.ics')
  })

  it('derives slug and date from the event and first slot', () => {
    expect(icsFilenameFor({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT })).toBe(
      'scitrek-rocket-physics-2026-04-22.ics',
    )
  })

  it('slugifies the title when the event has no slug', () => {
    // Real events often arrive without a slug, and the id alone put a bare
    // UUID in the volunteer's downloads folder.
    const event = {
      id: '380b603a-cfd1-4e72-bfb9-58d1533d1ebd',
      title: 'CRISPR Module 1 — Goleta Valley Junior High',
    }
    expect(icsFilenameFor({ event, slot: FIXTURE_SLOT })).toBe(
      'scitrek-crispr-module-1-goleta-valley-junior-high-2026-04-22.ics',
    )
  })

  it('falls back to the id when there is no slug or title', () => {
    expect(icsFilenameFor({ event: { id: 'abc' }, slot: FIXTURE_SLOT })).toBe(
      'scitrek-abc-2026-04-22.ics',
    )
  })

  it('marks a multi-session export', () => {
    expect(
      icsFilenameFor({ event: FIXTURE_EVENT, slots: [FIXTURE_SLOT, SECOND_SLOT] }),
    ).toBe('scitrek-rocket-physics-slots-2026-04-22.ics')
  })
})

describe('downloadIcs — DOM side effect', () => {
  let createObjectUrlSpy
  let revokeObjectUrlSpy
  let appendSpy
  let removeSpy

  beforeEach(() => {
    // jsdom ships neither of these.
    if (typeof URL.createObjectURL !== 'function') URL.createObjectURL = () => ''
    if (typeof URL.revokeObjectURL !== 'function') {
      URL.revokeObjectURL = () => undefined
    }
    createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
    revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockReturnValue(undefined)
    appendSpy = vi.spyOn(document.body, 'appendChild')
    removeSpy = vi.spyOn(document.body, 'removeChild')
  })

  afterEach(() => vi.restoreAllMocks())

  it('creates an anchor carrying the sanitised filename', () => {
    downloadIcs({
      event: FIXTURE_EVENT,
      slot: FIXTURE_SLOT,
      filename: 'scitrek-rocket-physics-2026-04-22.ics',
    })
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:mock')
    const anchor = appendSpy.mock.calls[0][0]
    expect(anchor.tagName).toBe('A')
    expect(anchor.getAttribute('download')).toBe(
      'scitrek-rocket-physics-2026-04-22.ics',
    )
    expect(anchor.href).toContain('blob:mock')
    expect(removeSpy).toHaveBeenCalledWith(anchor)
  })

  it('sanitises a caller-supplied filename containing colons', () => {
    downloadIcs({
      event: FIXTURE_EVENT,
      slot: FIXTURE_SLOT,
      filename: 'scitrek-42-2026-04-22T09:00:00Z.ics',
    })
    const anchor = appendSpy.mock.calls[0][0]
    expect(anchor.getAttribute('download')).not.toContain(':')
  })

  it('derives a filename when none is supplied', () => {
    const name = downloadIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT })
    expect(name).toBe('scitrek-rocket-physics-2026-04-22.ics')
  })

  it('serves a text/calendar blob', () => {
    downloadIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT })
    const blob = createObjectUrlSpy.mock.calls[0][0]
    expect(blob.type).toBe('text/calendar;charset=utf-8')
  })
})
