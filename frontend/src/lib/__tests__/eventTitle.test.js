import { describe, it, expect } from "vitest";
import { isValidEventTitle } from "../eventTitle";

describe("isValidEventTitle (SCRUM-154)", () => {
  it("accepts the canonical shape", () => {
    expect(isValidEventTitle("Week 7 - Conservation of Mass - GVJH")).toBe(true);
  });

  it("accepts multi-digit weeks and schools with spaces", () => {
    expect(
      isValidEventTitle("Week 10 - Germs - Dos Pueblos High School"),
    ).toBe(true);
  });

  it("ignores surrounding whitespace", () => {
    expect(isValidEventTitle("  Week 7 - Germs - GVJH  ")).toBe(true);
  });

  it("rejects the loose spacing the old titles used", () => {
    // The two real examples that motivated the rule.
    expect(isValidEventTitle("Week 7-Conservation of Mass- GVJH")).toBe(false);
    expect(isValidEventTitle("Week 5- Germs- LaCumbre")).toBe(false);
  });

  it("rejects a title with no week", () => {
    expect(isValidEventTitle("Conservation of Mass - GVJH")).toBe(false);
  });

  it("rejects a title with no school", () => {
    expect(isValidEventTitle("Week 7 - Conservation of Mass")).toBe(false);
  });

  it("rejects a non-numeric week", () => {
    expect(isValidEventTitle("Week seven - Germs - GVJH")).toBe(false);
  });

  it("rejects empty and missing titles", () => {
    expect(isValidEventTitle("")).toBe(false);
    expect(isValidEventTitle("   ")).toBe(false);
    expect(isValidEventTitle(null)).toBe(false);
    expect(isValidEventTitle(undefined)).toBe(false);
  });
});
