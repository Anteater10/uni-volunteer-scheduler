/**
 * api.public.test.js
 *
 * Tests for the api.public.* namespace — 5 helpers for unauthenticated
 * public endpoints. Verifies:
 *   - Correct URLs and HTTP methods
 *   - No Authorization header on public calls (T-10-01)
 *   - Query params serialised correctly
 *   - 429 errors propagate with err.status === 429 (D-08)
 *   - 409 errors propagate with err.status === 409 (capacity-full)
 */

import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Reset module between tests so fetch mock is clean
beforeEach(() => {
  localStorage.clear();
  vi.resetModules();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function makeOkFetch(body = {}) {
  return vi.fn(async () => ({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => body,
  }));
}

function makeErrorFetch(status, body = {}) {
  return vi.fn(async () => ({
    ok: false,
    status,
    headers: { get: () => "application/json" },
    json: async () => body,
  }));
}

function capturedUrl(mockFetch) {
  return mockFetch.mock.calls[0][0];
}

function capturedInit(mockFetch) {
  return mockFetch.mock.calls[0][1];
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

describe("api.public.getCurrentWeek", () => {
  it("calls GET /api/v1/public/current-week with auth:false", async () => {
    const mockFetch = makeOkFetch({ quarter: "spring", year: 2026, week_number: 3 });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    const result = await api.public.getCurrentWeek();

    expect(mockFetch).toHaveBeenCalledOnce();
    const url = capturedUrl(mockFetch);
    expect(url).toContain("/api/v1/public/current-week");

    // No Authorization header (T-10-01)
    const init = capturedInit(mockFetch);
    expect(init.headers?.Authorization).toBeUndefined();

    expect(result.quarter).toBe("spring");
  });
});

describe("api.public.listEvents", () => {
  it("calls GET /api/v1/public/events with correct query params and auth:false", async () => {
    const mockFetch = makeOkFetch([]);
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.public.listEvents({ quarter: "spring", year: 2026, week_number: 3 });

    expect(mockFetch).toHaveBeenCalledOnce();
    const url = capturedUrl(mockFetch);
    expect(url).toContain("/api/v1/public/events");
    expect(url).toContain("quarter=spring");
    expect(url).toContain("year=2026");
    expect(url).toContain("week_number=3");

    // No Authorization header (T-10-01)
    const init = capturedInit(mockFetch);
    expect(init.headers?.Authorization).toBeUndefined();
  });
});

describe("api.public.getEvent", () => {
  it("calls GET /api/v1/public/events/{uuid} with auth:false", async () => {
    const eventId = "550e8400-e29b-41d4-a716-446655440000";
    const mockFetch = makeOkFetch({ id: eventId, title: "SciTrek" });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.public.getEvent(eventId);

    expect(mockFetch).toHaveBeenCalledOnce();
    const url = capturedUrl(mockFetch);
    expect(url).toContain(`/api/v1/public/events/${eventId}`);

    const init = capturedInit(mockFetch);
    expect(init.headers?.Authorization).toBeUndefined();
  });
});

describe("api.public.createSignup", () => {
  it("calls POST /api/v1/public/signups with body and auth:false", async () => {
    const body = { first_name: "Alice", last_name: "Smith", email: "alice@example.com", slot_ids: [] };
    const mockFetch = makeOkFetch({ volunteer_id: "abc", signup_ids: [], magic_link_sent: true });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.public.createSignup(body);

    expect(mockFetch).toHaveBeenCalledOnce();
    const url = capturedUrl(mockFetch);
    expect(url).toContain("/api/v1/public/signups");

    const init = capturedInit(mockFetch);
    expect(init.method).toBe("POST");
    expect(init.headers?.Authorization).toBeUndefined();
    // Body should be JSON-encoded
    expect(JSON.parse(init.body).email).toBe("alice@example.com");
  });
});

describe("api.public.orientationStatus", () => {
  it("calls GET /api/v1/public/orientation-status?email= with auth:false", async () => {
    const mockFetch = makeOkFetch({ has_attended_orientation: true, last_attended_at: null });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.public.orientationStatus("alice@example.com");

    expect(mockFetch).toHaveBeenCalledOnce();
    const url = capturedUrl(mockFetch);
    expect(url).toContain("/api/v1/public/orientation-status");
    expect(url).toContain("email=alice%40example.com");

    const init = capturedInit(mockFetch);
    expect(init.headers?.Authorization).toBeUndefined();
  });
});

describe("api.public error propagation", () => {
  it("429 response: error has err.status === 429 (D-08 rate-limit detection)", async () => {
    const mockFetch = makeErrorFetch(429, { detail: "Too Many Requests" });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    let caught = null;
    try {
      await api.public.getCurrentWeek();
    } catch (e) {
      caught = e;
    }
    expect(caught).not.toBeNull();
    expect(caught.status).toBe(429);
  });

  it("409 response: error has err.status === 409 (capacity-full)", async () => {
    const mockFetch = makeErrorFetch(409, { detail: "slot capacity full" });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    let caught = null;
    try {
      await api.public.createSignup({ slot_ids: ["abc"] });
    } catch (e) {
      caught = e;
    }
    expect(caught).not.toBeNull();
    expect(caught.status).toBe(409);
  });
});
