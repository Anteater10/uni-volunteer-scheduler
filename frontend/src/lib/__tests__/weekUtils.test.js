/**
 * weekUtils.test.js
 *
 * Tests for pure week navigation utility functions.
 * Covers normal increments, quarter boundary rollovers (D-10),
 * and year rollovers in both directions.
 */

import { describe, it, expect } from "vitest";
import { getNextWeek, getPrevWeek, formatWeekLabel } from "../weekUtils.js";

describe("getNextWeek — normal increment", () => {
  it("increments week_number within same quarter", () => {
    const result = getNextWeek("spring", 2026, 5);
    expect(result).toEqual({ quarter: "spring", year: 2026, week_number: 6 });
  });

  it("increments week 1 to week 2", () => {
    const result = getNextWeek("winter", 2026, 1);
    expect(result).toEqual({ quarter: "winter", year: 2026, week_number: 2 });
  });
});

describe("getNextWeek — quarter boundary rollover (D-10)", () => {
  it("spring week 11 rolls over to summer week 1", () => {
    const result = getNextWeek("spring", 2026, 11);
    expect(result).toEqual({ quarter: "summer", year: 2026, week_number: 1 });
  });

  it("winter week 11 rolls over to spring week 1", () => {
    const result = getNextWeek("winter", 2026, 11);
    expect(result).toEqual({ quarter: "spring", year: 2026, week_number: 1 });
  });

  it("summer week 11 rolls over to fall week 1", () => {
    const result = getNextWeek("summer", 2026, 11);
    expect(result).toEqual({ quarter: "fall", year: 2026, week_number: 1 });
  });

  it("fall week 11 rolls over to winter of next year", () => {
    const result = getNextWeek("fall", 2026, 11);
    expect(result).toEqual({ quarter: "winter", year: 2027, week_number: 1 });
  });
});

describe("getPrevWeek — normal decrement", () => {
  it("decrements week_number within same quarter", () => {
    const result = getPrevWeek("spring", 2026, 5);
    expect(result).toEqual({ quarter: "spring", year: 2026, week_number: 4 });
  });

  it("decrements week 11 to week 10", () => {
    const result = getPrevWeek("fall", 2026, 11);
    expect(result).toEqual({ quarter: "fall", year: 2026, week_number: 10 });
  });
});

describe("getPrevWeek — quarter boundary rollover (D-10)", () => {
  it("spring week 1 rolls back to winter week 11", () => {
    const result = getPrevWeek("spring", 2026, 1);
    expect(result).toEqual({ quarter: "winter", year: 2026, week_number: 11 });
  });

  it("summer week 1 rolls back to spring week 11", () => {
    const result = getPrevWeek("summer", 2026, 1);
    expect(result).toEqual({ quarter: "spring", year: 2026, week_number: 11 });
  });

  it("fall week 1 rolls back to summer week 11", () => {
    const result = getPrevWeek("fall", 2026, 1);
    expect(result).toEqual({ quarter: "summer", year: 2026, week_number: 11 });
  });

  it("winter week 1 rolls back to fall of previous year", () => {
    const result = getPrevWeek("winter", 2026, 1);
    expect(result).toEqual({ quarter: "fall", year: 2025, week_number: 11 });
  });
});

describe("formatWeekLabel", () => {
  it("formats a spring week label", () => {
    expect(formatWeekLabel("spring", 2026, 3)).toBe("Spring 2026 - Week 3");
  });

  it("capitalises the quarter name", () => {
    expect(formatWeekLabel("winter", 2027, 1)).toBe("Winter 2027 - Week 1");
  });

  it("formats fall with double-digit week", () => {
    expect(formatWeekLabel("fall", 2026, 11)).toBe("Fall 2026 - Week 11");
  });
});
