// src/lib/authStorage.js
// Minimal token storage for UVSE (access token only)

const ACCESS_KEY = "uvse_access_token";

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

// Back-compat helpers (in case any older code still calls these)
export function getAccessToken() {
  return getToken();
}
export function setTokens({ accessToken }) {
  if (accessToken) setToken(accessToken);
}
export function clearTokens() {
  clearToken();
}
export function getRefreshToken() {
  return ""; // backend doesn't use refresh tokens in your current setup
}

const authStorage = { getToken, setToken, clearToken };
export default authStorage;
