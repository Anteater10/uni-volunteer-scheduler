// REST client for the Phase 30 copilot router.
//
// Streaming for POST /sessions/:id/messages is handled separately in
// useCopilotStream.js because fetch + ReadableStream is more flexible
// than the lib/api wrapper, which assumes JSON responses.
import { authorizedFetch } from "../lib/authToken";
import { API_BASE } from "../lib/apiBase";

export const COPILOT_BASE = `${API_BASE}/copilot`;

async function jsonOrThrow(res) {
  if (!res.ok) {
    let body = null;
    try {
      body = await res.json();
    } catch {
      // ignore
    }
    const err = new Error(body?.detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

export async function createSession() {
  const res = await authorizedFetch(`${COPILOT_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return jsonOrThrow(res);
}

export async function listSessions() {
  const res = await authorizedFetch(`${COPILOT_BASE}/sessions`);
  return jsonOrThrow(res);
}

export async function getSession(sessionId) {
  const res = await authorizedFetch(`${COPILOT_BASE}/sessions/${sessionId}`);
  return jsonOrThrow(res);
}

export async function confirmCall(callId, approved) {
  const res = await authorizedFetch(`${COPILOT_BASE}/confirm/${callId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  return jsonOrThrow(res);
}

export async function getProfile() {
  const res = await authorizedFetch(`${COPILOT_BASE}/profile`);
  return jsonOrThrow(res);
}

export async function deleteProfile() {
  const res = await authorizedFetch(`${COPILOT_BASE}/profile`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return true;
}

export const copilotApi = {
  createSession,
  listSessions,
  getSession,
  confirmCall,
  getProfile,
  deleteProfile,
};
export default copilotApi;
