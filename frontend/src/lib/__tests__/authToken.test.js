/**
 * Tests for lib/authToken.js — the Phase L3 access-token accessor, the
 * single-flight cookie-based refresh, and authorizedFetch.
 *
 * Why this file is thorough out of proportion to its size: every branch here
 * is one where the failure mode is either "all staff are silently logged
 * out" or "the token is exfiltratable again". The bug this phase nearly
 * shipped (a csrf cookie the SPA could not read) was invisible to jsdom
 * precisely because a test fabricated the cookie instead of reproducing what
 * the server sends — so these assert on behaviour, and the Path semantics
 * are pinned server-side in backend/tests/test_auth.py where they are real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const CSRF = "csrf-value-abc";
const NEW_ACCESS = "new-access-token";

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  };
}

async function freshModules() {
  // resetModules per test so the module-scoped in-memory token and the
  // refreshPromise singleton do not leak between cases.
  vi.resetModules();
  const authToken = await import("../authToken.js");
  const authStorage = (await import("../authStorage.js")).default;
  return { ...authToken, authStorage };
}

beforeEach(() => {
  document.cookie = `csrf_token=${CSRF}`;
  vi.restoreAllMocks();
  // navigator.locks is absent in jsdom; individual tests opt into it.
  delete navigator.locks;
});

afterEach(() => {
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  delete navigator.locks;
});

describe("readCsrfCookie", () => {
  it("reads the csrf cookie set by the server", async () => {
    const { readCsrfCookie } = await freshModules();
    expect(readCsrfCookie()).toBe(CSRF);
  });

  it("returns empty string when the cookie is absent", async () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    const { readCsrfCookie } = await freshModules();
    expect(readCsrfCookie()).toBe("");
  });

  it("url-decodes the value", async () => {
    document.cookie = "csrf_token=a%2Bb%3Dc";
    const { readCsrfCookie } = await freshModules();
    expect(readCsrfCookie()).toBe("a+b=c");
  });

  it("does not match a cookie whose name merely ends in csrf_token", async () => {
    // Guards the regex boundary: `not_csrf_token=` must not be read as ours.
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "not_csrf_token=wrong-value";
    const { readCsrfCookie } = await freshModules();
    expect(readCsrfCookie()).toBe("");
    document.cookie = "not_csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });
});

describe("refreshAccessToken", () => {
  it("posts to /auth/refresh with credentials and the csrf header, and stores the token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { access_token: NEW_ACCESS }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { refreshAccessToken, authStorage } = await freshModules();
    const token = await refreshAccessToken();

    expect(token).toBe(NEW_ACCESS);
    expect(authStorage.getToken()).toBe(NEW_ACCESS);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/refresh");
    expect(init.method).toBe("POST");
    // credentials:"include" is what makes the browser send the HttpOnly
    // refresh cookie at all; without it the request is anonymous.
    expect(init.credentials).toBe("include");
    expect(init.headers["X-CSRF-Token"]).toBe(CSRF);
    // The refresh token must never be in the body — it is the cookie's job.
    expect(init.body).toBeUndefined();
  });

  it("makes NO request at all when there is no csrf cookie", async () => {
    // Caught by the pre-existing public-signup e2e spec: with the boot
    // refresh running on every page load, an anonymous visitor to the public
    // site has no cookies, so the request 403'd — a console error on a
    // surface where the volunteer e2e specs forbid them (PART-02), plus a
    // wasted per-IP throttle slot on every public page view.
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { refreshAccessToken, authStorage } = await freshModules();
    await expect(refreshAccessToken()).rejects.toThrow("NO_SESSION");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(authStorage.getToken()).toBe("");
  });

  it("authorizedFetch does not attempt a doomed refresh either", async () => {
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch } = await freshModules();
    const res = await authorizedFetch("https://x/y");

    expect(res.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1); // the original only
  });

  it.each([401, 403])(
    "clears the in-memory token on %i — the session is genuinely gone",
    async (status) => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, {})));
      const { refreshAccessToken, authStorage } = await freshModules();
      authStorage.setToken("stale-token");

      await expect(refreshAccessToken()).rejects.toThrow("REFRESH_REJECTED");
      expect(authStorage.getToken()).toBe("");
    },
  );

  it.each([429, 500, 502, 503])(
    "does NOT clear the token on %i — transient, and refresh runs on every page load",
    async (status) => {
      // The regression this guards: staff share one campus NAT, so the
      // per-IP throttle is reachable in normal use. Treating 429 as
      // "logged out" drops a still-valid session, and the re-login it
      // provokes consumes more quota.
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, {})));
      const { refreshAccessToken, authStorage } = await freshModules();
      authStorage.setToken("still-valid");

      await expect(refreshAccessToken()).rejects.toThrow(
        `REFRESH_UNAVAILABLE_${status}`,
      );
      expect(authStorage.getToken()).toBe("still-valid");
    },
  );

  it("collapses concurrent callers into one request", async () => {
    let resolveFetch;
    const fetchMock = vi.fn(
      () => new Promise((r) => {
        resolveFetch = () => r(jsonResponse(200, { access_token: NEW_ACCESS }));
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { refreshAccessToken } = await freshModules();
    const all = Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ]);
    resolveFetch();
    const results = await all;

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(results).toEqual([NEW_ACCESS, NEW_ACCESS, NEW_ACCESS]);
  });

  it("does not cache a rejection — a later call retries", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(500, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: NEW_ACCESS }));
    vi.stubGlobal("fetch", fetchMock);

    const { refreshAccessToken } = await freshModules();
    await expect(refreshAccessToken()).rejects.toThrow();
    await expect(refreshAccessToken()).resolves.toBe(NEW_ACCESS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("serializes through the Web Lock when navigator.locks exists", async () => {
    // Cross-tab serialization is what stops two tabs replaying the same
    // refresh cookie, which the server reads as token theft.
    const order = [];
    navigator.locks = {
      request: vi.fn(async (name, cb) => {
        order.push(`lock:${name}`);
        const out = await cb();
        order.push("unlock");
        return out;
      }),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        order.push("fetch");
        return jsonResponse(200, { access_token: NEW_ACCESS });
      }),
    );

    const { refreshAccessToken } = await freshModules();
    await expect(refreshAccessToken()).resolves.toBe(NEW_ACCESS);

    expect(navigator.locks.request).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["lock:uvs-auth-refresh", "fetch", "unlock"]);
  });

  it("always re-posts inside the lock even when a stale token is in memory", async () => {
    // The bug this pins: short-circuiting on "a token is already in memory"
    // would return the EXPIRED token on the 401 path, which is exactly when
    // refresh is called, and loop forever.
    navigator.locks = { request: vi.fn((_n, cb) => cb()) };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { access_token: NEW_ACCESS }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { refreshAccessToken, authStorage } = await freshModules();
    authStorage.setToken("expired-token");

    await expect(refreshAccessToken()).resolves.toBe(NEW_ACCESS);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("authorizedFetch", () => {
  it("attaches the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    await authorizedFetch("https://x/y");

    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe(
      "Bearer tok-1",
    );
  });

  it("sends no Authorization header when there is no token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch } = await freshModules();
    await authorizedFetch("https://x/y");

    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBeNull();
  });

  it("preserves a Headers instance instead of flattening it to {}", async () => {
    // `{...new Headers()}` yields {}, which would silently drop
    // Content-Type/Accept for any caller passing a Headers object.
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    await authorizedFetch("https://x/y", {
      headers: new Headers({ Accept: "text/event-stream" }),
    });

    const sent = fetchMock.mock.calls[0][1].headers;
    expect(sent.get("Accept")).toBe("text/event-stream");
    expect(sent.get("Authorization")).toBe("Bearer tok-1");
  });

  it("preserves the abort signal across the retry", async () => {
    const ac = new AbortController();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: NEW_ACCESS }))
      .mockResolvedValueOnce(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    const res = await authorizedFetch("https://x/y", { signal: ac.signal });

    expect(res.status).toBe(200);
    // first attempt and the retry both carry the signal
    expect(fetchMock.mock.calls[0][1].signal).toBe(ac.signal);
    expect(fetchMock.mock.calls[2][1].signal).toBe(ac.signal);
  });

  it("refreshes and retries once on 401, with the new token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: NEW_ACCESS }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("expired");
    const res = await authorizedFetch("https://x/y");

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1].headers.get("Authorization")).toBe(
      `Bearer ${NEW_ACCESS}`,
    );
  });

  it("retries on 401 even when no token was held initially", async () => {
    // A request that fires before the boot refresh finishes would otherwise
    // surface a spurious 401 to the caller.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: NEW_ACCESS }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch } = await freshModules();
    const res = await authorizedFetch("https://x/y");

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("returns the original 401 when the refresh itself fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: "nope" }))
      .mockResolvedValueOnce(jsonResponse(401, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("expired");
    const res = await authorizedFetch("https://x/y");

    expect(res.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2); // no third attempt
  });

  it("does not retry a request whose body cannot be replayed", async () => {
    // A ReadableStream body is consumed by the first attempt; retrying would
    // throw "body stream already read" instead of the 401 the caller expects.
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(401, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    const body = new ReadableStream({ start: (c) => c.close() });
    const res = await authorizedFetch("https://x/y", { method: "POST", body });

    expect(res.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["string", () => "a=1"],
    ["URLSearchParams", () => new URLSearchParams({ a: "1" })],
    ["Blob", () => new Blob(["x"])],
    ["ArrayBuffer", () => new ArrayBuffer(4)],
  ])("does retry a replayable %s body", async (_label, makeBody) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: NEW_ACCESS }))
      .mockResolvedValueOnce(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    const res = await authorizedFetch("https://x/y", {
      method: "POST",
      body: makeBody(),
    });

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("passes non-401 responses straight through", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, {}));
    vi.stubGlobal("fetch", fetchMock);

    const { authorizedFetch, authStorage } = await freshModules();
    authStorage.setToken("tok-1");
    const res = await authorizedFetch("https://x/y");

    expect(res.status).toBe(500);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("getAccessToken", () => {
  it("reflects the in-memory token", async () => {
    const { getAccessToken, authStorage } = await freshModules();
    expect(getAccessToken()).toBe("");
    authStorage.setToken("abc");
    expect(getAccessToken()).toBe("abc");
  });
});
