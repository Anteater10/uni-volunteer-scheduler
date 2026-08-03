/**
 * api.slots.test.js
 *
 * Regression tests for the api.slots.* namespace.
 *
 * The namespace was missing from api.js entirely while EventsSection.jsx
 * called api.slots.create/update/delete to persist slot edits — saving an
 * event threw "Cannot read properties of undefined (reading 'update')"
 * after the event PUT had already succeeded, so slot changes were silently
 * dropped. EventsSection.test.jsx never caught it because its api mock
 * invents a slots object, asserting against a namespace that existed only
 * in the mock.
 *
 * These tests import the REAL api module, so they fail if the namespace or
 * any of its methods goes missing again.
 */

import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

beforeEach(() => {
  localStorage.clear();
  vi.resetModules();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

function makeOkFetch(body = {}) {
  return vi.fn(async () => ({
    ok: true,
    status: 200,
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

describe("api.slots namespace", () => {
  it("exposes every method EventsSection and friends call", async () => {
    const { api } = await import("../api.js");

    expect(api.slots).toBeDefined();
    for (const method of ["list", "create", "update", "delete", "generate"]) {
      expect(typeof api.slots[method]).toBe("function");
    }
  });

  it("list calls GET /slots/ with params", async () => {
    const mockFetch = makeOkFetch([]);
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.slots.list({ event_id: "evt-1" });

    expect(capturedUrl(mockFetch)).toContain("/slots/?event_id=evt-1");
    expect(capturedInit(mockFetch).method).toBe("GET");
  });

  it("create posts to /slots/ with event_id as a query param", async () => {
    const mockFetch = makeOkFetch({ id: "slot-1" });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.slots.create("evt-1", { capacity: 4 });

    const url = capturedUrl(mockFetch);
    expect(url).toContain("/slots/");
    expect(url).toContain("event_id=evt-1");

    const init = capturedInit(mockFetch);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ capacity: 4 });
  });

  it("update PATCHes /slots/{id} with the payload", async () => {
    const mockFetch = makeOkFetch({ id: "slot-1" });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.slots.update("slot-1", { capacity: 40 });

    expect(capturedUrl(mockFetch)).toContain("/slots/slot-1");

    const init = capturedInit(mockFetch);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ capacity: 40 });
  });

  it("delete DELETEs /slots/{id}", async () => {
    const mockFetch = makeOkFetch({});
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.slots.delete("slot-1");

    expect(capturedUrl(mockFetch)).toContain("/slots/slot-1");
    expect(capturedInit(mockFetch).method).toBe("DELETE");
  });

  it("generate posts to /events/{id}/generate_slots", async () => {
    const mockFetch = makeOkFetch({ created: 3 });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("../api.js");
    await api.slots.generate("evt-1", { slot_type: "period", date: "2026-08-04" });

    expect(capturedUrl(mockFetch)).toContain("/events/evt-1/generate_slots");
    expect(capturedInit(mockFetch).method).toBe("POST");
  });
});
