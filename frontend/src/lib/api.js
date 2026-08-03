// src/lib/api.js
import authStorage from "./authStorage";
import { API_BASE } from "./apiBase";

// -------------------------
// Single-flight refresh-on-401
// -------------------------

/** Module-scoped promise so concurrent 401s queue behind one refresh call. */
let refreshPromise = null;

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Concurrent callers share the same in-flight promise (thundering-herd guard).
 * On success: updates authStorage with new tokens and returns the new access token.
 * On failure: clears all auth state and throws.
 */
async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refreshToken = authStorage.getRefreshToken();
    if (!refreshToken) throw new Error("NO_REFRESH_TOKEN");
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) {
      authStorage.clearAll();
      throw new Error("REFRESH_FAILED");
    }
    const data = await res.json();
    authStorage.setToken(data.access_token);
    authStorage.setRefreshToken(data.refresh_token);
    return data.access_token;
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

function buildQuery(params = {}) {
  const qp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    qp.set(k, String(v));
  });
  const s = qp.toString();
  return s ? `?${s}` : "";
}

async function safeReadJson(res) {
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function extractErrorMessage(json, fallback) {
  if (!json) return fallback;

  if (typeof json.detail === "string") return json.detail;

  if (Array.isArray(json.detail) && json.detail.length > 0) {
    const first = json.detail[0];
    if (typeof first === "string") return first;
    if (first?.msg) return first.msg;
  }

  if (typeof json.message === "string") return json.message;

  return fallback;
}

// Paths that must never trigger the refresh-on-401 retry loop.
const NO_RETRY_PATHS = ["/auth/refresh", "/auth/token"];

async function request(path, { method = "GET", params, body, auth = true, headers } = {}) {
  const token = auth ? authStorage.getToken() : "";

  const url = `${API_BASE}${path}${buildQuery(params)}`;
  const init = {
    method,
    headers: {
      ...(headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };

  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let res = await fetch(url, init);

  // Refresh-on-401: only retry when:
  //   1. The response is 401
  //   2. The original request had an Authorization header (auth=true with a token)
  //   3. The path is not an auth endpoint itself (prevents infinite loop)
  if (
    res.status === 401 &&
    token &&
    !NO_RETRY_PATHS.some((p) => path.startsWith(p))
  ) {
    try {
      const newToken = await refreshAccessToken();
      // Retry the original request with the new access token
      const retryInit = {
        ...init,
        headers: {
          ...init.headers,
          Authorization: `Bearer ${newToken}`,
        },
      };
      res = await fetch(url, retryInit);
    } catch {
      // Refresh failed — clear auth and fall through to throw below
      authStorage.clearAll();
      throw new Error("Session expired. Please log in again.");
    }
  }

  if (res.status === 204) return null;

  const json = await safeReadJson(res);

  if (!res.ok) {
    const fallback = `${method} ${path} failed (${res.status})`;
    const err = new Error(extractErrorMessage(json, fallback));
    err.status = res.status;
    err.response = { status: res.status, data: json };
    // Structured backend error codes drive UI branches (NO_SIGNUP_FOR_EMAIL,
    // WRONG_VENUE_CODE, ORIENTATION_REQUIRED, ...). The AUDIT-03 global
    // handler normalizes HTTPExceptions to {error, code, detail}, so the
    // top-level code is the real shape; the nested form is kept as a
    // defensive fallback for any non-normalized path.
    // NOTE: AUDIT-03 always sets code (default "http_<status>"), so err.code
    // is populated on virtually every API error — branch on exact values,
    // never on err.code truthiness.
    if (json?.code) err.code = json.code;
    else if (json?.detail?.code) err.code = json.detail.code;
    throw err;
  }

  return json;
}

// Download helper (CSV, ICS, etc.)
export async function downloadBlob(path, filename, { auth = true, params, headers } = {}) {
  const token = auth ? authStorage.getToken() : "";
  const url = `${API_BASE}${path}${buildQuery(params)}`;

  const res = await fetch(url, {
    method: "GET",
    headers: {
      ...(headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    const json = await safeReadJson(res);
    const fallback = `GET ${path} failed (${res.status})`;
    throw new Error(extractErrorMessage(json, fallback));
  }

  const blob = await res.blob();
  const a = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  a.href = objectUrl;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

// --------------------
// AUTH (FastAPI OAuth2PasswordRequestForm)
// --------------------
// Backend: POST /api/v1/auth/token with form fields: username, password
async function login(email, password) {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);

  const url = `${API_BASE}/auth/token`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });

  const json = await safeReadJson(res);

  if (!res.ok) {
    const fallback = `POST /auth/token failed (${res.status})`;
    throw new Error(extractErrorMessage(json, fallback));
  }

  // Store both tokens so refresh-on-401 works for the full session lifetime
  if (json?.access_token) authStorage.setToken(json.access_token);
  if (json?.refresh_token) authStorage.setRefreshToken(json.refresh_token);

  return json;
}

function logout() {
  authStorage.clearAll();
}

async function setPasswordFromInvite(token, password) {
  const json = await request("/auth/set-password", {
    method: "POST",
    auth: false,
    body: { token, password },
  });
  if (json?.access_token) authStorage.setToken(json.access_token);
  if (json?.refresh_token) authStorage.setRefreshToken(json.refresh_token);
  return json;
}

// PR #51 — self-service password management.
async function changePassword(currentPassword, newPassword) {
  return request("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

// Always resolves with 202 whether or not the address has an account.
async function forgotPassword(email) {
  return request("/auth/forgot-password", {
    method: "POST",
    auth: false,
    body: { email },
  });
}

// --------------------
// USERS
// --------------------
async function me() {
  return request("/users/me", { method: "GET" });
}

// Self-service profile edit. The backend only honours name, university_id and
// notify_email here — role and email are admin-only, by design.
async function updateMe(body) {
  return request("/users/me", { method: "PATCH", body });
}

// --------------------
// EVENTS
// --------------------
async function listEvents(params) {
  // Staff-only endpoint since the release hardening pass — anonymous
  // callers use api.public.listEvents (/public/events) instead.
  // Trailing slash matters: the router declares "/", so "/events" costs an
  // extra 307 round-trip on every call.
  return request("/events/", { method: "GET", auth: true, params });
}

async function getEvent(eventId) {
  return request(`/events/${eventId}`, { method: "GET", auth: true });
}

async function createEvent(payload) {
  return request("/events/", { method: "POST", body: payload });
}

async function updateEvent(eventId, payload) {
  return request(`/events/${eventId}`, { method: "PUT", body: payload });
}

async function deleteEvent(eventId) {
  return request(`/events/${eventId}`, { method: "DELETE" });
}

// --------------------
// SLOTS
// --------------------
async function listSlots(params) {
  // commonly: { event_id }. Sends the auth token when one is stored (staff
  // callers like BroadcastModal) so private events still resolve; anonymous
  // callers (EventCheckInPage) simply have no token to send, and the
  // backend restricts them to public events only.
  return request("/slots/", { method: "GET", params });
}

// IMPORTANT: your backend likely uses POST /slots?event_id=...
async function createSlot(eventId, payload) {
  return request("/slots/", { method: "POST", params: { event_id: eventId }, body: payload });
}

async function updateSlot(slotId, payload) {
  return request(`/slots/${slotId}`, { method: "PATCH", body: payload });
}

async function deleteSlot(slotId) {
  return request(`/slots/${slotId}`, { method: "DELETE" });
}

// IMPORTANT: your backend likely uses POST /events/{eventId}/generate_slots
async function generateSlots(eventId, payload) {
  return request(`/events/${eventId}/generate_slots`, { method: "POST", body: payload });
}

// --------------------
// QUESTIONS
// --------------------
async function listEventQuestions(eventId) {
  return request(`/events/${eventId}/questions`, { method: "GET" });
}

async function createEventQuestion(eventId, payload) {
  return request(`/events/${eventId}/questions`, { method: "POST", body: payload });
}

async function updateEventQuestion(questionId, payload) {
  return request(`/events/questions/${questionId}`, { method: "PUT", body: payload });
}

async function deleteEventQuestion(questionId) {
  return request(`/events/questions/${questionId}`, { method: "DELETE" });
}

// --------------------
// NOTIFICATIONS
// --------------------
async function listMyNotifications(params) {
  return request("/notifications/my", { method: "GET", params });
}

// --------------------
// ADMIN
// --------------------
async function adminSummary(params) {
  // fix/ux-quarter-batch: pass { quarter_id } to re-scope the *_quarter
  // aggregates to an explicitly selected quarter.
  return request("/admin/summary", { method: "GET", params });
}

async function adminListUsers(params) {
  return request("/users", { method: "GET", params });
}
async function adminCreateUser(payload) {
  return request("/users", { method: "POST", body: payload });
}
async function adminUpdateUser(userId, payload) {
  return request(`/users/${userId}`, { method: "PATCH", body: payload });
}
async function adminDeleteUser(userId) {
  return request(`/admin/users/${userId}`, { method: "DELETE" });
}

async function adminAuditLogs(params) {
  return request("/admin/audit-logs", { method: "GET", params });
}

async function adminCancelSignup(signupId) {
  return request(`/admin/signups/${signupId}/cancel`, { method: "POST" });
}

async function adminPromoteSignup(signupId) {
  return request(`/admin/signups/${signupId}/promote`, { method: "POST" });
}

async function adminMoveSignup(signupId, targetSlotId) {
  return request(`/admin/signups/${signupId}/move`, {
    method: "POST",
    body: { target_slot_id: targetSlotId },
  });
}

async function adminResendSignup(signupId) {
  return request(`/admin/signups/${signupId}/resend`, { method: "POST" });
}

// --------------------
// PUBLIC (unauthenticated) — phase 10
// IMPORTANT: do NOT log or persist volunteer email/phone anywhere in these helpers.
// --------------------
async function publicGetCurrentWeek() {
  return request("/public/current-week", { method: "GET", auth: false });
}
async function publicGetQuarters() {
  // Issue #24: ordered admin-entered quarter rows — powers week navigation.
  return request("/public/quarters", { method: "GET", auth: false });
}
async function publicListEvents(params) {
  return request("/public/events", { method: "GET", auth: false, params });
}
async function publicGetEvent(eventId) {
  return request(`/public/events/${eventId}`, { method: "GET", auth: false });
}
async function publicCreateSignup(body) {
  return request("/public/signups", { method: "POST", auth: false, body });
}
async function publicOrientationStatus(email) {
  return request("/public/orientation-status", { method: "GET", auth: false, params: { email } });
}
// Phase 21: cross-week/cross-module credit check. Pass eventId so the backend
// can resolve the module family from the event. Response shape adds
// has_credit + source + family_key.
async function publicOrientationCheck(email, eventId) {
  return request("/public/orientation-check", {
    method: "GET",
    auth: false,
    params: { email, event_id: eventId },
  });
}
async function publicConfirmSignup(token) {
  return request("/public/signups/confirm", { method: "POST", auth: false, params: { token } });
}
async function publicGetManageSignups(token) {
  return request("/public/signups/manage", { method: "GET", auth: false, params: { token } });
}

// Phase 24 — volunteer reminder preferences (token-gated)
async function publicGetPreferences(manageToken) {
  return request("/public/preferences", {
    method: "GET",
    auth: false,
    params: { manage_token: manageToken },
  });
}
async function publicUpdatePreferences(manageToken, patch) {
  return request("/public/preferences", {
    method: "PUT",
    auth: false,
    params: { manage_token: manageToken },
    body: patch,
  });
}

// Phase 24 — admin reminders page
async function adminListUpcomingReminders(days = 7) {
  return request("/admin/reminders/upcoming", { method: "GET", params: { days } });
}
async function adminSendReminderNow(signupId, kind) {
  return request("/admin/reminders/send-now", {
    method: "POST",
    body: { signup_id: signupId, kind },
  });
}

// Phase 26 — broadcast messages (organizer + admin).
// Returns the recipient-count preview for the modal. Optional params
// may carry { slot_id } to preview a single slot's roster.
async function getBroadcastRecipientCount(eventId, params) {
  return request(`/events/${eventId}/broadcast-recipients`, {
    method: "GET",
    params,
  });
}
// Sends a broadcast. On 429 the Error carries .status and .retryAfter.
// slot_id (optional) targets one slot's roster; omitted = all slots.
async function sendBroadcast(eventId, { subject, body_markdown, slot_id }) {
  const url = `${API_BASE}/events/${eventId}/broadcast`;
  const token = authStorage.getToken();
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      subject,
      body_markdown,
      ...(slot_id ? { slot_id } : {}),
    }),
  });
  const json = await safeReadJson(res);
  if (!res.ok) {
    const err = new Error(
      extractErrorMessage(json, `Broadcast failed (${res.status})`),
    );
    err.status = res.status;
    if (res.status === 429) {
      err.retryAfter = Number(res.headers.get("Retry-After") || 0) || null;
    }
    throw err;
  }
  return json;
}
async function listBroadcasts(eventId, days = 30) {
  return request(`/events/${eventId}/broadcasts`, {
    method: "GET",
    params: { days },
  });
}

// --------------------
// MAGIC LINK
// --------------------
async function resendMagicLink({ email, eventId }) {
  const url = `${API_BASE}/auth/magic/resend`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, event_id: eventId }),
  });
  const json = await safeReadJson(res);
  if (!res.ok) {
    const err = new Error(extractErrorMessage(json, `POST /auth/magic/resend failed (${res.status})`));
    err.status = res.status;
    throw err;
  }
  return json;
}

// Bundle API in BOTH flat + nested shapes so all your pages work
export const api = {
  // auth
  login,
  logout,
  setPasswordFromInvite,
  changePassword,
  forgotPassword,

  // users
  me,
  updateMe,

  // events
  listEvents,
  getEvent,
  createEvent,
  updateEvent,
  deleteEvent,

  // slots
  listSlots,
  createSlot,
  updateSlot,
  deleteSlot,
  generateSlots,

  // magic link
  resendMagicLink,

  // questions
  listEventQuestions,
  createEventQuestion,
  updateEventQuestion,
  deleteEventQuestion,

  // notifications
  listMyNotifications,

  // admin
  adminSummary,
  adminListUsers,
  adminCreateUser,
  adminUpdateUser,
  adminDeleteUser,
  adminAuditLogs,

  // Nested aliases (so code like api.signups.my works)
  events: {
    list: (params) => listEvents(params),
    get: (id) => getEvent(id),
    create: (payload) => createEvent(payload),
    update: (id, payload) => updateEvent(id, payload),
    delete: (id) => deleteEvent(id),
  },
  slots: {
    list: (params) => listSlots(params),
    create: (eventId, payload) => createSlot(eventId, payload),
    update: (slotId, payload) => updateSlot(slotId, payload),
    delete: (slotId) => deleteSlot(slotId),
    generate: (eventId, payload) => generateSlots(eventId, payload),
  },
  notifications: {
    my: (params) => listMyNotifications(params),
  },
  // public (unauthenticated) — phase 10
  public: {
    getCurrentWeek: () => publicGetCurrentWeek(),
    getQuarters: () => publicGetQuarters(),
    listEvents: (params) => publicListEvents(params),
    getEvent: (id) => publicGetEvent(id),
    createSignup: (body) => publicCreateSignup(body),
    orientationStatus: (email) => publicOrientationStatus(email),
    // Phase 21
    orientationCheck: (email, eventId) => publicOrientationCheck(email, eventId),
    // Phase 22
    getFormSchema: (eventId) =>
      request(`/public/events/${eventId}/form-schema`, {
        method: "GET",
        auth: false,
      }),
    confirmSignup: (token) => publicConfirmSignup(token),
    getManageSignups: (token) => publicGetManageSignups(token),
    // Phase 24 — reminder preferences
    getPreferences: (manageToken) => publicGetPreferences(manageToken),
    updatePreferences: (manageToken, patch) =>
      publicUpdatePreferences(manageToken, patch),
    // Event-QR check-in (post-integration) — organizer shows a QR that points
    // at /event-check-in/:eventId; volunteer enters email and hits this.
    checkInByEmail: (eventId, email, venueCode) =>
      request(`/events/${eventId}/check-in-by-email`, {
        method: "POST",
        auth: false,
        body: { email, venue_code: venueCode },
      }),
    // Issue #31 UX rework — pick-your-shift check-in: lookup lists the
    // volunteer's shifts with window verdicts; selected checks in the tapped
    // shift(s) only. Both are venue-code gated; the QR URL carries the code.
    checkInLookup: (eventId, email, venueCode) =>
      request(`/events/${eventId}/check-in-lookup`, {
        method: "POST",
        auth: false,
        body: { email, venue_code: venueCode },
      }),
    checkInSelected: (eventId, email, signupIds, venueCode) =>
      request(`/events/${eventId}/check-in-selected`, {
        method: "POST",
        auth: false,
        body: { email, venue_code: venueCode, signup_ids: signupIds },
      }),
  },

  // Phase 21 — organizer-scoped helpers
  organizer: {
    grantOrientation: (eventId, signupId) =>
      request(
        `/organizer/events/${eventId}/signups/${signupId}/grant-orientation`,
        { method: "POST" },
      ),
    // Phase 22 — quick-add form field from roster page
    appendEventField: (eventId, field) =>
      request(`/organizer/events/${eventId}/form-fields`, {
        method: "POST",
        body: field,
      }),
    // Phase 25 — organizer manual waitlist promote (WAIT-03)
    // `allowOverfill` takes the slot past capacity — the organizer confirms
    // it first. Without it the server refuses any promote into a full slot,
    // which is nearly every waitlisted volunteer.
    promoteSignup: (eventId, signupId, { allowOverfill = false } = {}) =>
      request(
        `/organizer/events/${eventId}/signups/${signupId}/promote` +
          (allowOverfill ? "?allow_overfill=true" : ""),
        { method: "POST" },
      ),
    // Phase 26 — broadcast messages (organizer reuse of same endpoints)
    broadcastRecipientCount: (eventId, params) =>
      getBroadcastRecipientCount(eventId, params),
    sendBroadcast: (eventId, payload) => sendBroadcast(eventId, payload),
    listBroadcasts: (eventId, days = 30) => listBroadcasts(eventId, days),
  },

  admin: {
    summary: (params) => adminSummary(params),
    // Phase 29 (HIDE-01) — site-wide settings singleton
    siteSettings: {
      get: () => request("/admin/site-settings", { method: "GET" }),
      update: (patch) =>
        request("/admin/site-settings", { method: "PATCH", body: patch }),
    },
    users: {
      // Phase 16 Plan 03 (ADMIN-18..21): invite / deactivate / reactivate wire
      // up to Plan 02's backend endpoints. Legacy create/update/delete kept for
      // compatibility but the UI flow prefers invite + soft-delete.
      list: (params = {}) => request("/users/", { method: "GET", params }),
      create: (payload) => adminCreateUser(payload),
      update: (id, payload) => adminUpdateUser(id, payload),
      delete: (id) => adminDeleteUser(id),
      invite: (body) => request("/users/invite", { method: "POST", body }),
      deactivate: (id) =>
        request(`/users/${id}/deactivate`, { method: "POST", body: {} }),
      reactivate: (id) =>
        request(`/users/${id}/reactivate`, { method: "POST", body: {} }),
      ccpaExport: (userId, reason) =>
        request(`/admin/users/${userId}/ccpa-export`, { method: "GET", params: { reason } }),
      ccpaDelete: (userId, reason) =>
        request(`/admin/users/${userId}/ccpa-delete`, { method: "POST", body: { reason } }),
    },
    auditLogs: (params) => adminAuditLogs(params),
    eventAnalytics: (eventId) => request(`/admin/events/${eventId}/analytics`, { method: "GET" }),
    eventRoster: (eventId, privacy) =>
      request(`/admin/events/${eventId}/roster`, { method: "GET", params: { privacy } }),
    notify: (eventId, payload) =>
      request(`/admin/events/${eventId}/notify`, { method: "POST", body: payload }),
    signups: {
      cancel: (id) => adminCancelSignup(id),
      promote: (id) => adminPromoteSignup(id),
      move: (id, targetSlotId) => adminMoveSignup(id, targetSlotId),
      resend: (id) => adminResendSignup(id),
    },
    analytics: {
      // JSON read helpers — consumed by ExportsSection panels in Plan 06
      volunteerHours: (params = {}) =>
        request("/admin/analytics/volunteer-hours", { method: "GET", params }),
      attendanceRates: (params = {}) =>
        request("/admin/analytics/attendance-rates", { method: "GET", params }),
      noShowRates: (params = {}) =>
        request("/admin/analytics/no-show-rates", { method: "GET", params }),
      // CSV download helpers — consumed by ExportsSection Download CSV buttons in Plan 06
      volunteerHoursCsv: (params = {}) =>
        downloadBlob("/admin/analytics/volunteer-hours.csv", "volunteer-hours.csv", { params }),
      attendanceRatesCsv: (params = {}) =>
        downloadBlob("/admin/analytics/attendance-rates.csv", "attendance-rates.csv", { params }),
      noShowRatesCsv: (params = {}) =>
        downloadBlob("/admin/analytics/no-show-rates.csv", "no-show-rates.csv", { params }),

      // Phase 18 Plan 03 — extra SciTrek-focused reports
      eventFillRates: (params = {}) =>
        request("/admin/analytics/event-fill-rates", { method: "GET", params }),
      eventFillRatesCsv: (params = {}) =>
        downloadBlob("/admin/analytics/event-fill-rates.csv", "event-fill-rates.csv", { params }),
      hoursBySchool: (params = {}) =>
        request("/admin/analytics/hours-by-school", { method: "GET", params }),
      hoursBySchoolCsv: (params = {}) =>
        downloadBlob("/admin/analytics/hours-by-school.csv", "hours-by-school.csv", { params }),
      uniqueVolunteers: (params = {}) =>
        request("/admin/analytics/unique-volunteers", { method: "GET", params }),
      uniqueVolunteersCsv: (params = {}) =>
        downloadBlob("/admin/analytics/unique-volunteers.csv", "unique-volunteers.csv", { params }),
      cancellationRates: (params = {}) =>
        request("/admin/analytics/cancellation-rates", { method: "GET", params }),
      cancellationRatesCsv: (params = {}) =>
        downloadBlob("/admin/analytics/cancellation-rates.csv", "cancellation-rates.csv", { params }),
      modulePopularity: (params = {}) =>
        request("/admin/analytics/module-popularity", { method: "GET", params }),
      modulePopularityCsv: (params = {}) =>
        downloadBlob("/admin/analytics/module-popularity.csv", "module-popularity.csv", { params }),
    },
    // Issue #24 — admin-entered quarters. create/update responses are
    // { quarter, relink_summary } so callers can surface recategorization.
    quarters: {
      list: () => request("/admin/quarters"),
      create: (payload) => request("/admin/quarters", { method: "POST", body: payload }),
      update: (id, payload) => request(`/admin/quarters/${id}`, { method: "PATCH", body: payload }),
      remove: (id) => request(`/admin/quarters/${id}`, { method: "DELETE" }),
      // Issue #33 — explicit archiving of past quarters.
      archive: (id) => request(`/admin/quarters/${id}/archive`, { method: "POST" }),
      restore: (id) => request(`/admin/quarters/${id}/restore`, { method: "POST" }),
      // Issue #38 — per-event attendance breakdown for a past quarter.
      retrospective: (id) => request(`/admin/quarters/${id}/retrospective`),
    },
    modules: {
      list: (params) => request("/admin/modules", { params }),
      create: (payload) => request("/admin/modules", { method: "POST", body: payload }),
      update: (slug, payload) => request(`/admin/modules/${slug}`, { method: "PATCH", body: payload }),
      delete: (slug) => request(`/admin/modules/${slug}`, { method: "DELETE" }),
      bulkDelete: (slugs) => Promise.all(slugs.map((s) => request(`/admin/modules/${s}`, { method: "DELETE" }))),
      restore: (slug) => request(`/admin/modules/${slug}/restore`, { method: "POST" }),
      clone: (slug, { new_slug, new_name }) =>
        request(`/admin/modules/${slug}/clone`, {
          method: "POST",
          body: { new_slug, new_name },
        }),
      // Phase 22 — default form schema on the module
      setDefaultFormSchema: (slug, schema) =>
        request(`/admin/modules/${slug}/default-form-schema`, {
          method: "PUT",
          body: { schema },
        }),
    },
    // Phase 22 — per-event form schema override
    setEventFormSchema: (eventId, schema) =>
      request(`/admin/events/${eventId}/form-schema`, {
        method: "PUT",
        body: { schema },
      }),
    // Phase 25 — admin reorder waitlist (WAIT-05)
    reorderWaitlist: (eventId, slotId, orderedIds) =>
      request(
        `/admin/events/${eventId}/slots/${slotId}/waitlist-order`,
        {
          method: "PATCH",
          body: { ordered_signup_ids: orderedIds },
        },
      ),
    // Phase 24 — scheduled reminder emails
    reminders: {
      listUpcoming: (days = 7) => adminListUpcomingReminders(days),
      sendNow: (signupId, kind) => adminSendReminderNow(signupId, kind),
    },
    // Phase 26 — broadcast messages
    broadcastRecipientCount: (eventId, params) =>
      getBroadcastRecipientCount(eventId, params),
    sendBroadcast: (eventId, payload) => sendBroadcast(eventId, payload),
    listBroadcasts: (eventId, days = 30) => listBroadcasts(eventId, days),
    // Phase 21 — orientation credit engine (issue #30: permanent per
    // (email, family); quarter_id is optional "earned in" metadata)
    orientationCredits: {
      list: (params = {}) =>
        request("/admin/orientation-credits", { method: "GET", params }),
      create: ({ volunteer_email, family_key, quarter_id, notes = null }) =>
        request("/admin/orientation-credits", {
          method: "POST",
          body: { volunteer_email, family_key, quarter_id, notes },
        }),
      revoke: (creditId) =>
        request(`/admin/orientation-credits/${creditId}`, { method: "DELETE" }),
    },
  },
};

export default api;
