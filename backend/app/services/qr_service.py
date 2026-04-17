"""Phase 28 — QR check-in service.

Generates PNG QR images that encode the volunteer's existing magic-link
manage URL. Organizers scan the QR at the venue; the decoded URL either
opens the self check-in flow for the volunteer or feeds the decoded
``manage_token`` into the organizer's roster-side scanner which resolves
signup_id via :func:`app.routers.organizer.signup_by_manage_token` and
POSTs the existing ``/signups/{id}/check-in`` endpoint.

Design notes
------------
- Zero new auth surface (QR-04): payload is the existing SIGNUP_MANAGE
  magic-link URL. The raw token is sent once to the volunteer via email;
  when the organizer scans it, they are proving physical possession of
  the QR — no additional grant of privilege beyond the email.
- ``generate_signup_qr`` will issue a fresh SIGNUP_MANAGE token if the
  signup doesn't already have one the service can sign a URL with. This
  lets ``send_waitlist_promote`` (which reuses ``send_confirmation``)
  inherit QR generation without the caller plumbing a raw token through.
- Pure PNG output; the email builder wraps it as an inline CID attachment.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import qrcode

from .. import models
from ..config import settings
from ..magic_link_service import SIGNUP_CONFIRM_TTL_MINUTES, issue_token

logger = logging.getLogger(__name__)

# Default TTL for QR-backing tokens. The check-in QR is stable for the
# lifetime of the signup (per CONTEXT: "no rotation needed"), so we reuse
# the 14-day signup-confirm TTL.
_QR_TOKEN_TTL_MINUTES = SIGNUP_CONFIRM_TTL_MINUTES


def generate_qr_png(payload: str) -> bytes:
    """Render ``payload`` as a PNG-encoded QR code.

    The default box_size + border keep the image comfortably under
    ~4 KB for the manage URL we encode, which keeps inline email
    attachments small.

    Args:
        payload: The string to encode. Typically a URL.

    Returns:
        PNG bytes. Non-empty.
    """
    if not payload:
        raise ValueError("payload must be non-empty")
    qr = qrcode.QRCode(
        version=None,  # auto-fit
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _manage_url(token: str) -> str:
    """Build the manage URL the QR encodes.

    Uses ``settings.frontend_base_url`` (aliased from ``frontend_url``).
    """
    base = (settings.frontend_base_url or settings.frontend_url or "").rstrip(
        "/"
    )
    return f"{base}/manage?manage_token={token}"


def _find_existing_manage_token_hash(
    signup: models.Signup,
) -> Optional[models.MagicLinkToken]:
    """Return a live SIGNUP_CONFIRM / SIGNUP_MANAGE token row for the signup.

    We cannot recover the RAW token from the hash, but the presence of a
    live hash tells us the volunteer already holds one — in that case,
    we still issue a fresh token for the QR because we have no other
    way to produce a clickable URL.
    """
    tokens = getattr(signup, "magic_link_tokens", None) or []
    now = datetime.now(timezone.utc)
    candidates = [
        t
        for t in tokens
        if t.consumed_at is None
        and t.expires_at > now
        and t.purpose
        in (
            models.MagicLinkPurpose.SIGNUP_MANAGE,
            models.MagicLinkPurpose.SIGNUP_CONFIRM,
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: t.expires_at)


def get_or_issue_qr_token(
    db, signup: models.Signup, *, raw_token: str | None = None
) -> str:
    """Return a raw manage token usable in the QR payload.

    Precedence:
      1. ``raw_token`` passed by the caller (e.g. the signup-confirmation
         celery task still holds the original raw token from
         ``issue_token``; it passes it through).
      2. Freshly-issued SIGNUP_MANAGE token — adds a row to
         ``magic_link_tokens``. Caller is responsible for ``db.commit()``.
    """
    if raw_token:
        return raw_token
    # Issue a long-lived manage token. The hash lands in magic_link_tokens
    # so the organizer lookup endpoint can resolve it back to signup_id.
    volunteer = getattr(signup, "volunteer", None)
    email = volunteer.email if volunteer else ""
    return issue_token(
        db,
        signup=signup,
        email=email,
        purpose=models.MagicLinkPurpose.SIGNUP_MANAGE,
        volunteer_id=getattr(volunteer, "id", None),
        ttl_minutes=_QR_TOKEN_TTL_MINUTES,
    )


def generate_signup_qr(
    db,
    signup_id: UUID | str,
    *,
    raw_token: str | None = None,
) -> tuple[bytes, str]:
    """Generate the PNG + URL pair for a signup's check-in QR.

    Returns ``(png_bytes, manage_url)``. Caller attaches the PNG as
    ``cid:qr-{signup_id}`` and embeds ``<img src="cid:qr-{signup_id}">``
    in the HTML body. Plain-text bodies should include ``manage_url``
    as the fallback line.

    When ``raw_token`` is None, a fresh SIGNUP_MANAGE token is issued and
    persisted. The caller owns the db.commit() boundary.
    """
    if isinstance(signup_id, str):
        signup_id = UUID(signup_id)
    signup = (
        db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    )
    if signup is None:
        raise LookupError(f"Signup {signup_id} not found")

    token = get_or_issue_qr_token(db, signup, raw_token=raw_token)
    url = _manage_url(token)
    png = generate_qr_png(url)
    return png, url


__all__ = [
    "generate_qr_png",
    "generate_signup_qr",
    "get_or_issue_qr_token",
]
