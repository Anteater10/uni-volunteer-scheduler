# Architecture Research

**Domain:** Brownfield FastAPI + React volunteer scheduler (UCSB Sci Trek)
**Researched:** 2026-04-08
**Confidence:** HIGH — based on direct codebase analysis, not search speculation

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (React SPA — Vite)                                      │
│  ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │  Pages   │ │Components │ │ AuthContext  │ │TanStack Query │  │
│  │ (views)  │ │(Layout,   │ │+ authStorage │ │ (server cache)│  │
│  │          │ │Protected  │ │              │ │               │  │
│  │          │ │Route)     │ │              │ │               │  │
│  └────┬─────┘ └─────┬─────┘ └──────┬───────┘ └───────┬───────┘  │
│       └─────────────┴──────────────┴─────────────────┘          │
│                        lib/api.js (fetch wrapper)                │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ HTTPS REST /api/v1
┌─────────────────────────────────▼────────────────────────────────┐
│  FastAPI (Uvicorn — port 8000)                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Routers: auth / users / events / slots / signups /         │  │
│  │          notifications / portals / admin                   │  │
│  │  Each router → Depends(get_db, get_current_user,           │  │
│  │                         require_role, rate_limit)          │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │ SQLAlchemy ORM  (models.py + schemas.py)                   │  │
│  │ Helpers: deps.py (JWT, hashing, audit), database.py        │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│               .delay() ─────▼──── Celery task queue              │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ celery_app.py tasks: send_email_notification,             │   │
│  │                      schedule_reminders, weekly_digest    │   │
│  └──────────────┬────────────────────────────────────────────┘   │
└─────────────────┼────────────────────────────────────────────────┘
                  │
    ┌─────────────┼──────────────┐
    │             │              │
┌───▼───┐   ┌────▼────┐   ┌─────▼──────┐
│Postgres│   │  Redis  │   │  Resend/   │
│(ORM +  │   │(broker +│   │  SendGrid  │
│Alembic)│   │ cache + │   │  (email)   │
└────────┘   │rate lim)│   └────────────┘
             └─────────┘
```

### Component Responsibilities

| Component | Responsibility | Location |
|-----------|----------------|----------|
| `lib/api.js` | Single fetch wrapper; Bearer token injection; error normalization; flat + nested aliases | `frontend/src/lib/api.js` |
| `AuthContext` | Session state, `isAuthed`, `role`, `login/logout/reloadMe` | `frontend/src/state/authContext.jsx` |
| TanStack Query | Server-state cache; invalidation after mutations | wired in `main.jsx` |
| `Pages/*` | Route-level data fetch + view composition | `frontend/src/pages/` |
| FastAPI routers | HTTP entry, validation, auth enforcement, task dispatch, audit log | `backend/app/routers/` |
| `deps.py` | `get_current_user`, `require_role`, `log_action`, JWT helpers, Redis rate-limiter | `backend/app/deps.py` |
| `models.py` | SQLAlchemy ORM; enums (UserRole, SignupStatus, etc.) | `backend/app/models.py` |
| `schemas.py` | Pydantic I/O contracts (request bodies + response shapes) | `backend/app/schemas.py` |
| `celery_app.py` | Async task runner; email delivery; scheduled reminders | `backend/app/celery_app.py` |
| Postgres | System of record; row-level locking for capacity-critical writes | Docker service `db` |
| Redis | Celery broker + result backend + rate-limit counter | Docker service `redis` |
| Alembic | Schema migration history; auto-applied by `migrate` service on boot | `backend/alembic/` |

---

## Component Boundaries for New Features

This section maps each planned capability to a precise insertion point in the existing architecture.

### (a) Signup Status State Machine

**Current state:** `SignupStatus` enum has only `confirmed | waitlisted | cancelled`. The full lifecycle (`registered → confirmed → checked_in → attended | no_show`) does not exist.

**Where to add:**
- `backend/app/models.py` — extend `SignupStatus` enum: add `registered`, `checked_in`, `attended`, `no_show`
- `backend/alembic/versions/` — new migration to `ALTER TYPE signupstatus ADD VALUE ...` (Postgres enum ALTER is append-only; new states must be added, not renamed)
- `backend/app/routers/signups.py` — add `POST /signups/{id}/check-in` and `POST /signups/{id}/mark` (attended/no_show) endpoints behind `require_role("organizer", "admin")`
- `backend/app/schemas.py` — extend `SignupRead` to expose new status values
- `frontend/src/lib/api.js` — add `api.signups.checkIn(id)` and `api.signups.mark(id, status)` functions

**State transition rules (enforce in router, not DB constraint):**
```
registered  → confirmed   (magic-link click)
confirmed   → checked_in  (organizer tap / self-check-in link)
confirmed   → cancelled   (user or organizer cancel)
checked_in  → attended    (organizer end-of-event finalization)
checked_in  → no_show     (organizer end-of-event finalization, or time-out sweep)
```

Transitions validated in the router handler before DB write. No DB check constraint needed (app-level is simpler to change and already the pattern for capacity logic). `log_action` must be called for every transition — these are the audit events prereq logic depends on.

**New initial status:** When a signup is created, initial status becomes `registered` (not `confirmed` as today). Magic-link confirmation flips it to `confirmed`. This is a **breaking change** to existing behavior — Phase 0 audit must flag whether any live data depends on the current default.

### (b) Magic-Link Token Design

**Current state:** Auth uses JWT access tokens + DB-persisted `RefreshToken` rows for session management. No one-time token pattern exists.

**Where to add:**
- `backend/app/models.py` — add `MagicLinkToken` table:
  ```python
  class MagicLinkToken(Base):
      __tablename__ = "magic_link_tokens"
      id         = Column(UUID, primary_key=True, default=uuid4)
      token      = Column(String(128), unique=True, nullable=False, index=True)
      user_id    = Column(UUID, ForeignKey("users.id"), nullable=True)   # null for pre-reg
      signup_id  = Column(UUID, ForeignKey("signups.id"), nullable=True) # for confirmation
      purpose    = Column(String(32), nullable=False)  # "confirm_signup" | "checkin"
      expires_at = Column(DateTime, nullable=False)
      used_at    = Column(DateTime, nullable=True)     # set on first use → one-time
  ```
- `backend/app/routers/auth.py` — add `GET /auth/magic/{token}` handler that verifies expiry, checks `used_at` is null (replay protection), sets `used_at`, performs the purpose-specific action (flip signup status, issue session JWT), and redirects to the relevant frontend page
- `backend/app/deps.py` — add `create_magic_token(db, purpose, signup_id=None, user_id=None, ttl_minutes=...)` helper (mirrors the `create_refresh_token` pattern — helpers never commit, caller commits)
- Token value: `secrets.token_urlsafe(32)` — 256 bits of entropy, stored as plain string (no hash needed since it's a one-time use token with expiry; hashing would require a lookup scan)
- TTL: 24h for signup confirmation; 45min window for check-in links (15 min before → 30 min after slot start)

**Check-in self-serve gate:** Confirm the token `purpose == "checkin"` AND `now` is within `[slot.start_time - 15min, slot.start_time + 30min]` AND the per-event `checkin_code` in the request matches (prevents from-home click). The `checkin_code` is a short alphanumeric displayed at the venue, stored on the `Event` or `Slot` row.

### (c) Prereq Query Placement

**Recommendation: application-layer check in `signups.py` router, not DB constraint.**

Rationale:
- Soft-warn UX requires reading the missing prereq detail (which module, when next available) — a DB constraint raises an opaque error, an app check returns a rich message
- The existing pattern for all business rules (capacity, signup window, duplicate check) is app-level in `signups.py` — consistency matters for maintainability
- Prereq rule can change (admin manual override, bypass for late joiners) — app code is easier to conditionally skip

**Query pattern** (add inside `create_signup` in `signups.py`, before the capacity lock):
```python
def _check_prereqs(db: Session, user_id, event: models.Event) -> list[str]:
    """Returns list of unmet prereq module slugs. Empty = eligible."""
    if not event.module_template_id:
        return []
    template = db.query(models.ModuleTemplate).get(event.module_template_id)
    if not template or not template.prereq_slugs:
        return []
    met = (
        db.query(models.ModuleTemplate.slug)
        .join(models.Event, models.Event.module_template_id == models.ModuleTemplate.id)
        .join(models.Slot, models.Slot.event_id == models.Event.id)
        .join(models.Signup, models.Signup.slot_id == models.Slot.id)
        .filter(
            models.Signup.user_id == user_id,
            models.Signup.status == models.SignupStatus.checked_in,
            models.ModuleTemplate.slug.in_(template.prereq_slugs),
        )
        .distinct()
        .all()
    )
    met_slugs = {row.slug for row in met}
    return [s for s in template.prereq_slugs if s not in met_slugs]
```

On unmet prereqs: raise `HTTP 422` with a structured body (`{"detail": "PREREQ_MISSING", "missing": [...], "next_slots": [...]}`) — not a hard block 400, because the frontend shows a soft warning and links to next orientation. Admin override endpoint (`POST /admin/signups/override-prereq`) bypasses this check entirely.

### (d) `module_templates` Table Relationship to Events

**New table** (does not exist yet):
```python
class ModuleTemplate(Base):
    __tablename__ = "module_templates"
    id             = Column(UUID, primary_key=True, default=uuid4)
    slug           = Column(String(64), unique=True, nullable=False, index=True)
    name           = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    prereq_slugs   = Column(JSON, nullable=True)   # list[str] — slugs of required templates
    default_capacity = Column(Integer, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    materials_list = Column(JSON, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, onupdate=datetime.utcnow)
    events         = relationship("Event", back_populates="module_template")
```

**`Event` model gets one new FK:**
```python
module_template_id = Column(UUID, ForeignKey("module_templates.id"), nullable=True)
module_template    = relationship("ModuleTemplate", back_populates="events")
```

`nullable=True` is intentional — not all events are module-based (admin-created one-offs). Prereq logic skips events where `module_template_id` is null.

**New router:** `backend/app/routers/module_templates.py` — CRUD behind `require_role("admin")`. Register in `main.py`.

**Relationship:** `ModuleTemplate` is a permanent record (one row per module type, updated in place). `Event` rows are ephemeral instantiations (one per occurrence). The CSV importer creates `Event` rows from `ModuleTemplate` rows. This is a one-to-many relationship where the template is the canonical source of prereqs and capacity defaults.

### (e) LLM CSV Import Pipeline as a Module Boundary

**Architecture:** Two-stage pipeline with a hard boundary between Stage 1 (LLM) and Stage 2 (deterministic). The boundary is a validated Pydantic schema.

**New router:** `backend/app/routers/import_csv.py`

```
POST /import/extract          (Stage 1 — admin only)
  Input:  multipart/form-data with CSV file
  Action: call LLM with structured output prompt
  Output: JSON preview payload (list of ImportRowPreview)

POST /import/commit           (Stage 2 — admin only)
  Input:  JSON list of ImportRowPreview (from Stage 1, possibly user-edited)
  Action: deterministic validator + atomic DB insert
  Output: summary (created_count, skipped_rows, errors)
```

**Stage 1 internals** (new module `backend/app/services/csv_extractor.py`):
- `extract_csv_to_preview(csv_text: str, templates: list[ModuleTemplate]) -> list[ImportRowPreview]`
- Single `anthropic.messages.create(...)` call with `tool_use` / `response_format` returning a Pydantic-validated list
- Pydantic schema (`ImportRowPreview`) is the contract crossing the boundary:
  ```python
  class ImportRowPreview(BaseModel):
      template_slug: str
      date: date
      start_time: time
      end_time: time
      location: str | None
      capacity: int | None
      confidence: float       # 0–1; flag rows < 0.7 for manual review
      raw_row: dict           # original CSV row, kept for audit
      warning: str | None     # populated if template_slug not found, date ambiguous, etc.
  ```
- Function is pure (no DB writes) — router handles DB session, this function only calls LLM
- Errors inside LLM call → catch, return `ImportRowPreview` with `confidence=0` and `warning` populated

**Stage 2 internals** (same module or `backend/app/services/csv_importer.py`):
- `commit_import(db: Session, rows: list[ImportRowPreview], actor: User) -> ImportResult`
- Validates `template_slug` exists in DB before any writes
- Uses a single transaction: `db.begin()` (implicit with SQLAlchemy), creates all `Event` rows, calls `log_action`, then `db.commit()` — or rolls back entirely on any error
- Does NOT call the LLM — purely SQL

**Why services/ subdirectory:** The LLM call and the importer are both multi-step operations that don't belong in a router handler. Using a `backend/app/services/` directory for them keeps routers thin (HTTP only) and makes the LLM call unit-testable without a FastAPI test client.

**Frontend:** New `AdminImportPage.jsx` with two-step UI (upload → preview table with editable rows → confirm button). Calls `api.admin.import.extract(file)` then `api.admin.import.commit(rows)`.

### (f) Celery Task Design for Notifications with Idempotency

**Current state:** `send_email_notification` is a bare `@celery.task` with no dedup key, no retry policy, no idempotency guard. `schedule_reminders` re-queries every 5 minutes and could fire duplicate emails if a previous run's tasks are still in-flight.

**Idempotency pattern:** Add a `NotificationDedup` table (or reuse the existing `Notification` table with a unique constraint):

Option A — Unique constraint on `Notification`:
```sql
ALTER TABLE notifications ADD COLUMN dedup_key VARCHAR(255);
CREATE UNIQUE INDEX ix_notifications_dedup ON notifications(dedup_key) WHERE dedup_key IS NOT NULL;
```
`dedup_key` format: `"{signup_id}:{kind}"` where `kind` is `confirm | reminder_24h | reminder_1h | cancel | checkin`. Before inserting a `Notification` row, the task checks for an existing row with the same `dedup_key`. If found, skip silently.

**Task redesign for `schedule_reminders`:**
```python
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_reminder(self, signup_id: str, kind: str) -> None:
    dedup_key = f"{signup_id}:{kind}"
    db = SessionLocal()
    try:
        exists = db.query(Notification).filter_by(dedup_key=dedup_key).first()
        if exists:
            return  # already sent, idempotent exit
        # ... build and send email ...
        db.add(Notification(..., dedup_key=dedup_key))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc)
    finally:
        db.close()
```

`schedule_reminders` becomes a pure dispatcher: it queries slots, then calls `send_reminder.apply_async(args=[signup_id, "reminder_24h"], task_id=dedup_key)`. Using Celery's `task_id` as the dedup key at the broker level prevents the same task from being enqueued twice (Celery rejects duplicate `task_id`s). Double-layered: broker-level dedup + DB-level dedup.

**Magic-link confirmation email:** dispatched from `auth.py` after creating `MagicLinkToken` and committing. Use dedup key `"confirm:{signup_id}"`.

**Rule:** All notification dispatches happen *after* `db.commit()` — never before, never inside the same transaction.

### (g) Frontend ↔ Backend Integration via `lib/api.js`

**Current state:** `api.js` is well-structured with both flat and nested aliases. New methods follow the existing pattern exactly.

**New methods to add per phase:**

Phase 2 (magic-link):
```js
// No new frontend calls needed — user clicks email link directly → backend redirect
// One new call: confirm page polls signup status after redirect lands
api.signups.get = (id) => request(`/signups/${id}`, { method: "GET" });
```

Phase 3 (check-in):
```js
// Organizer roster
api.organizer = {
  roster: (eventId) => request(`/organizer/events/${eventId}/roster`, { method: "GET" }),
  checkIn: (signupId) => request(`/signups/${signupId}/check-in`, { method: "POST" }),
  markAttendance: (signupId, status) =>
    request(`/signups/${signupId}/mark`, { method: "POST", body: { status } }),
};
// Self check-in — no auth token, link carries magic token
api.signups.selfCheckIn = (token, venueCode) =>
  request(`/auth/magic/${token}`, { method: "POST", auth: false, body: { venue_code: venueCode } });
```

Phase 4 (prereqs):
```js
api.signups.eligibility = (slotId) =>
  request(`/signups/eligibility`, { method: "GET", params: { slot_id: slotId } });
```

Phase 5 (CSV import):
```js
api.admin.import = {
  extract: (formData) => {
    // multipart — must not set Content-Type manually (browser sets boundary)
    const token = authStorage.getToken();
    return fetch(`${API_BASE}/import/extract`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }).then(r => r.json());
  },
  commit: (rows) => request("/import/commit", { method: "POST", body: rows }),
};
```

**TanStack Query invalidation pattern:** After any mutation (check-in, mark attendance, import commit), invalidate the relevant query keys. Convention used in this project: the page component calls `queryClient.invalidateQueries({ queryKey: ["signups", eventId] })` inside the `onSuccess` callback of a `useMutation` hook.

**5-second polling for organizer roster:**
```js
const { data } = useQuery({
  queryKey: ["roster", eventId],
  queryFn: () => api.organizer.roster(eventId),
  refetchInterval: 5000,          // poll every 5s
  refetchIntervalInBackground: false,  // pause when tab not active
});
```

### (h) E2E Test Layer via Playwright in CI

**New directory:** `e2e/` at repo root (parallel to `frontend/` and `backend/`).

**Structure:**
```
e2e/
├── playwright.config.js     # base URL = http://localhost:5173 (Vite dev) or http://localhost:8000
├── fixtures/
│   └── auth.js              # shared login helper returning page with stored auth state
├── tests/
│   ├── student-flow.spec.js  # register → confirm → browse → signup → MySignups
│   ├── organizer-flow.spec.js # login → dashboard → roster → check-in
│   ├── admin-flow.spec.js    # login → users CRUD → events CRUD → audit logs
│   └── checkin-flow.spec.js  # magic-link self check-in (added in Phase 3)
└── global-setup.js          # seed test DB with known fixtures
```

**CI integration:** GitHub Actions job runs after the existing backend test job, starts `docker compose up -d` (or `docker compose up -d db redis backend`), waits for health check, then `npx playwright test`. Playwright results uploaded as artifacts.

**Auth fixture pattern** (avoids re-login on every test):
```js
// fixtures/auth.js
export async function loginAs(browser, role) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.fill('[name="email"]', process.env[`TEST_${role.toUpperCase()}_EMAIL`]);
  await page.fill('[name="password"]', process.env[`TEST_${role.toUpperCase()}_PASSWORD`]);
  await page.click('[type="submit"]');
  await page.waitForURL("/events");
  await context.storageState({ path: `e2e/.auth/${role}.json` });
  return page;
}
```

---

## Recommended Project Structure (delta from current)

The existing structure is sound. New files slot in as:

```
backend/app/
├── services/                     # NEW — business logic extracted from routers
│   ├── __init__.py
│   ├── csv_extractor.py          # Stage 1 LLM call (pure function, no DB)
│   └── csv_importer.py           # Stage 2 deterministic DB writer
├── routers/
│   ├── (existing: auth, users, events, slots, signups, notifications, portals, admin)
│   ├── module_templates.py       # NEW — CRUD for ModuleTemplate, admin-only
│   └── import_csv.py             # NEW — /import/extract and /import/commit, admin-only
└── models.py                     # extend: MagicLinkToken, ModuleTemplate, SignupStatus enum

e2e/                              # NEW — Playwright test suite
├── playwright.config.js
├── fixtures/
└── tests/

frontend/src/
├── pages/
│   ├── (existing pages)
│   ├── AdminImportPage.jsx        # NEW — CSV import UI (Phase 5)
│   └── CheckInPage.jsx            # NEW — self check-in landing page (Phase 3)
├── components/
│   ├── (existing: Layout, ProtectedRoute)
│   ├── OrganizerRoster.jsx        # NEW — roster component with polling (Phase 3)
│   └── PrereqWarning.jsx          # NEW — soft-warn banner (Phase 4)
└── lib/
    └── api.js                     # extend with new method groups (see section g)
```

---

## Architectural Patterns

### Pattern 1: Router-Thin, Service-Fat (for new complex operations)

**What:** Router handler validates HTTP input and enforces auth. Business logic lives in `services/`. This is a new pattern — the existing codebase puts business logic directly in routers, which works for simple CRUD but not for multi-step operations like CSV import.

**When to use:** Any operation with more than one non-trivial step, or that needs unit-testing without HTTP overhead. Specifically: `csv_extractor.py`, `csv_importer.py`, `_check_prereqs()`.

**Trade-offs:** Adds one indirection layer. For simple endpoints (e.g., `module_templates` CRUD), inline logic in the router is still appropriate.

**Example:**
```python
# router: thin
@router.post("/import/extract", dependencies=[Depends(require_role("admin"))])
async def extract_csv(file: UploadFile, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    text = (await file.read()).decode()
    templates = db.query(models.ModuleTemplate).all()
    preview = await csv_extractor.extract_csv_to_preview(text, templates)  # pure function
    log_action(db, current_user, "import_extract", "CSV", None)
    db.commit()
    return preview

# service: fat
async def extract_csv_to_preview(csv_text, templates) -> list[ImportRowPreview]:
    # LLM call here — no db, no HTTP concerns
    ...
```

### Pattern 2: Enum Extension via Alembic (for SignupStatus)

**What:** Postgres `ENUM` types cannot have values removed, only appended. New states (`registered`, `checked_in`, `attended`, `no_show`) must be appended in a migration.

**When to use:** Any time a Python `enum.Enum` on a SQLAlchemy model is extended.

**Trade-offs:** Values cannot be removed without a more complex migration (create new type, swap column, drop old type). Append-only for new lifecycle states is acceptable here.

**Example migration fragment:**
```python
def upgrade():
    op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'registered'")
    op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'checked_in'")
    op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'attended'")
    op.execute("ALTER TYPE signupstatus ADD VALUE IF NOT EXISTS 'no_show'")
```
`IF NOT EXISTS` is idempotent — safe to re-run.

### Pattern 3: Dedup Key Idempotency for Celery Tasks

**What:** Every notification task carries a `dedup_key` string (`"{signup_id}:{kind}"`). Before writing the `Notification` row, check for an existing row with the same key. At the Celery level, pass `task_id=dedup_key` so the broker refuses duplicate enqueues.

**When to use:** All notification tasks. Any scheduled task that could be re-dispatched on overlap.

**Trade-offs:** Requires a `dedup_key` column on `Notification` with a unique index. Adds one SELECT before each notification write.

### Pattern 4: Hard Boundary at the LLM Output (CSV Import)

**What:** Stage 1 (LLM) and Stage 2 (deterministic) are separated by a Pydantic-validated JSON payload. Stage 2 receives only validated data and never calls the LLM. The UI shows Stage 1 output to a human before Stage 2 runs.

**When to use:** Any LLM-assisted operation where errors must be caught before DB writes. Non-negotiable for CSV import.

**Trade-offs:** Two HTTP round-trips (extract, then commit). Acceptable given the admin-only, once-per-year usage pattern.

---

## Data Flow

### State Machine Transitions

```
POST /auth/register
    → Signup created with status=registered
    → MagicLinkToken(purpose="confirm_signup") created
    → send_email_notification.delay("confirm:{signup_id}")

GET /auth/magic/{token}   (user clicks email link)
    → MagicLinkToken verified (expiry, used_at=null)
    → MagicLinkToken.used_at = now
    → Signup.status = confirmed
    → redirect to /my-signups

POST /signups/{id}/check-in   (organizer tap on roster)
    → require_role(organizer, admin)
    → Signup.status = checked_in
    → log_action
    → optional: dispatch checkin confirmation email

POST /signups/{id}/mark   (organizer end-of-event finalization)
    → require_role(organizer, admin)
    → body: { status: "attended" | "no_show" }
    → Signup.status = attended | no_show
    → log_action
```

### Prereq Check Flow

```
POST /signups  (user attempts signup for a module with prereqs)
    → _check_prereqs(db, user_id, event) called before capacity lock
    → If unmet: return HTTP 422 with missing slugs + next available slot info
    → If met (or no prereqs): proceed with existing capacity lock + signup creation
    → Admin bypass: POST /admin/signups/override-prereq skips prereq check
```

### CSV Import Flow

```
Admin uploads CSV file
    → POST /import/extract
    → csv_extractor.extract_csv_to_preview(text, templates)
    → LLM call → validated list[ImportRowPreview]
    → Response: preview JSON (shown in UI)

Admin reviews, edits, clicks Confirm
    → POST /import/commit (body = reviewed preview rows)
    → csv_importer.commit_import(db, rows, actor)
    → For each row: validate template_slug exists → create Event row
    → All in one transaction → commit or rollback
    → log_action for each created event
    → Response: { created: N, skipped: M, errors: [...] }
```

### Notification Dedup Flow

```
schedule_reminders fires every 5 min
    → Query slots starting in 24h ± 2.5min
    → For each confirmed signup:
        dedup_key = f"{signup_id}:reminder_24h"
        send_reminder.apply_async(args=[signup_id, "reminder_24h"], task_id=dedup_key)
        (broker rejects if task_id already queued or executing)

send_reminder task executes
    → Check Notification table for existing dedup_key row
    → If exists: return (idempotent)
    → If not: send email, insert Notification(dedup_key=dedup_key)
```

---

## Scaling Considerations

| Scale | Architecture Notes |
|-------|--------------------|
| Current (< 100 users) | Existing monolith is correct. No changes needed for scale. |
| 100–500 users (Sci Trek realistic max) | Existing architecture handles this comfortably. Row locking in signups already covers concurrency at this scale. |
| 1k–10k users | Redis-backed rate limiting already in place. Add `pgbouncer` connection pooling before any DB scaling. Consider moving `schedule_reminders` to a separate queue with concurrency=1 to prevent fan-out. |
| Beyond this | Out of scope for this project and university deployment context. |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: LLM in Stage 2

**What people do:** Let the LLM "fix" data during the commit phase.
**Why it's wrong:** Makes Stage 2 non-deterministic and non-auditable. If the import fails, there is no clean rollback.
**Do this instead:** All fuzzy normalization happens in Stage 1. Stage 2 only receives validated, human-reviewed data.

### Anti-Pattern 2: Celery Task Dispatched Before Commit

**What people do:** Call `send_email_notification.delay(...)` before or during the transaction.
**Why it's wrong:** If the transaction rolls back, the task is already queued and will fire for a signup that does not exist.
**Do this instead:** Always dispatch Celery tasks after `db.commit()`. This is already the pattern in `signups.py` — maintain it everywhere.

### Anti-Pattern 3: DB Constraint for Prereq Logic

**What people do:** Add a Postgres trigger or check constraint enforcing prereqs at the DB level.
**Why it's wrong:** Produces opaque errors that cannot carry the "you need X, here is the next slot" rich message. Also blocks admin override paths without special session variables.
**Do this instead:** App-level check in `signups.py::create_signup` before the capacity lock. Return structured 422 with missing prereq details.

### Anti-Pattern 4: Hardcoding Signup Status Strings

**What people do:** Compare `signup.status == "confirmed"` as a string.
**Why it's wrong:** Will silently mis-match after the enum is extended; the Postgres enum and Python enum must stay in sync.
**Do this instead:** Always compare against `models.SignupStatus.confirmed` (Python enum member). The existing codebase already does this consistently.

### Anti-Pattern 5: Polling Roster on Every Render

**What people do:** `useEffect` with `setInterval` calling the API every second.
**Why it's wrong:** Floods the backend; creates memory leaks on component unmount.
**Do this instead:** TanStack Query `refetchInterval: 5000` with `refetchIntervalInBackground: false` — already available in the project's stack, handles cleanup automatically.

### Anti-Pattern 6: Growing `celery_app.py` Unbounded

**What people do:** Add every new task to the single `celery_app.py` file.
**Why it's wrong:** The file already mixes app setup, email helper, and task definitions. Adding notification variants, check-in tasks, and import-related tasks will make it unmanageable.
**Do this instead:** Split into `celery_app.py` (app + beat schedule only) and `backend/app/tasks/` package (`notifications.py`, `reminders.py`) imported by `celery_app.py`. This is a refactor for Phase 6, not Phase 0.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SendGrid (current) | `SendGridAPIClient` in `celery_app.py` | Replace with Resend (simpler API, free tier 3k/mo). Drop-in: replace `_send_email_via_sendgrid` with a Resend HTTP call. |
| Resend (planned) | `httpx.post("https://api.resend.com/emails", ...)` inside the same send helper | Resend has no official Python SDK complexity; plain HTTPS POST with API key header |
| Anthropic (Phase 5) | `anthropic.Anthropic().messages.create(...)` in `services/csv_extractor.py` | Single sync call; wrap in `asyncio.to_thread` if used from an async FastAPI handler |
| UCSB SSO (optional) | OIDC via `authlib` — already wired in `auth.py` | Hooks exist; needs `OIDC_CLIENT_ID/SECRET/ISSUER` env vars |

### Internal Module Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Router → Service | Direct function call (sync or async) | Services receive `db: Session`, return domain objects or Pydantic models |
| Router → Celery | `task.delay(...)` or `task.apply_async(...)` after `db.commit()` | Never before commit |
| `deps.py` → Routers | FastAPI `Depends(...)` injection | `log_action` and `get_current_user` are pure helpers — they never commit |
| Stage 1 → Stage 2 | Pydantic `list[ImportRowPreview]` passed through the HTTP response and re-submitted | Human in the loop between the two stages |
| Frontend → Backend | `lib/api.js` — all calls go through the single `request()` wrapper | No page should call `fetch` directly |
| TanStack Query → `api.js` | `queryFn: () => api.someMethod(...)` | Query keys must include all parameters used in the queryFn |

---

## Suggested Build Order

Based on module dependencies and integration risk:

1. **Phase 0 — Backend audit + full frontend wiring:** No new architecture; fix what exists. Establish Playwright E2E baseline. This is the foundation every subsequent phase builds on.

2. **Phase 1 — Mobile-first Tailwind pass:** Pure frontend. No backend changes. Safe to do immediately after Phase 0.

3. **Phase 2 — Magic-link confirmation:** Add `MagicLinkToken` model + migration + `GET /auth/magic/{token}` handler + extend `SignupStatus` enum with `registered`. Narrowly scoped, low blast radius.

4. **Phase 3 — Check-in state machine + organizer roster:** Depends on Phase 2 (full `SignupStatus` enum). Add `POST /signups/{id}/check-in`, `POST /signups/{id}/mark`, self-check-in magic-link variant, `OrganizerRoster` component with polling. This is the largest backend phase.

5. **Phase 4 — Prereq enforcement:** Depends on Phase 3 (`checked_in` status must exist in real data). Add `ModuleTemplate` table + FK on `Event` + `_check_prereqs` + soft-warn API response + `PrereqWarning` frontend component.

6. **Phase 5 — Event template + LLM CSV import:** Depends on Phase 4 (`ModuleTemplate` table already exists). Add `services/csv_extractor.py`, `services/csv_importer.py`, `import_csv.py` router, `AdminImportPage.jsx`.

7. **Phase 6 — Notifications polish:** Depends on Phase 2 (magic-link email already sends). Add dedup keys to all reminder tasks, cancellation email on slot removal, 1h reminder variant. Refactor `celery_app.py` into `tasks/` package.

8. **Phase 7 — Admin dashboard polish:** Depends on Phases 4, 5, 6. Manual eligibility override UI, bulk template CRUD, CSV import UI surface (already built in Phase 5), audit log polish.

9. **Phase 8 — Deployment:** Depends on all prior phases being stable. UCSB infrastructure target, secrets management, monitoring, handoff docs.

---

## Sources

- Direct analysis of `backend/app/models.py`, `backend/app/routers/signups.py`, `backend/app/routers/auth.py`, `backend/app/celery_app.py`, `frontend/src/lib/api.js` — HIGH confidence
- `.planning/codebase/ARCHITECTURE.md` and `.planning/codebase/STRUCTURE.md` — HIGH confidence (generated from codebase)
- `.planning/PROJECT.md` and `IDEAS.md` — HIGH confidence (product decisions captured from planning session)

---

*Architecture research for: uni-volunteer-scheduler (brownfield FastAPI + React)*
*Researched: 2026-04-08*
