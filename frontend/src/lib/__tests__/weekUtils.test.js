/**
 * weekUtils.test.js — issue #24 rewrite, reworked for SCRUM-48.
 *
 * Navigation walks the admin-entered quarter rows from GET /public/quarters
 * (summer Sessions A/B as separate rows). SCRUM-48: it steps (quarter ×
 * school level) pairs rather than weeks, so each row yields two positions and
 * a three-quarter schedule gives six. Navigation returns null past the ends so
 * callers can disable arrows.
 */

import { describe, it, expect } from "vitest";
import {
  DEFAULT_SCHOOL_BRANCH,
  SCHOOL_BRANCHES,
  activeQuarters,
  archivedQuarters,
  findQuarterById,
  getNextQuarterLevel,
  getPrevQuarterLevel,
  formatQuarterLevelLabel,
  isSchoolBranch,
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

describe("school level vocabulary", () => {
  it("offers exactly the two levels a volunteer browses by", () => {
    // `both` is a module property, not a tab — its events surface under each
    // of these instead of getting a position of their own.
    expect(SCHOOL_BRANCHES).toEqual(["middle_school", "high_school"]);
    expect(DEFAULT_SCHOOL_BRANCH).toBe("middle_school");
  });

  it("isSchoolBranch rejects anything not a browsable level", () => {
    expect(isSchoolBranch("middle_school")).toBe(true);
    expect(isSchoolBranch("high_school")).toBe(true);
    expect(isSchoolBranch("both")).toBe(false);
    expect(isSchoolBranch(null)).toBe(false);
    expect(isSchoolBranch("elementary")).toBe(false);
  });
});

describe("getNextQuarterLevel", () => {
  it("steps to the next level within a quarter", () => {
    expect(getNextQuarterLevel(QUARTERS, "spring-26", "middle_school")).toEqual({
      quarter_id: "spring-26",
      school_branch: "high_school",
    });
  });

  it("rolls from a quarter's last level into the next entered row", () => {
    expect(getNextQuarterLevel(QUARTERS, "spring-26", "high_school")).toEqual({
      quarter_id: "summer-26-a",
      school_branch: "middle_school",
    });
  });

  it("rolls Session A into Session B", () => {
    expect(getNextQuarterLevel(QUARTERS, "summer-26-a", "high_school")).toEqual({
      quarter_id: "summer-26-b",
      school_branch: "middle_school",
    });
  });

  it("returns null past the last position", () => {
    expect(getNextQuarterLevel(QUARTERS, "summer-26-b", "high_school")).toBeNull();
  });

  it("returns null for an unknown quarter id", () => {
    expect(getNextQuarterLevel(QUARTERS, "nope", "middle_school")).toBeNull();
  });

  it("returns null for a level that is not browsable", () => {
    expect(getNextQuarterLevel(QUARTERS, "spring-26", "both")).toBeNull();
  });
});

describe("getPrevQuarterLevel", () => {
  it("steps back a level within a quarter", () => {
    expect(getPrevQuarterLevel(QUARTERS, "summer-26-a", "high_school")).toEqual({
      quarter_id: "summer-26-a",
      school_branch: "middle_school",
    });
  });

  it("rolls the first level back to the previous row's last level", () => {
    expect(getPrevQuarterLevel(QUARTERS, "summer-26-a", "middle_school")).toEqual({
      quarter_id: "spring-26",
      school_branch: "high_school",
    });
  });

  it("returns null before the first position", () => {
    expect(getPrevQuarterLevel(QUARTERS, "spring-26", "middle_school")).toBeNull();
  });
});

describe("a full walk covers every quarter × level pair", () => {
  it("visits 2 positions per quarter, in order, then stops", () => {
    // The arithmetic the feature was specified by: 3 quarters → 6 positions.
    let position = { quarter_id: "spring-26", school_branch: "middle_school" };
    const visited = [position];
    for (let guard = 0; guard < 20; guard += 1) {
      const next = getNextQuarterLevel(
        QUARTERS,
        position.quarter_id,
        position.school_branch,
      );
      if (!next) break;
      visited.push(next);
      position = next;
    }
    expect(visited).toEqual([
      { quarter_id: "spring-26", school_branch: "middle_school" },
      { quarter_id: "spring-26", school_branch: "high_school" },
      { quarter_id: "summer-26-a", school_branch: "middle_school" },
      { quarter_id: "summer-26-a", school_branch: "high_school" },
      { quarter_id: "summer-26-b", school_branch: "middle_school" },
      { quarter_id: "summer-26-b", school_branch: "high_school" },
    ]);
    expect(visited).toHaveLength(QUARTERS.length * SCHOOL_BRANCHES.length);
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

  it("prev from Session A's first level has nowhere to go once spring is archived", () => {
    expect(
      getPrevQuarterLevel(withArchived, "summer-26-a", "middle_school"),
    ).toBeNull();
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

  it("moves level-by-level within the archived row", () => {
    expect(getNextQuarterLevel(withArchived, "spring-26", "middle_school")).toEqual({
      quarter_id: "spring-26",
      school_branch: "high_school",
    });
    expect(getPrevQuarterLevel(withArchived, "spring-26", "high_school")).toEqual({
      quarter_id: "spring-26",
      school_branch: "middle_school",
    });
  });

  it("never rolls out of the archived row at either end", () => {
    expect(getNextQuarterLevel(withArchived, "spring-26", "high_school")).toBeNull();
    expect(getPrevQuarterLevel(withArchived, "spring-26", "middle_school")).toBeNull();
  });
});

describe("formatQuarterLevelLabel", () => {
  it("uses the row's display name (session-aware)", () => {
    expect(formatQuarterLevelLabel(SESSION_B, "middle_school")).toBe(
      "Summer 2026 · Session B — Middle School",
    );
    expect(formatQuarterLevelLabel(SPRING, "high_school")).toBe(
      "Spring 2026 — High School",
    );
  });

  it("degrades without a row rather than rendering undefined", () => {
    expect(formatQuarterLevelLabel(null, "high_school")).toBe("High School");
    expect(formatQuarterLevelLabel(SPRING, "nonsense")).toBe("Spring 2026");
  });
});

describe("resolveLegacyParams", () => {
  it("resolves a legacy quarter/year link to the matching row's default level", () => {
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "spring", year: 2026 }),
    ).toEqual({
      quarter_id: "spring-26",
      school_branch: "middle_school",
    });
  });

  it("ignores a legacy &week= rather than choking on it", () => {
    // The whole point: links already sitting in volunteers' inboxes still land
    // somewhere sensible instead of erroring.
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "spring", year: 2026, week: 5 }),
    ).toEqual({
      quarter_id: "spring-26",
      school_branch: "middle_school",
    });
  });

  it("picks the first session for an ambiguous legacy summer link", () => {
    expect(
      resolveLegacyParams(QUARTERS, { quarter: "summer", year: 2026, week: 2 }),
    ).toEqual({
      quarter_id: "summer-26-a",
      school_branch: "middle_school",
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
