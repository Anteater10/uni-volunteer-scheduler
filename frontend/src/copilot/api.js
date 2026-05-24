// REST client for the Phase 30 copilot router.
//
// Streaming for POST /sessions/:id/messages is handled separately in
// useCopilotStream.js because fetch + ReadableStream is more flexible
// than the lib/api wrapper, which assumes JSON responses.
import authStorage from "../lib/authStorage";

const RAW_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const API_BASE = RAW_BASE.endsWith("/api/v1") ? RAW_BASE : `${RAW_BASE}/api/v1`;

export const COPILOT_BASE = `${API_BASE}/copilot`;

function authHeaders() {
  const tok = authStorage.getToken();
  return tok ? { Authorization: `Bearer ${tok}` } : {};
}

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
  const res = await fetch(`${COPILOT_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  });
  return jsonOrThrow(res);
}

export async function listSessions() {
  const res = await fetch(`${COPILOT_BASE}/sessions`, {
    headers: authHeaders(),
  });
  return jsonOrThrow(res);
}

export async function getSession(sessionId) {
  const res = await fetch(`${COPILOT_BASE}/sessions/${sessionId}`, {
    headers: authHeaders(),
  });
  return jsonOrThrow(res);
}

export async function confirmCall(callId, approved) {
  const res = await fetch(`${COPILOT_BASE}/confirm/${callId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ approved }),
  });
  return jsonOrThrow(res);
}

export async function getProfile() {
  const res = await fetch(`${COPILOT_BASE}/profile`, {
    headers: authHeaders(),
  });
  return jsonOrThrow(res);
}

export async function deleteProfile() {
  const res = await fetch(`${COPILOT_BASE}/profile`, {
    method: "DELETE",
    headers: authHeaders(),
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
