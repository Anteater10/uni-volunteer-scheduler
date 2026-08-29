# Decision: staff auth tokens stay in `localStorage`, with a narrowed refresh window

**Status:** **accepted · 2026-08-28 · Andy Subramanian** (project owner).
**Scope:** F1 in [security-review-frontend-infra.md](security-review-frontend-infra.md),
"Both auth tokens live in `localStorage`" — HIGH.
**Companion change:** `refresh_token_expires_days` 14 → **2** (`backend/app/config.py:45`).

## What is actually exposed

`frontend/src/lib/authStorage.js:12,17,30,35` persists both tokens in
`localStorage`:

| Token | Lifetime (before) | Lifetime (now) | What it grants |
|---|---|---|---|
| Access | 60 min | 60 min (unchanged) | API calls as that user |
| **Refresh** | **14 days** | **2 days** | Mints access tokens for its whole window — equivalent to the account |

Any JavaScript running on the origin can read both. `localStorage` is not
partitioned by script, so a single XSS, a compromised npm dependency, or a
browser extension with host access exfiltrates them.

## Who this affects — staff only

**Admin and organizer accounts only.** This is the point most likely to be
misread, so it is recorded explicitly:

| | Staff login | Volunteer magic link |
|---|---|---|
| Setting | `refresh_token_expires_days` (`config.py:45`) | `SIGNUP_CONFIRM_TTL_MINUTES = 20160` (`magic_link_service.py:37`) |
| Value | **2 days** (was 14) | **14 days — deliberately unchanged** |
| In `localStorage`? | yes | **no** |

**Volunteers hold no tokens at all.** Consuming a magic link
(`routers/magic.py:33`) flips a signup `pending → confirmed` and redirects — it
never issues a session. That is the account-less pivot working as designed, and
it means F1 has no volunteer-facing surface whatsoever.

The two systems both used 14 days. **That was a coincidence, not a shared
setting** — two constants, two files, two subsystems. A future reader must not
"tidy up" the mismatch by re-syncing them. The comment at `config.py:45` says so
in the code as well.

## Why we are accepting rather than migrating to cookies

**The blast radius is small in headcount, large in per-account value.** A handful
of staff accounts, each of which can read every volunteer's name, email, and
phone. So the risk is real, but it is bounded by a population we control and can
re-credential in minutes.

**Reuse detection already converts silent theft into detected theft.** Migration
`0040_refresh_token_family_and_reuse` implements refresh-token families: a stolen
token that the legitimate client later also uses trips the reuse check and the
whole family is revoked. This does **not** close the hole — it does nothing if
the attacker is the only party using the token — but it turns the common case
from "silent 14-day access" into "access until the real user next logs in."

**CSP is the control that actually matters here, and it is already scheduled.**
F1 says an XSS can *read* the tokens; F2 (no `Content-Security-Policy`) is why
nothing stops it *sending* them anywhere. A `connect-src` allowlist is the
compensating control this decision depends on, and it lands in Phase 3 of
`.planning/ROADMAP-2026-08-28.md`. **If F2 is dropped or deferred, this decision
must be reopened.** That is a condition, not a footnote.

**The real fix is a genuine project, at the worst possible moment.** Moving the
refresh token to an `HttpOnly; Secure; SameSite` cookie means a cookie-setting
login/refresh endpoint, CSRF protection on the refresh call (an `HttpOnly` cookie
is sent automatically — which is exactly why CSRF then applies), and a frontend
that stops persisting tokens. That is ~21 frontend files plus `routers/auth.py`,
1–2 days, **in the login path, immediately before a handoff to a developer who
has never deployed this system**. Phase 7 is the only pass that has ever driven
this application in a browser; breaking auth on the eve of it is a worse expected
outcome than the exposure being accepted.

## The compensating change

`refresh_token_expires_days: 14 → 2`. One line, no migration, no schema change.

- **Cuts the stolen-token window by 7×** — the single largest reduction available
  for the effort.
- **Costs nothing to volunteers**, who have no session.
- **Costs staff a re-login every 2 days.** Accepted deliberately: it is a handful
  of people who are already at a keyboard when they use the admin UI.

## Conditions of this acceptance

1. **F2 security headers ship**, including a CSP with an explicit `connect-src`.
   This decision is void without it.
2. **`refresh_token_expires_days` stays at 2 or lower.** Raising it reopens F1.
3. **The volunteer magic-link TTL is not touched** by anyone acting on this
   decision. It is a separate system and stays at 14 days.
4. **The cookie migration goes on the post-handoff known-issues list**, not into
   the void. Accepting is a deferral with a name on it, not a closure.
5. **Revisit if staff headcount or scope grows** — more organizer accounts, or
   any role that can export bulk volunteer PII, changes the arithmetic above.

## What this decision does not cover

- The access token also sits in `localStorage`. Its 60-minute bound is doing the
  work there; no change was made.
- No dynamic testing has been done. Nobody has attempted an actual XSS against
  this application. That is Phase 7 (W6.4) and the ZAP pass (T2), both undone.
