// src/lib/authStorage.js
// Token storage for UVSE — access token + refresh token

const ACCESS_KEY = "uvse_access_token";
const REFRESH_KEY = "uvse_refresh_token";

// -------------------------
// Access token
// -------------------------

export function getToken() {
  return localStorage.getItem(ACCESS_KEY) || "";
}

export function setToken(token) {
  if (typeof token === "string" && token.length > 0) {
    localStorage.setItem(ACCESS_KEY, token);
  }
}

export function clearToken() {
  localStorage.removeItem(ACCESS_KEY);
}

// -------------------------
// Refresh token
// -------------------------

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY) || "";
}

export function setRefreshToken(token) {
  if (typeof token === "string" && token.length > 0) {
    localStorage.setItem(REFRESH_KEY, token);
  }
}

export function clearRefreshToken() {
  localStorage.removeItem(REFRESH_KEY);
}

// -------------------------
// Combined helpers
// -------------------------

/** Clear ALL auth tokens (access + refresh). Use on logout or auth failure. */
export function clearAll() {
  clearToken();
  clearRefreshToken();
}

// Back-compat helpers (in case any older code still calls these)
export function getAccessToken() {
  return getToken();
}
export function setAccessToken(token) {
  setToken(token);
}
export function setTokens({ accessToken, refreshToken }) {
  if (accessToken) setToken(accessToken);
  if (refreshToken) setRefreshToken(refreshToken);
}
export function clearTokens() {
  clearAll();
}

const authStorage = {
  getToken,
  setToken,
  clearToken,
  getRefreshToken,
  setRefreshToken,
  clearRefreshToken,
  clearAll,
  getAccessToken,
  setAccessToken,
};
export default authStorage;
