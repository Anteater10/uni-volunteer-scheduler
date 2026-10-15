/* global process -- tests switch the machine's timezone via process.env.TZ */
// The admin page printed "ENDS 29 Aug 2026 at 02:59" for an event whose last
// session is Friday the 28th at 3pm. Nothing was wrong with the data: the
// event ends 23:59 Pacific, which is 06:59 UTC on the Saturday, and the page
// formatted that instant in the browser's timezone rather than the venue's.
//
// These tests pin the venue timezone rather than the machine's, so they mean
// the same thing on a laptop in Santa Barbara and in CI.
import { afterEach, describe, expect, it } from "vitest";

import {
  fmtVenueDate,
  fmtVenueDateTime,
  fmtVenueTime,
  fmtVenueWeekday,
} from "../venueTime";

describe("venue time", () => {
  it("renders a late-evening Pacific instant on the Pacific day", () => {
    // 2026-08-29T06:59:00Z is 2026-08-28 23:59 Pacific.
    expect(fmtVenueDateTime("2026-08-29T06:59:00Z")).toContain("Aug 28");
    expect(fmtVenueDateTime("2026-08-29T06:59:00Z")).toContain("11:59 PM");
  });

  it("renders an early-morning Pacific instant on the Pacific day", () => {
    // 2026-08-17T16:00:00Z is 9am Pacific on the 17th.
    expect(fmtVenueDateTime("2026-08-17T16:00:00Z")).toContain("Aug 17");
    expect(fmtVenueDateTime("2026-08-17T16:00:00Z")).toContain("9:00 AM");
  });

  it("keeps a date-only value on the day it names", () => {
    // The trap: UTC midnight is the previous afternoon in Pacific, and local
    // midnight is the previous day in Pacific from anywhere east of it.
    expect(fmtVenueDate("2026-08-17")).toBe("Mon, Aug 17");
    expect(fmtVenueWeekday("2026-08-17")).toBe("Monday");
  });

  it("handles the winter offset too", () => {
    // PST is UTC-8, so 2026-01-15T07:30:00Z is 11:30pm on the 14th.
    expect(fmtVenueDateTime("2026-01-15T07:30:00Z")).toContain("Jan 14");
  });

  it("falls back rather than printing Invalid Date", () => {
    expect(fmtVenueDateTime(null)).toBe("—");
    expect(fmtVenueDateTime("not a date")).toBe("—");
    expect(fmtVenueDate(undefined)).toBe("");
    expect(fmtVenueWeekday(null)).toBe("");
  });

  it("renders a bare time in Pacific", () => {
    // The live roster's cards and section headers (Kim's report, 2026-10-13).
    expect(fmtVenueTime("2026-08-17T16:00:00Z")).toBe("9:00 AM");
    expect(fmtVenueTime("2026-01-15T07:30:00Z")).toBe("11:30 PM");
    expect(fmtVenueTime(null)).toBe("");
    expect(fmtVenueTime("not a date", "?")).toBe("?");
  });
});

describe("venue time from a browser outside Pacific", () => {
  const originalTz = process.env.TZ;
  afterEach(() => {
    process.env.TZ = originalTz;
  });

  it("prints Pacific even when the machine is in New York or Tokyo", () => {
    // Prove the switch takes: the machine's own clock now reads noon.
    process.env.TZ = "America/New_York";
    expect(new Date("2026-08-17T16:00:00Z").getHours()).toBe(12);
    for (const tz of ["America/New_York", "Asia/Tokyo", "UTC"]) {
      process.env.TZ = tz;
      // 16:00Z is noon in New York and 1am next day in Tokyo; the venue
      // still reads 9:00 AM on the 17th.
      expect(fmtVenueTime("2026-08-17T16:00:00Z")).toBe("9:00 AM");
      expect(fmtVenueDate("2026-08-17T16:00:00Z")).toBe("Mon, Aug 17");
    }
  });
});
