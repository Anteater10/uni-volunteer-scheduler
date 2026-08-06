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

// Issue #31 — mis-tap recovery: revert checked_in back to confirmed.
export async function undoCheckInSignup(signupId) {
  return _authedRequest("POST", `/signups/${signupId}/undo-check-in`);
}

// 2026-08-02 shifts: check-in is keyed on (commitment, session), not on the
// booking alone. A volunteer holding a Tue+Wed shift is checked in twice, once
// per day, and can be present Tuesday and absent Wednesday — so there is no
// single "check in this shift" call to make.
export async function checkInSession(shiftSignupId, slotId) {
  return _authedRequest(
    "POST",
    `/shift-signups/${shiftSignupId}/sessions/${slotId}/check-in`,
  );
}

export async function undoCheckInSession(shiftSignupId, slotId) {
  return _authedRequest(
    "POST",
    `/shift-signups/${shiftSignupId}/sessions/${slotId}/undo-check-in`,
  );
}

export async function resolveEvent(eventId, { attended, no_show }) {
  return _authedRequest("POST", `/events/${eventId}/resolve`, { attended, no_show });
}

// Grant-on-slot-end (2026-07-24): per-slot "End slot". Ending an orientation
// slot auto-grants orientation credit to every volunteer marked attended.
export async function resolveSlot(slotId, { attended, no_show }) {
  return _authedRequest("POST", `/slots/${slotId}/resolve`, { attended, no_show });
}

// fix/ux-quarter-batch — undo "End event": resolved signups return to the
// live roster and the event's completed_at stamp clears.
export async function reopenEvent(eventId) {
  return _authedRequest("POST", `/events/${eventId}/reopen`);
}

// Internal: thin wrapper matching the api.js request pattern
import authStorage from "../lib/authStorage";
import { API_BASE } from "../lib/apiBase";

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
