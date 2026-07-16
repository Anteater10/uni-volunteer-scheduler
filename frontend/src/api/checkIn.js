// Phase 3: Self check-in API helpers
import authStorage from "../lib/authStorage";
import { API_BASE } from "../lib/apiBase";

async function _request(method, path, body) {
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

export async function getSignupEvent(signupId) {
  return _request("GET", `/signups/${signupId}`);
}

export async function selfCheckIn(eventId, signupId, venueCode) {
  return _request("POST", `/events/${eventId}/self-check-in`, {
    signup_id: signupId,
    venue_code: venueCode,
  });
}
