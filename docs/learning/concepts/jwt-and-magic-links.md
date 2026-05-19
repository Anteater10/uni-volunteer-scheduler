# JWT, Magic Links, and Stateless Authentication

## Why this matters

Authentication is the place where interviewers stop being friendly and
start probing your security instincts. The reason: it is the surface where
junior engineers make catastrophic, production-breaking mistakes —
algorithm confusion attacks, JWTs in `localStorage`, refresh tokens stored
as plaintext, magic links sent over HTTP, tokens with no expiration. A
strong candidate on a backend or full-stack interview is expected to know:

1. What a JWT actually is (three base64-encoded segments, joined by dots).
2. Why "stateless" is a marketing word that comes with real engineering
   trade-offs.
3. How magic-link authentication works and why it is a single-use
   bearer-token scheme.
4. The shape of refresh-token rotation and why you do it.
5. The named attacks: `alg=none`, key confusion (HS256 with an RSA public
   key), token theft via XSS, replay attacks.

This lecture walks through all of it using the actual auth stack from
this codebase, which happens to ship two distinct token systems in
production: stateful magic-link tokens for the account-less participant
flow, and JWT access + opaque refresh tokens for admin/organizer login.

## The design choice

### Sessions versus tokens

Server-side sessions are the traditional pattern: on login, the server
generates a random session ID, stores it in a database or Redis with the
user ID attached, and sends the session ID back as a cookie. Every
subsequent request, the browser sends the cookie; the server looks the ID
up; if it exists, the user is authenticated. Logout is a single DELETE in
the session store.

```
POST /login → sets Cookie: sid=abc123 (HttpOnly, Secure, SameSite=Lax)
GET /me     → reads cookie, looks up sid in Redis, returns user
```

Strengths: revocation is free (just delete the row), the cookie is opaque
(no information leaks), the session row can carry arbitrary state, and
`HttpOnly` cookies are immune to XSS theft.

Weaknesses: every authenticated request hits the session store. At small
scale that is fine; at large scale you pay for the round-trip. Multi-region
deployments need cross-region session replication.

### JWT — stateless tokens

A JWT (JSON Web Token, RFC 7519) is a signed JSON object that carries the
user's identity inside it. On login, the server generates a JWT containing
the user ID and claims, signs it with a secret, and sends it back. The
client stores it and includes it in the `Authorization` header on every
request. The server verifies the signature locally — no database lookup —
and reads the claims.

```
POST /login → returns { access_token: "eyJhbGc..." }
GET /me     → Authorization: Bearer eyJhbGc...
              server verifies signature → reads sub → returns user
```

Strengths: no per-request session lookup, easy to scale across services
(any service with the secret can verify), works for service-to-service
auth, fits API-first architectures.

Weaknesses: **revocation is hard**. The token is valid until it expires;
you cannot un-issue it. The standard mitigation is short access-token TTLs
(15 minutes is typical) with a separate refresh-token mechanism for
long-lived sessions. JWTs are also bigger than session IDs (a few hundred
bytes vs ~32) and they carry information that a passive observer with the
token can decode (they are signed, not encrypted).

### Magic links — passwordless email auth

A magic link is a single-use bearer token embedded in a URL, delivered via
email. The user clicks the link, the server consumes the token, and
issues a real session/JWT. There is no password anywhere in the system.

```
POST /signup     → server creates pending row + magic-link token,
                   emails: https://app/auth/magic/abc123xyz
User clicks link → GET /auth/magic/abc123xyz consumes token,
                   confirms the signup
```

The trade-off versus passwords: you eliminate the entire "users picking
bad passwords" problem and the "password database breach" problem, but
you make email security the gating factor. If the user's email is
compromised, every magic-link service the user has is compromised. This
is also true of password resets, so in practice the security floor is
roughly the same.

### When you use which

In this codebase, both patterns coexist:

- **Participants** never log in. They sign up for events; an email goes
  out; clicking the link confirms the signup. No password, no account,
  no JWT. The magic-link token is the entire auth surface.
- **Admins and organizers** log in with password + JWT access + opaque
  refresh. Stateful refresh tokens (in the DB, rotated on use); stateless
  access tokens (short-lived JWTs).

The choice is driven by the user model. A participant interaction is one
event-shaped transaction; sessions add no value. An admin spends an hour
managing rosters; the JWT + refresh dance amortizes well.

## How it works under the hood

### Anatomy of a JWT

A JWT is three base64url-encoded JSON segments joined by dots:

```
HEADER . PAYLOAD . SIGNATURE
```

A real-looking example:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3MWY2MmFmYy0xOTNkLTRiMjUtYTBkZS00ZWZjMTM5Mjc2N2IiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3MTU3MjQ4MDB9.A_signature_blob_here
```

Decoding the first segment (base64url):

```json
{ "alg": "HS256", "typ": "JWT" }
```

Decoding the second:

```json
{
  "sub": "71f62afc-193d-4b25-a0de-4efc1392767b",
  "role": "admin",
  "exp": 1715724800
}
```

The third segment is `HMAC-SHA256(base64url(header) + "." + base64url(payload), secret)`.

Standard claim names (RFC 7519):

- `sub` — subject (usually user ID)
- `iss` — issuer
- `aud` — audience
- `exp` — expiration timestamp (UNIX seconds)
- `iat` — issued-at timestamp
- `nbf` — not-before timestamp
- `jti` — JWT ID (unique token identifier, for revocation lists)

Anything else is a "private claim." This codebase adds `role` (admin /
organizer / participant) and, for invite tokens, `purpose: "invite"`.

### HS256 versus RS256

Two dominant signing algorithms:

- **HS256** — HMAC with SHA-256. Symmetric. The signing party and the
  verifying party share a single secret. Simple, fast, perfect when both
  sides are the same service.
- **RS256** — RSA signature with SHA-256. Asymmetric. The signer holds a
  private key; verifiers hold the public key. Use this when one service
  issues tokens and many services verify them (microservices,
  identity-provider patterns, OIDC).

This codebase uses HS256 because there is one backend service. The secret
is `settings.jwt_secret`, configured via environment variable.

### Verification flow

```python
from jose import jwt, JWTError

try:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],   # MUST be a list, MUST be explicit
    )
    user_id = payload.get("sub")
except JWTError:
    raise HTTPException(401)
```

The library does five things:

1. Splits the token on `.`, base64url-decodes the three segments.
2. Reads the `alg` claim from the header.
3. **Checks `alg` is in the `algorithms` allowlist** (this is the part
   that defeats `alg=none`).
4. Recomputes the signature over header+payload using the secret/public
   key, compares it to the signature segment (constant-time compare).
5. Checks `exp` against the current clock.

If any step fails, the library raises. The route handler returns 401.
The mechanical part is straightforward; the security part is whether the
library is configured correctly.

### Magic-link token flow

A magic-link token in this codebase is not a JWT. It is a 32-byte
cryptographic random string (`secrets.token_urlsafe(32)`), URL-safe,
~43 characters. The SHA-256 hash of the raw token is stored in the
`magic_link_tokens` table along with the related signup ID, the email,
the issue time, and an expiration timestamp. The raw token appears
exactly once outside the issuance code — inside the email body — and is
never logged.

```
1. User signs up
   ─► server INSERT INTO signups (status='pending')
   ─► server generates raw = secrets.token_urlsafe(32)
   ─► server INSERT INTO magic_link_tokens (token_hash = sha256(raw), expires_at, signup_id)
   ─► server sends email containing https://app/auth/magic/<raw>

2. User clicks the link
   ─► GET /auth/magic/<raw>
   ─► server computes sha256(raw), looks up the row
   ─► validates: not consumed, not expired
   ─► atomic UPDATE … SET consumed_at = NOW() WHERE consumed_at IS NULL
   ─► if updated == 1 (we won the race), flip signup to confirmed
   ─► redirect to /signup/confirmed
```

Three properties make it secure:

- **Single-use.** The atomic update prevents replay. Two browsers clicking
  the same link result in exactly one confirmation.
- **Hashed at rest.** Even if the DB leaks, the attacker has SHA-256
  digests, not usable tokens. No rainbow tables — the input is
  32 bytes of randomness.
- **Short TTL.** This codebase uses a configurable TTL (default tens of
  minutes for re-auth, 14 days for confirmation links). Expiration is
  enforced in the consumption query.

The contrast with JWTs: magic-link tokens are stateful. The DB row IS the
auth state. You can revoke instantly (DELETE the row), audit (every
issuance and consumption is a row event), and rate-limit by counting
recent rows. The cost is the per-link DB round-trip.

## How this codebase uses it

### JWT access tokens — `backend/app/deps.py`

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expires_minutes
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user
```

Defaults from `backend/app/config.py`:

```python
jwt_algorithm: str = "HS256"
access_token_expires_minutes: int = 60
refresh_token_expires_days: int = 14
```

The access token TTL is one hour. The role is embedded in the token so
role-checks (`require_role`) do not need a DB hit.

### Login + refresh — `backend/app/routers/auth.py`

```python
@router.post("/token", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = ...):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or user.hashed_password is None:
        raise HTTPException(401, "Incorrect email or password")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password")

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    raw_refresh = _issue_refresh_token(db, user)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": raw_refresh}
```

Refresh tokens are NOT JWTs in this codebase — they are 48-byte random
strings stored hashed:

```python
def _issue_refresh_token(db: Session, user: models.User) -> str:
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)
    rt = models.RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires,
        created_at=datetime.now(timezone.utc),
    )
    db.add(rt); db.flush()
    return raw
```

This is the right design. JWT refresh tokens are an anti-pattern — they
defeat the only thing you got from being stateful, which is the ability
to revoke. Storing refresh tokens as opaque random strings in the DB
means a `DELETE FROM refresh_tokens WHERE user_id = ?` is a real logout.

Rotation on refresh is enforced explicitly:

```python
@router.post("/refresh", response_model=schemas.Token)
def refresh_token(payload: RefreshRequest, db: Session = ...):
    user = _consume_refresh_token(db, payload.refresh_token)   # DELETES old row
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_raw_refresh = _issue_refresh_token(db, user)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": new_raw_refresh}
```

Every successful refresh deletes the consumed token and issues a new
one. If an attacker steals a refresh token and uses it, the legitimate
user's next refresh attempt fails with 401, and they get logged out —
which surfaces the compromise instead of hiding it. (A more advanced
version would proactively revoke ALL of the user's refresh tokens on
detection of a re-used token; this is reuse detection.)

### Magic links — `backend/app/magic_link_service.py`

```python
def issue_token(db, signup, email, *, purpose=MagicLinkPurpose.SIGNUP_CONFIRM, ...):
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    row = MagicLinkToken(
        token_hash=token_hash,
        signup_id=signup.id,
        email=email.lower(),
        expires_at=expires_at,
        purpose=purpose,
        volunteer_id=volunteer_id,
    )
    db.add(row); db.flush()
    return raw

def consume_token(db, raw):
    token_hash = _hash_token(raw)
    row = db.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
    if row is None:                                return ConsumeResult.not_found, None
    if row.consumed_at is not None:                return ConsumeResult.used, None
    if row.expires_at < datetime.now(timezone.utc): return ConsumeResult.expired, None
    # Atomic single-use guarantee
    updated = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.id == row.id, MagicLinkToken.consumed_at.is_(None))
        .update({"consumed_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    if updated != 1: return ConsumeResult.used, None
    ...
```

The atomic UPDATE … WHERE consumed_at IS NULL is doing the heavy lifting.
If two requests race (user clicks the link twice in quick succession, or
an email scanner pre-fetches the link), exactly one wins.

### Invite tokens are JWTs — `backend/app/services/invite.py`

This is an interesting hybrid. Admin invites use a JWT (not a magic-link
token) because the invite carries enough context (`user_id`, `purpose`)
that storing state would be redundant — the JWT is self-validating:

```python
INVITE_TOKEN_TTL_DAYS = 7
INVITE_TOKEN_PURPOSE = "invite"

def create_invite_token(user: models.User) -> str:
    payload = {
        "sub": str(user.id),
        "purpose": INVITE_TOKEN_PURPOSE,
        "exp": datetime.now(timezone.utc) + timedelta(days=INVITE_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def verify_invite_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("purpose") != INVITE_TOKEN_PURPOSE:
        raise JWTError("Wrong token purpose")
    return payload.get("sub")
```

Notice the `purpose` claim check. This prevents an access token from
being repurposed as an invite token or vice versa. Always tag tokens
with a purpose; never let a token meant for context A be valid in
context B.

### Frontend storage — `frontend/src/lib/authStorage.js`

```js
const ACCESS_KEY = "uvse_access_token";
const REFRESH_KEY = "uvse_refresh_token";

export function getToken()         { return localStorage.getItem(ACCESS_KEY) || ""; }
export function setToken(token)    { localStorage.setItem(ACCESS_KEY, token); }
export function clearAll()         { clearToken(); clearRefreshToken(); }
```

And the API client (`frontend/src/lib/api.js`) attaches the access token
to every request:

```js
headers: {
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
}
```

`localStorage` storage is a deliberate trade-off — see the pitfalls
section.

## Common pitfalls

### 1. `alg=none`

The 2015 CVE that made JWT famous for the wrong reasons. The original
spec allowed `"alg": "none"`, meaning unsigned tokens. Several libraries
defaulted to accepting it; an attacker could forge any token by setting
the header to `{"alg":"none"}` and supplying an empty signature.

```python
# ❌ Wrong — uses whatever alg the token claims, including "none"
jwt.decode(token, secret)

# ✅ Correct — explicitly allowlist algorithms
jwt.decode(token, secret, algorithms=["HS256"])
```

This codebase passes `algorithms=[settings.jwt_algorithm]` explicitly.
Any code that does not is a CVE waiting to happen.

### 2. Key confusion (HS256 with the RS256 public key)

If your service uses RS256 and exposes the public key (it's public,
that's fine), an attacker can take the public key, claim
`"alg":"HS256"` in the token header, sign with the public key as if it
were an HMAC secret, and submit the token. A naive verifier reads
`alg=HS256` from the header, fetches "the secret" (which is the public
key), and verifies successfully.

Same fix: hardcode the expected algorithm in the verify call. Never
trust the header.

### 3. `localStorage` vs cookies for JWT storage

This is the religious-war question.

**`localStorage`** — accessible from JavaScript. If you have an XSS
vulnerability anywhere on your origin, the attacker reads the token and
sends it home. The mitigations are strict CSP, framework-level XSS
defenses (React's default escaping helps), and short token TTL.

**HttpOnly cookies** — not accessible from JavaScript. Immune to XSS
exfiltration of the token. But cookies are sent on every same-origin
request, so you have a CSRF surface; you need SameSite=Lax/Strict (most
of the way there) plus CSRF tokens for state-changing requests.

This codebase uses `localStorage`. Why this works in practice:

- React's default JSX escaping prevents stored-XSS in user-supplied
  fields (no `dangerouslySetInnerHTML`).
- Access token TTL is short (60 minutes). Even if stolen, the window is
  bounded.
- Refresh tokens rotate on every use; a stolen refresh token gets
  invalidated the next time the real user refreshes.
- The application is internal-ish (UCSB SciTrek staff and volunteers).

In a higher-stakes environment (banking, healthcare PHI), prefer
HttpOnly cookies and pay the CSRF cost.

### 4. Missing `exp` validation

Hand-rolled JWT verification often skips expiration. Don't:

```python
# ❌ Verifies signature but ignores exp
jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})
```

Library defaults are usually correct. If you turn off `verify_exp`,
write a comment explaining why.

### 5. Long-lived access tokens

If you set the access TTL to 7 days "for convenience," you have built
something with the security properties of a session but none of the
revocation. A leaked token is good for a week. Short TTLs + refresh
tokens give you the same UX without the exposure.

### 6. Putting secrets in JWT payload

JWTs are **signed, not encrypted.** Anyone holding the token can read
the payload. Putting an API key, a password reset link, or PII in the
payload is the same as putting it on a billboard.

```json
// ❌ Visible to anyone who exfiltrates the token
{ "sub": "user-123", "stripe_api_key": "sk_live_xxx" }
```

If you need confidentiality, use JWE (JSON Web Encryption) or, more
commonly, just put the data server-side and reference it by ID.

### 7. Missing `purpose` discrimination

This codebase's invite token has `purpose: "invite"` and rejects any
JWT without it. If you skip this check, an attacker who obtains a
legitimate access token can submit it to `POST /auth/set-password` and
claim to be setting a password from an invite. Always tag tokens with
purpose; always verify it on consumption.

### 8. Magic-link tokens leaked via email forwarding / browser history

Magic links land in the user's email inbox, which is then synced to
multiple devices and possibly forwarded. They also end up in browser
history when clicked. Mitigations:

- **Single use** (consumed on first click).
- **Short TTL** (link valid for tens of minutes for re-auth flows; longer
  is acceptable for sign-up confirmation because the token does not grant
  ongoing access).
- **Email-bound and IP-rate-limited** (this codebase does both).
- **No sensitive query params in the redirect target** — the magic link
  redirects to a confirmation page, not a "logged in" landing page with
  more tokens in the URL.

### 9. Clock skew

`exp` is wall-clock-sensitive. If the issuing service and the verifying
service drift by more than a few seconds, you get spurious 401s right
before tokens expire. Standard mitigations: NTP on every host, a
configurable leeway (`jwt.decode(..., leeway=10)`) of 5–30 seconds.

## Interview Q&A

**Q1 (junior). What is a JWT?**
A JSON Web Token. Three base64url-encoded segments joined by dots:
header, payload, signature. The header says what algorithm signed it,
the payload is JSON with claims about the user, and the signature is an
HMAC or RSA signature over the first two segments. The server can
verify the signature without a database lookup, which is what makes
JWTs "stateless."

**Q2 (junior). What's the difference between authentication and
authorization?**
Authentication is "who are you" — proving the identity. Authorization
is "what are you allowed to do" — checking permissions. JWTs typically
carry both: `sub` identifies the user, additional claims like `role` or
`scope` say what the user is allowed to do.

**Q3 (mid). How does a magic-link login differ from password login?**
A password login submits credentials to the server, the server verifies
them, and issues a session/token. A magic-link login does not use a
credential the user remembers; instead the server emails a one-time
URL containing a random token. Clicking the link consumes the token and
issues the real session. The user proves identity by demonstrating
control of their email account.

**Q4 (mid). Why use refresh tokens at all? Why not just longer JWTs?**
Because JWTs can't be revoked. If you make the access token long-lived,
a leaked token is good for the whole lifetime. The refresh pattern
keeps the access token short (so the blast radius of theft is small)
and uses a stateful refresh token (revocable) to mint new access
tokens. You get the scaling benefit of stateless verification on the
hot path and the security benefit of revocation on the rare path.

**Q5 (mid, security). Explain the `alg=none` attack.**
The original JWT spec listed `none` as a valid algorithm meaning
"unsigned." Some libraries trusted the `alg` claim from the token
header to pick the verification algorithm. An attacker could craft a
token with `{"alg":"none"}`, an arbitrary payload, and an empty
signature; the library would see `alg=none`, skip signature checks, and
accept the token. The mitigation is to pass an explicit algorithms
allowlist to the verify call and never let the token dictate which
algorithm to use.

**Q6 (mid, security). Where do you store a JWT on the client?**
Trade-off question. `localStorage` is exposed to any JS running on
your origin — XSS means token theft. HttpOnly cookies are immune to JS
but expose a CSRF surface. The defensive answer: HttpOnly + Secure +
SameSite=Lax cookies for the access token, with CSRF tokens for state
changes. The pragmatic answer (and what this codebase does):
`localStorage` with short access-token TTL, refresh-token rotation,
strict CSP, and a framework like React that escapes by default.

**Q7 (senior). Design an auth system for an event-signup app where
participants don't have accounts but admins do. Walk me through the
choices.**
Participants: magic-link only. Each signup generates a server-side
token (random 32 bytes, hashed at rest, short TTL), emailed as a URL.
Single-use, atomically consumed on click. No JWT. No login. The
"session" is bounded to the click that confirms the signup.

Admins: classic JWT access + opaque refresh. Access token is HS256
with `sub` and `role`, ~60-minute TTL. Refresh token is 48 bytes of
randomness, hashed at rest, rotated on every refresh, ~14-day TTL.
Logout revokes the refresh token immediately; access token expires on
its own within an hour.

Defensive bits: rate-limit magic-link issuance per email and per IP
(Redis counters with a one-hour window), tag invite/reset tokens with
a `purpose` claim and check it on consumption, use `algorithms=["HS256"]`
explicitly on every JWT decode, store tokens as SHA-256 hex in the DB
and never log raw values.

This is the architecture this codebase ships.

**Q8 (senior, security). An attacker steals a refresh token. What
happens?**
With rotation: the attacker uses the stolen refresh token, gets a new
access token + new refresh token, and the old refresh token is invalid.
The next time the legitimate user tries to refresh, they get a 401 and
get logged out — surfacing the compromise. With reuse detection (one
step further), the moment a previously-revoked refresh token is
presented again, ALL of that user's refresh tokens are revoked
defensively, which kicks the attacker out too.

Without rotation: the attacker has indefinite access until the refresh
token expires. The user has no signal anything is wrong.

The defense is to make stolen tokens loud, not silent. Rotation +
reuse detection is the standard pattern.

## Further reading

- RFC 7519 (JWT spec): <https://datatracker.ietf.org/doc/html/rfc7519>
- RFC 6750 (Bearer token usage): <https://datatracker.ietf.org/doc/html/rfc6750>
- jwt.io — paste-and-decode debugger; useful but DO NOT paste production
  tokens
- OWASP JWT cheat sheet: <https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html>
- Auth0's "JWT Handbook" — free PDF, the canonical primer
- "The OAuth 2.0 Authorization Framework" RFC 6749 — context for how
  refresh tokens are supposed to work
- Pragmatic blog post: "Stop using JWT for sessions" by Sven Slootweg —
  the strongest counterargument, worth reading even if you disagree
- `python-jose` source for `jwt.decode` — short and educational
