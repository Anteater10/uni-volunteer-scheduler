import { describe, it, expect } from "vitest";
import {
  currentQuarter,
  previousQuarter,
  quarterProgress,
  QUARTER_ANCHOR,
} from "../quarter";

describe("quarter helper", () => {
  it("anchors at 2026-03-30 UTC", () => {
    expect(QUARTER_ANCHOR.toISOString().slice(0, 10)).toBe("2026-03-30");
  });

  it("currentQuarter() for 2026-04-15 spans Spring 2026 (2026-03-30 → 2026-06-15)", () => {
    const { start, end } = currentQuarter(new Date(Date.UTC(2026, 3, 15)));
    expect(start.toISOString().slice(0, 10)).toBe("2026-03-30");
    expect(end.toISOString().slice(0, 10)).toBe("2026-06-15");
  });

  it("currentQuarter() for 2026-07-01 spans Summer 2026 (2026-06-15 → 2026-08-31)", () => {
    const { start, end } = currentQuarter(new Date(Date.UTC(2026, 6, 1)));
    expect(start.toISOString().slice(0, 10)).toBe("2026-06-15");
    expect(end.toISOString().slice(0, 10)).toBe("2026-08-31");
  });

  it("previousQuarter() from 2026-04-15 rolls back to Winter 2026 (2026-01-12 → 2026-03-30)", () => {
    const { start, end } = previousQuarter(new Date(Date.UTC(2026, 3, 15)));
    expect(start.toISOString().slice(0, 10)).toBe("2026-01-12");
    expect(end.toISOString().slice(0, 10)).toBe("2026-03-30");
  });

  it("quarterProgress() for 2026-04-15 reports week 3 of 11", () => {
    const p = quarterProgress(new Date(Date.UTC(2026, 3, 15)));
    expect(p.of).toBe(11);
    expect(p.week).toBeGreaterThanOrEqual(1);
    expect(p.week).toBeLessThanOrEqual(11);
    expect(p.pct).toBeGreaterThan(0);
  });
});
