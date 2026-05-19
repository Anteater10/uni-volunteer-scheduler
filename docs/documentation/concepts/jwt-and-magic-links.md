# JWT and Magic Links — Reference

## TL;DR

This codebase runs two authentication mechanisms side by side. **JWT access
tokens + opaque refresh tokens** handle admin/organizer login: short-lived
signed JSON tokens for stateless verification on every request, plus
server-stored refresh tokens that rotate on use. **Magic-link tokens**
handle the account-less participant flow: server-stored 32-byte random
tokens delivered via email, single-use, hashed at rest, with TTL and rate
limiting. Both stacks are deliberately stateful where revocation matters
(refresh tokens, magic links) and stateless where speed matters (access
token verification).

## Token shape

### Access token (JWT, HS256)

Header:

```json
{ "alg": "HS256", "typ": "JWT" }
```

Payload (this codebase):

```json
{
  "sub": "71f62afc-193d-4b25-a0de-4efc1392767b",
  "role": "admin",
  "exp": 1715724800
}
```

Serialized form (three base64url segments, joined by dots):

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJzdWIiOiI3MWY2MmFmYy0xOTNkLTRiMjUtYTBkZS00ZWZjMTM5Mjc2N2IiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3MTU3MjQ4MDB9
.
<32-byte HMAC-SHA256 signature, base64url-encoded>
```

Standard claims supported by the library (`python-jose`):

| Claim | Meaning | Used here? |
|---|---|---|
| `sub` | subject (user ID) | yes |
| `iss` | issuer | no |
| `aud` | audience | no |
| `exp` | expiration (UNIX seconds) | yes |
| `iat` | issued-at | implicit via library |
| `nbf` | not-before | no |
| `jti` | unique token ID | no |

Private claims used by this codebase:

| Claim | Where | Meaning |
|---|---|---|
| `role` | access tokens | `admin` / `organizer` / `participant` |
| `purpose` | invite tokens | `"invite"` (rejects re-use as access token) |

### Refresh token (opaque)

Not a JWT. A 48-byte URL-safe random string, hashed and stored:

```
raw:  uG_uF9...43-character-url-safe-string...
hash: SHA-256(raw)  → 64 hex chars stored in refresh_tokens.token_hash
```

Database row shape (`models.RefreshToken`):

```python
RefreshToken(
    id: UUID,
    user_id: UUID,
    token_hash: str,        # sha256 hex of the raw token
    expires_at: datetime,   # now + 14 days by default
    created_at: datetime,
    revoked_at: datetime | None,  # null while live
)
```

### Magic-link token (opaque, stateful)

```python
raw = secrets.token_urlsafe(32)  # 32 bytes of randomness, ~43 chars
hash = SHA-256(raw)
```

Database row shape (`models.MagicLinkToken`):

```python
MagicLinkToken(
    id: UUID,
    token_hash: str,                 # sha256 hex
    signup_id: UUID,                 # which signup this confirms
    volunteer_id: UUID | None,       # optional, enables batch confirm
    email: str,                      # lowercased
    purpose: MagicLinkPurpose,       # signup_confirm | reauth | ...
    expires_at: datetime,
    consumed_at: datetime | None,    # null while unused
    created_at: datetime,
)
```

## Mental model

Three orthogonal questions to ask of any token:

1. **Stateful or stateless?** Stateful tokens have a server-side row; you
   can revoke. Stateless tokens are self-validating against a key; you
   can't revoke until they expire. JWTs are stateless; refresh tokens and
   magic-link tokens are stateful.
2. **Bearer or proof-of-possession?** Bearer means "whoever holds the
   token is the user." Everything in this codebase is bearer. Proof-of-
   possession (DPoP, mTLS-bound tokens) requires the holder to prove they
   own a private key; outside the scope here.
3. **How is it revoked?** Stateless: wait for `exp`. Stateful: delete or
   mark `revoked_at`. Magic-link: `consumed_at` flips on first use; the
   atomic UPDATE-WHERE-NULL is the revocation primitive.

The matrix for this codebase:

| Token | Type | Lifetime | Revocation | Storage |
|---|---|---|---|---|
| Access | JWT, stateless | 60 min | wait for exp | client memory + localStorage |
| Refresh | opaque, stateful | 14 days | DELETE row | DB, hashed |
| Magic-link | opaque, stateful | 20 min – 14 days | consumed_at flip | DB, hashed |
| Invite | JWT, stateless | 7 days | wait for exp | email only |

Note the invite tokens are JWTs (stateless), which is unusual. The
reason: they carry a `purpose: "invite"` claim and the `sub` user is
already in the DB; the JWT acts as a portable, self-validating capability
without needing a row.

## Usage in this codebase

### JWT helpers — `backend/app/deps.py`

```python
def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expires_minutes
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        role = payload.get("role")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user
```

Settings (`backend/app/config.py`):

```python
jwt_secret: str                                # required, env var
jwt_algorithm: str = "HS256"
access_token_expires_minutes: int = 60
refresh_token_expires_days: int = 14
```

### Login + refresh — `backend/app/routers/auth.py`

`POST /auth/token` — password login, returns access + refresh.

```python
access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
raw_refresh = _issue_refresh_token(db, user)
user.last_login_at = datetime.now(timezone.utc)
db.commit()
return {"access_token": access_token, "token_type": "bearer", "refresh_token": raw_refresh}
```

`POST /auth/refresh` — rotation enforced.

```python
@router.post("/refresh", response_model=schemas.Token)
def refresh_token(payload: RefreshRequest, db: Session = ...):
    user = _consume_refresh_token(db, payload.refresh_token)  # deletes the row
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_raw_refresh = _issue_refresh_token(db, user)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer", "refresh_token": new_raw_refresh}
```

`POST /auth/logout` — revokes the refresh token, leaves access to expire.

```python
@router.post("/logout")
def logout(payload: RefreshRequest, db: Session = ..., current_user = Depends(get_current_user)):
    _revoke_refresh_token(db, payload.refresh_token)
    db.commit()
    return {"detail": "Logged out"}
```

### Invite tokens — `backend/app/services/invite.py`

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

The `purpose` check is what prevents an access token from being submitted
to `POST /auth/set-password`. Any JWT consumer outside the access-token
path SHOULD check `purpose`.

### Magic links — `backend/app/magic_link_service.py`

Issuance:

```python
def issue_token(db, signup, email, *, purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
                volunteer_id=None, ttl_minutes=None) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    ttl = ttl_minutes if ttl_minutes is not None else settings.magic_link_ttl_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    row = MagicLinkToken(
        token_hash=token_hash, signup_id=signup.id,
        email=email.lower(), expires_at=expires_at,
        purpose=purpose, volunteer_id=volunteer_id,
    )
    db.add(row); db.flush()
    return raw
```

Atomic single-use consumption:

```python
def consume_token(db, raw):
    token_hash = _hash_token(raw)
    row = db.query(MagicLinkToken).filter_by(token_hash=token_hash).first()
    if row is None:                                 return ConsumeResult.not_found, None
    if row.consumed_at is not None:                 return ConsumeResult.used, None
    if row.expires_at < datetime.now(timezone.utc): return ConsumeResult.expired, None
    updated = (
        db.query(MagicLinkToken)
        .filter(MagicLinkToken.id == row.id, MagicLinkToken.consumed_at.is_(None))
        .update({"consumed_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    if updated != 1: return ConsumeResult.used, None
    ...
```

Rate limiting (Redis, per-email + per-IP, one-hour window):

```python
def check_rate_limit(redis_client, email, ip):
    email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
    hour = int(time.time() // 3600)
    pipe = redis_client.pipeline()
    pipe.incr(f"magic:email:{email_hash}:{hour}"); pipe.expire(..., 3600)
    pipe.incr(f"magic:ip:{ip}:{hour}");            pipe.expire(..., 3600)
    email_count, _, ip_count, _ = pipe.execute()
    return (email_count <= settings.magic_link_max_per_email_per_hour
            and ip_count    <= settings.magic_link_max_per_ip_per_hour)
```

Endpoint (`backend/app/routers/magic.py`):

```python
@router.get("/{token}")
def consume_magic_link(token: str, db: Session = Depends(get_db)):
    result, signup = consume_token(db, token)
    if result == ConsumeResult.ok:
        db.commit()
        return RedirectResponse(f"{frontend_base}/signup/confirmed?event={event_id}", 302)
    reason = {ConsumeResult.expired: "expired", ConsumeResult.used: "used",
              ConsumeResult.not_found: "not_found"}[result]
    return RedirectResponse(f"{frontend_base}/signup/confirm-failed?reason={reason}", 302)
```

### Frontend storage — `frontend/src/lib/authStorage.js`

```js
const ACCESS_KEY = "uvse_access_token";
const REFRESH_KEY = "uvse_refresh_token";

export function getToken()       { return localStorage.getItem(ACCESS_KEY) || ""; }
export function setToken(token)  { localStorage.setItem(ACCESS_KEY, token); }
export function clearAll()       { clearToken(); clearRefreshToken(); }
```

Attached to requests by `frontend/src/lib/api.js`:

```js
headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }
```

## Operational concerns

### Secret management

The HS256 secret (`settings.jwt_secret`) is the entire trust anchor of
the JWT system. Operational rules:

- **Never check it into source control.** Provided via environment
  variable, set in `.env` (gitignored) for dev, set in deployment
  config for prod.
- **Rotate periodically.** Rotation is painful with HS256 because every
  outstanding token must be re-issued; in practice, the migration
  path is to support `algorithms=[old, new]` during a transition
  window. This codebase has not exercised that path yet.
- **Length: 256 bits minimum** for HS256 (32 random bytes from
  `secrets.token_bytes(32)`, base64-encoded to ~44 chars).

### Token revocation

| Token | Revocation behavior |
|---|---|
| Access (JWT) | None. Expires within 60 min. Compromised tokens are valid until exp. |
| Refresh | DELETE row in `refresh_tokens`. Immediate. Triggered by `/auth/logout` and by rotation on every `/auth/refresh`. |
| Magic-link | `consumed_at` flips on first successful consumption. Atomic. Or wait for `expires_at`. |
| Invite | None. Expires after 7 days. Compromised invites are valid until exp. Mitigation: short TTL. |

There is no global access-token revocation list. For a higher-stakes
deployment you would add a `jti` claim per access token plus a Redis
set of revoked `jti`s checked on every request — this gives you
revocation at the cost of one Redis GET per request, recovering most
of the stateful pattern.

### Clock skew

`exp` is compared against the verifier's wall clock. If issuer and
verifier are on different hosts, they must stay synchronized (NTP).
A 5–30 second leeway argument to `jwt.decode` is standard if you see
spurious 401s right at token expiration.

### Token rotation policy

Refresh tokens rotate on every use. Implementation: `_consume_refresh_token`
deletes the old row before issuing the new one, inside the same
transaction. If the user's browser dies mid-refresh, the worst case is
they get logged out and have to log in again — acceptable.

A more advanced policy (not implemented): **reuse detection.** If a
refresh token that was already consumed appears again, presume the
session is compromised and revoke ALL refresh tokens for that user. The
attacker gets booted; the legitimate user gets booted; both are alerted
to re-authenticate. This is the OAuth 2.1 recommended pattern.

### Rate limits

Per-IP + per-path rate limiting on auth endpoints via Redis:

- `/auth/token` — 30 req / 60 sec / IP
- `/auth/set-password` — 20 req / 60 sec / IP
- `/auth/magic/resend` — per-email-hash and per-IP, one-hour windows,
  configurable via `magic_link_max_per_email_per_hour` and
  `magic_link_max_per_ip_per_hour`

Implemented in `backend/app/deps.py::rate_limit` (general per-IP) and
`magic_link_service.check_rate_limit` (per-email-hash + per-IP).

### Audit logging

Auth-relevant events emit `AuditLog` rows: `user_login`, `user_logout`,
`token_refresh`, `sso_login`, `sso_register`, `user_set_password`. These
are written inside the same transaction as the auth operation so
rollback discards both consistently.

### XSS exposure

Access tokens live in `localStorage`. XSS at any same-origin endpoint
exfiltrates them. Defensive layers:

1. React's default JSX escaping (no `dangerouslySetInnerHTML` in this
   codebase as of v1.2-prod).
2. Short access-token TTL caps the window.
3. CSP headers on the frontend (deployment-level concern, not
   application code).

For a deployment with stricter requirements (PHI, payments), move
access tokens to HttpOnly + Secure + SameSite=Lax cookies and add
CSRF protection.

### SSO interop

`/auth/sso/login` and `/auth/sso/callback` (Authlib OIDC) mint the
same access + refresh token pair after a successful OIDC dance. The
backend acts as the JWT issuer for the application even when identity
came from an external IdP, which keeps the rest of the system simple
(one token format, one verify path).

## Glossary

- **JWT (JSON Web Token)** — RFC 7519. A signed JSON object encoded as
  three base64url segments joined by dots.
- **HS256** — HMAC-SHA-256. Symmetric JWT signing; one shared secret
  signs and verifies.
- **RS256** — RSA-SHA-256. Asymmetric JWT signing; private key signs,
  public key verifies. Not used here.
- **Claim** — A key in a JWT payload. Standard claims (`sub`, `exp`,
  `iat`) are defined in RFC 7519; private claims (`role`, `purpose`)
  are application-specific.
- **`sub`** — Subject. The user (or principal) the token identifies.
- **`exp`** — Expiration claim. UNIX seconds. Past-due tokens fail
  verification.
- **Stateless authentication** — Server validates a token using a key
  it already has; no per-request DB lookup. JWT-style.
- **Stateful authentication** — Token is an opaque ID looked up in a
  server-side store. Sessions, refresh tokens, magic-link tokens.
- **Bearer token** — Possession of the token is sufficient proof.
  Anyone who has the token can impersonate the user.
- **Refresh token** — Long-lived credential used to mint new access
  tokens without re-authenticating.
- **Rotation** — Issuing a new refresh token on every use and
  invalidating the old one. Limits the lifetime of a stolen token.
- **Reuse detection** — Treating a re-presented (already-consumed)
  refresh token as evidence of compromise; revokes all of the user's
  refresh tokens.
- **Magic link** — A single-use URL containing a random token, sent to
  the user via email. Clicking confirms identity.
- **`alg=none` attack** — Forging a token by claiming the unsigned
  algorithm. Mitigated by passing an explicit algorithms allowlist on
  every decode call.
- **Key confusion attack** — Forging an HS256 token using an RS256
  public key as the HMAC secret, against a verifier that trusts the
  token's `alg` header. Same mitigation as above.
- **JWE (JSON Web Encryption)** — Encrypted variant of JWT. Use when
  the payload must be confidential, not just authentic.
- **`jti`** — JWT ID claim. A unique identifier per token; the building
  block for revocation lists.
- **OIDC (OpenID Connect)** — Identity layer on top of OAuth 2.0. The
  SSO endpoints in this codebase use OIDC via Authlib.
