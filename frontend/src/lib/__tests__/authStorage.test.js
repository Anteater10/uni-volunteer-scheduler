/**
 * Tests for lib/authStorage.js after Phase L3 turned it from a localStorage
 * wrapper into an in-memory holder.
 *
 * The two properties worth pinning:
 *   1. The access token must NOT be written to localStorage — that is the
 *      whole point of the phase, and a regression would be invisible in
 *      normal use.
 *   2. The legacy keys from the old build must be cleaned up on load. Every
 *      member of staff who used the previous version still has a real,
 *      server-valid refresh token sitting in localStorage; leaving it there
 *      keeps the exact exposure this phase closes open for exactly the
 *      people who already have it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const LEGACY_ACCESS = "uvse_access_token";
const LEGACY_REFRESH = "uvse_refresh_token";

async function freshModule() {
  vi.resetModules();
  return (await import("../authStorage.js")).default;
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("legacy key cleanup", () => {
  it("removes tokens left in localStorage by the pre-L3 build", async () => {
    localStorage.setItem(LEGACY_ACCESS, "old-access");
    localStorage.setItem(LEGACY_REFRESH, "old-and-still-valid-refresh");

    await freshModule();

    expect(localStorage.getItem(LEGACY_ACCESS)).toBeNull();
    expect(localStorage.getItem(LEGACY_REFRESH)).toBeNull();
  });

  it("leaves unrelated keys alone", async () => {
    localStorage.setItem("admin.selectedQuarterId", "q-123");
    await freshModule();
    expect(localStorage.getItem("admin.selectedQuarterId")).toBe("q-123");
  });

  it("survives localStorage throwing", async () => {
    // Blocked site data / strict privacy modes make the accessor itself
    // throw. Failing here would take the whole app down on boot.
    const spy = vi
      .spyOn(Storage.prototype, "removeItem")
      .mockImplementation(() => {
        throw new Error("SecurityError: access denied");
      });

    await expect(freshModule()).resolves.toBeTruthy();
    spy.mockRestore();
  });
});

describe("in-memory access token", () => {
  it("round-trips a token without touching localStorage", async () => {
    const authStorage = await freshModule();
    authStorage.setToken("in-memory-only");

    expect(authStorage.getToken()).toBe("in-memory-only");
    // The property the phase exists for: nothing readable by other JS.
    expect(localStorage.getItem(LEGACY_ACCESS)).toBeNull();
    expect(Object.keys(localStorage)).toHaveLength(0);
  });

  it("starts empty", async () => {
    const authStorage = await freshModule();
    expect(authStorage.getToken()).toBe("");
  });

  it("does not survive a module reload — a page reload has no token", async () => {
    const first = await freshModule();
    first.setToken("tab-session-token");
    expect(first.getToken()).toBe("tab-session-token");

    // Re-importing is the closest analogue to a fresh page load; the boot
    // silent-refresh in state/authContext.jsx exists because of this.
    const second = await freshModule();
    expect(second.getToken()).toBe("");
  });

  it("ignores empty and non-string values", async () => {
    const authStorage = await freshModule();
    authStorage.setToken("real");
    authStorage.setToken("");
    authStorage.setToken(null);
    authStorage.setToken(undefined);
    authStorage.setToken(42);
    expect(authStorage.getToken()).toBe("real");
  });

  it("clearToken empties it", async () => {
    const authStorage = await freshModule();
    authStorage.setToken("abc");
    authStorage.clearToken();
    expect(authStorage.getToken()).toBe("");
  });

  it("clearAll empties it", async () => {
    const authStorage = await freshModule();
    authStorage.setToken("abc");
    authStorage.clearAll();
    expect(authStorage.getToken()).toBe("");
  });

  it("exposes the back-compat accessor aliases", async () => {
    const authStorage = await freshModule();
    authStorage.setAccessToken("via-alias");
    expect(authStorage.getAccessToken()).toBe("via-alias");
    expect(authStorage.getToken()).toBe("via-alias");
  });

  it("has no refresh-token API at all", async () => {
    // JS must have no way to reach the refresh token — it is HttpOnly now.
    const authStorage = await freshModule();
    expect(authStorage.getRefreshToken).toBeUndefined();
    expect(authStorage.setRefreshToken).toBeUndefined();
    expect(authStorage.clearRefreshToken).toBeUndefined();
  });
});
