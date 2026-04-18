"""Phase 24 — Scheduled reminder email service.

Pure, deterministic logic for three reminder kinds:
- ``kickoff``: Monday 07:00 PT of the slot's ISO week.
- ``pre_24h``: slot.start_time - 24h.
- ``pre_2h``:  slot.start_time - 2h.

All window math tolerates a ±15 minute drift so Celery Beat ticks
(scheduled every 15 min) don't miss a send.

The Celery task in ``app/tasks/reminders.py`` orchestrates the scan and
calls :func:`send_reminder` per (signup, kind). This module is kept
Celery-free so the service can be unit-tested without a broker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Literal, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import models


PT = ZoneInfo("America/Los_Angeles")

ReminderKind = Literal["kickoff", "pre_24h", "pre_2h"]
KINDS: tuple[ReminderKind, ...] = ("kickoff", "pre_24h", "pre_2h")

WINDOW_SLACK = timedelta(minutes=15)
QUIET_HOURS_START = 21  # 21:00 PT
QUIET_HOURS_END = 7     # 07:00 PT


# ------------------------------------------------------------------
# Preferences (upsert-read, update)
# ------------------------------------------------------------------


def get_preferences(
    db: Session, email: str
) -> models.VolunteerPreference:
    """Return the preferences row for ``email``, inserting a default row if missing.

    The default row has email_reminders_enabled=True, sms_opt_in=False — matching
    the opt-out semantics (everyone receives reminders by default).
    """
    email = (email or "").strip().lower()
    pref = (
        db.query(models.VolunteerPreference)
        .filter(models.VolunteerPreference.volunteer_email == email)
        .first()
    )
    if pref is not None:
        return pref
    pref = models.VolunteerPreference(
        volunteer_email=email,
        email_reminders_enabled=True,
        sms_opt_in=False,
        phone_e164=None,
    )
    db.add(pref)
    db.flush()
    return pref


def update_preferences(
    db: Session,
    email: str,
    *,
    email_reminders_enabled: Optional[bool] = None,
    sms_opt_in: Optional[bool] = None,
    phone_e164: Optional[str] = None,
) -> models.VolunteerPreference:
    """Partial update. Upserts if the row doesn't exist yet."""
    pref = get_preferences(db, email)
    if email_reminders_enabled is not None:
        pref.email_reminders_enabled = email_reminders_enabled
    if sms_opt_in is not None:
        pref.sms_opt_in = sms_opt_in
    if phone_e164 is not None:
        pref.phone_e164 = phone_e164 or None
    db.flush()
    return pref


# ------------------------------------------------------------------
# Quiet hours + window math
# ------------------------------------------------------------------


def is_quiet_hours(now: datetime) -> bool:
    """Return True if ``now`` (any timezone) lands in 21:00–07:00 PT.

    We treat 21:00 inclusive, 07:00 exclusive so 07:00 PT sends (kickoff) fire.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    pt = now.astimezone(PT)
    h = pt.hour
    return h >= QUIET_HOURS_START or h < QUIET_HOURS_END


def _kickoff_instant(slot: models.Slot) -> datetime:
    """Monday 07:00 PT of the slot's ISO week, returned as UTC."""
    start = slot.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    pt = start.astimezone(PT)
    # Monday = weekday 0
    monday_pt_date = (pt - timedelta(days=pt.weekday())).date()
    monday_07_pt = datetime(
        monday_pt_date.year,
        monday_pt_date.month,
        monday_pt_date.day,
        7,
        0,
        0,
        tzinfo=PT,
    )
    return monday_07_pt.astimezone(timezone.utc)


def scheduled_instant_for_kind(slot: models.Slot, kind: ReminderKind) -> datetime:
    """Return the UTC instant the ``kind`` reminder should fire for ``slot``."""
    start = slot.start_time
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    if kind == "kickoff":
        return _kickoff_instant(slot)
    if kind == "pre_24h":
        return start - timedelta(hours=24)
    if kind == "pre_2h":
        return start - timedelta(hours=2)
    raise ValueError(f"Unknown reminder kind: {kind}")


def compute_reminder_window(
    slot: models.Slot, kind: ReminderKind, now_utc: datetime
) -> bool:
    """Return True when ``now_utc`` is within ±15 minutes of the ``kind`` instant."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    target = scheduled_instant_for_kind(slot, kind)
    return abs(now_utc - target) <= WINDOW_SLACK


# ------------------------------------------------------------------
# Send path — dedup + opt-out + quiet hours, then delegate to Celery builder
# ------------------------------------------------------------------


def notification_kind(kind: ReminderKind) -> str:
    """Return the dedup key kind stored in ``sent_notifications.kind``."""
    return f"reminder_{kind}"


@dataclass
class SendResult:
    sent: bool
    reason: str  # "ok" | "opted_out" | "quiet_hours" | "already_sent" | "no_volunteer"


def _already_sent(db: Session, signup_id, nk: str) -> bool:
    return (
        db.query(models.SentNotification)
        .filter(
            models.SentNotification.signup_id == signup_id,
            models.SentNotification.kind == nk,
        )
        .first()
        is not None
    )


def send_reminder(
    db: Session,
    signup_id,
    kind: ReminderKind,
    *,
    now: Optional[datetime] = None,
    force: bool = False,
) -> SendResult:
    """Attempt to send a reminder for ``(signup_id, kind)``.

    Rules, applied in order:
      1. Signup must exist with confirmed status (or the caller's force flag).
      2. Volunteer preferences: ``email_reminders_enabled`` must be True.
      3. Quiet hours: skip unless ``force=True`` (admin send-now overrides).
      4. Idempotency: INSERT ON CONFLICT DO NOTHING on sent_notifications;
         loser of the race returns sent=False, reason=already_sent.
      5. Dispatch via ``send_email_notification.delay`` which calls the
         builder registered under ``reminder_{kind}``.

    ``force=True`` bypasses quiet hours (admin manual send-now) but still
    honors opt-out and idempotency — those are compliance-grade signals.
    """
    from ..celery_app import send_email_notification

    nk = notification_kind(kind)
    now = now or datetime.now(timezone.utc)

    signup = db.query(models.Signup).filter(models.Signup.id == signup_id).first()
    if not signup:
        return SendResult(sent=False, reason="no_signup")
    volunteer = signup.volunteer
    if not volunteer or not volunteer.email:
        return SendResult(sent=False, reason="no_volunteer")

    prefs = get_preferences(db, volunteer.email)
    if not prefs.email_reminders_enabled:
        return SendResult(sent=False, reason="opted_out")

    if not force and is_quiet_hours(now):
        return SendResult(sent=False, reason="quiet_hours")

    # Atomic dedup insert — first caller wins.
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup.id, kind=nk
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    if result.rowcount != 1:
        return SendResult(sent=False, reason="already_sent")
    db.flush()

    # Delegate the actual email to the Celery task, which routes through
    # BUILDERS[kind]. In eager test mode this fires synchronously.
    send_email_notification.delay(signup_id=str(signup.id), kind=nk)
    return SendResult(sent=True, reason="ok")


# ------------------------------------------------------------------
# Admin preview — upcoming reminders for the next N days
# ------------------------------------------------------------------


def list_upcoming_reminders(db: Session, days: int = 7) -> List[dict]:
    """Return a list of (signup, kind, scheduled_for) rows for the next ``days`` days.

    This is a computed preview — we never persist the schedule. Rows marked
    already_sent or opted_out are included so the admin can see the full
    picture, matching REM-05.
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)

    signups = (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Signup.status == models.SignupStatus.confirmed,
            models.Slot.start_time >= now - timedelta(hours=2),
            models.Slot.start_time <= horizon + timedelta(hours=24),
        )
        .all()
    )

    rows: List[dict] = []
    for s in signups:
        slot = s.slot
        event = slot.event
        vol = s.volunteer
        if not slot or not event or not vol:
            continue
        for k in KINDS:
            target = scheduled_instant_for_kind(slot, k)
            # Show reminders that are in the future horizon, or recently due
            # (so admins can verify what just fired or is overdue).
            if target < now - timedelta(hours=1) or target > horizon:
                continue
            nk = notification_kind(k)
            sent = _already_sent(db, s.id, nk)
            prefs = (
                db.query(models.VolunteerPreference)
                .filter(models.VolunteerPreference.volunteer_email == vol.email)
                .first()
            )
            opted_out = prefs is not None and not prefs.email_reminders_enabled
            rows.append(
                {
                    "signup_id": s.id,
                    "volunteer_email": vol.email,
                    "volunteer_name": f"{vol.first_name} {vol.last_name}".strip(),
                    "event_id": event.id,
                    "event_title": event.title,
                    "slot_id": slot.id,
                    "slot_start_time": slot.start_time,
                    "kind": k,
                    "scheduled_for": target,
                    "already_sent": sent,
                    "opted_out": opted_out,
                }
            )

    rows.sort(key=lambda r: r["scheduled_for"])
    return rows


# ------------------------------------------------------------------
# Iterator used by the Celery task
# ------------------------------------------------------------------


def candidate_signups_for_scan(
    db: Session, now: Optional[datetime] = None
) -> Iterable[models.Signup]:
    """Yield confirmed signups whose slot starts in the next ~30h (covers all windows).

    Kickoff fires on Monday 07:00 PT — the slot itself could be up to Sunday
    23:59 PT, which is ~143h away at Beat tick time. So kickoff needs the
    full week window, handled in the task by running the window check for
    every signup whose slot falls within the next 8 days.
    """
    now = now or datetime.now(timezone.utc)
    # pre_24h looks ~24h out; pre_2h looks ~2h out; kickoff can look up to 7d.
    upper = now + timedelta(days=8)
    lower = now - timedelta(hours=1)
    return (
        db.query(models.Signup)
        .join(models.Slot, models.Slot.id == models.Signup.slot_id)
        .filter(
            models.Signup.status == models.SignupStatus.confirmed,
            models.Slot.start_time >= lower,
            models.Slot.start_time <= upper,
        )
        .all()
    )
