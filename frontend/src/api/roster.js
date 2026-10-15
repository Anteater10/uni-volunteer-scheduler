// Phase 3: Roster API helpers

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

// Grant-on-slot-end (2026-07-24): per-slot "End slot". Ending an orientation
// slot auto-grants orientation credit to every volunteer marked attended.
// 2026-10-13: closing locks the slot's attendance until someone reopens it;
// 409 SLOT_CLOSED if it is already closed. "End event" also closes one slot
// at a time through here, so a session that hasn't started is never touched.
export async function resolveSlot(slotId, { attended, no_show }) {
  return _authedRequest("POST", `/slots/${slotId}/resolve`, { attended, no_show });
}

// 2026-10-13: undo one closed slot. attended goes back to checked in (keeping
// the check-in time), no show back to not checked in. Returns the fresh roster.
export async function reopenSlot(slotId) {
  return _authedRequest("POST", `/slots/${slotId}/reopen`);
}

// fix/ux-quarter-batch — undo "End event": every closed slot on the event
// reopens and the event's completed_at stamp clears.
export async function reopenEvent(eventId) {
  return _authedRequest("POST", `/events/${eventId}/reopen`);
}

// 2026-10-13: a tap or close that lands on a closed slot gets a 409 with code
// SLOT_CLOSED. The app's global HTTP error handler flattens the body to
// {error, code, detail: "<message>"}, so the code is top-level; the nested
// detail.code shape is accepted too in case a route ever bypasses it.
function hasCode(err, code) {
  const data = err?.response?.data;
  return data?.code === code || data?.detail?.code === code;
}

export function isSlotClosedError(err) {
  return hasCode(err, "SLOT_CLOSED");
}

// 2026-10-14: a slot can't be closed before it starts (409 SLOT_NOT_STARTED)
// — no-shows only exist for a session that has begun.
export function isSlotNotStartedError(err) {
  return hasCode(err, "SLOT_NOT_STARTED");
}

// Internal: thin wrapper matching the api.js request pattern
import { authorizedFetch } from "../lib/authToken";
import { API_BASE } from "../lib/apiBase";

async function _authedRequest(method, path, body) {
  const url = `${API_BASE}${path}`;
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await authorizedFetch(url, init);
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
