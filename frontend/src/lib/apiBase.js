// Single source of truth for the backend origin.
//
// Vite inlines VITE_API_URL at BUILD time — a bundle built without it can
// only ever talk to localhost. docker-compose.prod.yml guards the build arg
// with ${VITE_API_URL:?...}; keep that guard when adding new build paths.
//
// The `typeof import.meta` check keeps this importable under vitest/node.
export const RAW_BASE = (
  (typeof import.meta !== "undefined" ? import.meta.env?.VITE_API_URL : null) ||
  "http://localhost:8000"
).replace(/\/+$/, "");

export const API_BASE = RAW_BASE.endsWith("/api/v1")
  ? RAW_BASE
  : `${RAW_BASE}/api/v1`;
