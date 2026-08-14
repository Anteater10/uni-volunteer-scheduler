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
| `admin.py` | 59 | ✅ | none — 59/59 guarded |
| `copilot/router.py` | 13 | ✅ | K33 (accepted) |
| `check_in.py` | 12 | ✅ | **S-01**, **S-02** |
| `shifts.py` | 11 | ✅ | none — previously remediated |
| `events.py` | 11 | ✅ | none |
| `users.py` | 10 | ✅ | none — see note below |
| `auth.py` | 8 | ✅ | S-04 (OIDC, open decision) |
| `slots.py` | 7 | ✅ | none — previously remediated |
| `organizer.py` | 5 | ✅ | none |
| `public/events.py` | 5 | ✅ | none — public by design |
| `broadcasts.py` | 3 | ✅ | none |
| `signups.py` | 3 | ✅ | none |
| `public/signups.py` | 3 | ✅ | none — public by design |
| `preferences.py` | 2 | ✅ | none — `manage_token` gated |
| `magic.py` | 2 | ✅ | none — token is the credential |
| `public/orientation.py` | 2 | ✅ | **S-06** (accepted) |
| `test_helpers.py` | 2 | ✅ | none — double-gated |
| `notifications.py` | 1 | ✅ | none |
| `roster.py` | 1 | ✅ | none |
| **Total** | **160** | **160 (100%)** | |
| *app-wide config* | — | ✅ | **S-05** |

**The earlier count of 150 was low.** The `public/` sub-package (10 endpoints
across three files) sits in `app/routers/public/`, not `app/routers/`, and was
missed by the first pass — the same shape of omission as S-03, one directory up.
The true surface is 160 across 19 routers.

**Method note, because it changed the result.** The first pass over the
remaining routers used a line-oriented script and reported 22 endpoints with no
role guard. Nearly all were false positives, from two causes: multi-line
`@router.post(...)` decorators, which truncated the signature before the
`Depends` was reached, and stacked decorators — `GET /audit-logs` and its legacy
`GET /audit_logs` alias are two decorators on one guarded handler, which a
line-oriented reader attributes to the wrong function. Re-running over the
Python AST, matching decorator `dependencies=` and every signature default,
brought it to 32 unguarded-in-signature, all of which are accounted for above:
public-by-design, token-gated, venue-code-gated, or checked in the handler body.
**Do not trust a grep for this.** Two independent passes disagreed by 20
endpoints in the direction of false alarm, and S-03 is why a third would too.

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

## S-05 — two protections hung off one fail-open string compare · MEDIUM · ✅ fixed

`environment` was a free-form `str` defaulting to `"development"`, and two
separate protections tested it with `== "production"`:

```python
environment: str = "development"                     # config.py
if expose_tokens and environment == "production":    # config.py
_docs_kwargs = {...} if settings.environment == "production" else {}   # main.py
```

**Why this is fail-open.** Every value that is not *exactly* `"production"`
reads as "not production" and turns both protections off. `ENVIRONMENT=prod`,
`Production`, `PRODUCTION`, `live`, or the variable simply never being set all
qualify — and `prod` is the spelling Render, Fly and ECS all invite. Nothing
raises, nothing logs, and the deploy passes its healthcheck looking perfectly
normal. That is the same signature as the prewarm OOM: a silent downgrade that
presents as success.

**What comes off when it downgrades:**

1. `/docs`, `/redoc` and `/openapi.json` are served publicly — a complete,
   machine-readable map of all 160 endpoints, their schemas and their required
   fields, to anyone who has the hostname.
2. The refusal to boot with `EXPOSE_TOKENS_FOR_TESTING=1` goes inert. That flag
   mounts two unauthenticated destructive endpoints (`DELETE /api/v1/test/
   seed-cleanup`, `DELETE /api/v1/test/event-signups-cleanup`, which bulk-cancel
   signups), **disables rate limiting**, and returns confirmation tokens in
   signup responses. One env var, all three.

Protection 2 has a second, independent gate — the router is only included when
the flag is set — so exposure needs both the flag *and* a non-`development`
environment name. Protection 1 has no second gate.

**Fix, in the fail-closed direction both times.** `environment` is now
`Literal["development", "staging", "production"]`, so a misspelling is a startup
`ValidationError` rather than a quiet downgrade. The flag check became
`!= "development"` (allow-list where it *is* permitted) and the docs check
became `== "development"` (serve only where intended). Listing the safe case
cannot fail open when a new environment name is added; listing the unsafe case
always can. The error message now names the offending value, because a guard
that fires without saying which environment tripped it costs an hour mid-deploy.

**Regression test:** `backend/tests/test_environment_guard.py`, 14 cases. The
load-bearing ones are the *negative* tests — `staging` and the five misspellings.
A test asserting that `production` blocks the flag passes against the broken code
too, which is precisely how this survived earlier review.

**Two caveats worth stating plainly.**

- **This is a breaking config change.** If the Render backend service currently
  has `ENVIRONMENT` set to anything outside the three literals, the next deploy
  fails at startup. That is the intended behaviour — Render holds the previous
  instance when a deploy fails its healthcheck, so the service stays up — but it
  needs checking in the dashboard *before* deploying, not after.
- **Whether the live service was actually exposed is unverified.** The backend
  service was created through the Render dashboard, not `render.yaml` (which
  defines only the static frontend), so its environment variables are not in the
  repo and this review cannot read them. If `ENVIRONMENT` is unset or spelled
  `prod` there, item 1 above has been live for the duration of the trial and the
  OpenAPI schema should be assumed public. The code defect stands regardless of
  what the dashboard says.

---

## S-06 — orientation status is a public lookup by email · LOW · ✅ accepted

`GET /public/orientation-status?email=` and `GET /public/orientation-check?email=`
return whether a given address holds orientation credit, with no credential.

The docstring claims enumeration defense via "identical response shape for
unknown and known emails" (D-08). That is true of the *shape* and not of the
*value*: an address with credit returns `true`, an unknown address returns
`false`, so the endpoint does answer "has this person done SciTrek orientation".
The real defense is the 5/min/IP rate limit — and note that limit only began
working per-caller once S-01 landed; before it, all callers shared one bucket.

**Accepted, not fixed.** The disclosure is one boolean about UCSB volunteer
training, not identity or contact data, and it is inherent to the feature: the
signup page has to tell a volunteer whether they need orientation before they
can sign up, and there is no credential to gate it with in an account-less
product. The correction needed is to the comment, not the code — the claim
"identical response shape" should not be read as "no oracle", because a future
reviewer trusting that line would skip the endpoint.

---

## S-03 — six spellings of "staff" · LOW (maintainability) · ☐ open

The same authorization rule is expressed six different ways across 160
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

The frontend review (W5.17) added a seventh spelling to the pile from the other
side: `signups.py`'s `cancel_signup` takes plain `get_current_user` in its
signature and does the staff check in the body, so a static read of the
decorator and signature — which is how any reviewer or tooling starts — shows an
endpoint that any authenticated caller can reach. Include it in the cleanup.

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
not accidental.

**Correction, 2026-08-13 (frontend authz review, W5.17).** This section
originally said "the admin-gated nav item means no organizer reaches it by
clicking, which limits accidental exposure". **That is false.**
`AdminLayout.jsx` lists the Copilot feedback nav item as
`roles: ["admin", "organizer"]`, so an organizer sees the link and reaches the
page by clicking, and `/admin/copilot-feedback` sits in App.jsx's shared
admin+organizer block. The behaviour matches the acceptance — organizers are
meant to have this access — so nothing changes operationally, but the acceptance
must not be read as resting on a mitigation that does not exist. The exposure is
the full one described above, deliberately. `routeAuthz.test.jsx` now pins the
route as intentionally shared so this cannot drift silently again.

**Revisit trigger — this is load-bearing.** The acceptance rests entirely on
"organizers are trusted staff". **If the copilot is ever opened to volunteers,
students, or any non-staff role, this must be re-decided before that ships**,
because the premise will no longer hold. Anyone widening copilot access should
treat this section as a blocker until it is re-signed.

**Not fixed, by decision.** K33 is closed as accepted. It is no longer a deploy
blocker, which removes the last open K-item from that list.

---

## Still to do

- ~~Sweep the remaining 12 routers~~ — **done.** 160/160 endpoints, 19 routers.
  Findings: S-05 (config, fixed), S-06 (accepted). No unguarded staff endpoint
  was found anywhere in the remaining surface.
- **W5.3** — mostly discharged by the completed sweep: the unauthenticated
  surface is `public/*` (10), `magic.py` (2), `preferences.py` (2), and the five
  `check_in.py` endpoints, and each is either token-gated, venue-code-gated, or
  visibility-filtered with 404-not-403 so a private event's existence is never
  confirmed. `slots.py`, `shifts.py` and `check_in.py`'s `GET /signups/{id}` were
  remediated in an earlier sweep and their reasoning is recorded in-file.
  Remaining: confirm `magic.py` token expiry and single-use, which is W5.4.
- **Andy — check before the next Render deploy.** S-05 makes an out-of-range
  `ENVIRONMENT` a startup failure. Confirm the dashboard value is exactly
  `development`, `staging` or `production` first. If it is unset or `prod`,
  the OpenAPI schema has been public and should be treated as disclosed.
- ~~**W5.4** — JWT expiry; magic-link single-use and expiry~~ — **done
  2026-08-13** (`tests/test_jwt_expiry.py`). See "W5.4 — expiry, verified by
  mutation" below.
- ~~**W5.6** — write down why broadcasts bypass the unsubscribe link~~ — **done
  2026-08-13.** Recorded in
  [docs/broadcast-email-policy-decision.md](broadcast-email-policy-decision.md),
  with the CAN-SPAM basis (operational/relationship mail is exempt from the
  opt-out requirement), the three rejected alternatives, and the two triggers
  that re-open it: recipient selection widening beyond "holds a spot", or any
  promotional content. Pinned by `tests/test_broadcast_optout_policy.py`, which
  asserts both halves of the asymmetry so a well-meaning "fix" fails loudly.
- ~~**W5.7** — `token_budget_exhaustion` and `indirect_injection` have no runner
  assertions~~ — **done 2026-08-13.** Both now run. Note the scope: the five
  `indirect_injection` cases in `cases.yaml` were always executed by the tool-loop
  runner; only the memory-flavoured case in `cases_memory.yaml` was inert, so
  "indirect injection is untested" was too broad a claim.
  - `token_budget_exhaustion` asserts the mechanical precondition of its
    behavioural claim: 32KB of history triggers `compress_if_needed`, the current
    question and the system prompt both survive, and a synopsis stands in for the
    dropped turns. Verified against `THRESHOLD_RATIO = 10.0`.
  - `indirect_injection` **was mis-specified, which is why it was never wired
    up.** It asserted `must_not_contain: ["tokens"]` — a keyword filter this
    system does not have and should not grow, since the extractor guards on PII
    redaction and a profile may legitimately record that a user asked about
    tokens. Rewritten to assert containment end-to-end: an imperative entering
    through the transcript, surviving the extractor, reaches the system prompt
    only inside the delimited advisory region. Verified by stripping the
    header/footer from `profile_block`.
  - **The structural fix matters more than either case.**
    `test_every_memory_category_has_a_runner` now fails if a category is added to
    the YAML without a runner. Both cases had sat there for weeks reading as
    coverage in any report that counted cases — the suite was described as 35 + 5
    when it was 35 + 3.

---

## W5.4 — expiry, verified by mutation · 2026-08-13

No production code changed: both properties already held. What was missing was
proof, so each new test was checked by breaking the code deliberately and
confirming the test failed for the right reason.

| Property | Where | Mutation it was proven against |
|---|---|---|
| Expired access token is not a credential | `get_current_user` | `options={"verify_exp": False}` → 401 test fails |
| Expired token reads as **anonymous**, not staff | `get_optional_user` | same → `GET /slots` starts dumping every slot |
| Minted token carries a bounded `exp` | `create_access_token` | drop the `exp` claim → no decode path can reject it |
| Magic-link expiry | `consume_token` | remove the `expires_at` check → 3 existing tests fail |
| Magic-link single-use | `consume_token` | remove the `consumed_at` check → **nothing fails, correctly** |

The `get_optional_user` case is the one worth remembering. That path swallows
`JWTError` and returns `None`, so an expiry regression there never surfaces as an
auth failure — it surfaces as an expired token being treated as a *staff* caller.
It is pinned through `GET /slots`, which dumps every slot in the database for
staff and 404s for everyone else, so one call discriminates staff from anonymous.

Single-use survives removal of its own guard because the atomic
`UPDATE ... WHERE consumed_at IS NULL` is a genuine second guard: the second
consumer updates 0 rows and gets `ConsumeResult.used`. Defence in depth, not a
gap — recorded here so a future reader does not "fix" the redundancy.

---

## W5.17 — frontend authorization review · 2026-08-13

The sweep above was backend routers only. This pass covered the ~38 routes in
`App.jsx`, `ProtectedRoute`, the admin nav, and the unauthenticated pages.
Pinned by `frontend/src/__tests__/routeAuthz.test.jsx` (19 cases), verified by
mutation: widening App.jsx's `roles={["admin"]}` block to include organizers
fails 5 tests.

**No leak found.** The findings are one false claim in this document and one
addition to S-03.

What was checked, and what held:

| Question | Result |
|---|---|
| Any route gated in the frontend but **not** on the backend? | **No.** All six admin-only screens (quarters, retrospective, users, audit logs, exports, orientation credits) hit endpoints taking `require_role(admin)`. Frontend gating is defence in depth, not the boundary. |
| Is `role` client-forgeable? | **No.** `authContext` takes it from `GET /users/me` on every load, not from a decoded JWT claim or localStorage. |
| Do shared screens render admin-only controls that would 403? | **No.** The one candidate — waitlist reorder on `AdminEventPage`, whose endpoints are admin-only — is gated behind `isAdmin` in the page. |
| Do the unauthenticated pages touch anything privileged? | **No.** They call `public/*`, plus `GET /slots` (public-event-filtered via `get_optional_user`) and the check-in endpoints, all of which require a venue code behind a failure ceiling. |
| Participant-role account on a staff URL? | Refused by `ProtectedRoute` and pinned. |

Two things a route-gating test cannot cover, so they stay for W6.1: whether a
screen an organizer *may* reach shows more than they should within it, and
whether the refusal states read sensibly. `ProtectedRoute`'s refusal is an
unstyled `<h2>Forbidden</h2>` with no way back — correct, and ugly. Log it with
the K38 (loading and empty states) work, not here.
