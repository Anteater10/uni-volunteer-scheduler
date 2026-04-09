// Phase 3: Roster API helpers
// Re-exports convenience functions that use the main api module's request()
import api from "../lib/api";

export async function fetchRoster(eventId) {
  // api module doesn't expose raw request, so add to nested shape
  // We'll use a direct fetch approach matching the api module pattern
  return _authedRequest("GET", `/events/${eventId}/roster`);
}

export async function checkInSignup(signupId) {
  return _authedRequest("POST", `/signups/${signupId}/check-in`);
}

export async function resolveEvent(eventId, { attended, no_show }) {
  return _authedRequest("POST", `/events/${eventId}/resolve`, { attended, no_show });
}

// Internal: thin wrapper matching the api.js request pattern
import authStorage from "../lib/authStorage";

const RAW_BASE = (
  (typeof import.meta !== "undefined" ? import.meta.env?.VITE_API_URL : null) ||
  "http://localhost:8000"
).replace(/\/+$/, "");
const API_BASE = RAW_BASE.endsWith("/api/v1") ? RAW_BASE : `${RAW_BASE}/api/v1`;

async function _authedRequest(method, path, body) {
  const token = authStorage.getToken();
  const url = `${API_BASE}${path}`;
  const init = {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    const json = await res.json().catch(() => null);
    const err = new Error(
      typeof json?.detail === "string"
        ? json.detail
        : json?.detail?.message || `${method} ${path} failed (${res.status})`,
    );
    err.status = res.status;
    err.response = { status: res.status, data: json };
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}
