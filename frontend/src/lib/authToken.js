// src/lib/authToken.js
// Phase L3: shared access-token accessor + single-flight refresh, used by
// both lib/api.js's request() and every call site that hand-rolls fetch()
// with a bearer header instead of going through request() (the copilot
// surface, check-in, roster). Those bypass sites never retried on a 401
// before this existed — a token expiring mid-session just failed outright.
import authStorage from "./authStorage";
import { API_BASE } from "./apiBase";

export function getAccessToken() {
  return authStorage.getToken();
}

// Re-read per call, never cached: the server mints a fresh csrf_token on
// every rotation, so a module-level copy would go stale behind an open tab.
export function readCsrfCookie() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/** Module-scoped promise so concurrent 401s queue behind one refresh call. */
let refreshPromise = null;

const REFRESH_LOCK = "uvs-auth-refresh";

async function postRefresh() {
  // No `csrf ? ... : {}` fallback: refreshAccessToken has already refused to
  // get here without a csrf cookie, so a header-less branch would be dead
  // code that reads as though the request could ever be worth sending
  // without one. It cannot — it would 403.
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": readCsrfCookie() },
  });
  if (!res.ok) {
    // Only a 401/403 means the session is genuinely gone (bad, expired or
    // revoked refresh cookie). A 429 from the per-IP throttle, a 5xx, or a
    // proxy hiccup are transient — and since this runs on EVERY page load,
    // treating those as "logged out" would drop a still-valid session on a
    // blip. Staff behind one campus NAT share a throttle bucket, so 429 is
    // realistic. Leave the cookie alone and let the next attempt recover.
    if (res.status === 401 || res.status === 403) {
      authStorage.clearAll();
      throw new Error("REFRESH_REJECTED");
    }
    throw new Error(`REFRESH_UNAVAILABLE_${res.status}`);
  }
  const data = await res.json();
  authStorage.setToken(data.access_token);
  return data.access_token;
}

/**
 * Ask the server to mint a new access token from the HttpOnly refresh
 * cookie. The refresh token itself is never visible to this code — the
 * browser attaches the cookie automatically (credentials: "include"); the
 * csrf_token cookie (JS-readable by design) is echoed back as a header so
 * the backend's double-submit check can tell this apart from a cross-site
 * request riding on the same cookie.
 *
 * Serialized twice over, because the refresh token rotates on every use and
 * a replay of the spent value is indistinguishable from theft server-side:
 *   - `refreshPromise` collapses concurrent callers within one tab.
 *   - the Web Lock collapses them ACROSS tabs. Without it, two tabs reloaded
 *     together both read the same cookie and both POST; one rotates, the
 *     other replays a consumed token. The cookie jar is shared, so a tab
 *     that waits its turn simply picks up the rotated cookie and succeeds.
 * `navigator.locks` is absent in older Safari and in jsdom, so it degrades
 * to the single-tab guard rather than being required.
 */
export async function refreshAccessToken() {
  // No csrf cookie means there is no session to refresh, so skip the round
  // trip entirely. This matters on the PUBLIC surface: the boot refresh in
  // state/authContext.jsx runs on every page load, and an anonymous visitor
  // has no cookies at all — the request would 403 (no CSRF pair), which the
  // browser logs as a console error on a page where the volunteer-facing
  // e2e specs forbid console errors (PART-02), and would still consume a
  // slot in the per-IP throttle on every visit to a public page.
  //
  // The csrf cookie is the right signal precisely because it is the
  // JS-readable half: it is set alongside the refresh cookie, cleared with
  // it on logout, and shares its lifetime. If it is missing, a refresh
  // could not succeed anyway.
  if (!readCsrfCookie()) {
    authStorage.clearAll();
    throw new Error("NO_SESSION");
  }
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    if (typeof navigator !== "undefined" && navigator.locks?.request) {
      // Waits its turn, then always does its own POST. It deliberately does
      // NOT short-circuit on "a token is already in memory" — on the 401
      // path the in-memory token is the expired one we are here to replace,
      // so returning it would loop. Re-POSTing is correct and cheap: the
      // cookie jar is shared, so by now this reads whichever refresh cookie
      // the tab ahead left behind.
      return navigator.locks.request(REFRESH_LOCK, () => postRefresh());
    }
    return postRefresh();
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

/**
 * fetch() wrapper for call sites that need an Authorization header but
 * don't go through lib/api.js's request() (e.g. the copilot's SSE stream,
 * which needs raw fetch()+ReadableStream, not JSON). Attaches the current
 * access token and retries once via the shared refresh on a 401.
 */
export async function authorizedFetch(url, options = {}) {
  const attempt = (token) => {
    // new Headers() rather than a spread: `{...new Headers()}` yields {},
    // which would silently drop Content-Type/Accept for any caller that
    // passes a Headers instance instead of a plain object.
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(url, { ...options, headers });
  };

  let token = getAccessToken();
  let res = await attempt(token);

  // Retried even when there was no token to begin with: a request that fires
  // before the boot refresh has finished would otherwise surface a spurious
  // 401 to the caller. A retry with no refresh cookie just fails again and
  // returns the original response.
  if (res.status === 401) {
    // A stream body is consumed by the first attempt, so it cannot be
    // replayed — retrying would throw "body stream already read" instead of
    // whatever the caller was prepared to handle. Only the response is
    // streamed in the SSE case (the request body there is a string), so
    // nothing in the app hits this today; the guard is here so the next
    // caller who does gets its 401 rather than a TypeError.
    const bodyIsReplayable =
      !options.body ||
      typeof options.body === "string" ||
      options.body instanceof URLSearchParams ||
      options.body instanceof Blob ||
      options.body instanceof ArrayBuffer;
    if (!bodyIsReplayable) return res;

    try {
      token = await refreshAccessToken();
    } catch {
      return res; // Refresh failed — let the caller handle the original 401.
    }
    res = await attempt(token);
  }

  return res;
}
