// api.endpoints.test.js — every API helper sends the method, URL and body the
// backend expects, and the shared request/download/auth plumbing handles each
// response shape (errors, 204, refresh-on-401, non-JSON bodies).

vi.mock("../authStorage", () => ({
  default: { getToken: vi.fn(), setToken: vi.fn(), clearAll: vi.fn() },
}));
vi.mock("../authToken", () => ({
  authorizedFetch: vi.fn(),
  refreshAccessToken: vi.fn(),
  readCsrfCookie: vi.fn(),
}));

import { vi, describe, it, expect, beforeEach } from "vitest";
import authStorage from "../authStorage";
import { authorizedFetch, refreshAccessToken, readCsrfCookie } from "../authToken";
import { API_BASE } from "../apiBase";
import api, { downloadBlob } from "../api";

function jsonResponse(data, { status = 200, headers = {} } = {}) {
  const h = new Headers({ "content-type": "application/json", ...headers });
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: h,
    json: async () => data,
    blob: async () => new Blob(["x"]),
  };
}

function textResponse(status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "text/plain" }),
    json: async () => {
      throw new Error("not json");
    },
    blob: async () => new Blob(["a,b"]),
  };
}

let fetchMock;
beforeEach(() => {
  vi.clearAllMocks();
  fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
  globalThis.fetch = fetchMock;
  authStorage.getToken.mockReturnValue("tok");
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1);
  return {
    url: url.replace(API_BASE, ""),
    method: init.method,
    body: init.body === undefined ? undefined : JSON.parse(init.body),
    init,
  };
}

// [label, call, method, path (with query), body]
const ENDPOINTS = [
  ["changePassword", () => api.changePassword("a", "b"), "POST", "/auth/change-password", { current_password: "a", new_password: "b" }],
  ["forgotPassword", () => api.forgotPassword("e@x.com"), "POST", "/auth/forgot-password", { email: "e@x.com" }],
  ["me", () => api.me(), "GET", "/users/me"],
  ["updateMe", () => api.updateMe({ name: "N" }), "PATCH", "/users/me", { name: "N" }],
  ["listEvents", () => api.listEvents({ q: "x" }), "GET", "/events/?q=x"],
  ["events.list", () => api.events.list(), "GET", "/events/"],
  ["events.get", () => api.events.get("e1"), "GET", "/events/e1"],
  ["events.create", () => api.events.create({ t: 1 }), "POST", "/events/", { t: 1 }],
  ["events.update", () => api.events.update("e1", { t: 2 }), "PUT", "/events/e1", { t: 2 }],
  ["events.delete", () => api.events.delete("e1"), "DELETE", "/events/e1"],
  ["getEvent", () => api.getEvent("e1"), "GET", "/events/e1"],
  ["createEvent", () => api.createEvent({ a: 1 }), "POST", "/events/", { a: 1 }],
  ["updateEvent", () => api.updateEvent("e1", { a: 1 }), "PUT", "/events/e1", { a: 1 }],
  ["deleteEvent", () => api.deleteEvent("e1"), "DELETE", "/events/e1"],
  ["slots.list", () => api.slots.list({ event_id: "e1" }), "GET", "/slots/?event_id=e1"],
  ["slots.create", () => api.slots.create("e1", { c: 1 }), "POST", "/slots/?event_id=e1", { c: 1 }],
  ["slots.update", () => api.slots.update("s1", { c: 2 }), "PATCH", "/slots/s1", { c: 2 }],
  ["slots.delete", () => api.slots.delete("s1"), "DELETE", "/slots/s1"],
  ["slots.generate", () => api.slots.generate("e1", { g: 1 }), "POST", "/events/e1/generate_slots", { g: 1 }],
  ["listSlots", () => api.listSlots({ event_id: "e1" }), "GET", "/slots/?event_id=e1"],
  ["createSlot", () => api.createSlot("e1", {}), "POST", "/slots/?event_id=e1", {}],
  ["updateSlot", () => api.updateSlot("s1", {}), "PATCH", "/slots/s1", {}],
  ["deleteSlot", () => api.deleteSlot("s1"), "DELETE", "/slots/s1"],
  ["generateSlots", () => api.generateSlots("e1", {}), "POST", "/events/e1/generate_slots", {}],
  ["shifts.list", () => api.shifts.list("e1"), "GET", "/shifts/?event_id=e1"],
  ["shifts.create", () => api.shifts.create("e1", { n: 1 }), "POST", "/shifts/?event_id=e1", { n: 1 }],
  ["shifts.update", () => api.shifts.update("sh1", { n: 2 }), "PATCH", "/shifts/sh1", { n: 2 }],
  ["shifts.delete", () => api.shifts.delete("sh1"), "DELETE", "/shifts/sh1"],
  ["shifts.reorder", () => api.shifts.reorder("e1", ["a", "b"]), "POST", "/shifts/reorder?event_id=e1", { shift_ids: ["a", "b"] }],
  ["shifts.addSession", () => api.shifts.addSession("sh1", { s: 1 }), "POST", "/shifts/sh1/sessions", { s: 1 }],
  ["shifts.updateSession", () => api.shifts.updateSession("se1", { s: 2 }), "PATCH", "/shifts/sessions/se1", { s: 2 }],
  ["shifts.deleteSession", () => api.shifts.deleteSession("se1"), "DELETE", "/shifts/sessions/se1"],
  ["shifts.reorderSessions", () => api.shifts.reorderSessions("sh1", ["x"]), "POST", "/shifts/sh1/sessions/reorder", { session_ids: ["x"] }],
  ["shifts.swapSignup", () => api.shifts.swapSignup("ss1", "sh2"), "POST", "/shift-signups/ss1/swap", { target_shift_id: "sh2" }],
  ["shifts.checkInSession", () => api.shifts.checkInSession("ss1", "sl1", { a: 1 }), "POST", "/shift-signups/ss1/sessions/sl1/check-in", { a: 1 }],
  ["shifts.undoSessionCheckIn", () => api.shifts.undoSessionCheckIn("ss1", "sl1", { a: 1 }), "POST", "/shift-signups/ss1/sessions/sl1/undo-check-in", { a: 1 }],
  ["listEventQuestions", () => api.listEventQuestions("e1"), "GET", "/events/e1/questions"],
  ["createEventQuestion", () => api.createEventQuestion("e1", { q: 1 }), "POST", "/events/e1/questions", { q: 1 }],
  ["updateEventQuestion", () => api.updateEventQuestion("q1", { q: 2 }), "PUT", "/events/questions/q1", { q: 2 }],
  ["deleteEventQuestion", () => api.deleteEventQuestion("q1"), "DELETE", "/events/questions/q1"],
  ["listMyNotifications", () => api.listMyNotifications({ limit: 5 }), "GET", "/notifications/my?limit=5"],
  ["notifications.my", () => api.notifications.my(), "GET", "/notifications/my"],
  ["adminSummary", () => api.adminSummary({ quarter_id: "q" }), "GET", "/admin/summary?quarter_id=q"],
  ["adminListUsers", () => api.adminListUsers(), "GET", "/users"],
  ["adminCreateUser", () => api.adminCreateUser({ e: 1 }), "POST", "/users", { e: 1 }],
  ["adminUpdateUser", () => api.adminUpdateUser("u1", { e: 2 }), "PATCH", "/users/u1", { e: 2 }],
  ["adminDeleteUser", () => api.adminDeleteUser("u1"), "DELETE", "/admin/users/u1"],
  ["adminAuditLogs", () => api.adminAuditLogs({ page: 2 }), "GET", "/admin/audit-logs?page=2"],
  ["public.getCurrentWeek", () => api.public.getCurrentWeek(), "GET", "/public/current-week"],
  ["public.getQuarters", () => api.public.getQuarters(), "GET", "/public/quarters"],
  ["public.listEvents", () => api.public.listEvents({ week: 3 }), "GET", "/public/events?week=3"],
  ["public.getEvent", () => api.public.getEvent("e1"), "GET", "/public/events/e1"],
  ["public.createSignup", () => api.public.createSignup({ a: 1 }), "POST", "/public/signups", { a: 1 }],
  ["public.orientationStatus", () => api.public.orientationStatus("e@x.com"), "GET", "/public/orientation-status?email=e%40x.com"],
  ["public.orientationCheck", () => api.public.orientationCheck("e@x.com", "e1"), "GET", "/public/orientation-check?email=e%40x.com&event_id=e1"],
  ["public.getFormSchema", () => api.public.getFormSchema("e1"), "GET", "/public/events/e1/form-schema"],
  ["public.confirmSignup", () => api.public.confirmSignup("t"), "POST", "/public/signups/confirm?token=t"],
  ["public.getManageSignups", () => api.public.getManageSignups("t"), "GET", "/public/signups/manage?token=t"],
  ["public.getPreferences", () => api.public.getPreferences("m"), "GET", "/public/preferences?manage_token=m"],
  ["public.updatePreferences", () => api.public.updatePreferences("m", { sms: false }), "PUT", "/public/preferences?manage_token=m", { sms: false }],
  ["public.checkInByEmail", () => api.public.checkInByEmail("e1", "e@x.com", "1234"), "POST", "/events/e1/check-in-by-email", { email: "e@x.com", venue_code: "1234" }],
  ["public.checkInLookup", () => api.public.checkInLookup("e1", "e@x.com", "1234"), "POST", "/events/e1/check-in-lookup", { email: "e@x.com", venue_code: "1234" }],
  ["public.checkInSelected", () => api.public.checkInSelected("e1", "e@x.com", ["u"], "1234"), "POST", "/events/e1/check-in-selected", { email: "e@x.com", venue_code: "1234", unit_ids: ["u"] }],
  ["organizer.grantOrientation", () => api.organizer.grantOrientation("e1", "s1"), "POST", "/organizer/events/e1/signups/s1/grant-orientation"],
  ["organizer.grantOrientationForShift", () => api.organizer.grantOrientationForShift("e1", "ss1"), "POST", "/organizer/events/e1/shift-signups/ss1/grant-orientation"],
  ["organizer.appendEventField", () => api.organizer.appendEventField("e1", { f: 1 }), "POST", "/organizer/events/e1/form-fields", { f: 1 }],
  ["organizer.promoteSignup", () => api.organizer.promoteSignup("e1", "s1"), "POST", "/organizer/events/e1/signups/s1/promote"],
  ["organizer.promoteSignup overfill", () => api.organizer.promoteSignup("e1", "s1", { allowOverfill: true }), "POST", "/organizer/events/e1/signups/s1/promote?allow_overfill=true"],
  ["organizer.promoteShiftSignup", () => api.organizer.promoteShiftSignup("e1", "ss1"), "POST", "/organizer/events/e1/shift-signups/ss1/promote"],
  ["organizer.promoteShiftSignup overfill", () => api.organizer.promoteShiftSignup("e1", "ss1", { allowOverfill: true }), "POST", "/organizer/events/e1/shift-signups/ss1/promote?allow_overfill=true"],
  ["organizer.broadcastRecipientCount", () => api.organizer.broadcastRecipientCount("e1", { slot_id: "s" }), "GET", "/events/e1/broadcast-recipients?slot_id=s"],
  ["organizer.listBroadcasts", () => api.organizer.listBroadcasts("e1"), "GET", "/events/e1/broadcasts?days=30"],
  ["organizer.listBroadcasts days", () => api.organizer.listBroadcasts("e1", 7), "GET", "/events/e1/broadcasts?days=7"],
  ["admin.summary", () => api.admin.summary(), "GET", "/admin/summary"],
  ["admin.siteSettings.get", () => api.admin.siteSettings.get(), "GET", "/admin/site-settings"],
  ["admin.siteSettings.update", () => api.admin.siteSettings.update({ c: 1 }), "PATCH", "/admin/site-settings", { c: 1 }],
  ["admin.users.list", () => api.admin.users.list(), "GET", "/users/"],
  ["admin.users.create", () => api.admin.users.create({ a: 1 }), "POST", "/users", { a: 1 }],
  ["admin.users.update", () => api.admin.users.update("u1", { a: 1 }), "PATCH", "/users/u1", { a: 1 }],
  ["admin.users.delete", () => api.admin.users.delete("u1"), "DELETE", "/admin/users/u1"],
  ["admin.users.invite", () => api.admin.users.invite({ email: "e" }), "POST", "/users/invite", { email: "e" }],
  ["admin.users.deactivate", () => api.admin.users.deactivate("u1"), "POST", "/users/u1/deactivate", {}],
  ["admin.users.reactivate", () => api.admin.users.reactivate("u1"), "POST", "/users/u1/reactivate", {}],
  ["admin.users.ccpaExport", () => api.admin.users.ccpaExport("u1", "r"), "GET", "/admin/users/u1/ccpa-export?reason=r"],
  ["admin.users.ccpaDelete", () => api.admin.users.ccpaDelete("u1", "r"), "POST", "/admin/users/u1/ccpa-delete", { reason: "r" }],
  ["admin.auditLogs", () => api.admin.auditLogs(), "GET", "/admin/audit-logs"],
  ["admin.eventAnalytics", () => api.admin.eventAnalytics("e1"), "GET", "/admin/events/e1/analytics"],
  ["admin.eventRoster", () => api.admin.eventRoster("e1", "full"), "GET", "/admin/events/e1/roster?privacy=full"],
  ["admin.notify", () => api.admin.notify("e1", { m: 1 }), "POST", "/admin/events/e1/notify", { m: 1 }],
  ["admin.signups.cancel", () => api.admin.signups.cancel("s1"), "POST", "/admin/signups/s1/cancel"],
  ["admin.signups.uncancel", () => api.admin.signups.uncancel("s1"), "POST", "/admin/signups/s1/uncancel"],
  ["admin.signups.promote", () => api.admin.signups.promote("s1"), "POST", "/admin/signups/s1/promote"],
  ["admin.signups.move", () => api.admin.signups.move("s1", "sl2"), "POST", "/admin/signups/s1/move", { target_slot_id: "sl2" }],
  ["admin.signups.resend", () => api.admin.signups.resend("s1"), "POST", "/admin/signups/s1/resend"],
  ["admin.shiftSignups.promote", () => api.admin.shiftSignups.promote("ss1"), "POST", "/admin/shift-signups/ss1/promote"],
  ["admin.shiftSignups.cancel", () => api.admin.shiftSignups.cancel("ss1"), "POST", "/admin/shift-signups/ss1/cancel"],
  ["admin.shiftSignups.uncancel", () => api.admin.shiftSignups.uncancel("ss1"), "POST", "/admin/shift-signups/ss1/uncancel"],
  ["admin.shiftSignups.swap", () => api.admin.shiftSignups.swap("ss1", "sh2"), "POST", "/shift-signups/ss1/swap", { target_shift_id: "sh2" }],
  ["admin.analytics.volunteerHours", () => api.admin.analytics.volunteerHours(), "GET", "/admin/analytics/volunteer-hours"],
  ["admin.analytics.attendanceRates", () => api.admin.analytics.attendanceRates(), "GET", "/admin/analytics/attendance-rates"],
  ["admin.analytics.noShowRates", () => api.admin.analytics.noShowRates(), "GET", "/admin/analytics/no-show-rates"],
  ["admin.analytics.eventFillRates", () => api.admin.analytics.eventFillRates(), "GET", "/admin/analytics/event-fill-rates"],
  ["admin.analytics.hoursBySchool", () => api.admin.analytics.hoursBySchool(), "GET", "/admin/analytics/hours-by-school"],
  ["admin.analytics.uniqueVolunteers", () => api.admin.analytics.uniqueVolunteers(), "GET", "/admin/analytics/unique-volunteers"],
  ["admin.analytics.cancellationRates", () => api.admin.analytics.cancellationRates(), "GET", "/admin/analytics/cancellation-rates"],
  ["admin.analytics.modulePopularity", () => api.admin.analytics.modulePopularity({ q: 1 }), "GET", "/admin/analytics/module-popularity?q=1"],
  ["admin.quarters.list", () => api.admin.quarters.list(), "GET", "/admin/quarters"],
  ["admin.quarters.create", () => api.admin.quarters.create({ q: 1 }), "POST", "/admin/quarters", { q: 1 }],
  ["admin.quarters.update", () => api.admin.quarters.update("q1", { q: 2 }), "PATCH", "/admin/quarters/q1", { q: 2 }],
  ["admin.quarters.remove", () => api.admin.quarters.remove("q1"), "DELETE", "/admin/quarters/q1"],
  ["admin.quarters.archive", () => api.admin.quarters.archive("q1"), "POST", "/admin/quarters/q1/archive"],
  ["admin.quarters.restore", () => api.admin.quarters.restore("q1"), "POST", "/admin/quarters/q1/restore"],
  ["admin.quarters.retrospective", () => api.admin.quarters.retrospective("q1"), "GET", "/admin/quarters/q1/retrospective"],
  ["admin.modules.list", () => api.admin.modules.list({ all: 1 }), "GET", "/admin/modules?all=1"],
  ["admin.modules.create", () => api.admin.modules.create({ m: 1 }), "POST", "/admin/modules", { m: 1 }],
  ["admin.modules.update", () => api.admin.modules.update("bio", { m: 2 }), "PATCH", "/admin/modules/bio", { m: 2 }],
  ["admin.modules.delete", () => api.admin.modules.delete("bio"), "DELETE", "/admin/modules/bio"],
  ["admin.modules.restore", () => api.admin.modules.restore("bio"), "POST", "/admin/modules/bio/restore"],
  ["admin.modules.clone", () => api.admin.modules.clone("bio", { new_slug: "b2", new_name: "B2" }), "POST", "/admin/modules/bio/clone", { new_slug: "b2", new_name: "B2" }],
  ["admin.modules.setDefaultFormSchema", () => api.admin.modules.setDefaultFormSchema("bio", [1]), "PUT", "/admin/modules/bio/default-form-schema", { schema: [1] }],
  ["admin.setEventFormSchema", () => api.admin.setEventFormSchema("e1", [1]), "PUT", "/admin/events/e1/form-schema", { schema: [1] }],
  ["admin.addVolunteer", () => api.admin.addVolunteer("e1", { email: "e" }), "POST", "/admin/events/e1/add-volunteer", { email: "e" }],
  ["admin.reorderShiftWaitlist", () => api.admin.reorderShiftWaitlist("e1", "sh1", ["a"]), "PATCH", "/admin/events/e1/shifts/sh1/waitlist-order", { ordered_shift_signup_ids: ["a"] }],
  ["admin.reorderWaitlist", () => api.admin.reorderWaitlist("e1", "sl1", ["a"]), "PATCH", "/admin/events/e1/slots/sl1/waitlist-order", { ordered_signup_ids: ["a"] }],
  ["admin.reminders.listUpcoming", () => api.admin.reminders.listUpcoming(), "GET", "/admin/reminders/upcoming?days=7"],
  ["admin.reminders.listUpcoming days", () => api.admin.reminders.listUpcoming(3), "GET", "/admin/reminders/upcoming?days=3"],
  ["admin.reminders.sendNow signup", () => api.admin.reminders.sendNow({ signupId: "s1", kind: "k" }), "POST", "/admin/reminders/send-now", { signup_id: "s1", shift_signup_id: null, slot_id: null, kind: "k" }],
  ["admin.reminders.sendNow session", () => api.admin.reminders.sendNow({ shiftSignupId: "ss1", slotId: "sl1", kind: "k" }), "POST", "/admin/reminders/send-now", { signup_id: null, shift_signup_id: "ss1", slot_id: "sl1", kind: "k" }],
  ["admin.reminders.sendNow shift without slot", () => api.admin.reminders.sendNow({ shiftSignupId: "ss1", kind: "k" }), "POST", "/admin/reminders/send-now", { signup_id: null, shift_signup_id: "ss1", slot_id: null, kind: "k" }],
  ["admin.broadcastRecipientCount", () => api.admin.broadcastRecipientCount("e1"), "GET", "/events/e1/broadcast-recipients"],
  ["admin.listBroadcasts", () => api.admin.listBroadcasts("e1"), "GET", "/events/e1/broadcasts?days=30"],
  ["admin.listBroadcasts days", () => api.admin.listBroadcasts("e1", 5), "GET", "/events/e1/broadcasts?days=5"],
  ["admin.orientationCredits.list", () => api.admin.orientationCredits.list(), "GET", "/admin/orientation-credits"],
  ["admin.orientationCredits.create", () => api.admin.orientationCredits.create({ volunteer_email: "e", family_key: "f", quarter_id: "q" }), "POST", "/admin/orientation-credits", { volunteer_email: "e", family_key: "f", quarter_id: "q", notes: null }],
  ["admin.orientationCredits.create notes", () => api.admin.orientationCredits.create({ volunteer_email: "e", family_key: "f", quarter_id: "q", notes: "n" }), "POST", "/admin/orientation-credits", { volunteer_email: "e", family_key: "f", quarter_id: "q", notes: "n" }],
  ["admin.orientationCredits.revoke", () => api.admin.orientationCredits.revoke("c1"), "DELETE", "/admin/orientation-credits/c1"],
];

describe("every API helper hits the right endpoint", () => {
  it.each(ENDPOINTS)("%s", async (_label, call, method, path, body) => {
    await call();
    const c = lastCall();
    expect(c.method).toBe(method);
    expect(c.url).toBe(path);
    expect(c.body).toEqual(body);
  });

  it("modules.bulkDelete deletes each slug", async () => {
    await api.admin.modules.bulkDelete(["a", "b"]);
    expect(fetchMock.mock.calls.map(([u, i]) => [u.replace(API_BASE, ""), i.method])).toEqual([
      ["/admin/modules/a", "DELETE"],
      ["/admin/modules/b", "DELETE"],
    ]);
  });

  it("public helpers send no Authorization header", async () => {
    await api.public.getEvent("e1");
    expect(lastCall().init.headers.Authorization).toBeUndefined();
  });

  it("staff helpers send the bearer token", async () => {
    await api.me();
    expect(lastCall().init.headers.Authorization).toBe("Bearer tok");
  });

  it("auth paths include credentials", async () => {
    await api.changePassword("a", "b");
    expect(lastCall().init.credentials).toBe("include");
    await api.me();
    expect(lastCall().init.credentials).toBeUndefined();
  });

  it("drops empty query params", async () => {
    await api.listEvents({ a: "", b: null, c: undefined, d: 0 });
    expect(lastCall().url).toBe("/events/?d=0");
  });
});

describe("request() response handling", () => {
  it("returns null for 204", async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204, headers: new Headers() });
    await expect(api.me()).resolves.toBeNull();
  });

  it("returns null for a non-JSON success body", async () => {
    fetchMock.mockResolvedValueOnce(textResponse(200));
    await expect(api.me()).resolves.toBeNull();
  });

  it("returns null when a JSON body fails to parse", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true, status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => { throw new SyntaxError("bad"); },
    });
    await expect(api.me()).resolves.toBeNull();
  });

  it.each([
    [{ detail: "plain detail" }, "plain detail"],
    [{ detail: ["first string"] }, "first string"],
    [{ detail: [{ msg: "field msg" }] }, "field msg"],
    [{ detail: [{ loc: ["x"] }] }, "GET /users/me failed (400)"],
    [{ detail: [] }, "GET /users/me failed (400)"],
    [{ message: "top message" }, "top message"],
    [{ other: 1 }, "GET /users/me failed (400)"],
  ])("error message from %j", async (json, message) => {
    fetchMock.mockResolvedValueOnce(jsonResponse(json, { status: 400 }));
    await expect(api.me()).rejects.toMatchObject({ message, status: 400 });
  });

  it("error without a JSON body uses the fallback", async () => {
    fetchMock.mockResolvedValueOnce(textResponse(500));
    await expect(api.me()).rejects.toMatchObject({
      message: "GET /users/me failed (500)",
      response: { status: 500, data: null },
    });
  });

  it("carries a top-level error code", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ code: "ORIENTATION_REQUIRED", detail: "x" }, { status: 422 }));
    await expect(api.public.createSignup({})).rejects.toMatchObject({ code: "ORIENTATION_REQUIRED" });
  });

  it("falls back to a nested detail.code", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: { code: "NESTED" } }, { status: 422 }));
    await expect(api.public.createSignup({})).rejects.toMatchObject({ code: "NESTED" });
  });

  it("leaves code unset when there is none", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "x" }, { status: 400 }));
    const err = await api.me().catch((e) => e);
    expect(err.code).toBeUndefined();
  });

  it("retries once with a fresh token on 401", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({}, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ id: 1 }));
    refreshAccessToken.mockResolvedValueOnce("new-tok");
    await expect(api.me()).resolves.toEqual({ id: 1 });
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer new-tok");
  });

  it("clears auth and throws when the refresh fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, { status: 401 }));
    refreshAccessToken.mockRejectedValueOnce(new Error("no"));
    await expect(api.me()).rejects.toThrow(/session expired/i);
    expect(authStorage.clearAll).toHaveBeenCalled();
  });

  it("does not retry a 401 without a token", async () => {
    authStorage.getToken.mockReturnValue("");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, { status: 401 }));
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(refreshAccessToken).not.toHaveBeenCalled();
  });

  it("does not retry a 401 on a public (auth=false) call", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, { status: 401 }));
    await expect(api.public.getEvent("e1")).rejects.toMatchObject({ status: 401 });
    expect(refreshAccessToken).not.toHaveBeenCalled();
  });
});

describe("login / logout / invite", () => {
  it("login stores the access token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "a1" }));
    await api.login("e@x.com", "pw");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE}/auth/token`);
    expect(init.body).toBe("username=e%40x.com&password=pw");
    expect(init.credentials).toBe("include");
    expect(authStorage.setToken).toHaveBeenCalledWith("a1");
  });

  it("login without a token in the body stores nothing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}));
    await api.login("e@x.com", "pw");
    expect(authStorage.setToken).not.toHaveBeenCalled();
  });

  it("login failure throws the server message", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Bad creds" }, { status: 401 }));
    await expect(api.login("e", "p")).rejects.toThrow("Bad creds");
  });

  it("login failure without a body uses the fallback", async () => {
    fetchMock.mockResolvedValueOnce(textResponse(500));
    await expect(api.login("e", "p")).rejects.toThrow("POST /auth/token failed (500)");
  });

  it("logout sends bearer and csrf when present", async () => {
    readCsrfCookie.mockReturnValue("csrf1");
    await api.logout();
    const init = fetchMock.mock.calls[0][1];
    expect(init.headers).toEqual({ Authorization: "Bearer tok", "X-CSRF-Token": "csrf1" });
    expect(authStorage.clearAll).toHaveBeenCalled();
  });

  it("logout still clears locally when offline and with no tokens", async () => {
    authStorage.getToken.mockReturnValue("");
    readCsrfCookie.mockReturnValue("");
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await api.logout();
    expect(fetchMock.mock.calls[0][1].headers).toEqual({});
    expect(authStorage.clearAll).toHaveBeenCalled();
  });

  it("setPasswordFromInvite stores a returned token", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "a2" }));
    await api.setPasswordFromInvite("t", "pw");
    expect(lastCall()).toMatchObject({ url: "/auth/set-password", method: "POST", body: { token: "t", password: "pw" } });
    expect(authStorage.setToken).toHaveBeenCalledWith("a2");
  });

  it("setPasswordFromInvite without a token stores nothing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}));
    await api.setPasswordFromInvite("t", "pw");
    expect(authStorage.setToken).not.toHaveBeenCalled();
  });
});

describe("sendBroadcast", () => {
  beforeEach(() => authorizedFetch.mockResolvedValue(jsonResponse({ sent: 3 })));

  it("sends subject and body only when no scope is given", async () => {
    await expect(api.admin.sendBroadcast("e1", { subject: "S", body_markdown: "B" })).resolves.toEqual({ sent: 3 });
    const [url, init] = authorizedFetch.mock.calls[0];
    expect(url).toBe(`${API_BASE}/events/e1/broadcast`);
    expect(JSON.parse(init.body)).toEqual({ subject: "S", body_markdown: "B" });
  });

  it("includes slot and shift scope when given", async () => {
    await api.organizer.sendBroadcast("e1", { subject: "S", body_markdown: "B", slot_id: "s", shift_id: "h" });
    expect(JSON.parse(authorizedFetch.mock.calls[0][1].body)).toEqual({ subject: "S", body_markdown: "B", slot_id: "s", shift_id: "h" });
  });

  it("429 carries retryAfter", async () => {
    authorizedFetch.mockResolvedValueOnce(jsonResponse({ detail: "slow down" }, { status: 429, headers: { "Retry-After": "42" } }));
    await expect(api.admin.sendBroadcast("e1", {})).rejects.toMatchObject({ status: 429, retryAfter: 42, message: "slow down" });
  });

  it("429 without Retry-After has a null retryAfter", async () => {
    authorizedFetch.mockResolvedValueOnce(jsonResponse({}, { status: 429 }));
    await expect(api.admin.sendBroadcast("e1", {})).rejects.toMatchObject({ retryAfter: null, message: "Broadcast failed (429)" });
  });

  it("other errors have no retryAfter", async () => {
    authorizedFetch.mockResolvedValueOnce(jsonResponse({}, { status: 500 }));
    const err = await api.admin.sendBroadcast("e1", {}).catch((e) => e);
    expect(err.status).toBe(500);
    expect(err.retryAfter).toBeUndefined();
  });
});

describe("resendMagicLink", () => {
  it("posts the email and event", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: 1 }));
    await expect(api.resendMagicLink({ email: "e", eventId: "e1" })).resolves.toEqual({ ok: 1 });
    expect(lastCall()).toMatchObject({ url: "/auth/magic/resend", method: "POST", body: { email: "e", event_id: "e1" } });
  });

  it("throws with the status on failure", async () => {
    fetchMock.mockResolvedValueOnce(textResponse(429));
    await expect(api.resendMagicLink({ email: "e", eventId: "e1" })).rejects.toMatchObject({
      status: 429, message: "POST /auth/magic/resend failed (429)",
    });
  });
});

describe("downloadBlob and CSV helpers", () => {
  beforeEach(() => {
    globalThis.URL.createObjectURL = vi.fn(() => "blob:1");
    globalThis.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    authorizedFetch.mockResolvedValue(textResponse(200));
  });

  it.each([
    ["volunteerHoursCsv", "/admin/analytics/volunteer-hours.csv", "volunteer-hours.csv"],
    ["attendanceRatesCsv", "/admin/analytics/attendance-rates.csv", "attendance-rates.csv"],
    ["noShowRatesCsv", "/admin/analytics/no-show-rates.csv", "no-show-rates.csv"],
    ["eventFillRatesCsv", "/admin/analytics/event-fill-rates.csv", "event-fill-rates.csv"],
    ["hoursBySchoolCsv", "/admin/analytics/hours-by-school.csv", "hours-by-school.csv"],
    ["uniqueVolunteersCsv", "/admin/analytics/unique-volunteers.csv", "unique-volunteers.csv"],
    ["cancellationRatesCsv", "/admin/analytics/cancellation-rates.csv", "cancellation-rates.csv"],
    ["modulePopularityCsv", "/admin/analytics/module-popularity.csv", "module-popularity.csv"],
  ])("%s downloads through the authorized fetch", async (name, path) => {
    await api.admin.analytics[name]({ from: "2026-01-01" });
    expect(authorizedFetch.mock.calls[0][0]).toBe(`${API_BASE}${path}?from=2026-01-01`);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
  });

  it("CSV helpers default to no params", async () => {
    await api.admin.analytics.volunteerHoursCsv();
    expect(authorizedFetch.mock.calls[0][0]).toBe(`${API_BASE}/admin/analytics/volunteer-hours.csv`);
  });

  it("a public download uses plain fetch and a default filename", async () => {
    fetchMock.mockResolvedValueOnce(textResponse(200));
    const created = [];
    const orig = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = orig(tag);
      created.push(el);
      return el;
    });
    await downloadBlob("/public/x.ics", undefined, { auth: false, headers: { A: "1" } });
    expect(fetchMock.mock.calls[0][1]).toEqual({ method: "GET", headers: { A: "1" } });
    expect(created[0].download).toBe("download");
    expect(authorizedFetch).not.toHaveBeenCalled();
    document.createElement.mockRestore();
  });

  it("a failed download throws the server message", async () => {
    authorizedFetch.mockResolvedValueOnce(jsonResponse({ detail: "Forbidden" }, { status: 403 }));
    await expect(downloadBlob("/admin/x.csv", "x.csv")).rejects.toThrow("Forbidden");
  });

  it("a failed public download reads no JSON from a header-less response", async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 404, headers: new Headers() });
    await expect(downloadBlob("/public/x.ics", "x.ics", { auth: false })).rejects.toThrow(
      "GET /public/x.ics failed (404)",
    );
  });

  it("a failed download without a body uses the fallback", async () => {
    authorizedFetch.mockResolvedValueOnce(textResponse(500));
    await expect(downloadBlob("/admin/x.csv", "x.csv")).rejects.toThrow("GET /admin/x.csv failed (500)");
  });
});
