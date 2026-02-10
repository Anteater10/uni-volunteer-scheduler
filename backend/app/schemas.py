# backend/app/schemas.py
from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict

from .models import UserRole, SignupStatus, NotificationType, PrivacyMode


# -------------------------
# Pydantic v2 ORM support
# -------------------------
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class SlotCreate(SlotBase):
    pass


class SlotRead(ORMBase, SlotBase):
    id: UUID
    current_count: int


class SlotUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    capacity: Optional[int] = None


class SlotRecurrenceCreate(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int
    frequency: Literal["daily", "weekly"]
    count: int


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


class VolunteerHoursRow(BaseModel):
    user_id: UUID
    name: str
    email: EmailStr
    total_hours: float


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
