/**
 * refreshOn401.test.js
 *
 * Verifies that api.js transparently recovers from 401 responses via the
 * refresh-on-401 mechanism, and that concurrent 401s queue behind a single
 * in-flight refresh call (thundering-herd guard, T-00-11).
 *
 * Phase L3: the refresh token moved to an HttpOnly cookie the browser
 * manages — this test never sees it. The access token lives in memory
 * (authStorage.js), seeded directly rather than via localStorage, and the
 * refresh call carries credentials + an X-CSRF-Token header read from
 * document.cookie instead of a JSON body.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

const FAKE_ACCESS = "expired-access-token";
const FAKE_NEW_ACCESS = "new-access-token-xyz";
const FAKE_CSRF = "test-csrf-token";

// Reset module state between tests so the in-memory access token and
// `refreshPromise` singleton are both fresh each time.
beforeEach(() => {
  document.cookie = `csrf_token=${FAKE_CSRF}`;
  vi.resetModules();
  vi.restoreAllMocks();
});

afterEach(() => {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

// -----------------------------------------------------------------------
// Helper: build a mock fetch that sequences through a list of responses.
// -----------------------------------------------------------------------
function makeFetch(responses) {
  let call = 0;
  return vi.fn(async (url, _init) => {
    const spec = responses[Math.min(call++, responses.length - 1)];
    return {
      ok: spec.status >= 200 && spec.status < 300,
      status: spec.status,
      headers: {
        get: () => "application/json",
      },
      json: async () => spec.body,
      blob: async () => new Blob(),
    };
  });
}

describe("refresh-on-401", () => {
  it("retries a protected request once after a 401 and returns the 200 body", async () => {
    // Call sequence:
    //   1st call  → original request → 401
    //   2nd call  → POST /auth/refresh → 200 with a new access token
    //   3rd call  → retry original request → 200 with data
    const mockFetch = makeFetch([
      { status: 401, body: { detail: "Not authenticated" } },
      { status: 200, body: { access_token: FAKE_NEW_ACCESS } },
      { status: 200, body: { id: "user-1", name: "Alice" } },
    ]);
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    const authStorage = (await import("../authStorage.js")).default;
    authStorage.setToken(FAKE_ACCESS);

    const result = await api.me();

    expect(result).toEqual({ id: "user-1", name: "Alice" });
    expect(mockFetch).toHaveBeenCalledTimes(3);

    // The second call must be to the /auth/refresh endpoint, cookie-based
    const refreshCall = mockFetch.mock.calls[1];
    expect(refreshCall[0]).toContain("/auth/refresh");
    expect(refreshCall[1].method).toBe("POST");
    expect(refreshCall[1].credentials).toBe("include");
    expect(refreshCall[1].headers["X-CSRF-Token"]).toBe(FAKE_CSRF);
    expect(refreshCall[1].body).toBeUndefined();

    // New access token stored in memory
    expect(authStorage.getToken()).toBe(FAKE_NEW_ACCESS);
  });

  it("queues concurrent 401s behind a single refresh — /auth/refresh called exactly once", async () => {
    // Each api.me() returns 401 on its first attempt, then 200 on retry.
    // The /auth/refresh call also returns a single 200.
    //
    // Call pattern with 3 concurrent me() calls:
    //   Calls 1-3  → all three original requests → 401
    //   Call  4    → ONE /auth/refresh → 200 (other two queue on the same promise)
    //   Calls 5-7  → three retries → 200

    let fetchCall = 0;
    const mockFetch = vi.fn(async (url, _init) => {
      fetchCall++;
      // Identify refresh calls by URL
      if (typeof url === "string" && url.includes("/auth/refresh")) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => "application/json" },
          json: async () => ({ access_token: FAKE_NEW_ACCESS }),
        };
      }
      // Original requests: first 3 calls → 401; subsequent → 200
      if (fetchCall <= 3) {
        return {
          ok: false,
          status: 401,
          headers: { get: () => "application/json" },
          json: async () => ({ detail: "Unauthorized" }),
        };
      }
      return {
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: async () => ({ id: "user-1", name: "Alice" }),
      };
    });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    const authStorage = (await import("../authStorage.js")).default;
    authStorage.setToken(FAKE_ACCESS);

    // Fire three concurrent me() calls
    const [r1, r2, r3] = await Promise.all([api.me(), api.me(), api.me()]);

    expect(r1).toEqual({ id: "user-1", name: "Alice" });
    expect(r2).toEqual({ id: "user-1", name: "Alice" });
    expect(r3).toEqual({ id: "user-1", name: "Alice" });

    // Count how many times /auth/refresh was called — must be exactly once
    const refreshCalls = mockFetch.mock.calls.filter(
      ([url]) => typeof url === "string" && url.includes("/auth/refresh")
    );
    // thundering-herd guard: /auth/refresh must be called exactly once
    // (equivalent to toHaveBeenCalledTimes(1) on the refresh-only subset)
    expect(refreshCalls.length).toBe(1);
  });

  it("clears auth and throws when refresh itself fails", async () => {
    const mockFetch = makeFetch([
      { status: 401, body: { detail: "Unauthorized" } },
      { status: 401, body: { error: "invalid_refresh_token" } },
    ]);
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    const authStorage = (await import("../authStorage.js")).default;
    authStorage.setToken(FAKE_ACCESS);

    await expect(api.me()).rejects.toThrow();

    // In-memory auth state must be cleared after a failed refresh
    expect(authStorage.getToken()).toBeFalsy();
  });
});
