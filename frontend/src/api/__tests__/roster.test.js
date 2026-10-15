// The roster API helpers: each one has to hit the right path with the right
// verb, and a failure has to surface the server's message and the raw
// response, because the roster page reads `detail.code` (SLOT_CLOSED) off it.
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/authToken", () => ({ authorizedFetch: vi.fn() }));
vi.mock("../../lib/apiBase", () => ({ API_BASE: "http://api.test/api/v1" }));

import { authorizedFetch } from "../../lib/authToken";
import {
  fetchRoster,
  checkInSignup,
  undoCheckInSignup,
  checkInSession,
  undoCheckInSession,
  resolveSlot,
  reopenSlot,
  reopenEvent,
  isSlotClosedError,
  isSlotNotStartedError,
} from "../roster";

function ok(body, status = 200) {
  return { ok: true, status, json: () => Promise.resolve(body) };
}

function fail(status, body) {
  return {
    ok: false,
    status,
    json: () =>
      body === undefined ? Promise.reject(new Error("no body")) : Promise.resolve(body),
  };
}

const BASE = "http://api.test/api/v1";

beforeEach(() => {
  authorizedFetch.mockReset();
  authorizedFetch.mockResolvedValue(ok({ fine: true }));
});

describe("roster api paths", () => {
  it.each([
    ["fetchRoster", () => fetchRoster("ev-1"), "GET", "/events/ev-1/roster"],
    ["checkInSignup", () => checkInSignup("s-1"), "POST", "/signups/s-1/check-in"],
    ["undoCheckInSignup", () => undoCheckInSignup("s-1"), "POST", "/signups/s-1/undo-check-in"],
    ["checkInSession", () => checkInSession("c-1", "sl-1"), "POST", "/shift-signups/c-1/sessions/sl-1/check-in"],
    ["undoCheckInSession", () => undoCheckInSession("c-1", "sl-1"), "POST", "/shift-signups/c-1/sessions/sl-1/undo-check-in"],
    ["reopenSlot", () => reopenSlot("sl-1"), "POST", "/slots/sl-1/reopen"],
    ["reopenEvent", () => reopenEvent("ev-1"), "POST", "/events/ev-1/reopen"],
  ])("%s", async (_name, call, method, path) => {
    await expect(call()).resolves.toEqual({ fine: true });
    const [url, init] = authorizedFetch.mock.calls[0];
    expect(url).toBe(`${BASE}${path}`);
    expect(init.method).toBe(method);
    expect(init.body).toBeUndefined();
  });

  it("resolveSlot sends the decisions as JSON", async () => {
    await resolveSlot("sl-1", { attended: ["a"], no_show: ["b"], extra: 1 });
    const [url, init] = authorizedFetch.mock.calls[0];
    expect(url).toBe(`${BASE}/slots/sl-1/resolve`);
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ attended: ["a"], no_show: ["b"] });
  });

  it("returns null for a 204", async () => {
    authorizedFetch.mockResolvedValue(ok(null, 204));
    await expect(reopenSlot("sl-1")).resolves.toBeNull();
  });
});

describe("roster api errors", () => {
  it("uses a string detail as the message", async () => {
    authorizedFetch.mockResolvedValue(fail(404, { detail: "Slot not found" }));
    await expect(reopenSlot("sl-1")).rejects.toMatchObject({
      message: "Slot not found",
      status: 404,
    });
  });

  it("surfaces the real flattened SLOT_CLOSED body", async () => {
    // main.py's global handler: {error, code, detail: "<message>"}.
    const body = {
      error: "http_409",
      code: "SLOT_CLOSED",
      detail: "This slot is closed. Reopen it to change attendance.",
    };
    authorizedFetch.mockResolvedValue(fail(409, body));
    const err = await checkInSignup("s-1").catch((e) => e);
    expect(err.message).toBe("This slot is closed. Reopen it to change attendance.");
    expect(err.response).toEqual({ status: 409, data: body });
    expect(isSlotClosedError(err)).toBe(true);
  });

  it("keeps an object detail's code on the response for SLOT_CLOSED", async () => {
    const body = {
      detail: {
        code: "SLOT_CLOSED",
        message: "This slot is closed. Reopen it to change attendance.",
      },
    };
    authorizedFetch.mockResolvedValue(fail(409, body));
    const err = await checkInSignup("s-1").catch((e) => e);
    expect(err.message).toBe("This slot is closed. Reopen it to change attendance.");
    expect(err.status).toBe(409);
    expect(err.response).toEqual({ status: 409, data: body });
    // Nested shape is tolerated too.
    expect(isSlotClosedError(err)).toBe(true);
  });

  it("falls back to method, path and status without a usable body", async () => {
    authorizedFetch.mockResolvedValue(fail(500));
    const err = await reopenEvent("ev-1").catch((e) => e);
    expect(err.message).toBe("POST /events/ev-1/reopen failed (500)");
    expect(err.response).toEqual({ status: 500, data: null });
  });

  it("falls back when the detail object has no message", async () => {
    authorizedFetch.mockResolvedValue(fail(422, { detail: { code: "X" } }));
    await expect(fetchRoster("ev-1")).rejects.toThrow(
      "GET /events/ev-1/roster failed (422)",
    );
  });
});

describe("isSlotClosedError", () => {
  it("is false for anything that isn't a SLOT_CLOSED response", () => {
    expect(isSlotClosedError(undefined)).toBe(false);
    expect(isSlotClosedError(new Error("x"))).toBe(false);
    expect(isSlotClosedError({ response: { data: { code: "http_409" } } })).toBe(false);
    expect(isSlotClosedError({ response: { data: { detail: "SLOT_CLOSED" } } })).toBe(false);
  });
});

describe("isSlotNotStartedError", () => {
  it("reads the flattened code, or a nested one", () => {
    expect(
      isSlotNotStartedError({ response: { data: { code: "SLOT_NOT_STARTED" } } }),
    ).toBe(true);
    expect(
      isSlotNotStartedError({ response: { data: { detail: { code: "SLOT_NOT_STARTED" } } } }),
    ).toBe(true);
    expect(isSlotNotStartedError({ response: { data: { code: "SLOT_CLOSED" } } })).toBe(false);
    expect(isSlotNotStartedError(null)).toBe(false);
  });
});
