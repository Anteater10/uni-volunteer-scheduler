"""Shared credential-state fingerprint for reset/invite tokens (Task 6).

Both the password-reset and invite flows mint a stateless JWT and previously
verified it by signature + expiry alone, which let a captured link be
replayed as many times as it wanted until it expired. Rather than add a
consumed-token table (a schema change), each token is bound at mint time to
the user's *current* `hashed_password` value via a `fp` claim. Verifying a
token then means: signature/purpose/expiry check (unchanged) PLUS "does
this fp still match the user's hashed_password right now?" Any successful
password set changes `hashed_password` (bcrypt salts every hash uniquely,
even for the same plaintext), so:

- replaying the very token just used to set the password fails (the hash it
  was minted against no longer matches);
- any other outstanding reset/invite token minted before that change also
  fails, regardless of which flow performed the change.

Design note: the fingerprint is NOT a plain `sha256(hashed_password)`. It is
HMAC-SHA256 keyed with the server's JWT secret. A bare digest is a fixed,
un-keyed function of the hash — computable and checkable by anyone who
merely captured a token, and in principle a target for offline correlation
against the bcrypt hash if it ever leaked. Keying it with a secret only the
server holds means the fp claim can only be produced or verified
server-side, cannot be used to learn anything about the underlying password
hash, and can't be forged without the same secret that already signs the
enclosing JWT.
"""
from __future__ import annotations

import hashlib
import hmac

from jose import jwt

from .. import models
from ..config import settings

# Stable sentinel for invited users who have no password yet. Setting the
# first password moves hashed_password from None to a real bcrypt hash,
# which changes the fingerprint and invalidates outstanding invite tokens
# exactly like any other credential-state change.
_NO_PASSWORD_SENTINEL = ""


def credential_fingerprint(user: models.User) -> str:
    """HMAC-SHA256(jwt_secret, hashed_password or sentinel), hex-encoded."""
    material = user.hashed_password or _NO_PASSWORD_SENTINEL
    return hmac.new(
        settings.jwt_secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def token_fingerprint_matches(token: str, user: models.User) -> bool:
    """True if `token`'s `fp` claim matches `user`'s current credential state.

    Call this only after the token's signature/purpose/expiry have already
    been validated (e.g. via verify_reset_token/verify_invite_token) and the
    user row has been loaded — it re-decodes the token (still signature- and
    expiry-checked) purely to compare the fp claim, so it works uniformly
    for both reset and invite tokens.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    claimed = payload.get("fp") or ""
    return hmac.compare_digest(claimed, credential_fingerprint(user))
