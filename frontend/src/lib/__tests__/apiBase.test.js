// Single source of truth for the backend origin — every API module must
// derive its base URL from here instead of re-reading VITE_API_URL.
import { describe, it, expect } from "vitest";
import { API_BASE, RAW_BASE } from "../apiBase";

describe("apiBase", () => {
  it("appends /api/v1 exactly once", () => {
    expect(API_BASE.endsWith("/api/v1")).toBe(true);
    expect(API_BASE.includes("/api/v1/api/v1")).toBe(false);
  });

  it("has no trailing slash on the raw origin", () => {
    expect(RAW_BASE.endsWith("/")).toBe(false);
  });

  it("falls back to localhost in dev when VITE_API_URL is unset", () => {
    // vitest runs without VITE_API_URL, so the module resolves the fallback.
    expect(API_BASE).toBe("http://localhost:8000/api/v1");
  });
});
