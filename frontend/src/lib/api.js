// src/lib/api.js
import authStorage from "./authStorage";

// .env example:
// VITE_API_URL=http://localhost:8000
// (do NOT include /api/v1; we'll append it safely)
const RAW_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const API_BASE = RAW_BASE.endsWith("/api/v1") ? RAW_BASE : `${RAW_BASE}/api/v1`;

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

  const res = await fetch(url, init);

  if (res.status === 204) return null;

  const json = await safeReadJson(res);

  if (!res.ok) {
    const fallback = `${method} ${path} failed (${res.status})`;
    throw new Error(extractErrorMessage(json, fallback));
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

  // expecting { access_token, token_type }
  if (json?.access_token) authStorage.setToken(json.access_token);

  return json;
}

// Backend: POST /api/v1/auth/register (public)
async function register(payload) {
  return request("/auth/register", { method: "POST", auth: false, body: payload });
}

function logout() {
  authStorage.clearToken();
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
  return request(`/events/${eventId}`, { method: "PATCH", body: payload });
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
  return request("/slots", { method: "GET", auth: false, params });
}

// IMPORTANT: your backend likely uses POST /slots?event_id=...
async function createSlot(eventId, payload) {
  return request("/slots", { method: "POST", params: { event_id: eventId }, body: payload });
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
async function createSignup(payload) {
  return request("/signups", { method: "POST", body: payload });
}

// Backend uses POST cancel (not DELETE) in your FastAPI design
async function cancelSignup(signupId) {
  return request(`/signups/${signupId}/cancel`, { method: "POST" });
}

async function listMySignups(params) {
  return request("/signups/my", { method: "GET", params });
}

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
  return request(`/event-questions/${questionId}`, { method: "PATCH", body: payload });
}

async function deleteEventQuestion(questionId) {
  return request(`/event-questions/${questionId}`, { method: "DELETE" });
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
  // your AuditLogsPage mentions /admin/audit_logs
  return request("/admin/audit_logs", { method: "GET", params });
}

// Bundle API in BOTH flat + nested shapes so all your pages work
export const api = {
  // auth
  login,
  register,
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
  createSignup,
  cancelSignup,
  listMySignups,
  listEventSignups,

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
  signups: {
    create: (payload) => createSignup(payload),
    cancel: (id) => cancelSignup(id),
    my: (params) => listMySignups(params),
  },
  notifications: {
    my: (params) => listMyNotifications(params),
  },
  portals: {
    getBySlug: (slug) => getPortalBySlug(slug),
  },
  admin: {
    summary: () => adminSummary(),
    users: {
      list: (params) => adminListUsers(params),
      create: (payload) => adminCreateUser(payload),
      update: (id, payload) => adminUpdateUser(id, payload),
      delete: (id) => adminDeleteUser(id),
    },
    auditLogs: (params) => adminAuditLogs(params),
    eventAnalytics: (eventId) => request(`/admin/events/${eventId}/analytics`, { method: "GET" }),
    eventRoster: (eventId, privacy) =>
      request(`/admin/events/${eventId}/roster`, { method: "GET", params: { privacy } }),
    notify: (eventId, payload) =>
      request(`/admin/events/${eventId}/notify`, { method: "POST", body: payload }),
  },
};

export default api;
