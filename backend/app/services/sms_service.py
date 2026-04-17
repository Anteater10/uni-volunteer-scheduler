"""Phase 27 — SMS service (AWS SNS).

Mirrors the shape of ``reminder_service`` but delivers SMS via AWS SNS.
Feature-flagged behind ``settings.sms_enabled`` — when False every path
short-circuits to ``{"status": "skipped_flag_off"}``. Quiet hours reuse
Phase 24's ``reminder_service.is_quiet_hours`` to avoid duplication.

Bodies carry a TCPA-compliant "Reply STOP to opt out." footer and every
template stays under 160 chars (GSM-7 single segment).

The SNS client is created lazily the first time ``send_sms`` runs with
the flag on — unit tests patch ``_get_sns_client`` or the module-level
``sns.publish`` call so there's zero boto3 traffic in CI.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from . import reminder_service

logger = logging.getLogger(__name__)

PT = ZoneInfo("America/Los_Angeles")

# Templates + scheduling constants.
SMS_PRE_2H_WINDOW = timedelta(minutes=15)  # ± around target
SMS_NO_SHOW_OFFSET = timedelta(minutes=30)  # 30 min after slot start
SMS_NO_SHOW_WINDOW = timedelta(minutes=15)

SmsKind = Literal["sms_pre_2h", "sms_no_show"]
SMS_KINDS: Tuple[SmsKind, ...] = ("sms_pre_2h", "sms_no_show")

STOP_FOOTER = "Reply STOP to opt out."
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# ------------------------------------------------------------------
# SNS client — lazily constructed so import doesn't require boto3 at rest.
# ------------------------------------------------------------------

_sns_client = None  # module-level cache — tests can monkeypatch.


def _get_sns_client():  # pragma: no cover — exercised only with flag on
    """Return a cached boto3 SNS client. Created on first call."""
    global _sns_client
    if _sns_client is not None:
        return _sns_client
    import boto3  # local import so module imports cleanly without boto3 in dev

    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
    if settings.aws_secret_access_key:
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    _sns_client = boto3.client("sns", **kwargs)
    return _sns_client


def _reset_client_cache() -> None:
    """Test helper — drop the cached client so tests can re-patch boto3."""
    global _sns_client
    _sns_client = None


# ------------------------------------------------------------------
# Body templates
# ------------------------------------------------------------------


def _fmt_pt_time(dt: datetime) -> str:
    """Format a datetime into a short PT wall-clock string like ``2:30pm``."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    pt = dt.astimezone(PT)
    hour = pt.hour % 12 or 12
    suffix = "am" if pt.hour < 12 else "pm"
    if pt.minute:
        return f"{hour}:{pt.minute:02d}{suffix}"
    return f"{hour}{suffix}"


def format_pre_2h_body(*, event_title: str, venue: str, start_time: datetime) -> str:
    """Pre-event 2h SMS body. <160 chars incl. footer."""
    title = (event_title or "your shift")[:40]
    loc = (venue or "the venue")[:30]
    when = _fmt_pt_time(start_time)
    body = f"SciTrek: {title} at {loc} in 2h ({when}). {STOP_FOOTER}"
    return _ensure_footer(body)


def format_no_show_body(*, first_name: str, event_title: str, start_time: datetime) -> str:
    """No-show nudge body. Keep terse so we stay under 160 chars."""
    name = (first_name or "").split()[0][:20] or "hi"
    title = (event_title or "your shift")[:30]
    when = _fmt_pt_time(start_time)
    body = f"Hi {name}! You missed {title} at {when}. On your way? {STOP_FOOTER}"
    return _ensure_footer(body)


def _ensure_footer(body: str) -> str:
    """Guarantee the STOP footer is at the end of the body."""
    if STOP_FOOTER in body:
        return body
    sep = "" if body.endswith(" ") else " "
    return f"{body}{sep}{STOP_FOOTER}"


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------


def is_valid_e164(phone: str | None) -> bool:
    if not phone:
        return False
    return bool(E164_RE.match(phone.strip()))


# ------------------------------------------------------------------
# send_sms — core transport
# ------------------------------------------------------------------


@dataclass
class SmsResult:
    status: str  # "sent" | "skipped_flag_off" | "failed" | "invalid_phone"
    message_id: Optional[str] = None
    error: Optional[str] = None


def send_sms(to_phone_e164: str, body: str) -> dict:
    """Deliver ``body`` to ``to_phone_e164`` via AWS SNS.

    Return shape: ``{"status": "sent"|"skipped_flag_off"|"failed"|"invalid_phone", ...}``.

    Never raises — callers expect to get a dict and decide what to do.
    """
    if not settings.sms_enabled:
        logger.info("sms_disabled_skipping phone=***")
        return {"status": "skipped_flag_off"}

    if not is_valid_e164(to_phone_e164):
        logger.warning("sms_invalid_phone_skipping")
        return {"status": "invalid_phone"}

    body = _ensure_footer(body or "")

    try:
        client = _get_sns_client()
        resp = client.publish(PhoneNumber=to_phone_e164, Message=body)
        message_id = resp.get("MessageId") if isinstance(resp, dict) else None
        logger.info("sms_sent message_id=%s", message_id)
        return {"status": "sent", "message_id": message_id}
    except Exception as exc:  # noqa: BLE001 — SNS raises a variety of types
        logger.exception("sms_send_failed")
        return {"status": "failed", "error": str(exc)}


# ------------------------------------------------------------------
# should_send_sms — combines flag / opt-in / phone / quiet hours.
# ------------------------------------------------------------------


def should_send_sms(db: Session, signup: models.Signup, *, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Return ``(True, "")`` if the signup is eligible for an SMS right now.

    Otherwise ``(False, reason)`` where reason is one of:
    ``flag_off``, ``no_volunteer``, ``no_phone``, ``opted_out``, ``quiet_hours``.
    """
    if not settings.sms_enabled:
        return (False, "flag_off")
    vol = signup.volunteer if signup else None
    if not vol or not vol.email:
        return (False, "no_volunteer")
    prefs = reminder_service.get_preferences(db, vol.email)
    if not prefs.sms_opt_in:
        return (False, "opted_out")
    phone = prefs.phone_e164 or getattr(vol, "phone_e164", None)
    if not is_valid_e164(phone):
        return (False, "no_phone")
    if reminder_service.is_quiet_hours(now or datetime.now(timezone.utc)):
        return (False, "quiet_hours")
    return (True, "")


# ------------------------------------------------------------------
# Window math (mirrors reminder_service patterns)
# ------------------------------------------------------------------


def is_in_pre_2h_window(slot: models.Slot, now_utc: datetime) -> bool:
    """True if ``now_utc`` is within ±15 min of ``slot.start_time - 2h``."""
    start = slot.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    target = start - timedelta(hours=2)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return abs(now_utc - target) <= SMS_PRE_2H_WINDOW


def is_in_no_show_window(slot: models.Slot, now_utc: datetime) -> bool:
    """True if ``now_utc`` is within ±15 min of ``slot.start_time + 30min``."""
    start = slot.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    target = start + SMS_NO_SHOW_OFFSET
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return abs(now_utc - target) <= SMS_NO_SHOW_WINDOW


# ------------------------------------------------------------------
# Idempotent dispatch helpers
# ------------------------------------------------------------------


def _dedup_insert(db: Session, signup_id, kind: str) -> bool:
    """INSERT ON CONFLICT DO NOTHING — return True if we won the race."""
    stmt = (
        pg_insert(models.SentNotification)
        .values(signup_id=signup_id, kind=kind)
        .on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    )
    result = db.execute(stmt)
    return result.rowcount == 1


def _phone_for(db: Session, signup: models.Signup) -> Optional[str]:
    """Resolve the E.164 phone for a signup (prefs first, volunteer fallback)."""
    vol = signup.volunteer
    if vol is None or not vol.email:
        return None
    prefs = reminder_service.get_preferences(db, vol.email)
    phone = prefs.phone_e164 or getattr(vol, "phone_e164", None)
    return phone if is_valid_e164(phone) else None


def send_and_record(
    db: Session,
    *,
    signup: models.Signup,
    kind: SmsKind,
    body: str,
    actor: Optional[models.User] = None,
) -> dict:
    """Dedup insert + send; log audit on failure.

    Caller is responsible for eligibility checks (use ``should_send_sms``).
    Returns the dict produced by ``send_sms`` augmented with
    ``{"dedup": "inserted"|"already_sent", "kind": kind}``.
    """
    if not _dedup_insert(db, signup.id, kind):
        return {"status": "skipped_duplicate", "dedup": "already_sent", "kind": kind}

    phone = _phone_for(db, signup)
    if not phone:
        return {"status": "invalid_phone", "dedup": "inserted", "kind": kind}

    result = send_sms(phone, body)
    result["dedup"] = "inserted"
    result["kind"] = kind

    if result.get("status") == "failed":
        # Audit the failure so admins can investigate delivery issues.
        from ..deps import log_action  # avoid circular import at module load

        log_action(
            db,
            actor,
            "sms_send_failed",
            "Signup",
            str(signup.id),
            extra={
                "kind": kind,
                "error": result.get("error"),
            },
        )
    return result


# ------------------------------------------------------------------
# Preview for admin endpoint
# ------------------------------------------------------------------


def list_upcoming_sms(db: Session, days: int = 7) -> list[dict]:
    """Return rows describing pre_2h + no_show sends in the next ``days``."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    signups = (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Signup.status.in_(
                [models.SignupStatus.confirmed, models.SignupStatus.pending]
            ),
            models.Slot.start_time >= now - timedelta(hours=2),
            models.Slot.start_time <= horizon,
        )
        .all()
    )

    rows: list[dict] = []
    for s in signups:
        slot = s.slot
        event = slot.event if slot else None
        vol = s.volunteer
        if not slot or not event or not vol:
            continue
        pre_2h_target = slot.start_time - timedelta(hours=2)
        no_show_target = slot.start_time + SMS_NO_SHOW_OFFSET
        prefs = (
            db.query(models.VolunteerPreference)
            .filter(models.VolunteerPreference.volunteer_email == vol.email)
            .first()
        )
        opted_in = bool(prefs and prefs.sms_opt_in)
        phone = (prefs.phone_e164 if prefs else None) or getattr(vol, "phone_e164", None)

        for kind, target in (
            ("sms_pre_2h", pre_2h_target),
            ("sms_no_show", no_show_target),
        ):
            if target < now - timedelta(hours=1) or target > horizon:
                continue
            already = (
                db.query(models.SentNotification)
                .filter(
                    models.SentNotification.signup_id == s.id,
                    models.SentNotification.kind == kind,
                )
                .first()
                is not None
            )
            rows.append(
                {
                    "signup_id": s.id,
                    "volunteer_email": vol.email,
                    "volunteer_name": f"{vol.first_name} {vol.last_name}".strip(),
                    "event_id": event.id,
                    "event_title": event.title,
                    "slot_id": slot.id,
                    "slot_start_time": slot.start_time,
                    "kind": kind,
                    "scheduled_for": target,
                    "already_sent": already,
                    "opted_in": opted_in,
                    "phone_on_file": bool(phone),
                }
            )

    rows.sort(key=lambda r: r["scheduled_for"])
    return rows
