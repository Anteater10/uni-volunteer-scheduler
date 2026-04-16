// src/lib/api.js
import authStorage from "./authStorage";

// .env example:
// VITE_API_URL=http://localhost:8000
// (do NOT include /api/v1; we'll append it safely)
const RAW_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const API_BASE = RAW_BASE.endsWith("/api/v1") ? RAW_BASE : `${RAW_BASE}/api/v1`;

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

// --------------------
// USERS
// --------------------
async function me() {
  return request("/users/me", { method: "GET" });
}

// --------------------
// EVENTS
// --------------------
async function listEvents(params) {
  return request("/events", { method: "GET", auth: false, params });
}

async function getEvent(eventId) {
  return request(`/events/${eventId}`, { method: "GET", auth: false });
}

async function createEvent(payload) {
  return request("/events", { method: "POST", body: payload });
}

async function updateEvent(eventId, payload) {
  return request(`/events/${eventId}`, { method: "PUT", body: payload });
}

async function deleteEvent(eventId) {
  return request(`/events/${eventId}`, { method: "DELETE" });
}

async function cloneEvent(eventId) {
  return request(`/events/${eventId}/clone`, { method: "POST" });
}

// --------------------
// SLOTS
// --------------------
async function listSlots(params) {
  // commonly: { event_id }
  return request("/slots/", { method: "GET", auth: false, params });
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
// SIGNUPS
// --------------------
// TODO(phase0): no backend endpoint at /events/{id}/signups — tracked in API-AUDIT.md.
// Admin/organizer callers should use api.admin.eventRoster(eventId) instead.
// A public endpoint will be added in Plan 05 or 06.
async function listEventSignups(eventId) {
  return request(`/events/${eventId}/signups`, { method: "GET" });
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
// PORTALS
// --------------------
// Public portal view by slug: GET /api/v1/portals/{slug}
async function getPortalBySlug(slug) {
  return request(`/portals/${encodeURIComponent(slug)}`, { method: "GET", auth: false });
}

// Admin/organizer list portals: GET /api/v1/portals
async function listPortals(params) {
  return request("/portals", { method: "GET", params });
}

async function createPortal(payload) {
  return request("/portals", { method: "POST", body: payload });
}

// Attach/detach endpoints vary across backends.
// This is a sane default; adjust if your backend differs.
async function attachEventToPortal(portalId, eventId) {
  return request(`/portals/${portalId}/events/${eventId}`, { method: "POST" });
}
async function detachEventFromPortal(portalId, eventId) {
  return request(`/portals/${portalId}/events/${eventId}`, { method: "DELETE" });
}

// --------------------
// ADMIN
// --------------------
async function adminSummary() {
  return request("/admin/summary", { method: "GET" });
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
async function publicConfirmSignup(token) {
  return request("/public/signups/confirm", { method: "POST", auth: false, params: { token } });
}
async function publicGetManageSignups(token) {
  return request("/public/signups/manage", { method: "GET", auth: false, params: { token } });
}
async function publicCancelSignup(signupId, token) {
  return request(`/public/signups/${signupId}`, { method: "DELETE", auth: false, params: { token } });
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

  // users
  me,

  // events
  listEvents,
  getEvent,
  createEvent,
  updateEvent,
  deleteEvent,
  cloneEvent,

  // slots
  listSlots,
  createSlot,
  updateSlot,
  deleteSlot,
  generateSlots,

  // signups
  listEventSignups,

  // magic link
  resendMagicLink,

  // questions
  listEventQuestions,
  createEventQuestion,
  updateEventQuestion,
  deleteEventQuestion,

  // notifications
  listMyNotifications,

  // portals
  listPortals,
  getPortalBySlug,
  createPortal,
  attachEventToPortal,
  detachEventFromPortal,

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
    clone: (id) => cloneEvent(id),
  },
  notifications: {
    my: (params) => listMyNotifications(params),
  },
  portals: {
    getBySlug: (slug) => getPortalBySlug(slug),
  },
  // public (unauthenticated) — phase 10
  public: {
    getCurrentWeek: () => publicGetCurrentWeek(),
    listEvents: (params) => publicListEvents(params),
    getEvent: (id) => publicGetEvent(id),
    createSignup: (body) => publicCreateSignup(body),
    orientationStatus: (email) => publicOrientationStatus(email),
    confirmSignup: (token) => publicConfirmSignup(token),
    getManageSignups: (token) => publicGetManageSignups(token),
    cancelSignup: (signupId, token) => publicCancelSignup(signupId, token),
  },

  // --- Module Templates (Phase 5) ---
  getModuleTemplates: () => request("/admin/module-templates"),
  createModuleTemplate: (data) => request("/admin/module-templates", { method: "POST", body: data }),
  updateModuleTemplate: (slug, data) => request(`/admin/module-templates/${slug}`, { method: "PATCH", body: data }),
  deleteModuleTemplate: (slug) => request(`/admin/module-templates/${slug}`, { method: "DELETE" }),

  // --- CSV Imports (Phase 5) ---
  uploadCsvImport: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    const token = authStorage.getToken();
    return fetch(`${API_BASE}/admin/imports`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const json = await safeReadJson(res);
        throw new Error(extractErrorMessage(json, `Upload failed (${res.status})`));
      }
      return res.json();
    });
  },
  getCsvImport: (importId) => request(`/admin/imports/${importId}`),
  updateImportRow: (importId, rowIndex, data) =>
    request(`/admin/imports/${importId}/rows/${rowIndex}`, { method: "PATCH", body: data }),
  commitCsvImport: (importId) => request(`/admin/imports/${importId}/commit`, { method: "POST" }),

  admin: {
    summary: () => adminSummary(),
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
    },
    templates: {
      list: (params) => request("/admin/module-templates", { params }),
      create: (payload) => request("/admin/module-templates", { method: "POST", body: payload }),
      update: (slug, payload) => request(`/admin/module-templates/${slug}`, { method: "PATCH", body: payload }),
      delete: (slug) => request(`/admin/module-templates/${slug}`, { method: "DELETE" }),
      bulkDelete: (slugs) => Promise.all(slugs.map((s) => request(`/admin/module-templates/${s}`, { method: "DELETE" }))),
      restore: (slug) => request(`/admin/module-templates/${slug}/restore`, { method: "POST" }),
    },
    imports: {
      list: () => request("/admin/imports", { method: "GET" }),
      get: (importId) => request(`/admin/imports/${importId}`),
      upload: (file) => {
        const formData = new FormData();
        formData.append("file", file);
        const token = authStorage.getToken();
        return fetch(`${API_BASE}/admin/imports`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        }).then(async (res) => {
          if (!res.ok) {
            const json = await safeReadJson(res);
            throw new Error(extractErrorMessage(json, `Upload failed (${res.status})`));
          }
          return res.json();
        });
      },
      commit: (importId) => request(`/admin/imports/${importId}/commit`, { method: "POST" }),
      retry: (importId) => request(`/admin/imports/${importId}/retry`, { method: "POST" }),
      updateRow: (importId, rowIndex, data) =>
        request(`/admin/imports/${importId}/rows/${rowIndex}`, { method: "PATCH", body: data }),
    },
  },
};

export default api;
