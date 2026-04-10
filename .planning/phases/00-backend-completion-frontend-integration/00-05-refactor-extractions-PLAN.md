---
phase: 00-backend-completion-frontend-integration
plan: 05
type: execute
wave: 3
depends_on: [02, 03, 04]
files_modified:
  - backend/app/signup_service.py
  - backend/app/emails.py
  - backend/app/utils.py
  - backend/app/deps.py
  - backend/app/routers/signups.py
  - backend/app/routers/admin.py
  - backend/app/routers/events.py
  - backend/app/routers/users.py
  - backend/app/routers/slots.py
  - backend/app/celery_app.py
  - backend/app/main.py
autonomous: true
requirements:
  - REFACTOR-01
  - REFACTOR-02
  - AUDIT-02
  - AUDIT-03
must_haves:
  truths:
    - "signup_service.promote_waitlist_fifo is the only waitlist promotion path used by signups.py and admin.py"
    - "emails.py exports one function per transactional notification type and celery_app.py uses them instead of inline bodies"
    - "utils.py centralizes shared datetime/helper utilities (no duplicate definitions in routers)"
    - "deps.py exposes ensure_event_owner_or_admin and all routers import it"
    - "No occurrences of .dict() on Pydantic models in events.py, users.py, slots.py"
    - "update_me whitelists mutable fields (no setattr loop over arbitrary keys)"
    - "All 4xx/5xx HTTPException responses across auth/signups/admin/portals/slots/events routers return JSON shape {error, code, detail} via a global exception handler in main.py"
  artifacts:
    - path: "backend/app/signup_service.py"
      provides: "promote_waitlist_fifo with canonical (created_at, id) ordering"
      exports: ["promote_waitlist_fifo"]
    - path: "backend/app/emails.py"
      provides: "One function per notification kind (confirmation, cancellation, reminder_24h)"
      exports: ["send_confirmation", "send_cancellation", "send_reminder_24h"]
    - path: "backend/app/utils.py"
      provides: "Shared helpers (timezone utilities, etc.)"
  key_links:
    - from: "backend/app/routers/signups.py::cancel_signup"
      to: "backend/app/signup_service.py::promote_waitlist_fifo"
      via: "import + call"
      pattern: "from app.signup_service import promote_waitlist_fifo"
    - from: "backend/app/routers/admin.py"
      to: "backend/app/signup_service.py::promote_waitlist_fifo"
      via: "import + call (dedupes local copy)"
      pattern: "promote_waitlist_fifo"
    - from: "backend/app/celery_app.py::send_email_notification"
      to: "backend/app/emails.py::send_*"
      via: "dispatch table by kind"
      pattern: "from app.emails import"
---

<objective>
Extract the three bundled refactors from CONTEXT.md's "Refactors bundled into Phase 0" decision: `signup_service.py` (canonical waitlist promotion), `emails.py` (per-kind transactional email functions), and `utils.py`/`deps.py` centralization. Also complete the in-scope tech-debt cleanups (`.dict()` → `.model_dump()`, `update_me` whitelist).

Purpose: The waitlist ordering divergence between `signups.py` and `admin.py` is a latent correctness bug the Plan 07 cancel E2E will expose. The inline email bodies prevent Plan 06 tests from asserting notification content cleanly. These must land before the test plans run.
Output: Single source of truth for waitlist promotion and emails; routers thinned; tech-debt cleanups complete.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/00-backend-completion-frontend-integration/00-CONTEXT.md
@.planning/phases/00-backend-completion-frontend-integration/00-RESEARCH.md
@.planning/phases/00-backend-completion-frontend-integration/00-02-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-03-SUMMARY.md
@.planning/phases/00-backend-completion-frontend-integration/00-04-SUMMARY.md
@backend/app/routers/signups.py
@backend/app/routers/admin.py
@backend/app/routers/events.py
@backend/app/routers/users.py
@backend/app/routers/slots.py
@backend/app/celery_app.py
@backend/app/deps.py
@backend/app/models.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extract signup_service.promote_waitlist_fifo and rewire signups.py + admin.py</name>
  <files>backend/app/signup_service.py, backend/app/routers/signups.py, backend/app/routers/admin.py</files>
  <read_first>
    - backend/app/routers/signups.py (find the cancel handler and any waitlist promotion code)
    - backend/app/routers/admin.py (find the admin_cancel_signup handler and duplicate waitlist logic — research flagged ordering divergence)
    - backend/app/models.py (Signup, Slot, SignupStatus)
    - 00-CONTEXT.md "Refactors bundled into Phase 0" — `signup_service.py` bullet
    - 00-RESEARCH.md "Architecture Patterns" section discussing waitlist ordering
  </read_first>
  <action>
    1. Create `backend/app/signup_service.py`:
       ```python
       """Canonical signup service operations.

       Single source of truth for:
       - promote_waitlist_fifo: promote the oldest waitlisted signup when capacity frees
       """
       from datetime import datetime, timezone
       from sqlalchemy.orm import Session
       from app.models import Signup, SignupStatus, Slot

       def promote_waitlist_fifo(db: Session, slot_id: int) -> Signup | None:
           """Promote the first-in waitlisted signup for this slot, if any.

           Canonical ordering: (created_at ASC, id ASC). Uses SELECT FOR UPDATE
           on the slot to serialize concurrent cancels. Returns the promoted
           Signup or None if the waitlist is empty.
           """
           slot = db.query(Slot).filter(Slot.id == slot_id).with_for_update().one()
           next_up = (
               db.query(Signup)
               .filter(Signup.slot_id == slot_id, Signup.status == SignupStatus.waitlisted)
               .order_by(Signup.created_at.asc(), Signup.id.asc())
               .with_for_update(skip_locked=True)
               .first()
           )
           if not next_up:
               return None
           next_up.status = SignupStatus.confirmed
           next_up.updated_at = datetime.now(timezone.utc)
           db.flush()
           return next_up
       ```
    2. In `backend/app/routers/signups.py::cancel_signup`, replace any inline waitlist promotion with `from app.signup_service import promote_waitlist_fifo` and a single call site: `promoted = promote_waitlist_fifo(db, signup.slot_id)` — then use the return value to trigger the confirmation email for `promoted` via the emails module (Task 2 wires it).
    3. In `backend/app/routers/admin.py::admin_cancel_signup` (or equivalent), remove the duplicate local waitlist logic and call `promote_waitlist_fifo` the same way.
    4. Do NOT drop the `current_count` column or alter its update logic — CONTEXT.md explicitly defers this. Add a module-level comment in `signup_service.py`: `# NOTE: current_count is defensively updated by the caller; do not touch here.`
  </action>
  <verify>
    <automated>cd backend && grep -q "def promote_waitlist_fifo" backend/app/signup_service.py && grep -q "from app.signup_service import promote_waitlist_fifo" backend/app/routers/signups.py && grep -q "from app.signup_service import promote_waitlist_fifo" backend/app/routers/admin.py && python -c "from app.signup_service import promote_waitlist_fifo; from app.routers import signups, admin; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/app/signup_service.py` exists
    - `grep -q "def promote_waitlist_fifo" backend/app/signup_service.py` succeeds
    - `grep -q "order_by(Signup.created_at.asc(), Signup.id.asc())" backend/app/signup_service.py` succeeds
    - `grep -q "with_for_update" backend/app/signup_service.py` succeeds
    - `grep -q "from app.signup_service import promote_waitlist_fifo" backend/app/routers/signups.py` succeeds
    - `grep -q "from app.signup_service import promote_waitlist_fifo" backend/app/routers/admin.py` succeeds
    - `python -c "from app.routers import signups, admin"` exits 0
  </acceptance_criteria>
  <done>Single waitlist promotion function; both routers import it; divergent ordering eliminated.</done>
</task>

<task type="auto">
  <name>Task 2: Extract emails.py and rewire celery_app dispatch + cancel confirmation</name>
  <files>backend/app/emails.py, backend/app/celery_app.py, backend/app/routers/signups.py</files>
  <read_first>
    - backend/app/celery_app.py (find every inline email body — expected kinds: confirmation, cancellation, reminder_24h)
    - backend/app/routers/signups.py (cancel handler — find any inline email composition)
    - backend/app/routers/admin.py (broadcast/notify vectors — leave untouched but note in SUMMARY)
    - 00-CONTEXT.md "Refactors bundled into Phase 0" — emails.py bullet
  </read_first>
  <action>
    1. Create `backend/app/emails.py`:
       ```python
       """Transactional email builders.

       One function per notification kind. Each returns a dict the SendGrid
       helper consumes: {to, subject, html, text}.
       """
       from app.models import Signup

       def send_confirmation(signup: Signup) -> dict:
           return {
               "to": signup.user.email,
               "subject": f"You're signed up: {signup.slot.event.name}",
               "html": f"<p>Confirmed for {signup.slot.event.name} on {signup.slot.start_time.isoformat()}.</p>",
               "text": f"Confirmed for {signup.slot.event.name} on {signup.slot.start_time.isoformat()}.",
           }

       def send_cancellation(signup: Signup) -> dict:
           return {
               "to": signup.user.email,
               "subject": f"Signup cancelled: {signup.slot.event.name}",
               "html": f"<p>Your signup for {signup.slot.event.name} has been cancelled.</p>",
               "text": f"Your signup for {signup.slot.event.name} has been cancelled.",
           }

       def send_reminder_24h(signup: Signup) -> dict:
           return {
               "to": signup.user.email,
               "subject": f"Reminder: {signup.slot.event.name} tomorrow",
               "html": f"<p>Reminder: {signup.slot.event.name} at {signup.slot.start_time.isoformat()}.</p>",
               "text": f"Reminder: {signup.slot.event.name} at {signup.slot.start_time.isoformat()}.",
           }

       BUILDERS = {
           "confirmation": send_confirmation,
           "cancellation": send_cancellation,
           "reminder_24h": send_reminder_24h,
       }
       ```
    2. In `backend/app/celery_app.py::send_email_notification`:
       - Replace the inline email body construction with:
         ```python
         from app.emails import BUILDERS
         builder = BUILDERS.get(kind)
         if builder is None:
             raise ValueError(f"Unknown notification kind: {kind}")
         payload = builder(signup)
         ```
       - Pass `payload` to the existing SendGrid helper.
       - On success, write the `Notification` row as today (content fields populated from `payload`).
    3. In `backend/app/routers/signups.py::cancel_signup`, after a successful cancel + `promote_waitlist_fifo`:
       - Enqueue `send_email_notification.delay(signup_id=cancelled.id, kind="cancellation")`.
       - If a waitlist row was promoted, also enqueue `send_email_notification.delay(signup_id=promoted.id, kind="confirmation")`.
    4. Do NOT refactor admin.py broadcast emails — those are deferred (CONTEXT.md explicitly defers broadcast templating).
  </action>
  <verify>
    <automated>cd backend && test -f backend/app/emails.py && grep -q "BUILDERS" backend/app/emails.py && grep -q "from app.emails import" backend/app/celery_app.py && grep -q 'kind="cancellation"' backend/app/routers/signups.py && grep -q 'kind="confirmation"' backend/app/routers/signups.py && python -c "from app.emails import BUILDERS; assert set(BUILDERS.keys()) == {'confirmation','cancellation','reminder_24h'}; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/app/emails.py` exists
    - `grep -q "BUILDERS" backend/app/emails.py` succeeds
    - `grep -q "confirmation" backend/app/emails.py` succeeds
    - `grep -q "cancellation" backend/app/emails.py` succeeds
    - `grep -q "reminder_24h" backend/app/emails.py` succeeds
    - `grep -q "from app.emails import" backend/app/celery_app.py` succeeds
    - `grep -q 'kind="cancellation"' backend/app/routers/signups.py` succeeds
    - `python -c "from app.emails import BUILDERS; assert len(BUILDERS) == 3"` exits 0
  </acceptance_criteria>
  <done>All transactional email bodies live in emails.py; celery_app dispatches by kind; cancel flow enqueues cancellation + (conditional) confirmation emails.</done>
</task>

<task type="auto">
  <name>Task 3: Centralize utils.py + deps.ensure_event_owner_or_admin, fix .dict() and update_me whitelist</name>
  <files>backend/app/utils.py, backend/app/deps.py, backend/app/routers/events.py, backend/app/routers/users.py, backend/app/routers/slots.py</files>
  <read_first>
    - backend/app/deps.py (find any duplicate `_ensure_event_owner_or_admin` or similar helpers)
    - backend/app/routers/events.py (find local copies of ownership checks; find `.dict(` calls)
    - backend/app/routers/users.py (find `update_me` handler — look for setattr loop over arbitrary keys)
    - backend/app/routers/slots.py (find `.dict(` calls)
    - 00-CONTEXT.md "Tech-debt cleanups" block
    - 00-RESEARCH.md "Pitfall 2: Pydantic .dict() Deprecation" and "Pitfall 7: update_me Privilege Escalation"
  </read_first>
  <action>
    1. Create `backend/app/utils.py` (if not already created in a prior plan):
       ```python
       """Shared utilities for routers and services."""
       from datetime import datetime, timezone

       def utcnow() -> datetime:
           """Timezone-aware UTC now. Use instead of datetime.utcnow()."""
           return datetime.now(timezone.utc)
       ```
    2. In `backend/app/deps.py`, define (or move) a single canonical helper:
       ```python
       from fastapi import HTTPException, status
       from app.models import Event, User

       def ensure_event_owner_or_admin(event: Event, user: User) -> None:
           if user.is_admin:
               return
           if event.owner_id != user.id:
               raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not event owner")
       ```
       Remove duplicate copies from `routers/events.py` and any other router that redefined it. Routers import: `from app.deps import ensure_event_owner_or_admin`.
    3. In `routers/events.py`, `routers/users.py`, `routers/slots.py`, replace every `payload.dict(exclude_unset=True)` or `payload.dict()` with `payload.model_dump(exclude_unset=True)`. Do the same for any other Pydantic v1-style `.dict()` call on a BaseModel instance.
    4. In `routers/users.py::update_me`:
       - Define a module-level constant: `_USER_UPDATE_ALLOWED_FIELDS = {"name", "phone"}` (confirm the exact allow-list by reading `UserUpdate` schema; exclude `is_admin`, `email`, `password_hash`, `id`, `created_at`).
       - Replace any `for k, v in payload.dict().items(): setattr(user, k, v)` with:
         ```python
         data = payload.model_dump(exclude_unset=True)
         for k, v in data.items():
             if k not in _USER_UPDATE_ALLOWED_FIELDS:
                 continue
             setattr(user, k, v)
         ```
    5. Do NOT touch admin.py's user-update path — it has its own (intended) elevated permissions. Leave the admin endpoint as is.
  </action>
  <verify>
    <automated>cd backend && test -f backend/app/utils.py && grep -q "def ensure_event_owner_or_admin" backend/app/deps.py && grep -q "from app.deps import ensure_event_owner_or_admin" backend/app/routers/events.py && ! grep -rn "\.dict(exclude_unset" backend/app/routers/ && ! grep -rn "\.dict()" backend/app/routers/events.py backend/app/routers/users.py backend/app/routers/slots.py && grep -q "_USER_UPDATE_ALLOWED_FIELDS" backend/app/routers/users.py && python -c "from app.routers import events, users, slots, signups, admin; from app import deps, utils; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - File `backend/app/utils.py` exists
    - `grep -q "def ensure_event_owner_or_admin" backend/app/deps.py` succeeds
    - `grep -q "from app.deps import ensure_event_owner_or_admin" backend/app/routers/events.py` succeeds
    - `grep -rn "\.dict(exclude_unset" backend/app/routers/` returns empty
    - `grep -q "model_dump(exclude_unset=True)" backend/app/routers/events.py` succeeds
    - `grep -q "model_dump(exclude_unset=True)" backend/app/routers/users.py` succeeds
    - `grep -q "model_dump(exclude_unset=True)" backend/app/routers/slots.py` succeeds
    - `grep -q "_USER_UPDATE_ALLOWED_FIELDS" backend/app/routers/users.py` succeeds
    - `python -c "from app.routers import events, users, slots, signups, admin"` exits 0
  </acceptance_criteria>
  <done>Shared helpers centralized; Pydantic deprecation warnings gone from the three named files; update_me no longer permits arbitrary setattr.</done>
</task>


<task type="auto">
  <name>Task 4: Add global HTTPException handler enforcing {error, code, detail} response shape (AUDIT-03)</name>
  <files>backend/app/main.py, backend/app/routers/auth.py, backend/app/routers/signups.py, backend/app/routers/admin.py, backend/app/routers/portals.py, backend/app/routers/slots.py, backend/app/routers/events.py</files>
  <read_first>
    - backend/app/main.py (locate FastAPI app construction and existing exception handlers if any)
    - backend/app/routers/auth.py, signups.py, admin.py, portals.py, slots.py, events.py (grep for `raise HTTPException` to see current detail shapes)
    - 00-RESEARCH.md AUDIT-03 row and error-shape analysis
  </read_first>
  <action>
    1. In `backend/app/main.py`, after `app = FastAPI(...)` and after any existing middleware, register a global exception handler:
       ```python
       from fastapi import Request
       from fastapi.exceptions import HTTPException as FastAPIHTTPException
       from fastapi.responses import JSONResponse
       from starlette.exceptions import HTTPException as StarletteHTTPException

       @app.exception_handler(StarletteHTTPException)
       async def http_exception_handler(request: Request, exc: StarletteHTTPException):
           """Normalize every HTTPException into {error, code, detail} (AUDIT-03).

           - error:  short machine-readable slug derived from status code
                     (e.g. 'http_401', 'http_403', 'http_404')
           - code:   when the raising site passed a dict detail with a 'code' key,
                     surface that; else the same status-code slug
           - detail: the original string detail (or detail['detail'] when dict)
           """
           status_code = exc.status_code
           raw = exc.detail
           if isinstance(raw, dict):
               code = raw.get("code", f"http_{status_code}")
               detail = raw.get("detail", raw.get("message", ""))
               error = raw.get("error", f"http_{status_code}")
           else:
               code = f"http_{status_code}"
               detail = raw if isinstance(raw, str) else str(raw)
               error = f"http_{status_code}"
           return JSONResponse(
               status_code=status_code,
               content={"error": error, "code": code, "detail": detail},
           )
       ```
    2. Walk every router file listed in `<files>` and verify existing `raise HTTPException(...)` call sites. Where a router currently raises with a bare string that carries a known semantic code (e.g. `AUTH_REFRESH_INVALID`, `SIGNUP_CAPACITY_FULL`), convert to the dict form so the handler can surface the code:
       ```python
       raise HTTPException(status_code=401, detail={"code": "AUTH_REFRESH_INVALID", "detail": "refresh token invalid"})
       ```
       Only convert call sites whose code is referenced by Plan 06 tests (`AUTH_REFRESH_INVALID` in `auth.py` is the canonical example). Leave other raises alone — the handler will still wrap them into `{error, code, detail}` using the default slug.
    3. Do NOT alter pydantic validation errors (422). Do NOT register a generic `Exception` handler — only `HTTPException` per AUDIT-03 scope.
  </action>
  <verify>
    <automated>cd backend && grep -q "@app.exception_handler" backend/app/main.py && grep -q "http_exception_handler" backend/app/main.py && grep -qE '"error".*"code".*"detail"' backend/app/main.py && grep -q 'AUTH_REFRESH_INVALID' backend/app/routers/auth.py && python -c "from app.main import app; handlers = app.exception_handlers; from starlette.exceptions import HTTPException as SHE; assert SHE in handlers, 'HTTPException handler not registered'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "@app.exception_handler" backend/app/main.py` succeeds
    - `grep -q "http_exception_handler" backend/app/main.py` succeeds
    - `grep -qE '"error".*"code".*"detail"' backend/app/main.py` succeeds (all three keys present in handler body)
    - `grep -q "StarletteHTTPException\|HTTPException" backend/app/main.py` succeeds
    - `grep -q 'AUTH_REFRESH_INVALID' backend/app/routers/auth.py` succeeds (canonical coded raise in place)
    - `python -c "from starlette.exceptions import HTTPException as SHE; from app.main import app; assert SHE in app.exception_handlers"` exits 0
    - No router in `backend/app/routers/` returns a response body missing any of `error`/`code`/`detail` for a 4xx — enforced by Plan 06 `test_error_response_shape` probing auth, signups, and admin routers
  </acceptance_criteria>
  <done>Global HTTPException handler registered in main.py; every 4xx/5xx crossing FastAPI is normalized to `{error, code, detail}`; Plan 06 tests can assert the shape across multiple routers.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| PATCH /users/me → user model | User-controlled payload crossing into ORM; privilege escalation vector |
| Cancel signup → waitlist promotion | Concurrent cancels could double-promote without row locks |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-00-18 | Elevation of Privilege | `update_me` setattr over arbitrary keys could set `is_admin=True` | mitigate | Explicit `_USER_UPDATE_ALLOWED_FIELDS` whitelist; test added in Plan 06 asserts 403 or silent drop on admin field |
| T-00-19 | Tampering | Concurrent cancels double-promoting same waitlist row | mitigate | `SELECT FOR UPDATE` on slot + `SELECT FOR UPDATE SKIP LOCKED` on waitlist row; single canonical function |
| T-00-20 | Repudiation | Inline email bodies untestable | mitigate | Centralized `BUILDERS` dict in emails.py; Plan 06 asserts exact `subject`/`to` content |
| T-00-21 | Information Disclosure | Event ownership bypass via duplicate inconsistent helper | mitigate | Single `ensure_event_owner_or_admin` in deps.py; all routers import the same function |
| T-00-22 | Information Disclosure | Inconsistent 4xx error shapes leak stack context or expose undocumented fields | mitigate | Global `@app.exception_handler(HTTPException)` in main.py normalizes every error to `{error, code, detail}`; Plan 06 asserts shape across ≥3 routers |
</threat_model>

<verification>
- `grep -q "promote_waitlist_fifo" backend/app/signup_service.py` succeeds
- `grep -q "BUILDERS" backend/app/emails.py` succeeds
- `grep -q "_USER_UPDATE_ALLOWED_FIELDS" backend/app/routers/users.py` succeeds
- `grep -rn "\.dict(exclude_unset" backend/app/routers/` returns empty
- `grep -q "@app.exception_handler" backend/app/main.py` succeeds
- `grep -qE '"error".*"code".*"detail"' backend/app/main.py` succeeds
- `python -c "from app.routers import events, users, slots, signups, admin"` exits 0
</verification>

<success_criteria>
Three refactors landed (signup_service, emails, utils/deps); three tech-debt cleanups landed (.dict→.model_dump, update_me whitelist, shared ownership helper); global HTTPException handler enforces `{error, code, detail}` shape across all routers (AUDIT-03); all imports clean.
</success_criteria>

<output>
After completion, create `.planning/phases/00-backend-completion-frontend-integration/00-05-SUMMARY.md`
</output>
