/**
 * calendar.test.js
 *
 * Tests for RFC 5545 iCalendar (.ics) generation + download util.
 * Covers envelope shape, required VEVENT fields, text escaping, SUMMARY/LOCATION
 * formatting per UI-SPEC, VALARM, CRLF line endings, and downloadIcs DOM effect.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildIcs, downloadIcs } from '../calendar'

const FIXTURE_EVENT = {
  id: 42,
  title: 'Rocket Physics @ Goleta Valley JH',
  description: 'Hands-on rocket lab for 7th graders',
  school: 'Goleta Valley JH',
  slug: 'rocket-physics',
  start_date: '2026-04-22',
}
const FIXTURE_SLOT = {
  id: 7,
  start_time: '2026-04-22T09:00:00',
  end_time: '2026-04-22T11:00:00',
  location: 'Goleta Valley JH Room 12',
}
const ORIGIN = 'https://scitrek.test'

describe('buildIcs — envelope', () => {
  it('contains BEGIN:VCALENDAR, VERSION:2.0, PRODID, CALSCALE, END:VCALENDAR', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('BEGIN:VCALENDAR')
    expect(out).toContain('VERSION:2.0')
    expect(out).toContain('PRODID:-//SciTrek//Volunteer Scheduler//EN')
    expect(out).toContain('CALSCALE:GREGORIAN')
    expect(out).toContain('END:VCALENDAR')
  })
})

describe('buildIcs — required VEVENT fields', () => {
  it('UID matches scitrek-{event.id}-slot-{slot.id}@scitrek.ucsb.edu', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('UID:scitrek-42-slot-7@scitrek.ucsb.edu')
  })
  it('DTSTAMP is UTC form with Z suffix', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toMatch(/DTSTAMP:\d{8}T\d{6}Z/)
  })
  it('DTSTART is floating form (no Z, no TZID)', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toMatch(/DTSTART:\d{8}T\d{6}(?!Z)/)
    expect(out).not.toMatch(/DTSTART:[^\r\n]*Z/)
  })
  it('DTEND is present and floating form', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toMatch(/DTEND:\d{8}T\d{6}(?!Z)/)
  })
})

describe('buildIcs — escaping (RFC 5545 §3.3.11)', () => {
  it('escapes commas, semicolons, backslashes, newlines in DESCRIPTION', () => {
    const evt = { ...FIXTURE_EVENT, description: 'Line1, part;two\\slash\nline2' }
    const out = buildIcs({ event: evt, slot: FIXTURE_SLOT, origin: ORIGIN })
    // backslash escaped first, then newline, comma, semicolon
    expect(out).toContain('DESCRIPTION:Line1\\, part\\;two\\\\slash\\nline2')
  })
  it('escapes same characters in SUMMARY (via title)', () => {
    const evt = { ...FIXTURE_EVENT, title: 'Ev,ent;One\\Two' }
    const out = buildIcs({ event: evt, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('SUMMARY:Sci Trek: Ev\\,ent\\;One\\\\Two')
  })
})

describe('buildIcs — SUMMARY / LOCATION / DESCRIPTION / URL', () => {
  it('SUMMARY prefixes "Sci Trek: " per UI-SPEC', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('SUMMARY:Sci Trek: Rocket Physics @ Goleta Valley JH')
  })
  it('LOCATION uses slot.location when present', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('LOCATION:Goleta Valley JH Room 12')
  })
  it('LOCATION falls back to event.school when slot.location empty', () => {
    const slot = { ...FIXTURE_SLOT, location: '' }
    const out = buildIcs({ event: FIXTURE_EVENT, slot, origin: ORIGIN })
    expect(out).toContain('LOCATION:Goleta Valley JH')
  })
  it('DESCRIPTION appends event URL back to /events/:id', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('https://scitrek.test/events/42')
  })
  it('URL line points to {origin}/events/:id', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('URL:https://scitrek.test/events/42')
  })
})

describe('buildIcs — VALARM', () => {
  it('includes ACTION:DISPLAY + TRIGGER:-PT1H (one hour before)', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out).toContain('BEGIN:VALARM')
    expect(out).toContain('ACTION:DISPLAY')
    expect(out).toContain('TRIGGER:-PT1H')
    expect(out).toContain('END:VALARM')
  })
})

describe('buildIcs — line endings', () => {
  it('every line is CRLF terminated', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    // Count CRLFs — must match line count
    const crlfCount = (out.match(/\r\n/g) || []).length
    const lfOnlyCount = (out.match(/(?<!\r)\n/g) || []).length
    expect(crlfCount).toBeGreaterThan(15) // envelope + VEVENT fields + VALARM
    expect(lfOnlyCount).toBe(0)
  })
  it('ends with CRLF', () => {
    const out = buildIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, origin: ORIGIN })
    expect(out.endsWith('\r\n')).toBe(true)
  })
})

describe('downloadIcs — DOM side effect', () => {
  let createObjectUrlSpy
  let revokeObjectUrlSpy
  let appendSpy
  let removeSpy

  beforeEach(() => {
    // jsdom does not implement URL.createObjectURL / revokeObjectURL out of the
    // box. Define no-op stubs first so vi.spyOn can attach to existing methods.
    if (typeof URL.createObjectURL !== 'function') {
      URL.createObjectURL = () => ''
    }
    if (typeof URL.revokeObjectURL !== 'function') {
      URL.revokeObjectURL = () => undefined
    }
    createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
    revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockReturnValue(undefined)
    appendSpy = vi.spyOn(document.body, 'appendChild')
    removeSpy = vi.spyOn(document.body, 'removeChild')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('creates anchor with download attribute set to provided filename', () => {
    const filename = 'scitrek-rocket-physics-2026-04-22.ics'
    downloadIcs({ event: FIXTURE_EVENT, slot: FIXTURE_SLOT, filename })
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:mock')
    // The anchor passed to appendChild carries the download attr
    const anchorArg = appendSpy.mock.calls[0][0]
    expect(anchorArg.tagName).toBe('A')
    expect(anchorArg.getAttribute('download')).toBe(filename)
    expect(anchorArg.href).toContain('blob:mock')
    expect(removeSpy).toHaveBeenCalledWith(anchorArg)
  })
})
