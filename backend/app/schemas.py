# backend/app/schemas.py
import datetime as _dt
from datetime import date as DateType, datetime, timezone
from typing import Optional, List, Literal, Dict, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .models import UserRole, SignupStatus, NotificationType, PrivacyMode, Quarter, SlotType


# -------------------------
# Pydantic v2 ORM support
# -------------------------
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _to_utc_aware(dt: datetime | None) -> datetime | None:
    """Serialization direction: keep the UTC offset on the wire.

    Every datetime column is timestamptz. Read schemas must emit an offset
    ("+00:00"/"Z") or `new Date()` in the browser reads the value as local
    time and shifts every displayed clock time.
    """
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    # Phase 16 Plan 02: Users page surface
    is_active: bool = True
    last_login_at: Optional[datetime] = None
    # Override: read responses accept any string email, including reserved
    # test TLDs like .test/.example (RFC 2606) that EmailStr rejects.
    email: str


class UserInvite(BaseModel):
    """Admin-only invite payload (D-11, D-41). Name + Email + Role only."""
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    role: Literal["admin", "organizer"]


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
    slot_type: SlotType = SlotType.PERIOD
    date: Optional[DateType] = None
    location: Optional[str] = None


class SlotRead(ORMBase, SlotBase):
    id: UUID
    current_count: int
    slot_type: Optional[SlotType] = None
    date: Optional[DateType] = None
    location: Optional[str] = None
    # Shifts design: a period slot is a *session* inside a shift, and its
    # capacity/current_count above are inert — the shift owns the counter.
    # NULL shift_id means an orientation slot, which is still bookable alone.
    shift_id: Optional[UUID] = None
    name: Optional[str] = None
    sort_order: int = 0

    # Same method name as SlotBase's validator → replaces it, so Read
    # payloads keep the UTC offset instead of stripping it.
    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_slot_datetimes(cls, value: datetime) -> datetime:
        return _to_utc_aware(value)


class SlotUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    capacity: Optional[int] = None
    slot_type: Optional[SlotType] = None
    date: Optional[DateType] = None
    location: Optional[str] = None

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
    slot_type: SlotType = SlotType.PERIOD
    location: Optional[str] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_recurrence_datetimes(cls, value: datetime) -> datetime:
        return _to_utc_naive(value)


# =========================
# SHIFT SCHEMAS
# =========================
# A shift is the bookable unit: volunteers commit to all of its sessions or
# none of them. Sessions are Slot rows with slot_type='period'; the shift
# carries the single capacity and the single waitlist.
class ShiftSessionBase(BaseModel):
    start_time: datetime
    end_time: datetime
    name: Optional[str] = None
    date: Optional[DateType] = None
    location: Optional[str] = None
    sort_order: int = 0

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_session_datetimes(cls, value: datetime) -> datetime:
        return _to_utc_naive(value)


class ShiftSessionCreate(ShiftSessionBase):
    pass


class ShiftSessionUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    name: Optional[str] = None
    date: Optional[DateType] = None
    location: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_session_update_datetimes(cls, value: datetime | None) -> datetime | None:
        return _to_utc_naive(value)


class ShiftCreate(BaseModel):
    name: str = Field(min_length=1)
    capacity: int = Field(gt=0)
    sort_order: int = 0
    # A shift with no sessions is not bookable and cannot be checked in to,
    # so it is rejected rather than stored as an empty shell.
    sessions: List[ShiftSessionCreate] = Field(min_length=1)


class ShiftUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    capacity: Optional[int] = Field(default=None, gt=0)
    sort_order: Optional[int] = None


class ShiftRead(ORMBase):
    id: UUID
    event_id: UUID
    name: str
    sort_order: int
    capacity: int
    current_count: int
    sessions: List[SlotRead] = []


class SessionAttendanceRead(ORMBase):
    """One "did they show up" record. Absent from a roster row means no record
    yet — the normal state before a session is checked in or closed out."""

    slot_id: UUID
    status: SignupStatus
    checked_in_at: Optional[datetime] = None


class ShiftSignupRead(ORMBase):
    """Staff-facing view of a commitment. `status` is lifecycle only
    (pending / confirmed / waitlisted / cancelled) — attendance lives in
    `session_attendance`, one entry per session actually resolved."""

    id: UUID
    shift_id: UUID
    volunteer_id: UUID
    status: SignupStatus
    timestamp: datetime
    session_attendance: List[SessionAttendanceRead] = []


class ShiftReorderRequest(BaseModel):
    """Full ordering for one event's shifts — every shift id, in display
    order. Partial lists are rejected so two concurrent reorders cannot
    interleave into an order neither organizer asked for."""
    shift_ids: List[UUID] = Field(min_length=1)


class SlotGenerationResult(BaseModel):
    """What a recurrence produced. An orientation recurrence fills `slots`; a
    period recurrence fills `shifts` (one single-session shift per occurrence,
    which is what those slots used to be)."""

    slots: List[SlotRead] = []
    shifts: List[ShiftRead] = []


class SessionReorderRequest(BaseModel):
    """Full ordering for one shift's sessions. Same all-or-nothing contract as
    `ShiftReorderRequest`."""
    session_ids: List[UUID] = Field(min_length=1)


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
    quarter: Optional[Quarter] = None
    year: Optional[int] = None
    week_number: Optional[int] = None
    school: Optional[str] = None
    module_slug: Optional[str] = None
    # Only orientation slots may be created here — a period slot has to belong
    # to a shift, so bundles come in through `shifts`.
    slots: Optional[List[SlotCreate]] = None
    shifts: Optional[List[ShiftCreate]] = None
    # Duplicate flow: the event this payload was prefilled from. The server
    # copies what the form can't carry (form_schema, reminder toggle,
    # shifted signup window) and audits the create as event_duplicate.
    source_event_id: Optional[UUID] = None


class EventRead(ORMBase, EventBase):
    id: UUID
    owner_id: UUID
    module_slug: Optional[str] = None
    quarter: Optional[Quarter] = None
    year: Optional[int] = None
    week_number: Optional[int] = None
    quarter_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    # Set once every expected signup is resolved (attended/no_show); null
    # again after a reopen. The admin list derives its Completed badge here.
    completed_at: Optional[datetime] = None
    # `slots` stays the flat list (orientation slots plus every shift's
    # sessions) so check-in windows and ICS generation keep one place to look;
    # `shifts` is the bookable view.
    slots: List[SlotRead] = []
    shifts: List[ShiftRead] = []

    # Same method name as EventBase's validator → replaces it, so Read
    # payloads keep the UTC offset instead of stripping it.
    @field_validator("start_date", "end_date", "signup_open_at", "signup_close_at")
    @classmethod
    def normalize_event_datetimes(cls, value: datetime | None) -> datetime | None:
        return _to_utc_aware(value)


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
    # Admins can reassign / backfill an event's module. When present the
    # router validates the slug exists. Omit to leave module unchanged.
    module_slug: Optional[str] = None

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
    # Phase 09: user_id replaced by volunteer_id (D-01, D-06)
    volunteer_id: UUID
    slot_id: UUID
    status: SignupStatus
    timestamp: datetime
    # Issue #31: check-in surfaces read this back after check-in/undo.
    checked_in_at: Optional[datetime] = None
    answers: List[SignupAnswerRead] = []
    event_title: Optional[str] = None
    event_location: Optional[str] = None
    slot_start_time: Optional[datetime] = None
    slot_end_time: Optional[datetime] = None
    timezone_label: Optional[str] = None
    waitlist_position: Optional[int] = None


class SelfCheckInSignupRead(BaseModel):
    """Narrow, no-auth-safe read for GET /signups/{id} (self-check-in flow).

    Sweep remediation: this endpoint used to return the full SignupRead —
    including volunteer_id and the volunteer's custom-form answers — to
    anyone who knew the signup_id, with no other gate. It exists only so
    the self-check-in page (frontend/src/pages/SelfCheckInPage.jsx) can
    render a title/time and discover event_id before the venue code is
    entered, so the response is limited to exactly that.
    """
    id: UUID
    event_id: UUID
    event_title: str
    status: SignupStatus
    checked_in_at: Optional[datetime] = None
    slot_start_time: Optional[datetime] = None


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
    volunteer_id: UUID
    volunteer_name: str
    email: str
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
    volunteer_id: UUID
    volunteer_name: str
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
    # Phase 29 (HIDE-01)
    hide_past_events_from_public: bool = True
    # Gate the standalone Audit Logs tab; off by default.
    show_audit_logs_tab: bool = False
    contact_email: Optional[str] = None


class SiteSettingsUpdate(BaseModel):
    default_privacy_mode: Optional[PrivacyMode] = None
    allowed_email_domain: Optional[str] = None
    # Phase 29 (HIDE-01) — optional so existing callers can PATCH other fields.
    hide_past_events_from_public: Optional[bool] = None
    show_audit_logs_tab: Optional[bool] = None
    contact_email: Optional[str] = None


# =========================
# ROSTER / CHECK-IN (Phase 3)
# =========================
class RosterRow(BaseModel):
    signup_id: UUID
    student_name: str
    status: SignupStatus
    slot_time: datetime
    checked_in_at: datetime | None = None
    # Issue #31: check-in surfaces group by slot — rows carry the slot's
    # identity so the UI can render per-slot sections (orientation vs period).
    slot_id: UUID | None = None
    slot_type: str | None = None
    slot_end: datetime | None = None
    slot_location: str | None = None


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


class EventCheckInByEmailRequest(BaseModel):
    email: str
    # Issue #31 hardening: the QR URL carries the venue code; every public
    # check-in endpoint requires it.
    venue_code: str


# Issue #31 UX rework — pick-your-shift check-in.
class CheckInShift(BaseModel):
    """One thing the volunteer can check in for.

    2026-08-02 shifts: `unit_id` is what the client sends back to select this
    row — an orientation signup id, or a session's slot id. `signup_id` and
    `shift_signup_id` are mutually exclusive and tell the UI which kind of row
    it is drawing (only a session has a shift name to show).
    """

    unit_id: UUID
    signup_id: Optional[UUID] = None
    shift_signup_id: Optional[UUID] = None
    shift_id: Optional[UUID] = None
    shift_name: Optional[str] = None
    session_name: Optional[str] = None
    slot_id: UUID
    slot_type: Optional[str] = None
    slot_location: Optional[str] = None
    slot_start: Optional[datetime] = None
    slot_end: Optional[datetime] = None
    status: str
    window_state: Literal["open", "upcoming", "closed"]
    window_opens_at: Optional[datetime] = None


class CheckInLookupResponse(BaseModel):
    event_id: UUID
    event_title: str
    volunteer_name: str
    shifts: List[CheckInShift] = []


class CheckInSelectedRequest(BaseModel):
    email: str
    venue_code: str
    # 2026-08-02 shifts: the ids echoed back from CheckInShift.unit_id, which
    # may be orientation signup ids or session slot ids. Named for the field it
    # carries rather than for one of the two kinds it can hold.
    unit_ids: List[UUID] = Field(min_length=1)


class EventCheckInByEmailSignup(BaseModel):
    unit_id: UUID
    signup_id: UUID | None = None
    shift_signup_id: UUID | None = None
    shift_id: UUID | None = None
    shift_name: str | None = None
    session_name: str | None = None
    slot_id: UUID
    slot_start: datetime | None = None
    slot_end: datetime | None = None
    # Issue #31: the QR result names the shift (orientation vs period), not
    # just a time range.
    slot_type: str | None = None
    slot_location: str | None = None
    status: str
    newly_checked_in: bool


class EventCheckInByEmailResponse(BaseModel):
    event_id: UUID
    event_title: str
    volunteer_name: str
    count_checked_in: int
    count_already_checked_in: int
    signups: List[EventCheckInByEmailSignup]



# =========================
# MODULE SCHEMAS (Phase 5)
# =========================
class ModuleBase(BaseModel):
    name: str
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: int = 20
    duration_minutes: int = 90
    session_count: int = 1
    materials: List[str] = []
    description: Optional[str] = None
    metadata: dict = {}
    # Per-module orientation credit grouping. When omitted on create, the
    # service defaults it to the slug so each new module forms its own
    # credit family.
    family_key: Optional[str] = None


class ModuleCreate(ModuleBase):
    slug: str


class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: Optional[int] = None
    duration_minutes: Optional[int] = None
    session_count: Optional[int] = None
    materials: Optional[List[str]] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    family_key: Optional[str] = None


class ModuleRead(ORMBase):
    slug: str
    name: str
    # Phase 08 (D-05): prerequisite slugs field removed
    default_capacity: int = 20
    duration_minutes: int = 90
    session_count: int = 1
    materials: List[str] = []
    description: Optional[str] = None
    metadata: dict = Field(default={}, validation_alias="metadata_")
    # Phase 22: default form schema list (used by FormFieldsDrawer)
    default_form_schema: List[dict] = []
    family_key: Optional[str] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# =========================
# SENT NOTIFICATION SCHEMAS (Phase 6)
# =========================
class SentNotificationRead(ORMBase):
    id: UUID
    signup_id: UUID
    kind: str
    sent_at: datetime
    provider_id: Optional[str] = None


# =========================
# PHASE 09: PUBLIC SIGNUP SCHEMAS
# =========================
from datetime import date  # noqa: E402 (local import to avoid circular)


class VolunteerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)


class VolunteerRead(BaseModel):
    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone_e164: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PublicSignupCreate(VolunteerCreate):
    # 2026-08-02 shifts: `slot_ids` is now orientation-only — a bare period
    # slot id is refused, because period slots are booked as part of a shift.
    # `shift_ids` carries the bundles. At least one of the two is required.
    slot_ids: List[UUID] = Field(default_factory=list, max_length=20)
    shift_ids: List[UUID] = Field(default_factory=list, max_length=20)
    # Phase 22: optional dynamic form responses keyed by field_id. Soft-warn:
    # backend does NOT raise if a required field is skipped — just records
    # the missing field_ids in the response for organizer display.
    responses: Optional[List["SignupResponseCreate"]] = None

    @model_validator(mode="after")
    def require_something_to_book(self):
        if not self.slot_ids and not self.shift_ids:
            raise ValueError("Select at least one shift or orientation session")
        return self


class PublicSignupResultItem(BaseModel):
    """Phase 25 — per-signup result so the UI can branch confirmed vs waitlisted.

    2026-08-02 shifts: one item per booked unit. An orientation booking sets
    `signup_id`/`slot_id`; a shift booking sets `shift_signup_id`/`shift_id`.
    """

    signup_id: Optional[UUID] = None
    # Which slot this result belongs to — lets the UI badge slots without
    # relying on the order of the submitted slot_ids list.
    slot_id: Optional[UUID] = None
    shift_signup_id: Optional[UUID] = None
    shift_id: Optional[UUID] = None
    status: SignupStatus
    # 1-indexed position within the waitlist when status == waitlisted. None
    # otherwise. Ordering matches waitlist_service.compute_waitlist_position
    # (timestamp ASC, id ASC) — for a shift, the same rule one level up.
    position: Optional[int] = None


class PublicSignupResponse(BaseModel):
    volunteer_id: UUID
    signup_ids: List[UUID]
    # Shift commitments created by this batch, alongside `signup_ids` for the
    # orientation bookings.
    shift_signup_ids: List[UUID] = []
    magic_link_sent: bool
    confirm_token: str | None = None
    # Phase 22: soft-warn list of field_ids that were required but left blank.
    # Clients can surface these to the participant without blocking the signup
    # (organizer remains the ultimate authority on missing answers).
    missing_required: List[str] = []
    # Phase 25 — per-signup status + waitlist position. Empty for legacy test
    # fixtures that construct this schema directly.
    signups: List[PublicSignupResultItem] = []


class SlotSignupRead(BaseModel):
    """Public-facing signup: first name + last initial only."""
    first_name: str
    last_initial: str
    model_config = ConfigDict(from_attributes=True)


class PublicSlotRead(BaseModel):
    id: UUID
    slot_type: SlotType
    date: DateType
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    capacity: int
    filled: int  # = slot.current_count
    signups: List[SlotSignupRead] = []
    model_config = ConfigDict(from_attributes=True)


class PublicSessionRead(BaseModel):
    """One session inside a shift, as the volunteer sees it. Carries a real
    organizer-given `name` — the old frontend numbered periods itself, which
    had no database backing and disagreed between views."""

    id: UUID
    name: Optional[str] = None
    sort_order: int = 0
    date: DateType
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PublicShiftRead(BaseModel):
    """The bookable unit: commit to every session or none."""

    id: UUID
    name: str
    sort_order: int = 0
    capacity: int
    filled: int  # = shift.current_count
    sessions: List[PublicSessionRead] = []
    model_config = ConfigDict(from_attributes=True)


class PublicEventRead(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    quarter: Optional[Quarter] = None
    year: Optional[int] = None
    week_number: Optional[int] = None
    quarter_id: Optional[UUID] = None
    school: Optional[str] = None
    module_slug: Optional[str] = None
    start_date: datetime  # Event.start_date is DateTime not Date in model
    end_date: datetime
    # Phase 29 (LOCK-01) — expose signup window so the public UI can render
    # an opens/closes banner and disable the submit outside the window.
    signup_open_at: Optional[datetime] = None
    signup_close_at: Optional[datetime] = None
    # `slots` is orientation-only now — period slots appear as sessions inside
    # `shifts`, which is what the volunteer actually picks from.
    slots: List[PublicSlotRead] = []
    shifts: List[PublicShiftRead] = []
    model_config = ConfigDict(from_attributes=True)


class CurrentWeekRead(BaseModel):
    """Current week resolved from admin-entered quarters (issue #24).

    configured=False → no quarters entered yet (quarter fields are null).
    is_gap=True with starts_on set → between quarters; the named quarter
    starts on starts_on. is_gap=True with starts_on null → past the last
    entered quarter (admin should enter the next one).
    """

    configured: bool = True
    quarter: Optional[str] = None
    year: Optional[int] = None
    week_number: Optional[int] = None
    quarter_id: Optional[UUID] = None
    label: str = ""
    weeks_in_quarter: Optional[int] = None
    is_gap: bool = False
    starts_on: Optional[DateType] = None


class QuarterBase(BaseModel):
    """Admin-entered quarter (issue #24): the only inputs are the naming
    triple and the two dates from the UCSB academic calendar — weeks
    self-populate from the range."""

    season: Quarter
    year: int = Field(ge=2020, le=2100)
    label: str = Field(default="", max_length=64)
    start_date: DateType
    end_date: DateType


class QuarterCreate(QuarterBase):
    pass


class QuarterUpdate(BaseModel):
    season: Optional[Quarter] = None
    year: Optional[int] = Field(default=None, ge=2020, le=2100)
    label: Optional[str] = Field(default=None, max_length=64)
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None


class QuarterRead(ORMBase):
    id: UUID
    season: Quarter
    year: int
    label: str
    start_date: DateType
    end_date: DateType
    weeks_in_quarter: int
    display_name: str
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PublicQuarterRead(ORMBase):
    id: UUID
    season: Quarter
    year: int
    label: str
    start_date: DateType
    end_date: DateType
    weeks_in_quarter: int
    display_name: str
    archived_at: Optional[datetime] = None


class RelinkSummary(BaseModel):
    """How a quarter create/update recategorized events — surfaced in the
    UI so cache rewrites are visible, never silent."""

    linked: int
    weeks_changed: int
    unlinked: int


class QuarterWriteResult(BaseModel):
    quarter: QuarterRead
    relink_summary: RelinkSummary


class QuarterRetroEventRow(BaseModel):
    """Issue #38: one event of a quarter retrospective with attendance buckets."""

    event_id: UUID
    title: str
    start_date: datetime
    week_number: Optional[int] = None
    slot_count: int
    capacity: int
    signups: int
    attended: int
    no_shows: int


class QuarterRetroTotals(BaseModel):
    events: int
    slots: int
    capacity: int
    signups: int
    attended: int
    no_shows: int
    attendance_rate: float


class QuarterRetrospective(BaseModel):
    quarter: QuarterRead
    totals: QuarterRetroTotals
    events: List[QuarterRetroEventRow] = []


class OrientationStatusRead(BaseModel):
    has_attended_orientation: bool
    last_attended_at: Optional[datetime] = None
    # Phase 21: has_credit is the cross-week/cross-module answer the modal uses.
    # has_attended_orientation is kept for legacy callers. For the legacy
    # endpoint both remain true together.
    has_credit: bool = False
    source: Optional[Literal["attendance", "grant"]] = None
    family_key: Optional[str] = None


# =========================
# ORIENTATION CREDIT (Phase 21)
# =========================
class OrientationCreditCreate(BaseModel):
    volunteer_email: EmailStr
    family_key: str = Field(min_length=1, max_length=255)
    # Issue #30: optionally records which quarter the credit was earned in —
    # display metadata only; credit is permanent per (email, family).
    quarter_id: Optional[UUID] = None
    notes: Optional[str] = None


class OrientationCreditRead(ORMBase):
    id: UUID
    volunteer_email: str
    family_key: str
    quarter_id: Optional[UUID] = None
    quarter_label: Optional[str] = None
    source: Literal["attendance", "grant"]
    granted_by_user_id: Optional[UUID] = None
    granted_by_label: Optional[str] = None
    granted_at: datetime
    revoked_at: Optional[datetime] = None
    notes: Optional[str] = None


class TokenedSignupRead(BaseModel):
    signup_id: UUID
    status: SignupStatus
    slot: PublicSlotRead
    # Phase 25 — 1-indexed waitlist position when status == waitlisted. Null
    # otherwise. Computed live per read; no DB column.
    waitlist_position: Optional[int] = None


class TokenedShiftSignupRead(BaseModel):
    """A shift commitment on the read-only manage page: the shift, its sessions
    in organizer order, and the waitlist position if any."""

    shift_signup_id: UUID
    status: SignupStatus
    shift: PublicShiftRead
    waitlist_position: Optional[int] = None


class TokenedManageRead(BaseModel):
    volunteer_id: UUID
    volunteer_first_name: str
    volunteer_last_name: str
    event_id: UUID
    # Orientation bookings.
    signups: List[TokenedSignupRead]
    # Shift commitments — the bulk of what a volunteer holds.
    shift_signups: List[TokenedShiftSignupRead] = []
    contact_email: Optional[str] = None


# =========================
# CUSTOM FORM FIELDS (Phase 22)
# =========================
# The form schema is a JSON array of field descriptors stored on
# ``modules.default_form_schema`` and ``events.form_schema``.
# Responses land in the ``signup_responses`` table.

FormFieldType = Literal[
    "text",
    "textarea",
    "select",
    "radio",
    "checkbox",
    "phone",
    "email",
]


class FormFieldSchema(BaseModel):
    """One field descriptor in a form schema.

    - ``id`` must be a stable, unique, URL-safe slug. Never changes once
      used — responses are snapshotted by it.
    - ``options`` is required when ``type`` is select/radio/checkbox.
    """

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    type: FormFieldType
    required: bool = False
    help_text: Optional[str] = None
    options: Optional[List[str]] = None
    order: int = 0


class SignupResponseCreate(BaseModel):
    """Inbound payload: one response per field_id from the participant."""

    field_id: str = Field(min_length=1, max_length=64)
    # ``value`` can be a string (free text) OR list/dict (multi-select,
    # structured) — the service decides how to persist it.
    value: Any = None


class SignupResponseRead(ORMBase):
    field_id: str
    value_text: Optional[str] = None
    value_json: Optional[Any] = None
    # Decorated by the service with the field's current label when joined
    # against the event's effective schema. Optional so raw ORM loads still
    # validate.
    label: Optional[str] = None


# =========================
# VOLUNTEER PREFERENCES (Phase 24 — reminder opt-out)
# =========================
class VolunteerPreferenceRead(ORMBase):
    volunteer_email: str
    email_reminders_enabled: bool
    sms_opt_in: bool
    phone_e164: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class VolunteerPreferenceUpdate(BaseModel):
    email_reminders_enabled: Optional[bool] = None
    sms_opt_in: Optional[bool] = None
    phone_e164: Optional[str] = None


# =========================
# REMINDERS (Phase 24 — admin preview + send-now)
# =========================
ReminderKind = Literal["kickoff", "pre_24h", "pre_2h"]


class UpcomingReminderRow(BaseModel):
    signup_id: UUID
    volunteer_email: str
    volunteer_name: str
    event_id: UUID
    event_title: str
    slot_id: UUID
    slot_start_time: datetime
    kind: ReminderKind
    scheduled_for: datetime  # UTC — when the window opens
    already_sent: bool
    opted_out: bool


class ReminderSendNowRequest(BaseModel):
    signup_id: UUID
    kind: ReminderKind


class ReminderSendNowResponse(BaseModel):
    signup_id: UUID
    kind: ReminderKind
    sent: bool
    reason: Optional[str] = None  # "already_sent" | "opted_out" | "ok"


# -------------------------
# Phase 26 — Broadcast messages
# -------------------------


class BroadcastCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    body_markdown: str = Field(..., min_length=1, max_length=20000)
    # None => every slot on the event (pre-slot-scoping behavior).
    slot_id: Optional[UUID] = None


class BroadcastResult(BaseModel):
    broadcast_id: str
    recipient_count: int
    sent_at: datetime


class BroadcastSummary(BaseModel):
    broadcast_id: str
    subject: str
    recipient_count: int
    actor_label: Optional[str] = None
    sent_at: datetime
    slot_id: Optional[str] = None


class BroadcastRecipientCount(BaseModel):
    recipient_count: int
