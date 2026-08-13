# W5 — security review

Status: **in progress.** Started 2026-08-13. Owner: Andy Subramanian.

The gate for this phase is not "no findings". It is: every high or critical
finding either **remediated** or **accepted in writing, by name, with the
exposure stated plainly**. An acceptance that softens what it is accepting is
indistinguishable from an oversight when someone reads it in a year, so the
acceptances below describe the worst case, not the likely case.

---

## Coverage

The sweep walks every endpoint's guard against its intended audience. It is
deliberately **not** a grep: see [S-03](#s-03--six-spellings-of-staff) for why a
pattern search cannot cover this surface, and note that K33 was originally found
by reading one file.

| Router | Endpoints | Swept | Findings |
|---|---|---|---|
| `signups.py` | 4 | ✅ | none |
| `users.py` | 10 | ✅ | none — see note below |
| `auth.py` | 8 | ✅ | S-04 (OIDC, open decision) |
| `notifications.py` | 1 | ✅ | none |
| `check_in.py` | 12 | ✅ | **S-01**, **S-02** |
| `admin.py` | 59 | ☐ | — |
| `copilot/router.py` | 13 | ☐ | K33 (accepted) |
| `shifts.py` | 11 | ☐ | — |
| `events.py` | 11 | ☐ | — |
| `slots.py` | 7 | ☐ | — |
| `organizer.py` | 5 | ☐ | — |
| `broadcasts.py` | 3 | ☐ | — |
| `preferences.py` | 2 | ☐ | — |
| `magic.py` | 2 | ☐ | — |
| `roster.py` | 1 | ☐ | — |
| `test_helpers.py` | 2 | ☐ | — |
| **Total** | **150** | **35 (23%)** | |

**`users.py` deserves a positive note**, because it is the file where privilege
escalation would most likely live and it is built correctly. `PATCH /me` uses a
`setattr` loop — the classic mass-assignment shape — but is protected twice
independently: `schemas.UserUpdate` has no `role` field at all, *and*
`_USER_UPDATE_ALLOWED_FIELDS` allow-lists three fields. Role changes exist only
on `PATCH /users/{user_id}`, which is `require_role(admin)` and additionally
carries a self-demote guard, a last-active-admin guard, and a `FOR UPDATE` lock.
Login lockout counts on the user row rather than an IP, so it cannot be used to
lock staff out en masse.

---

## S-01 — uvicorn on Render did not trust proxy headers · HIGH · ✅ fixed

`backend/start_render.sh` started uvicorn without `--proxy-headers`, while
`docker-compose.prod.yml:101` has always passed it. Render terminates TLS and
forwards, so `request.client.host` was Render's internal proxy address for
**every** request.

This is an availability bug before it is a security one:

1. **Day-of-event outage.** `deps.rate_limit` keys its bucket on
   `rate:{client.host}:{path}`. With every caller resolving to the same address,
   all volunteers shared **one** bucket per path. The public check-in endpoints
   allow 30 requests / 60s and the volunteer flow spends two or more per person
   (`check-in-lookup`, then `check-in-selected`), so roughly a dozen people
   scanning the event QR simultaneously begins returning 429 to each other — on
   a classroom floor, mid-event, with no message that explains why.
2. **Weakened throttles.** The same collapse removed the per-attacker ceiling
   standing between a guesser and the 4-digit venue code (see S-02), and the IP
   half of `check_reset_rate_limit` stopped contributing anything.
3. **Blind audit trail.** `auth.py:379` and `magic.py:85` log that address, so
   an investigation would have had only the proxy's address to work from.

**Fix:** `--proxy-headers --forwarded-allow-ips="*"`, with the reasoning recorded
at the site. `"*"` is safe *only* because the service is reachable exclusively
through Render's proxy — if this container is ever given a directly-routable
port, a caller could spoof `X-Forwarded-For` and forge their rate-limit
identity, and the allow-list must be narrowed to the real hop first. The compose
path keeps its CIDR, because there the hop is a known Caddy container.

**Regression test:** `backend/tests/test_proxy_headers.py`. These are
file-content assertions on purpose — the flag lives in a start command, so
nothing in the running app can observe whether it was passed. The only place the
regression is visible is the file that omits it, and losing it is a one-word
edit that produces no failing request anywhere.

---

## S-02 — the venue code is four digits, and never rotates · MEDIUM · ✅ fixed

> **Decided 2026-08-13 by Andy Subramanian: keep four digits, add an attempt
> ceiling.** Implemented in `app/services/venue_code_attempts.py`, wired into all
> four gated endpoints via `_venue_code_ceiling` in `routers/check_in.py`.
> Default 10 wrong codes per 15 minutes, keyed on **(event, caller address)**.
>
> **Why per caller and not per event.** An event-wide counter would let anyone
> shut down check-in for every volunteer at a visit by deliberately burning the
> ceiling — trading an information leak for an outage on the one flow that has to
> work on a classroom floor. That is a worse bargain than the leak.
>
> **This control depends on S-01.** Before proxy headers were trusted, every
> caller resolved to Render's proxy, so a per-caller counter *would have been*
> event-wide in practice, with exactly the DoS property above. If
> `--proxy-headers` is ever dropped, this protection inverts into an outage;
> `tests/test_proxy_headers.py` exists to prevent that.
>
> **Volunteers never trip it.** The QR URL carries the code, so the normal path
> submits a correct one. Only manual entry can fail, and a correct code forgives
> earlier fumbles — including when the request then fails downstream (arriving
> early, outside the check-in window), so being early never burns the ceiling.
>
> **Residual risk, unchanged and accepted.** A per-caller ceiling does not stop a
> distributed attacker: at 10 per 15 minutes, covering all 10,000 candidates needs
> on the order of a thousand distinct addresses. That is the bar four digits can
> support. If the threat model ever includes a motivated distributed attacker, the
> answer is a longer code, not a tighter ceiling.
>
> **Redis failures fail open**, matching `deps.rate_limit` — "the guess ceiling is
> off for the duration" beats "nobody at the event can check in". The boundary is
> still `_require_venue_code`, which is unaffected.
>
> Tests: `tests/test_venue_code_ceiling.py` (14, the counter and its failure
> modes) and `tests/test_venue_code_ceiling_endpoints.py` (8, parametrized over
> all four endpoints — a helper wrapping three of four is the failure mode there).

The original finding follows, for the record.



`models.py:255` declares `venue_code = Column(String(4))` and `roster.py:41`
fills it with `f"{secrets.randbelow(10000):04d}"` — a **10,000-value** space,
generated once when a roster is first built and never rotated afterwards.

The code is the only gate on five no-auth endpoints in `check_in.py`
(`self-check-in`, `check-in-lookup`, `check-in-selected`, `check-in-by-email`,
and the narrowed `GET /signups/{id}`).

**What the code protects.** Guessing it yields three things:

- **A participation oracle.** The email-based endpoints answer 404
  (`NoSignupForEmailError`) for an address holding nothing on the event, and
  200 otherwise. That difference reveals whether a named person volunteers at a
  named school on a named date.
- **Their schedule.** `check-in-lookup` returns the volunteer's shifts on that
  event with per-shift window verdicts.
- **Write access to attendance.** `check-in-by-email` will mark a volunteer
  present without their involvement.

**What is already right, and should not be undone.** `_require_venue_code` runs
*before* any email or volunteer resolution, deliberately and with a comment
saying so — a wrong code cannot be used to probe participation. The endpoints
are rate-limited. `GET /signups/{id}` was narrowed by an earlier sweep to only
the fields `SelfCheckInPage.jsx` renders. The design is sound; the parameter is
the question.

**Cost to attack.** With per-IP throttling restored by S-01, 10,000 candidates
at 30/60s is ~5.5 hours from a single address, and minutes if distributed across
a handful. Nothing locks out or rotates after repeated failures. Before S-01 the
throttle was not per-attacker at all.

**Mitigating context, stated fairly.** An attacker needs to know the event
exists and care about a specific volunteer; the data is attendance at a
university outreach visit, not financial or medical; and the code is read aloud
to a room of volunteers by design, so it is semi-public in the physical world
regardless of its length.

**Why this is a decision and not a fix.** Lengthening the code trades usability
in the exact moment it matters — an organizer reading it to a room, volunteers
typing it on phones. Four digits was very likely chosen for that reason, and
that is a legitimate reason. Options:

| Option | Effect | Cost |
|---|---|---|
| Leave at 4 digits, accept in writing | none | this section becomes an acceptance |
| 6 alphanumeric (~2.2 billion) | brute force becomes infeasible | more to read out and type |
| Keep 4 digits, rotate per event-day | shrinks the window to one day | small code change; codes stop being stable |
| Keep 4 digits, add a per-event attempt ceiling | attacker locked out well before exhausting the space | small code change; a fumbling organizer could trip it |

**Recommendation:** the per-event attempt ceiling. It preserves the 4-digit
usability that the flow was designed around and removes the brute-force path,
which is the actual exposure. Awaiting Andy's call.

---

## S-03 — six spellings of "staff" · LOW (maintainability) · ☐ open

The same authorization rule is expressed six different ways across 150
endpoints:

| Idiom | Sites |
|---|---|
| `require_role(models.UserRole.admin)` | 42 |
| `require_role(models.UserRole.admin, models.UserRole.organizer)` | 26 |
| `require_role(models.UserRole.organizer, models.UserRole.admin)` | 19 |
| `_require_admin_or_organizer(...)` (copilot-local helper) | 14 |
| `Depends(require_staff)` | 8 |
| `require_role(UserRole.organizer, UserRole.admin)` | 8 |
| in-body `if current_user.role not in (...)` | `signups.py` ×4, `users.py` ×7 |

No single search covers that set, which is the mechanism by which K33 sat
unnoticed behind an admin-gated nav item, and why the first pass of this sweep
initially mis-scoped its own target list (28 endpoints looked unguarded because
their check is in the handler body rather than the signature).

Not a live vulnerability — coverage is genuinely good. It is a **standing
obstacle to ever auditing this surface again**, including by whoever inherits it.
Recommend one cleanup commit collapsing all six onto `require_role`, scheduled
*after* the sweep so it does not churn the files being read.

---

## S-04 — OIDC is half-wired · LOW · ⛔️ needs a decision

`auth.py` registers an OIDC client when three settings are present. All three
are `None`, there is no UI entry point, and two endpoints (`GET /sso/login`,
`GET /sso/callback`) are live and unauthenticated. Dormant authentication paths
are the worst category of dead code: they carry real risk and have no owner or
test coverage.

**Recommendation:** delete both endpoints and the registration. Restoring them
from git history is easy if SSO is ever wanted.

---

## Accepted risks

### K33 — organizers can read other staff's copilot conversations

**Accepted 2026-08-13 by Andy Subramanian.**

**The exposure, stated plainly.** `GET /api/v1/copilot/admin/feedback/weekly`
and `GET /api/v1/copilot/admin/feedback/bottom-messages`
(`copilot/router.py:1169`, `:1190`) are guarded by
`_require_admin_or_organizer`. Any organizer account can therefore read
**every other staff member's verbatim copilot messages** — what they typed, what
the assistant replied — plus their thumbs-down comments.
`feedback.aggregates.bottom_messages` applies **no user filter at all**, so this
is the whole population, not the caller's own rows.

**Grounds for acceptance.** Organizers are trusted staff. This is consistent
with the 2026-08-12 ruling that organizer reads are unscoped, and with how this
team actually operates. Two existing tests —
`test_weekly_organizer_allowed` and `test_bottom_messages_organizer_allowed` in
`backend/tests/copilot/api/test_feedback_admin_endpoints.py` — assert organizer
access returns 200, so the behaviour is intentional and documented in the suite,
not accidental. The admin-gated nav item means no organizer reaches it by
clicking, which limits accidental exposure.

**Revisit trigger — this is load-bearing.** The acceptance rests entirely on
"organizers are trusted staff". **If the copilot is ever opened to volunteers,
students, or any non-staff role, this must be re-decided before that ships**,
because the premise will no longer hold. Anyone widening copilot access should
treat this section as a blocker until it is re-signed.

**Not fixed, by decision.** K33 is closed as accepted. It is no longer a deploy
blocker, which removes the last open K-item from that list.

---

## Still to do

- Sweep the remaining 12 routers (115 endpoints), `admin.py` first by volume and
  `broadcasts.py` first by risk.
- **W5.3** — confirm the unauthenticated surface (public signup, magic-link
  manage, the five `check_in.py` endpoints) cannot enumerate volunteers beyond
  what S-02 describes.
- **W5.4** — JWT expiry; magic-link single-use and expiry.
- **W5.6** — write down why broadcasts bypass the unsubscribe link (operational,
  not promotional) so it is a recorded decision rather than a scramble later.
- **W5.7** — `token_budget_exhaustion` and `indirect_injection` are documented
  adversarial surfaces with no runner assertions. Assert them or mark them
  explicitly untested.
