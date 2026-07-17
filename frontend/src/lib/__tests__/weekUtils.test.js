/**
 * weekUtils.test.js — issue #24 rewrite.
 *
 * Week navigation walks the admin-entered quarter rows from
 * GET /public/quarters (real week counts per row, summer Sessions A/B as
 * separate rows) instead of assuming a fixed 11-week cycle. Navigation
 * returns null past the ends so callers can disable arrows.
 */

import { describe, it, expect } from "vitest";
import {
  activeQuarters,
  archivedQuarters,
  findQuarterById,
  getNextWeek,
  getPrevWeek,
  formatWeekLabel,
  resolveLegacyParams,
  quarterContaining,
  activeOrRecentQuarter,
} from "../weekUtils.js";

const SPRING = {
  id: "spring-26",
  season: "spring",
  year: 2026,
  label: "",
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: null,
};
const SESSION_A = {
  id: "summer-26-a",
  season: "summer",
  year: 2026,
  label: "Session A",
  start_date: "2026-06-22",
  end_date: "2026-07-31",
  weeks_in_quarter: 6,
  display_name: "Summer 2026 · Session A",
  archived_at: null,
};
const SESSION_B = {
  id: "summer-26-b",
  season: "summer",
  year: 2026,
  label: "Session B",
  start_date: "2026-08-03",
  end_date: "2026-09-11",
  weeks_in_quarter: 6,
  display_name: "Summer 2026 · Session B",
  archived_at: null,
};
const QUARTERS = [SPRING, SESSION_A, SESSION_B];

describe("getNextWeek", () => {
  it("increments within a quarter", () => {
    expect(getNextWeek(QUARTERS, "spring-26", 5)).toEqual({
      quarter_id: "spring-26",
      week_number: 6,
    });
  });

  it("rolls from a quarter's final week into the next entered row", () => {
    expect(getNextWeek(QUARTERS, "spring-26", 11)).toEqual({
      quarter_id: "summer-26-a",
      week_number: 1,
    });
  });

  it("rolls Session A week 6 into Session B week 1 (real week counts)", () => {
    expect(getNextWeek(QUARTERS, "summer-26-a", 6)).toEqual({
      quarter_id: "summer-26-b",
      week_number: 1,
    });
  });

  it("returns null past the last entered quarter", () => {
    expect(getNextWeek(QUARTERS, "summer-26-b", 6)).toBeNull();
  });

  it("returns null for an unknown quarter id", () => {
    expect(getNextWeek(QUARTERS, "nope", 3)).toBeNull();
  });
});

describe("getPrevWeek", () => {
  it("decrements within a quarter", () => {
    expect(getPrevWeek(QUARTERS, "summer-26-a", 3)).toEqual({
      quarter_id: "summer-26-a",
      week_number: 2,
    });
  });

  it("rolls week 1 back to the previous row's final week", () => {
    expect(getPrevWeek(QUARTERS, "summer-26-a", 1)).toEqual({
      quarter_id: "spring-26",
      week_number: 11,
    });
  });

  it("returns null before the first entered quarter", () => {
    expect(getPrevWeek(QUARTERS, "spring-26", 1)).toBeNull();
  });
});

describe("archived rows are skipped in navigation", () => {
  const withArchived = [
    { ...SPRING, archived_at: "2026-07-01T00:00:00Z" },
    SESSION_A,
    SESSION_B,
  ];

  it("activeQuarters drops archived rows", () => {
    expect(activeQuarters(withArchived).map((q) => q.id)).toEqual([
      "summer-26-a",
      "summer-26-b",
    ]);
  });

  it("prev from Session A week 1 has nowhere to go once spring is archived", () => {
    expect(getPrevWeek(withArchived, "summer-26-a", 1)).toBeNull();
  });

  it("archivedQuarters lists only archived rows, ordered by start", () => {
    expect(archivedQuarters(withArchived).map((q) => q.id)).toEqual(["spring-26"]);
    expect(archivedQuarters(QUARTERS)).toEqual([]);
  });
});

describe("navigation inside an archived quarter is clamped to it (issue #33)", () => {
  const withArchived = [
    { ...SPRING, archived_at: "2026-07-01T00:00:00Z" },
    SESSION_A,
    SESSION_B,
  ];

  it("moves week-by-week within the archived row", () => {
    expect(getNextWeek(withArchived, "spring-26", 5)).toEqual({
      quarter_id: "spring-26",
      week_number: 6,
    });
    expect(getPrevWeek(withArchived, "spring-26", 5)).toEqual({
      quarter_id: "spring-26",
      week_number: 4,
    });
  });

  it("never rolls out of the archived row at either end", () => {
    expect(getNextWeek(withArchived, "spring-26", 11)).toBeNull();
    expect(getPrevWeek(withArchived, "spring-26", 1)).toBeNull();
  });
});

describe("formatWeekLabel", () => {
  it("uses the row's display name (session-aware)", () => {
    expect(formatWeekLabel(SESSION_B, 2)).toBe("Summer 2026 · Session B — Week 2");
    expect(formatWeekLabel(SPRING, 3)).toBe("Spring 2026 — Week 3");
  });
});

describe("resolveLegacyParams", () => {
  it("resolves a legacy quarter/year/week link to the matching row", () => {
    expect(resolveLegacyParams(QUARTERS, { quarter: "spring", year: 2026, week: 5 })).toEqual({
      quarter_id: "spring-26",
      week_number: 5,
    });
  });

  it("picks the first session for an ambiguous legacy summer link", () => {
    expect(resolveLegacyParams(QUARTERS, { quarter: "summer", year: 2026, week: 2 })).toEqual({
      quarter_id: "summer-26-a",
      week_number: 2,
    });
  });

  it("returns null when nothing matches", () => {
    expect(resolveLegacyParams(QUARTERS, { quarter: "fall", year: 2031, week: 1 })).toBeNull();
  });
});

describe("date → quarter helpers", () => {
  it("quarterContaining finds the covering row (inclusive bounds)", () => {
    expect(quarterContaining(QUARTERS, new Date(Date.UTC(2026, 3, 15))).id).toBe("spring-26");
    expect(quarterContaining(QUARTERS, new Date(Date.UTC(2026, 5, 14))).id).toBe("spring-26");
    expect(quarterContaining(QUARTERS, new Date(Date.UTC(2026, 5, 17)))).toBeNull();
  });

  it("findQuarterById returns the row or null", () => {
    expect(findQuarterById(QUARTERS, "summer-26-b").label).toBe("Session B");
    expect(findQuarterById(QUARTERS, "missing")).toBeNull();
  });

  it("activeOrRecentQuarter falls back to the most recently ended row in a gap", () => {
    expect(activeOrRecentQuarter(QUARTERS, new Date(Date.UTC(2026, 7, 1))).id).toBe(
      "summer-26-a",
    );
    expect(activeOrRecentQuarter(QUARTERS, new Date(Date.UTC(2026, 0, 1)))).toBeNull();
  });
});
