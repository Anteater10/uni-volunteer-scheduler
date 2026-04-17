# backend/app/models.py
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    Enum as SqlEnum,
    Text,
    JSON,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import backref, relationship

from .database import Base


# -------------------------
# Enums
# -------------------------


class UserRole(str, enum.Enum):
    admin = "admin"
    organizer = "organizer"
    participant = "participant"


class SignupStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    checked_in = "checked_in"
    attended = "attended"
    no_show = "no_show"
    waitlisted = "waitlisted"
    cancelled = "cancelled"


class MagicLinkPurpose(str, enum.Enum):
    email_confirm = "email_confirm"   # legacy, kept for Postgres compatibility
    check_in = "check_in"             # legacy
    SIGNUP_CONFIRM = "signup_confirm"  # NEW Phase 08
    SIGNUP_MANAGE = "signup_manage"    # NEW Phase 08


class CsvImportStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    committed = "committed"
    failed = "failed"


class NotificationType(str, enum.Enum):
    email = "email"
    sms = "sms"


class PrivacyMode(str, enum.Enum):
    full = "full"
    initials = "initials"
    anonymous = "anonymous"


class Quarter(str, enum.Enum):
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"


class SlotType(str, enum.Enum):
    ORIENTATION = "orientation"
    PERIOD = "period"


class ModuleType(str, enum.Enum):
    seminar = "seminar"
    orientation = "orientation"
    module = "module"


class OrientationCreditSource(str, enum.Enum):
    """Phase 21: how a volunteer earned orientation credit.

    - attendance: derived from a Signup with slot_type=ORIENTATION and
      status in (attended, checked_in). Implicit.
    - grant: explicit row written by an organizer/admin via the
      orientation_credits table.
    """
    attendance = "attendance"
    grant = "grant"


# -------------------------
# Volunteer table (Phase 08 — v1.1 account-less pivot)
# -------------------------


class Volunteer(Base):
    __tablename__ = "volunteers"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=text("gen_random_uuid()"))
    email = Column(String(255), nullable=False, unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_e164 = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False,
                        onupdate=func.now())

    signups = relationship("Signup", back_populates="volunteer")


# -------------------------
# User table
# -------------------------


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    # Phase 16 Plan 01: nullable so magic-link-only invites can create users
    hashed_password = Column(String(255), nullable=True)

    # ✅ lock enum name to match Alembic migration
    role = Column(
        SqlEnum(UserRole, values_callable=lambda x: [e.value for e in x], name="userrole"),
        default=UserRole.participant,
        nullable=False,
    )

    university_id = Column(String(64), nullable=True)
    notify_email = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Added in Phase 7 for CCPA soft-delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)
    # Phase 16 Plan 01: admin Users page surface
    is_active = Column(Boolean, nullable=False, server_default=text("true"), default=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    events = relationship("Event", back_populates="owner")
    # signups relationship removed in Phase 08 — Signup now keyed to Volunteer, not User
    notifications = relationship("Notification", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor")


# -------------------------
# Event table
# -------------------------


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    visibility = Column(String(32), default="public")
    branding_id = Column(String(64), nullable=True)

    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    # V3: event-level signup controls
    max_signups_per_user = Column(Integer, nullable=True)
    signup_open_at = Column(DateTime(timezone=True), nullable=True)
    signup_close_at = Column(DateTime(timezone=True), nullable=True)
    venue_code = Column(String(4), nullable=True)
    # Phase 08: module_slug FK to module_templates dropped (D-07); column stays as plain String
    module_slug = Column(String, nullable=True)
    reminder_1h_enabled = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Phase 08: new structured columns (R08-02)
    quarter = Column(
        SqlEnum(Quarter, values_callable=lambda x: [e.value for e in x], name="quarter"),
        nullable=True,
    )
    year = Column(Integer, nullable=True)
    week_number = Column(Integer, nullable=True)
    school = Column(String(255), nullable=True)

    # Phase 22: per-event form schema override. NULL means "use template default".
    form_schema = Column(JSONB, nullable=True, server_default=None)

    # Relationships
    owner = relationship("User", back_populates="events")
    slots = relationship("Slot", back_populates="event", cascade="all, delete-orphan")
    questions = relationship("CustomQuestion", back_populates="event", cascade="all, delete-orphan")
    portal_links = relationship("PortalEvent", back_populates="event", cascade="all, delete-orphan")


# -------------------------
# Slot table (timeslots)
# -------------------------


class Slot(Base):
    __tablename__ = "slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    capacity = Column(Integer, nullable=False, default=1)
    current_count = Column(Integer, nullable=False, default=0)

    # Phase 08: new columns (R08-03, D-02)
    slot_type = Column(
        SqlEnum(SlotType, values_callable=lambda x: [e.value for e in x], name="slottype"),
        nullable=False,
    )
    date = Column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    location = Column(String(255), nullable=True)

    __table_args__ = (Index("ix_slots_start_time", "start_time"),)

    # Relationships
    event = relationship("Event", back_populates="slots")
    signups = relationship("Signup", back_populates="slot", cascade="all, delete-orphan")


# -------------------------
# Signup table
# -------------------------


class Signup(Base):
    __tablename__ = "signups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Phase 08: user_id replaced with volunteer_id (D-01, D-06)
    volunteer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("volunteers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    slot_id = Column(UUID(as_uuid=True), ForeignKey("slots.id"), nullable=False)

    # ✅ lock enum name to match Alembic migration
    status = Column(
        SqlEnum(SignupStatus, values_callable=lambda x: [e.value for e in x], name="signupstatus"),
        default=SignupStatus.confirmed,
        nullable=False,
    )

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reminder_sent = Column(Boolean, nullable=False, default=False, server_default="false")
    reminder_24h_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_1h_sent_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("volunteer_id", "slot_id", name="uq_signups_volunteer_id_slot_id"),
    )

    # Relationships
    volunteer = relationship("Volunteer", back_populates="signups")
    slot = relationship("Slot", back_populates="signups")
    answers = relationship("CustomAnswer", back_populates="signup", cascade="all, delete-orphan")
    sent_notifications = relationship("SentNotification", back_populates="signup", cascade="all, delete-orphan")
    # Phase 22: dynamic form responses (replaces CustomAnswer going forward).
    responses = relationship(
        "SignupResponse",
        back_populates="signup",
        cascade="all, delete-orphan",
    )


# -------------------------
# Custom questions / answers
# -------------------------


class CustomQuestion(Base):
    """
    Per-event custom questions shown on the signup form.
    """

    __tablename__ = "custom_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)

    prompt = Column(Text, nullable=False)
    field_type = Column(String(32), nullable=False)  # text, textarea, select, checkbox, radio
    required = Column(Boolean, default=False)
    options = Column(JSON, nullable=True)  # list of choices, etc.
    sort_order = Column(Integer, default=0)

    event = relationship("Event", back_populates="questions")
    answers = relationship("CustomAnswer", back_populates="question", cascade="all, delete-orphan")


class CustomAnswer(Base):
    """
    A single user's answer to a custom question as part of a signup.
    """

    __tablename__ = "custom_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signup_id = Column(UUID(as_uuid=True), ForeignKey("signups.id"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("custom_questions.id"), nullable=False)

    value = Column(Text, nullable=False)

    signup = relationship("Signup", back_populates="answers")
    question = relationship("CustomQuestion", back_populates="answers")


# -------------------------
# Notification table
# -------------------------


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # CHECK constraint enforces exactly one of user_id/volunteer_id set (migration 0010)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    volunteer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("volunteers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ✅ lock enum name to match Alembic migration
    type = Column(
        SqlEnum(NotificationType, values_callable=lambda x: [e.value for e in x], name="notificationtype"),
        nullable=False,
    )

    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    delivery_method = Column(String(32), nullable=False)  # "email" or "sms"
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND volunteer_id IS NULL) OR (user_id IS NULL AND volunteer_id IS NOT NULL)",
            name="ck_notifications_recipient_xor",
        ),
    )

    user = relationship("User", back_populates="notifications")
    volunteer = relationship("Volunteer")


# -------------------------
# Refresh token table
# -------------------------


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # SHA-256 hex digest, never the raw token
    token_hash = Column(String(512), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


# -------------------------
# Audit log table
# -------------------------


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(128), nullable=False)
    entity_type = Column(String(128), nullable=False)
    entity_id = Column(String(128), nullable=True)

    extra = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    actor = relationship("User", back_populates="audit_logs")


# -------------------------
# Site-wide settings
# -------------------------


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, default=1)

    # ✅ lock enum name to match Alembic migration
    default_privacy_mode = Column(
        SqlEnum(PrivacyMode, values_callable=lambda x: [e.value for e in x], name="privacymode"),
        default=PrivacyMode.full,
    )

    allowed_email_domain = Column(String(255), nullable=True)


# -------------------------
# Portals (tabbed / grouped signups)
# -------------------------


class Portal(Base):
    """
    A named collection of events, e.g. "SciTrek Volunteers" or "Orientation Week".
    """

    __tablename__ = "portals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    visibility = Column(String(32), default="public")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    events = relationship("PortalEvent", back_populates="portal", cascade="all, delete-orphan")


class PortalEvent(Base):
    """
    Join table linking Portals to Events (many-to-many).
    """

    __tablename__ = "portal_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portal_id = Column(UUID(as_uuid=True), ForeignKey("portals.id"), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False)

    portal = relationship("Portal", back_populates="events")
    event = relationship("Event", back_populates="portal_links")


# -------------------------
# Magic link tokens
# -------------------------


class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    signup_id = Column(UUID(as_uuid=True), ForeignKey("signups.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    purpose = Column(
        SqlEnum(MagicLinkPurpose, values_callable=lambda x: [e.value for e in x], name="magiclinkpurpose"),
        nullable=False,
        server_default="email_confirm",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    # Phase 08: new volunteer_id FK (D-03)
    volunteer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("volunteers.id", ondelete="CASCADE"),
        nullable=True,
    )
    volunteer = relationship("Volunteer")

    signup = relationship("Signup", backref=backref("magic_link_tokens", passive_deletes=True))

    __table_args__ = (
        Index("ix_magic_link_tokens_email_created_at", "email", "created_at"),
    )


# -------------------------
# Module templates
# -------------------------


class ModuleTemplate(Base):
    __tablename__ = "module_templates"

    slug = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    # Phase 08: prereq_slugs column dropped (D-05)
    default_capacity = Column(Integer, nullable=False, server_default="20")
    duration_minutes = Column(Integer, nullable=False, server_default="90")
    type = Column(
        SqlEnum(ModuleType, values_callable=lambda x: [e.value for e in x], name="moduletype", create_type=False),
        nullable=False,
        server_default="module",
    )
    session_count = Column(Integer, nullable=False, server_default="1")
    materials = Column(ARRAY(String), nullable=False, server_default="{}")
    description = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    # Phase 21: optional grouping key so CRISPR-intro + CRISPR-advanced can share
    # an orientation family without merging slugs. Nullable; defaults to `slug` on
    # backfill — resolver prefers family_key when set.
    family_key = Column(String, nullable=True)
    # Phase 22: default form schema for every event created from this template.
    # JSONB list of field descriptors; see backend/app/services/form_schema_service.py.
    default_form_schema = Column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# -------------------------
# Orientation credits (Phase 21)
# -------------------------


class OrientationCredit(Base):
    """Explicit grant/revoke trail of orientation credit by (volunteer_email, family_key).

    Signup-based attendance is still the primary source; this table covers cases
    where an organizer/admin vouches for a volunteer outside the normal flow
    (walk-ins, historical records, corrections). See
    backend/app/services/orientation_service.py for the unified lookup.
    """

    __tablename__ = "orientation_credits"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    volunteer_email = Column(String(255), nullable=False, index=True)
    family_key = Column(String, nullable=False)
    source = Column(
        SqlEnum(
            OrientationCreditSource,
            values_callable=lambda x: [e.value for e in x],
            name="orientationcreditsource",
            create_type=False,
        ),
        nullable=False,
    )
    granted_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_orientation_credits_email_family",
            "volunteer_email",
            "family_key",
        ),
    )

    granted_by = relationship("User")


# -------------------------
# CSV Import tracking
# -------------------------


class CsvImport(Base):
    __tablename__ = "csv_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename = Column(String(512), nullable=False)
    raw_csv_hash = Column(String(64), nullable=False)
    status = Column(
        SqlEnum(CsvImportStatus, values_callable=lambda x: [e.value for e in x], name="csvimportstatus"),
        default=CsvImportStatus.pending,
        nullable=False,
    )
    result_payload = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    uploader = relationship("User")


# -------------------------
# Sent Notifications (dedup table for exactly-once email delivery)
# -------------------------


class SentNotification(Base):
    """Dedup table for exactly-once email delivery.

    The UNIQUE(signup_id, kind) constraint is the dedup key: Celery tasks
    INSERT ... ON CONFLICT DO NOTHING before calling the email provider.
    If the insert returns 0 rows, the email was already sent.
    """
    __tablename__ = "sent_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signup_id = Column(UUID(as_uuid=True), ForeignKey("signups.id"), nullable=False)
    kind = Column(String(32), nullable=False)  # magic_link|reminder_24h|reminder_1h|cancellation|reschedule
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    provider_id = Column(String(255), nullable=True)  # Resend message id

    __table_args__ = (
        Index("uq_sent_notifications_signup_kind", "signup_id", "kind", unique=True),
    )

    signup = relationship("Signup", back_populates="sent_notifications")

# -------------------------
# Signup responses (Phase 22 — custom form fields)
# -------------------------


class SignupResponse(Base):
    """One per (signup, field_id). Free-text in ``value_text``; structured
    answers (multi-select, arrays) in ``value_json``. The effective schema
    lives on the event (``Event.form_schema``) or template
    (``ModuleTemplate.default_form_schema``); responses are snapshotted by
    ``field_id`` so schema edits don't retroactively break old signups.
    """

    __tablename__ = "signup_responses"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    signup_id = Column(
        UUID(as_uuid=True),
        ForeignKey("signups.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_id = Column(String(128), nullable=False)
    value_text = Column(Text, nullable=True)
    value_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_signup_responses_signup_field",
            "signup_id",
            "field_id",
            unique=True,
        ),
    )

    signup = relationship("Signup", back_populates="responses")


# Phase 08: PrereqOverride model REMOVED (D-05).
# The legacy table was dropped in migration 0009. Router/service cleanup
# is Phase 12 scope, Phase 16 Plan 01 finished the admin-shell retirement.


# -------------------------
# Volunteer preferences (Phase 24)
# -------------------------


class VolunteerPreference(Base):
    """Per-volunteer notification preferences, keyed by email (stable identity).

    Mirrors the orientation_credits pattern — no FK to volunteers because a
    consent record must outlive volunteer deletions and predate the first
    signup. ``phone_e164`` is stored here so Phase 27 (SMS) has a persistent
    home without touching the volunteers row.
    """

    __tablename__ = "volunteer_preferences"

    volunteer_email = Column(String(255), primary_key=True, nullable=False)
    email_reminders_enabled = Column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    sms_opt_in = Column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    phone_e164 = Column(String(20), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
