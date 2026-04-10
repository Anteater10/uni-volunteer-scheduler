# backend/app/schemas.py
from datetime import datetime, timezone
from typing import Optional, List, Literal, Dict, Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator

from .models import UserRole, SignupStatus, NotificationType, PrivacyMode


# -------------------------
# Pydantic v2 ORM support
# -------------------------
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# =========================
# AUTH / TOKEN
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[UserRole] = None


# =========================
# USER SCHEMAS
# =========================
class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.participant
    university_id: Optional[str] = None
    notify_email: bool = True


class UserCreate(UserBase):
    password: str


# Important: ORMBase first is fine here because UserBase is plain BaseModel
# (and ORMBase has model_config for from_attributes)
class UserRead(ORMBase, UserBase):
    id: UUID
    created_at: datetime


class UserUpdate(BaseModel):
    name: Optional[str] = None
    university_id: Optional[str] = None
    notify_email: Optional[bool] = None


class UserAdminUpdate(BaseModel):
    name: Optional[str] = None
    university_id: Optional[str] = None
    notify_email: Optional[bool] = None
    role: Optional[UserRole] = None


# =========================
# SLOT SCHEMAS
# =========================
class SlotBase(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_slot_datetimes(cls, value: datetime) -> datetime:
        return _to_utc_naive(value)


class SlotCreate(SlotBase):
    pass


class SlotRead(ORMBase, SlotBase):
    id: UUID
    current_count: int


class SlotUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    capacity: Optional[int] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_slot_update_datetimes(cls, value: datetime | None) -> datetime | None:
        return _to_utc_naive(value)


class SlotRecurrenceCreate(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int
    frequency: Literal["daily", "weekly"]
    count: int

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_recurrence_datetimes(cls, value: datetime) -> datetime:
        return _to_utc_naive(value)


# =========================
# EVENT SCHEMAS
# =========================
class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    visibility: str = "public"
    branding_id: Optional[str] = None
    start_date: datetime
    end_date: datetime
    max_signups_per_user: Optional[int] = None
    signup_open_at: Optional[datetime] = None
    signup_close_at: Optional[datetime] = None

    @field_validator("start_date", "end_date", "signup_open_at", "signup_close_at")
    @classmethod
    def normalize_event_datetimes(cls, value: datetime | None) -> datetime | None:
        return _to_utc_naive(value)


class EventCreate(EventBase):
    slots: Optional[List[SlotCreate]] = None


class EventRead(ORMBase, EventBase):
    id: UUID
    owner_id: UUID
    slots: List[SlotRead] = []


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    visibility: Optional[str] = None
    branding_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_signups_per_user: Optional[int] = None
    signup_open_at: Optional[datetime] = None
    signup_close_at: Optional[datetime] = None

    @field_validator("start_date", "end_date", "signup_open_at", "signup_close_at")
    @classmethod
    def normalize_event_update_datetimes(cls, value: datetime | None) -> datetime | None:
        return _to_utc_naive(value)


# =========================
# CUSTOM QUESTIONS / ANSWERS
# =========================
class CustomQuestionBase(BaseModel):
    prompt: str
    field_type: Literal["text", "textarea", "select", "checkbox", "radio"]
    required: bool = False
    options: Optional[List[str]] = None
    sort_order: int = 0


class CustomQuestionCreate(CustomQuestionBase):
    pass


class CustomQuestionRead(ORMBase, CustomQuestionBase):
    id: UUID
    event_id: UUID


class CustomQuestionUpdate(BaseModel):
    prompt: Optional[str] = None
    field_type: Optional[Literal["text", "textarea", "select", "checkbox", "radio"]] = None
    required: Optional[bool] = None
    options: Optional[List[str]] = None
    sort_order: Optional[int] = None


class SignupAnswerCreate(BaseModel):
    question_id: UUID
    value: str


class SignupAnswerRead(ORMBase):
    id: UUID
    question_id: UUID
    value: str


# =========================
# SIGNUP SCHEMAS
# =========================
class SignupBase(BaseModel):
    slot_id: UUID


class SignupCreate(SignupBase):
    answers: Optional[List[SignupAnswerCreate]] = None


class SignupRead(ORMBase):
    id: UUID
    user_id: UUID
    slot_id: UUID
    status: SignupStatus
    timestamp: datetime
    answers: List[SignupAnswerRead] = []
    event_title: Optional[str] = None
    event_location: Optional[str] = None
    slot_start_time: Optional[datetime] = None
    slot_end_time: Optional[datetime] = None
    timezone_label: Optional[str] = None
    waitlist_position: Optional[int] = None


class SignupMoveRequest(BaseModel):
    target_slot_id: UUID


# =========================
# NOTIFICATION SCHEMAS
# =========================
class NotificationRead(ORMBase):
    id: UUID
    user_id: UUID
    type: NotificationType
    subject: str | None = None
    body: str
    delivery_method: str
    delivered_at: datetime | None
    created_at: datetime


# =========================
# REFRESH TOKEN SCHEMAS
# =========================
class RefreshTokenRead(ORMBase):
    id: UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


# =========================
# AUDIT LOG SCHEMAS
# =========================
class AuditLogRead(ORMBase):
    id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    extra: Dict[str, Any] | None
    timestamp: datetime


# =========================
# ADMIN ANALYTICS
# =========================
class AdminSummary(BaseModel):
    total_users: int
    total_events: int
    total_slots: int
    total_signups: int
    signups_last_7d: int


class EventAnalytics(BaseModel):
    event_id: UUID
    title: str
    total_slots: int
    total_capacity: int
    confirmed_signups: int
    waitlisted_signups: int


class PaginatedAuditLogs(BaseModel):
    items: List[AuditLogRead]
    total: int
    page: int
    page_size: int
    pages: int


class VolunteerHoursRow(BaseModel):
    user_id: UUID
    name: str
    hours: float
    events: int


class AttendanceRateRow(BaseModel):
    event_id: UUID
    name: str
    confirmed: int
    attended: int
    no_show: int
    rate: float


class NoShowRateRow(BaseModel):
    user_id: UUID
    name: str
    rate: float
    count: int


class CcpaDeleteRequest(BaseModel):
    reason: str = Field(..., min_length=5)


# =========================
# ORGANIZER BROADCAST
# =========================
class EventNotifyRequest(BaseModel):
    subject: str
    body: str
    include_waitlisted: bool = False


# =========================
# PRIVACY / SETTINGS
# =========================
class SiteSettingsRead(ORMBase):
    default_privacy_mode: PrivacyMode
    allowed_email_domain: Optional[str] = None


class SiteSettingsUpdate(BaseModel):
    default_privacy_mode: PrivacyMode
    allowed_email_domain: Optional[str] = None


# =========================
# PORTALS
# =========================
class PortalBase(BaseModel):
    name: str
    description: Optional[str] = None
    visibility: str = "public"


class PortalCreate(PortalBase):
    pass


class PortalRead(ORMBase, PortalBase):
    id: UUID
    slug: str


# ✅ FIX: PortalRead already includes ORMBase, so DON'T inherit ORMBase again.
class PortalDetail(PortalRead):
    events: List[EventRead] = []


# =========================
# ROSTER / CHECK-IN (Phase 3)
# =========================
class RosterRow(BaseModel):
    signup_id: UUID
    student_name: str
    status: SignupStatus
    slot_time: datetime
    checked_in_at: datetime | None = None


class RosterResponse(BaseModel):
    event_id: UUID
    event_name: str
    venue_code: str | None = None
    total: int
    checked_in_count: int
    rows: List[RosterRow]


class SelfCheckInRequest(BaseModel):
    signup_id: UUID
    venue_code: str


class ResolveEventRequest(BaseModel):
    attended: List[UUID] = []
    no_show: List[UUID] = []


# Phase 08 (D-05): Override table dropped in migration 0009.
# Stub schemas kept here to prevent router import failure until Phase 12 cleans up admin.py.
class PrereqOverrideCreate(BaseModel):
    module_slug: str
    reason: str


class PrereqOverrideRead(ORMBase):
    id: UUID
    user_id: UUID
    module_slug: str
    reason: str
    created_by: UUID
    created_at: datetime
    revoked_at: Optional[datetime] = None

# =========================
# MODULE TIMELINE (Phase 4)
# =========================
class ModuleTimelineItem(BaseModel):
    slug: str
    name: str
    status: str  # locked | unlocked | completed
    override_active: bool
    last_activity: Optional[datetime] = None


# =========================
# MODULE TEMPLATE SCHEMAS (Phase 5)
# =========================
class ModuleTemplateBase(BaseModel):
    name: str
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: int = 20
    duration_minutes: int = 90
    materials: List[str] = []
    description: Optional[str] = None
    metadata: dict = {}


class ModuleTemplateCreate(ModuleTemplateBase):
    slug: str


class ModuleTemplateUpdate(BaseModel):
    name: Optional[str] = None
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: Optional[int] = None
    duration_minutes: Optional[int] = None
    materials: Optional[List[str]] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None


class ModuleTemplateRead(ORMBase):
    slug: str
    name: str
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: int = 20
    duration_minutes: int = 90
    materials: List[str] = []
    description: Optional[str] = None
    metadata: dict = Field(default={}, validation_alias="metadata_")
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# =========================
# CSV IMPORT SCHEMAS (Phase 5)
# =========================
# =========================
# SENT NOTIFICATION SCHEMAS (Phase 6)
# =========================
class SentNotificationRead(ORMBase):
    id: UUID
    signup_id: UUID
    kind: str
    sent_at: datetime
    provider_id: Optional[str] = None


class CsvImportRead(ORMBase):
    id: UUID
    uploaded_by: UUID
    filename: str
    status: str
    result_payload: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
