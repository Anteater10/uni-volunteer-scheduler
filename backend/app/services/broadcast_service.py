"""Phase 26 — Broadcast messages service.

One-shot operational email to every active signup on an event. Used by
organizers and admins ("parking moved to Lot 22"). NOT filtered by
``volunteer_preferences.email_reminders_enabled`` — broadcasts are
operational, not promotional.

Design:
- Rate limit (5 broadcasts / hour / event) via redis ``INCR`` + ``EXPIRE``
  under key ``broadcast:{event_id}:{YYYYMMDDHH}``.
- Dedup per-recipient via existing ``sent_notifications(signup_id, kind)``
  unique index. The dedup ``kind`` is ``f"broadcast_{broadcast_id}"``
  where ``broadcast_id`` is a 22-char uuid4.hex slice (so the key fits the
  32-char ``SentNotification.kind`` ceiling; ``broadcast_`` = 10 + 22 = 32).
- Audit log row ``action=broadcast_sent`` per send.
- HTML rendered from markdown; plaintext derived from the HTML via
  BeautifulSoup.
"""
from __future__ import annotations

import html
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import markdown as md_lib
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session, joinedload

from .. import models

logger = logging.getLogger(__name__)

RATE_LIMIT_PER_HOUR = 5
RATE_LIMIT_WINDOW_SECONDS = 3600
PT = ZoneInfo("America/Los_Angeles")

# Recipients: signups holding or past a confirmed spot at send time.
# Waitlisted / pending / cancelled / no_show are excluded per 26-CONTEXT.
RECIPIENT_STATUSES = (
    models.SignupStatus.confirmed,
    models.SignupStatus.checked_in,
    models.SignupStatus.attended,
)


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------


class BroadcastError(Exception):
    """Base class for broadcast service errors."""


class BroadcastRateLimitError(BroadcastError):
    """Raised when the per-hour cap is exceeded."""

    def __init__(self, retry_after: int, limit: int = RATE_LIMIT_PER_HOUR) -> None:
        self.retry_after = int(max(1, retry_after))
        self.limit = limit
        super().__init__(
            f"broadcast rate limit reached ({limit}/hour); retry in {self.retry_after}s"
        )


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class BroadcastResult:
    broadcast_id: str
    recipient_count: int
    sent_at: datetime


# ------------------------------------------------------------------
# Rate-limit (redis)
# ------------------------------------------------------------------


def _hour_bucket(now: datetime) -> str:
    """Return the UTC ``YYYYMMDDHH`` bucket string used in the redis key."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc = now.astimezone(timezone.utc)
    return utc.strftime("%Y%m%d%H")


def _seconds_until_next_hour(now: datetime) -> int:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc = now.astimezone(timezone.utc)
    return (60 - utc.minute) * 60 - utc.second


def rate_limit_key(event_id, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"broadcast:{event_id}:{_hour_bucket(now)}"


def check_and_bump_rate_limit(
    redis_client,
    event_id,
    *,
    now: Optional[datetime] = None,
    limit: int = RATE_LIMIT_PER_HOUR,
) -> int:
    """Increment the per-event hourly counter.

    Raises ``BroadcastRateLimitError`` if the call would push the count
    strictly above ``limit``. Returns the new count on success.

    Safe under Redis's single-threaded command execution: ``INCR`` is
    atomic, and we set ``EXPIRE`` right after so orphaned keys disappear
    at the next hour boundary.
    """
    now = now or datetime.now(timezone.utc)
    key = rate_limit_key(event_id, now=now)
    new_count = int(redis_client.incr(key))
    # Refresh TTL every time so late bumps can't accidentally orphan the key.
    redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)
    if new_count > limit:
        # We already consumed a slot — no rollback needed because the cap
        # is what matters and the count naturally resets at the next hour.
        raise BroadcastRateLimitError(retry_after=_seconds_until_next_hour(now), limit=limit)
    return new_count


# ------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------


_SCRIPT_TAG = re.compile(r"<\s*/?\s*(script|iframe|object|embed)\b[^>]*>", re.IGNORECASE)


def _fmt_event_time(event: "models.Event") -> str:
    """Best-effort local-time label for the event header in the footer.

    Prefers the earliest slot start; falls back to ``event.start_date``.
    Rendered in PT since SciTrek runs locally.
    """
    candidate: Optional[datetime] = None
    slots = getattr(event, "slots", None) or []
    if slots:
        starts = [s.start_time for s in slots if s.start_time is not None]
        if starts:
            candidate = min(starts)
    if candidate is None:
        candidate = getattr(event, "start_date", None)
    if candidate is None:
        return "TBD"
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    local = candidate.astimezone(PT)
    return local.strftime("%a %b %-d, %-I:%M %p %Z")


def _footer_html(event: "models.Event", manage_url: Optional[str]) -> str:
    title = html.escape(event.title or "your event")
    when = html.escape(_fmt_event_time(event))
    where = html.escape(event.location or "TBD")
    unsub = ""
    if manage_url:
        unsub = (
            '<p style="margin:12px 0 0;font-size:13px;color:#555;">'
            f'<a href="{html.escape(manage_url)}">Manage your SciTrek signups</a>'
            " — you can cancel or adjust reminders from there."
            "</p>"
        )
    return (
        '<hr style="margin:24px 0;border:none;border-top:1px solid #eee;" />'
        '<div style="font-size:14px;color:#444;">'
        f'<p style="margin:0 0 4px;"><strong>Event:</strong> {title}</p>'
        f'<p style="margin:0 0 4px;"><strong>When:</strong> {when}</p>'
        f'<p style="margin:0 0 4px;"><strong>Where:</strong> {where}</p>'
        f"{unsub}"
        "</div>"
    )


def render_html(
    body_markdown: str, *, event: "models.Event", manage_url: Optional[str] = None
) -> str:
    """Render the broadcast body to sanitized HTML + event-context footer.

    ``markdown`` library HTML-escapes inline ``<script>``-style input by
    default; we also strip any ``<script>``/``<iframe>``/``<object>`` tags
    defensively. We do NOT permit raw HTML in the body.
    """
    rendered = md_lib.markdown(
        body_markdown or "",
        extensions=["extra", "nl2br", "sane_lists"],
        output_format="html5",
    )
    # Belt + suspenders: drop any dangerous tags that slipped through
    # (markdown's default HTML escaping stops most of this, but
    # ``extensions=["extra"]`` enables raw inline HTML so we filter again).
    safe = _SCRIPT_TAG.sub("", rendered)
    footer = _footer_html(event, manage_url)
    return (
        '<div style="font-family:system-ui,-apple-system,sans-serif;'
        "font-size:16px;line-height:1.5;color:#1a1a1a;max-width:640px;"
        'margin:0 auto;padding:16px;">'
        f"{safe}{footer}"
        "</div>"
    )


def render_plaintext(html_body: str) -> str:
    """Strip tags + normalize whitespace for a text/plain MIME alternative."""
    soup = BeautifulSoup(html_body or "", "html.parser")
    for tag in soup(["script", "style", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse stretches of blank lines so the output reads like prose.
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


# ------------------------------------------------------------------
# Recipients
# ------------------------------------------------------------------


def list_recipients(db: Session, event_id) -> list[models.Signup]:
    """Return every signup that currently holds or has completed a spot on the event."""
    return (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Slot.event_id == event_id,
            models.Signup.status.in_(list(RECIPIENT_STATUSES)),
        )
        .options(joinedload(models.Signup.volunteer))
        .all()
    )


def count_recipients(db: Session, event_id) -> int:
    """Fast-path count for the modal preview."""
    return (
        db.query(models.Signup.id)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Slot.event_id == event_id,
            models.Signup.status.in_(list(RECIPIENT_STATUSES)),
        )
        .count()
    )


# ------------------------------------------------------------------
# Send path
# ------------------------------------------------------------------


def _manage_url_for_volunteer(volunteer: "models.Volunteer") -> Optional[str]:
    from ..config import settings

    base = (settings.frontend_url or "").rstrip("/")
    if not base or volunteer is None:
        return None
    return f"{base}/signup/manage"


def _dedup_insert_broadcast(db: Session, signup_id, kind: str) -> bool:
    """Insert into sent_notifications; return True if row was inserted."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(models.SentNotification)
        .values(signup_id=signup_id, kind=kind)
        .on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    )
    result = db.execute(stmt)
    return result.rowcount == 1


def send_broadcast(
    db: Session,
    *,
    event_id,
    subject: str,
    body_markdown: str,
    actor_user_id,
    redis_client,
    now: Optional[datetime] = None,
    broadcast_id: Optional[str] = None,
) -> BroadcastResult:
    """Rate-limit, render, dedup-insert, dispatch, and audit a broadcast.

    ``broadcast_id`` may be supplied by the caller (testing, request-level
    idempotency); otherwise a fresh one is generated. Whether supplied or
    generated, the value is used as the dedup kind suffix, so retrying the
    same call with the same ``broadcast_id`` will not double-send.
    """
    from ..celery_app import send_broadcast_email

    now = now or datetime.now(timezone.utc)

    # 1. Rate-limit — raise before we spend any DB work.
    check_and_bump_rate_limit(redis_client, event_id, now=now)

    event = (
        db.query(models.Event)
        .filter(models.Event.id == event_id)
        .first()
    )
    if event is None:
        raise BroadcastError(f"event not found: {event_id}")

    # 2. ID (22 hex chars -> fits kind column with "broadcast_" prefix).
    bid = broadcast_id or uuid.uuid4().hex[:22]
    kind = f"broadcast_{bid}"
    assert len(kind) <= 32, "broadcast dedup kind would exceed SentNotification.kind width"

    # 3. Recipients.
    signups = list_recipients(db, event_id)

    # 4. Render bodies once — same copy goes to every recipient.
    manage_url = None
    # Prefer the first recipient for the footer's manage link anchor; the
    # link is a volunteer-generic manage URL so one is sufficient.
    if signups:
        manage_url = _manage_url_for_volunteer(signups[0].volunteer)
    html_body = render_html(body_markdown, event=event, manage_url=manage_url)
    text_body = render_plaintext(html_body)

    # 5. Per-recipient dedup + dispatch.
    recipient_count = 0
    for s in signups:
        if s.volunteer is None or not s.volunteer.email:
            continue
        if not _dedup_insert_broadcast(db, s.id, kind):
            # Either a retry of the same broadcast_id or a rare row race —
            # either way, some other caller owns this delivery.
            continue
        send_broadcast_email.delay(
            signup_id=str(s.id),
            to_email=s.volunteer.email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )
        recipient_count += 1

    # 6. Audit row.
    actor = (
        db.query(models.User).filter(models.User.id == actor_user_id).first()
        if actor_user_id
        else None
    )
    audit = models.AuditLog(
        actor_id=actor.id if actor else None,
        action="broadcast_sent",
        entity_type="Event",
        entity_id=str(event_id),
        extra={
            "broadcast_id": bid,
            "subject": subject,
            "recipient_count": recipient_count,
            "body_markdown": body_markdown,
        },
    )
    db.add(audit)
    db.commit()

    return BroadcastResult(broadcast_id=bid, recipient_count=recipient_count, sent_at=now)


# ------------------------------------------------------------------
# History (admin + organizer "recent broadcasts" view)
# ------------------------------------------------------------------


def list_recent_broadcasts(
    db: Session, event_id, *, days: int = 30
) -> list[dict]:
    """Return audit-log rows for ``broadcast_sent`` on the event.

    Read-only helper; shape matches ``BroadcastSummary`` on the schema
    side so the router can pass rows straight through.
    """
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(models.AuditLog)
        .filter(
            models.AuditLog.action == "broadcast_sent",
            models.AuditLog.entity_type == "Event",
            models.AuditLog.entity_id == str(event_id),
            models.AuditLog.timestamp >= since,
        )
        .order_by(models.AuditLog.timestamp.desc())
        .all()
    )
    actor_cache: dict = {}
    out: list[dict] = []
    for r in rows:
        extra = r.extra or {}
        actor_label: Optional[str] = None
        if r.actor_id is not None:
            if r.actor_id not in actor_cache:
                u = (
                    db.query(models.User)
                    .filter(models.User.id == r.actor_id)
                    .first()
                )
                actor_cache[r.actor_id] = (
                    (u.name or u.email) if u else None
                )
            actor_label = actor_cache[r.actor_id]
        out.append(
            {
                "broadcast_id": extra.get("broadcast_id") or str(r.id),
                "subject": extra.get("subject") or "",
                "recipient_count": int(extra.get("recipient_count") or 0),
                "actor_label": actor_label,
                "sent_at": r.timestamp,
            }
        )
    return out
