# backend/app/models.py
import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    Enum,
    Text,
    JSON,
    Index,
    func,
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
    email_confirm = "email_confirm"
    check_in = "check_in"


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


# -------------------------
# User table
# -------------------------


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    # ✅ lock enum name to match Alembic migration
    role = Column(Enum(UserRole, name="userrole"), default=UserRole.participant, nullable=False)

    university_id = Column(String(64), nullable=True)
    notify_email = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Added in Phase 7 for CCPA soft-delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    events = relationship("Event", back_populates="owner")
    signups = relationship("Signup", back_populates="user")
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
    module_slug = Column(String, ForeignKey("module_templates.slug"), nullable=True)
    reminder_1h_enabled = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    slot_id = Column(UUID(as_uuid=True), ForeignKey("slots.id"), nullable=False)

    # ✅ lock enum name to match Alembic migration
    status = Column(
        Enum(SignupStatus, name="signupstatus"),
        default=SignupStatus.confirmed,
        nullable=False,
    )

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reminder_sent = Column(Boolean, nullable=False, default=False, server_default="false")
    reminder_24h_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_1h_sent_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="signups")
    slot = relationship("Slot", back_populates="signups")
    answers = relationship("CustomAnswer", back_populates="signup", cascade="all, delete-orphan")
    sent_notifications = relationship("SentNotification", back_populates="signup", cascade="all, delete-orphan")


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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # ✅ lock enum name to match Alembic migration
    type = Column(Enum(NotificationType, name="notificationtype"), nullable=False)

    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    delivery_method = Column(String(32), nullable=False)  # "email" or "sms"
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notifications")


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
        Enum(PrivacyMode, name="privacymode"),
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
        Enum(MagicLinkPurpose, name="magiclinkpurpose"),
        nullable=False,
        server_default="email_confirm",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    signup = relationship("Signup", backref=backref("magic_link_tokens", passive_deletes=True))

    __table_args__ = (
        Index("ix_magic_link_tokens_email_created_at", "email", "created_at"),
    )


# -------------------------
# Module templates (stub — phase 5 will extend)
# -------------------------


class ModuleTemplate(Base):
    __tablename__ = "module_templates"

    slug = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    prereq_slugs = Column(ARRAY(String), nullable=False, server_default="{}")
    default_capacity = Column(Integer, nullable=False, server_default="20")
    duration_minutes = Column(Integer, nullable=False, server_default="90")
    materials = Column(ARRAY(String), nullable=False, server_default="{}")
    description = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=False, server_default="{}")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


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
        Enum(CsvImportStatus, name="csvimportstatus"),
        default=CsvImportStatus.pending,
        nullable=False,
    )
    result_payload = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    uploader = relationship("User")


# -------------------------
# Prereq overrides (admin audit-trailed)
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


class PrereqOverride(Base):
    __tablename__ = "prereq_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    module_slug = Column(String, ForeignKey("module_templates.slug"), nullable=False)
    reason = Column(String, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(reason) >= 10", name="prereq_overrides_reason_min_len"),
    )
