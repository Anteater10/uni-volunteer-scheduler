/**
 * weekUtils.test.js — issue #24 rewrite, reworked for SCRUM-48.
 *
 * Navigation walks the admin-entered quarter rows from GET /public/quarters
 * (summer Sessions A/B as separate rows). Each row is one combined public
 * schedule position. Navigation returns null past the ends so callers can
 * disable arrows.
 */

import { describe, it, expect } from "vitest";
import {
  activeQuarters,
  archivedQuarters,
  findQuarterById,
  getNextQuarter,
  getPrevQuarter,
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

describe("getNextQuarter", () => {
  it("rolls Session A into Session B", () => {
    expect(getNextQuarter(QUARTERS, "summer-26-a")).toEqual({
      quarter_id: "summer-26-b",
    });
  });

  it("returns null past the last position", () => {
    expect(getNextQuarter(QUARTERS, "summer-26-b")).toBeNull();
  });

  it("returns null for an unknown quarter id", () => {
    expect(getNextQuarter(QUARTERS, "nope")).toBeNull();
  });
});

describe("getPrevQuarter", () => {
  it("returns the previous entered quarter", () => {
    expect(getPrevQuarter(QUARTERS, "summer-26-a")).toEqual({
      quarter_id: "spring-26",
    });
  });

  it("returns null before the first position", () => {
    expect(getPrevQuarter(QUARTERS, "spring-26")).toBeNull();
  });
});

describe("a full walk covers every quarter", () => {
  it("visits each quarter once, in order, then stops", () => {
    let position = { quarter_id: "spring-26" };
    const visited = [position];
    for (let guard = 0; guard < 20; guard += 1) {
      const next = getNextQuarter(QUARTERS, position.quarter_id);
      if (!next) break;
      visited.push(next);
      position = next;
    }
    expect(visited).toEqual([
      { quarter_id: "spring-26" },
      { quarter_id: "summer-26-a" },
      { quarter_id: "summer-26-b" },
    ]);
    expect(visited).toHaveLength(QUARTERS.length);
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

  it("prev from Session A has nowhere to go once spring is archived", () => {
    expect(getPrevQuarter(withArchived, "summer-26-a")).toBeNull();
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

  it("never rolls out of the archived row at either end", () => {
    expect(getNextQuarter(withArchived, "spring-26")).toBeNull();
    expect(getPrevQuarter(withArchived, "spring-26")).toBeNull();
  });
});

describe("resolveLegacyParams", () => {
  it("resolves a legacy quarter/year link to the matching row", () => {
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "spring", year: 2026 }),
    ).toEqual({
      quarter_id: "spring-26",
    });
  });

  it("ignores a legacy &week= rather than choking on it", () => {
    // The whole point: links already sitting in volunteers' inboxes still land
    // somewhere sensible instead of erroring.
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "spring", year: 2026, week: 5 }),
    ).toEqual({
      quarter_id: "spring-26",
    });
  });

  it("picks the first session for an ambiguous legacy summer link", () => {
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "summer", year: 2026, week: 2 }),
    ).toEqual({
      quarter_id: "summer-26-a",
    });
  });

  it("returns null when nothing matches", () => {
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "fall", year: 2031, week: 1 }),
    ).toBeNull();
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
