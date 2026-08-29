# Security review — frontend and infrastructure

**Date:** 2026-08-20 · **Reviewer:** Claude (sweep), commissioned by Andy
**Scope:** signature sweep of the full tree — frontend, backend, infrastructure
(Docker, Caddy, CI, compose/env)
**Disposition:** report only. **No code was changed.**

> **Read the method before the findings.** This was a *pattern* sweep, not a file-by-file
> review. Roughly a dozen greps for known vulnerability signatures across the whole tree,
> then ~6 files opened to verify what they hit — out of 125 backend Python files and 102
> frontend source files. **Zero of the 159 endpoints were checked against their intended
> audience.** Every finding below therefore has a recognizable shape; the classes that do
> not (per-endpoint authorization, IDOR, business logic, auth-flow logic) are structurally
> invisible to it. K33 — an organizer-readable admin endpoint — was that class, and a human
> reading one file is what found it. See
> [security-review-endpoint-authz.md](security-review-endpoint-authz.md) for the
> endpoint-by-endpoint pass that covers it.

## Why this review exists

`docs/security-review-w5.md` covered the **backend**: router role guards, public
endpoints, JWT expiry, magic-link single-use, OIDC, the copilot PII boundary. Every
W5 item is server-side. Client-side concerns were never in its scope.

That gap was already known and written down — `.planning/ROAD-TO-DEPLOY.md:88`:

> **Gap nobody has covered: the frontend has never had an authz review.** … currently
> it is in neither W5 nor W6.1. Add it.

It was never added. This review closes it, and extends to infrastructure.

**A note on how the gap surfaced.** It was found by Andy, not by the audit, and not by
the status reporting — which recorded "W5 ✅ done" on the evidence that PRs #74 and #75
merged. That is evidence the *planned work landed*, not evidence the code is secure.
Those are different claims and the distinction is the reason this document exists.

---

## Findings

Severity is about this deployment: a university outreach scheduler holding volunteer
names, emails, phone numbers, and staff credentials. No payments, no health data.

### F1 · HIGH · Both auth tokens live in `localStorage`

> **Disposition 2026-08-28: ACCEPTED, with the refresh window cut 14 → 2 days.**
> Signed in [f1-token-storage-decision.md](f1-token-storage-decision.md).
> Staff-only — volunteers hold no tokens. **Conditional on F2 shipping a CSP.**

`frontend/src/lib/authStorage.js:12,17,30,35`

```js
const ACCESS_KEY = "uvse_access_token";
const REFRESH_KEY = "uvse_refresh_token";
export function getToken()        { return localStorage.getItem(ACCESS_KEY) || ""; }
export function getRefreshToken() { return localStorage.getItem(REFRESH_KEY) || ""; }
```

Any JavaScript running on the origin reads both. `localStorage` is not origin-partitioned
by script — a single XSS, a compromised npm dependency, or a malicious browser extension
with host access exfiltrates them.

The access token bounds itself at 60 minutes (`ACCESS_TOKEN_EXPIRES_MINUTES=60`). The
**refresh token is the real exposure at 14 days** (`REFRESH_TOKEN_EXPIRES_DAYS=14`), and
it mints access tokens for that whole window. Stealing it is equivalent to stealing the
staff account.

**Genuine mitigating factor, and it matters:** migration
`0040_refresh_token_family_and_reuse` implements refresh-token families with reuse
detection. A stolen token that the legitimate client later also uses trips the reuse
check and the family is revoked. That converts "silent 14-day access" into "access until
the real user next refreshes." It reduces the window; it does not close it, and it does
nothing if the attacker is the only one using the token.

**The standard fix** is to move the refresh token to an `HttpOnly; Secure; SameSite`
cookie so JavaScript cannot read it, keeping the short-lived access token in memory
(not `localStorage`). That is a backend + frontend change: a cookie-setting login/refresh
endpoint, CSRF protection on the refresh call (an `HttpOnly` cookie is sent
automatically, which is exactly why CSRF then applies), and a frontend that stops
persisting tokens. It is not a one-line change, and it is not W6 work — size it
deliberately.

### F2 · HIGH · No Content-Security-Policy or framing/type/referrer headers at the edge

`Caddyfile:36` sets exactly one security header:

```
header Strict-Transport-Security "max-age=31536000; includeSubDomains"
```

Missing: `Content-Security-Policy`, `X-Frame-Options` (or CSP `frame-ancestors`),
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`.

**This compounds F1 and should be read together with it.** F1 says an XSS can read the
tokens; the absence of CSP `connect-src` means nothing stops the same XSS from POSTing
them to an attacker's host. CSP is the control that makes an XSS expensive rather than
total. No `frame-ancestors`/`X-Frame-Options` also leaves the admin UI clickjackable.

Cheapest meaningful step: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin` — three lines, no application risk.
A real CSP needs a pass over what the SPA actually loads (Vite output, any inline
styles, the API origin) and should be rolled out `Content-Security-Policy-Report-Only`
first.

### F3 · MEDIUM · `react-router-dom` 7.14.0 has open advisories

`npm audit --omit=dev` reports **2 high** against `react-router` / `react-router-dom`
7.14.0. The vulnerable range is `7.0.0-pre.0 – 7.14.1`, so this deployment is inside it.

**Applicability is narrower than the count suggests, and the honest read matters here.**
Of the five advisories listed, four are specific to **RSC or SSR hydration** —
`RSCErrorHandler` protocol validation, `deserializeErrors()` constructor injection,
RSC-mode CSRF bypass, and server-side route matching DoS. This app is a **Vite SPA with
no SSR and no RSC**, so those four are not reachable here.

The one that plausibly does apply: **open redirect via protocol-relative URL** — a
same-origin redirect to a path beginning `//` reinterpreted as `//host`. Reachable
wherever a redirect target derives from a URL parameter.

So: patch it, but as hygiene on a clean upgrade, not as an emergency. It also stops the
audit from being permanently red, which is worth something on its own — a red audit
nobody can act on trains people to ignore it.

### F4 · LOW · Frontend container runs nginx as root

`frontend/Dockerfile` ends at `FROM nginx:1.27-alpine` with no `USER` directive, so the
nginx master process runs as root inside the container. This is the official image's
default and the workers drop to `nginx`, so the exposure is limited — but it is
inconsistent with `backend/Dockerfile:54`, which does drop to `USER appuser`. Worth
aligning for the same reason the backend does it.

### F5 · LOW (config-conditional) · `DEBUG=true` would log raw magic-link tokens

`backend/app/celery_app.py:763,875`

```python
if getattr(settings, "debug", False):
    logger.debug("signup_confirmation_token_preview token=%s", token)
```

Correctly gated, and `backend/.env.production.example` sets `DEBUG=false`. Recorded not
as a defect but as a **deploy-time trap**: a single env var turns volunteer
signup-confirmation and waitlist-promotion tokens into log lines, and those tokens are
bearer credentials for someone else's signup. If logs ship to a third party, that is
where they land. Worth an explicit line in the runbook.

---

## Verified clean

Recorded so nobody re-reviews these from scratch.

| Area | Result | Evidence |
|---|---|---|
| Secrets in the repo | Clean | Only `*.env.example` tracked; `.gitignore:3-9` allowlists templates only; no env file appears in `git log --diff-filter=A` |
| SQL injection | Clean | No f-string/`.format()`/`%` interpolation into `text()` or `execute()` anywhere in `backend/app`. The only f-string SQL is in two test files against hardcoded table names |
| Dynamic `ORDER BY` | Clean | No `order_by(text(...))` or `getattr`-driven column selection |
| XSS sinks | Clean | Exactly one `dangerouslySetInnerHTML`, at `BroadcastModal.jsx:369`. Its renderer (`previewMarkdown`, line 36) HTML-escapes **before** applying inline rules, and its link regex requires `https?://`, so `javascript:` URLs cannot be constructed. Input is the admin's own draft |
| Client-side authorization | Clean | `ProtectedRoute.jsx` gates on `roles`, and `authContext.jsx:13` sources `role` from the server via `api.me()` — not from a decoded token or a client-writable value. Backend guards remain the real enforcement |
| CORS | Clean | `main.py:150` uses an explicit origin list from config, never `*` |
| Backend container user | Clean | `backend/Dockerfile:54` drops to `USER appuser` |
| Sensitive data in logs | Clean apart from F5 | No password, secret, or API-key values reach a logger |

---

## Known and previously accepted — not re-litigated here

- **starlette form-parsing limit ignored** (BASE-CONFIG-36, CVSS 7.5). Cannot be patched
  without a dependency conflict; mitigated at the edge by `Caddyfile`'s 2MB
  `request_body` cap. Documented, with the constraint that the backend port must never
  be published separately for the mitigation to hold.
- **PII plaintext at rest.** Accepted in writing, signed, in `docs/pii-at-rest-decision.md`.
- **K33 — `/admin/feedback/*` readable by organizers.** Accepted, not fixed.

---

## What this review did not cover

Stated plainly rather than left implied.

- **No dynamic testing.** Everything above came from reading code and configuration.
  Nobody drove a browser, attempted an actual XSS, or ran a scanner against a running
  instance. That is W6's job and it remains undone.
- **No backend re-verification.** W5's findings and acceptances were taken as given.
- **No Python dependency CVE audit.** `npm audit` has no run pip equivalent here;
  `pip-audit` is not installed in the image.
- **No authenticated fuzzing, no secret-scanning of full git history** beyond env files.

## Suggested order, if these get fixed

1. **F2's three cheap headers** — minutes, no application risk, immediate value.
2. **F3 upgrade** — clean dependency bump, gets the audit green.
3. **F5 runbook line** — one sentence.
4. **F1 cookie migration** — real design work. Decide whether it precedes handoff or is
   written into the known-issues list with F2's CSP as the compensating control.
5. **F4** — align with the backend image whenever that Dockerfile is next touched.
