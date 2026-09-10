// src/lib/authStorage.js
// Phase L3: access token lives in memory only (never localStorage — an XSS
// anywhere in the app could otherwise read it). It does not survive a page
// reload; state/authContext.jsx re-derives it on boot via a silent
// /auth/refresh call against the HttpOnly refresh cookie (see lib/api.js's
// refreshAccessToken). The refresh token itself is never handled by JS at
// all — the backend manages it entirely through that cookie — so this
// module no longer has any refresh-token functions.

// Legacy keys from before Phase L3. Every member of staff who used the old
// build still has a real, server-valid refresh token sitting in
// localStorage, and it would stay there indefinitely — which is precisely
// the exposure this phase exists to close, left open for the people who
// already have it. Clearing on module load means the first load of the new
// build cleans the machine. Wrapped because localStorage throws outright in
// some privacy modes, and failing here would take the whole app down.
const LEGACY_KEYS = ["uvse_access_token", "uvse_refresh_token"];
try {
  for (const key of LEGACY_KEYS) localStorage.removeItem(key);
} catch {
  // No localStorage (private mode, blocked site data) — nothing to clean.
}

let accessToken = "";

// -------------------------
// Access token
// -------------------------

export function getToken() {
  return accessToken;
}

export function setToken(token) {
  if (typeof token === "string" && token.length > 0) {
    accessToken = token;
  }
}

export function clearToken() {
  accessToken = "";
}

// -------------------------
// Combined helpers
// -------------------------

/** Clear all in-memory auth state. Use on logout or auth failure. */
export function clearAll() {
  clearToken();
}

// Back-compat helpers (in case any older code still calls these)
export function getAccessToken() {
  return getToken();
}
export function setAccessToken(token) {
  setToken(token);
}

const authStorage = {
  getToken,
  setToken,
  clearToken,
  clearAll,
  getAccessToken,
  setAccessToken,
};
export default authStorage;
