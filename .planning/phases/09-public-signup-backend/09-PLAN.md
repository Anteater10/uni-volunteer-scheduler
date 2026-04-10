---
phase: 09-public-signup-backend
plan: 01
type: execute
wave: 1
depends_on: [08-schema-realignment-migration]
autonomous: true
files_modified:
  - backend/app/magic_link_service.py
  - backend/app/emails.py
  - backend/app/celery_app.py
  - backend/app/routers/admin.py
  - backend/app/routers/magic.py
  - backend/app/routers/signups.py
  - backend/app/routers/roster.py
  - backend/app/routers/users.py
  - backend/app/schemas.py
  - backend/app/main.py
  - backend/app/config.py
  - backend/app/services/phone_service.py
  - backend/app/services/volunteer_service.py
  - backend/app/services/public_signup_service.py
  - backend/app/services/orientation_service.py
  - backend/app/routers/public/__init__.py
  - backend/app/routers/public/events.py
  - backend/app/routers/public/signups.py
  - backend/app/routers/public/orientation.py
  - backend/app/email_templates/signup_confirm.html
  - backend/alembic/versions/0010_phase09_notifications_volunteer_fk.py
  - backend/tests/fixtures/factories.py
  - backend/tests/test_signups.py
  - backend/tests/test_check_in_endpoints.py
  - backend/tests/test_check_in_service.py
  - backend/tests/test_concurrent_check_in.py
  - backend/tests/test_models_magic_link.py
  - backend/tests/test_models_phase3.py
  - backend/tests/test_magic_link_service.py
  - backend/tests/test_magic_link_router.py
  - backend/tests/test_notifications_phase6.py
  - backend/tests/test_celery_reminders.py
  - backend/tests/test_admin.py
  - backend/tests/test_admin_phase7.py
  - backend/tests/test_roster_endpoints.py
  - backend/tests/test_contract.py
  - backend/tests/test_phone_service.py
  - backend/tests/test_public_events.py
  - backend/tests/test_public_signups_create.py
  - backend/tests/test_public_signups_confirm.py
  - backend/tests/test_public_signups_manage.py
  - backend/tests/test_public_orientation.py
  - backend/tests/test_magic_link_signup_purpose.py
  - backend/tests/test_expired_pending_cleanup.py
  - backend/tests/test_phase09_smoke.py
  - scripts/smoke_phase09.sh
requirements:
  - R09-01  # Volunteer upsert by email
  - R09-02  # POST /public/signups creates N signups
  - R09-03  # Confirm token flips pending → confirmed (batch)
  - R09-04  # Orientation-status endpoint (all-time scope)
  - R09-05  # Phone normalization (E.164, 422 on bad input)
  - R09-06  # Un-skip 74 tests at new baseline
  - R09-07  # GET /public/events filters by quarter+year+week+school
  - R09-08  # GET /public/events/{id} single event detail
  - R09-09  # Magic-link purpose refactor (signup_confirm/signup_manage, 14-day TTL)
  - R09-10  # Rate limiting on every /public/* route
  - R09-11  # Expired-pending cleanup (Celery beat, 14-day hard delete)
  - R09-12  # notifications schema migration 0010 (volunteer_id, CHECK constraint)
  - R09-13  # App boot gate and full integration smoke
must_haves:
  truths:
    - "python -c 'from app.main import app' exits 0 with no ImportError/AttributeError"
    - "pytest -q runs cleanly at a documented new baseline (target: 76 passed + ~73 un-skipped + new tests; 0 failed, ≤1 skipped)"
    - "POST /api/v1/public/signups with a new email creates exactly 1 Volunteer row and N Signup rows (one per slot_id), all status=pending"
    - "POST /api/v1/public/signups with an existing email does NOT create a duplicate Volunteer; signups attach to the existing row"
    - "Phone '805-555-1234' round-trips to '+18055551234'; phone 'not-a-phone' returns 422 with InvalidPhoneError message"
    - "POST /api/v1/public/signups/confirm?token=XXX flips all pending signups created in that batch to confirmed; second call is idempotent"
    - "Expired/used/unknown confirm tokens return 400 with a clear error, never 500"
    - "GET /api/v1/public/events?quarter=spring&year=2026&week=4 returns only events matching all three filters; optional school further narrows"
    - "GET /api/v1/public/events/{id} returns the event with slots and current filled/capacity for each slot"
    - "GET /api/v1/public/signups/manage?token=XXX returns that volunteer's upcoming signups for the token's event scope"
    - "DELETE /api/v1/public/signups/{id}?token=XXX cancels one signup only when the token is bound to the owning volunteer; other volunteers' tokens return 403"
    - "GET /api/v1/public/orientation-status?email=X returns identical response shape whether email exists or not (enumeration defense); true when any past attended orientation exists under that email (all-time)"
    - "11 POSTs to /public/signups from one IP in 60s: the 11th returns 429"
    - "alembic upgrade head → downgrade base → upgrade head round-trips cleanly including migration 0010 (no DuplicateObject, no FK violation)"
    - "A Celery beat task deletes pending signups whose signup_confirm token is >14 days old; the unit test confirms deletion with time travel"
    - "scripts/smoke_phase09.sh completes the full curl loop: create → confirm → manage → cancel-one, all green"
  artifacts:
    - path: "backend/alembic/versions/0010_phase09_notifications_volunteer_fk.py"
      provides: "notifications.volunteer_id FK, user_id nullable, CHECK constraint (exactly one of user_id/volunteer_id set)"
      contains: "def upgrade, def downgrade, CHECK constraint notifications_recipient_xor"
    - path: "backend/app/services/phone_service.py"
      provides: "normalize_us_phone(raw) -> E.164 str; raises InvalidPhoneError"
      exports: ["normalize_us_phone", "InvalidPhoneError"]
    - path: "backend/app/services/volunteer_service.py"
      provides: "upsert_volunteer_by_email via pg_insert.on_conflict_do_update"
      exports: ["upsert_volunteer"]
    - path: "backend/app/services/public_signup_service.py"
      provides: "create_public_signup — volunteer upsert + per-slot Signup rows + issue_token + enqueue confirmation email"
      exports: ["create_public_signup"]
    - path: "backend/app/services/orientation_service.py"
      provides: "has_attended_orientation(email) -> bool (all-time, enumeration-safe)"
      exports: ["has_attended_orientation", "OrientationStatus"]
    - path: "backend/app/routers/public/events.py"
      provides: "GET /public/events, GET /public/events/{event_id}"
      exports: ["router"]
    - path: "backend/app/routers/public/signups.py"
      provides: "POST /public/signups, POST /public/signups/confirm, GET /public/signups/manage, DELETE /public/signups/{id}"
      exports: ["router"]
    - path: "backend/app/routers/public/orientation.py"
      provides: "GET /public/orientation-status?email="
      exports: ["router"]
    - path: "backend/app/email_templates/signup_confirm.html"
      provides: "Jinja/string.Template signup confirmation email body"
      contains: "$volunteer_first_name, $slot_list, $confirm_url"
    - path: "scripts/smoke_phase09.sh"
      provides: "Manual curl smoke script driving the full signup→confirm→manage→cancel loop"
      contains: "curl -X POST /api/v1/public/signups, curl /confirm, curl /manage, curl -X DELETE"
  key_links:
    - from: "backend/app/routers/public/signups.py"
      to: "backend/app/services/public_signup_service.py::create_public_signup"
      via: "service call from POST /public/signups handler"
      pattern: "create_public_signup\\("
    - from: "backend/app/services/public_signup_service.py"
      to: "backend/app/magic_link_service.py::issue_token"
      via: "issue signup_confirm token with 14-day TTL"
      pattern: "issue_token\\(.*purpose=MagicLinkPurpose.SIGNUP_CONFIRM"
    - from: "backend/app/magic_link_service.py::consume_token"
      to: "SignupStatus.confirmed"
      via: "batch flip on signup_confirm purpose via volunteer_id+event_id join"
      pattern: "SignupStatus\\.confirmed"
    - from: "backend/app/routers/public/signups.py"
      to: "backend/app/deps.py::rate_limit"
      via: "Depends(rate_limit(max_requests=10, window_seconds=60)) on POST"
      pattern: "rate_limit\\(max_requests=10"
    - from: "backend/app/celery_app.py"
      to: "Signup.volunteer (not Signup.user)"
      via: "reminder/weekly_digest task body"
      pattern: "signup\\.volunteer"
    - from: "backend/app/celery_app.py::expire_pending_signups"
      to: "Signup hard delete"
      via: "Celery beat schedule entry"
      pattern: "beat_schedule.*expire_pending"
---

<objective>
Turn the Phase 08 schema into a working, tested, public HTTP surface for volunteer
signups. After this plan the app boots, `pytest -q` runs green at a documented new
baseline, and a curl user can complete the full signup → confirm → manage → cancel
loop against the backend.

Purpose: Unblock Phase 10 (frontend browse + signup form). Phase 10 needs exact
endpoint shapes, error responses, and rate-limit behavior — this plan delivers
all three, plus handoff notes in 09-SUMMARY.md.

Output: boot-fixed existing code, migration 0010, 4 new services, 3 new public
routers, new Pydantic schemas, new confirmation email template + Celery task,
expired-pending cleanup beat task, ~73 un-skipped tests, ~20 new tests, a curl
smoke script, and 09-SUMMARY.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS-v1.1-accountless.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-schema-realignment-migration/08-SUMMARY.md
@.planning/phases/08-schema-realignment-migration/08-VERIFICATION.md
@.planning/phases/09-public-signup-backend/09-RESEARCH.md
@CLAUDE.md

# Boot-fix target files (read before editing)
@backend/app/magic_link_service.py
@backend/app/emails.py
@backend/app/celery_app.py
@backend/app/routers/admin.py
@backend/app/routers/magic.py
@backend/app/routers/signups.py
@backend/app/routers/roster.py
@backend/app/routers/users.py
@backend/app/models.py
@backend/app/schemas.py
@backend/app/deps.py
@backend/app/config.py
@backend/app/main.py
@backend/tests/fixtures/factories.py
@backend/conftest.py
</context>

<interfaces>
<!-- Critical contracts extracted from Phase 08 schema + existing services. -->
<!-- Executor should use these directly — no further codebase exploration required. -->

### Models (backend/app/models.py — already landed by Phase 08)

```python
class Volunteer(Base):
    id: UUID  # PK, gen_random_uuid
    email: str  # UNIQUE, lowercased
    first_name: str
    last_name: str
    phone_e164: str | None
    created_at: datetime
    updated_at: datetime
    signups: relationship("Signup", back_populates="volunteer")

class Signup(Base):
    id: UUID
    volunteer_id: UUID  # FK volunteers.id ON DELETE RESTRICT, NOT NULL
    slot_id: UUID       # FK slots.id
    status: SignupStatus  # pending | confirmed | cancelled | checked_in | attended
    # no user_id column any more
    volunteer: relationship("Volunteer", back_populates="signups")
    slot: relationship("Slot")
    # UNIQUE (volunteer_id, slot_id)

class Slot(Base):
    id: UUID
    event_id: UUID
    slot_type: SlotType  # orientation | period
    date: date
    start_time: datetime
    end_time: datetime
    location: str | None
    capacity: int
    current_count: int

class Event(Base):
    id: UUID
    title: str
    quarter: Quarter  # winter | spring | summer | fall
    year: int
    week_number: int  # 1-11
    module_slug: str
    school: str
    start_date: date
    end_date: date

class MagicLinkToken(Base):
    id: UUID
    token_hash: str  # SHA-256
    signup_id: UUID  # NOT NULL (anchor signup)
    volunteer_id: UUID | None  # nullable FK added Phase 08
    email: str
    purpose: MagicLinkPurpose  # email_confirm | check_in | signup_confirm | signup_manage
    expires_at: datetime
    consumed_at: datetime | None

class Notification(Base):
    id: UUID
    user_id: UUID  # currently NOT NULL FK users.id — migration 0010 makes this nullable and adds volunteer_id
    # (post-0010) volunteer_id: UUID | None FK volunteers.id
    kind: NotificationType
    sent_at: datetime
```

### Existing services to reuse

```python
# backend/app/deps.py
def rate_limit(max_requests: int = 100, window_seconds: int = 60) -> Callable
    # Redis-backed per-IP+path counter. Raises 429.

# backend/app/magic_link_service.py (TO BE REFACTORED in Task 3)
# NEW signature after this plan:
def issue_token(
    db: Session,
    signup: Signup,
    email: str,
    *,
    purpose: MagicLinkPurpose = MagicLinkPurpose.SIGNUP_CONFIRM,
    volunteer_id: UUID | None = None,
    ttl_minutes: int | None = None,
) -> str

def consume_token(db: Session, raw_token: str) -> ConsumeResult
    # For SIGNUP_CONFIRM purpose: batch-flip all pending signups where
    # volunteer_id == token.volunteer_id AND slot.event_id == anchor.slot.event_id

# backend/app/celery_app.py
def send_email_notification(signup_id: str, kind: str) -> None
    # Existing reminder pipeline. Fix signup.user -> signup.volunteer inside.

# NEW task to add:
def send_signup_confirmation_email(
    volunteer_id: str,
    signup_ids: list[str],
    token: str,
    event_id: str,
) -> None
    # Uses email_templates/signup_confirm.html; logs to Celery logger (no Notification row).
```

### Route prefix

All new routers mount under `/api/v1/public` via `app.include_router(..., prefix="/api/v1")`
where each router already carries its own `/public` prefix.
</interfaces>

<locked_decisions>
The following are NON-NEGOTIABLE, set by Andy before planning. If any task
seems to contradict these, re-read the decision — the decision wins.

- **D-01 Signup status on creation = `pending`.** Reuse the existing `SignupStatus`
  enum value. No new migration for status values.
- **D-02 Pending signups COUNT against capacity.** (Research recommended the
  opposite; Andy overrode.) Capacity is checked against `current_count` that
  includes both `pending` and `confirmed`. Mitigation: the 14-day expired-pending
  cleanup task (Task 12) hard-deletes stale pendings.
- **D-03 Orientation-status scope = all-time, no filters.** Any past `attended`
  orientation signup for that email counts. No quarter/module filter.
- **D-04 Notifications migration 0010:** add `volunteer_id UUID FK volunteers
  nullable`, make `user_id` nullable, CHECK constraint `exactly one of
  (user_id, volunteer_id) is NOT NULL`. Use `postgresql.ENUM(..., create_type=False)`
  pattern if touching enums. Downgrade must `DROP TYPE` any new enums.
- **D-05 admin.py boot-fix = minimal rename ONLY.** Full admin rewrite is
  Phase 12. Any admin behavior that was genuinely tied to the user/prereq surface
  and no longer has a meaningful analog gets a stub returning a TODO response
  with a `# Phase 12: ...` comment. Do not redesign.
- **D-06 Magic-link refactor:** extend existing `magic_link_service.py` with
  `signup_confirm` and `signup_manage` purposes. Token lifetime = 14 days
  (20160 minutes). Token payload must include `volunteer_id`; the anchor
  `signup_id` stays on the row.
- **D-07 Phone normalization:** new `app/services/phone_service.py` with
  `normalize_us_phone(s) -> str` returning E.164 or raising `InvalidPhoneError`.
  Called during volunteer upsert.
- **D-08 Orientation-status enumeration defense:** endpoint returns the same
  shape regardless of whether email exists. No 404 for missing email. Rate
  limit (5/min/IP) bounds the oracle.
- **D-09 Rate limiting:** use existing `app.deps.rate_limit()` on every
  `/public/*` route. POST /signups = 10/min/IP. Reads = 60/min/IP.
- **D-10 Bucket C test + old endpoint:** DELETE `test_contract.py::test_createSignup_trailing_slash`
  AND delete the old auth'd POST `/signups/` endpoint code. Public endpoint
  replaces it.
- **D-11 Notification row for volunteer emails = SKIP.** After migration 0010,
  the CHECK constraint allows volunteer rows, but the new confirmation email
  task still logs to the Celery logger only (no Notification row) — the dedup
  `kind` pattern doesn't fit one-off confirmation emails.
- **D-12 Email template:** Use existing `string.Template` + file-based pattern
  in `backend/app/email_templates/` (same system as `confirmation.html`). Do
  NOT use inline HTML strings.
- **D-13 Boot gate is a HARD prerequisite.** Task 1 MUST deliver a bootable app
  before any other code work begins. Task 1 verify = `python -c "from app.main import app"`
  exits 0.
</locked_decisions>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| public internet → /api/v1/public/* | unauthenticated caller supplies email, phone, slot_ids, tokens |
| email inbox → /public/signups/confirm | magic-link token arrives via SendGrid; user forwards/replays possible |
| Redis → rate_limit() | counter backend; loss of Redis = rate-limit bypass |
| Postgres → signups/volunteers | the only authoritative capacity/identity store |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-09-01 | Spoofing | POST /public/signups — attacker submits a real volunteer's email to fill their slots | HIGH | mitigate | Signup lands as `pending`; real owner does not receive a confirmation (wrong email typed = attacker's) → attacker owns the token but the slot is held. Cleanup task (Task 12) deletes after 14 days. Email-keyed rate limit on magic-link issue bounds spam volume. Full fix (email-owned identity proof) deferred to post-v1.1. Document as known residual. |
| T-09-02 | Spoofing | POST /public/signups — attacker submits arbitrary email they do not own to spam real inboxes | HIGH | mitigate | Per-IP rate limit 10/min (Task 7). Email-keyed rate limit via existing `check_rate_limit()` (5 magic-link emails per email per hour). Residual: distributed IPs bypass — accepted as out-of-scope for v1 per Andy. Documented in 09-SUMMARY. |
| T-09-03 | Tampering | Confirm token — attacker guesses token URL | NEGLIGIBLE | mitigate | `secrets.token_urlsafe(32)` = 256 bits of entropy. Only SHA-256 hash stored. Brute force infeasible. No new work. |
| T-09-04 | Tampering | Manage/cancel token — attacker reuses another volunteer's token to cancel signups | HIGH | mitigate | DELETE /public/signups/{id}?token= MUST verify `token.volunteer_id == signup.volunteer_id` before accepting cancel. 403 on mismatch. Test: `test_public_signups_manage::test_cross_volunteer_cancel_forbidden`. |
| T-09-05 | Repudiation | No audit log on public cancel | LOW | accept | Phase 11 adds audit log hooks. Phase 09 scope is "make it work"; audit deferred. Documented in 09-SUMMARY as handoff for Phase 11. |
| T-09-06 | Information Disclosure | GET /orientation-status leaks whether an email has ever volunteered | LOW | mitigate | Endpoint returns identical JSON shape for unknown emails (`{has_attended_orientation: false}`). No 404. Combined with 5/min/IP rate limit bounds oracle. Residual: repeated probing over days still reveals attendance — accepted, attendance is not sensitive health data. |
| T-09-07 | Information Disclosure | Phone number as PII in logs | MEDIUM | mitigate | `phone_service.normalize_us_phone()` normalizes input without logging the raw value. Public router must NOT log request bodies. Add `# noqa: log-scrub` comment on service boundary. Verification: grep for `logger.*phone` in public router — should be zero hits. |
| T-09-08 | Information Disclosure | SendGrid API key in env | MEDIUM | accept | Already managed by existing settings system (Phase 06). Phase 09 does not introduce new credential surfaces. Confirmed: no new secrets added to `config.py`. |
| T-09-09 | Denial of Service | Rate-limit bypass via distributed IPs (botnet) | MEDIUM | accept | Out-of-scope for v1 per Andy. Cloudflare/WAF at infra layer is Phase 15+. Documented in 09-SUMMARY residual-risk section. |
| T-09-10 | Denial of Service | Pending signups hold capacity (D-02); spammer fills slots | HIGH | mitigate | Expired-pending cleanup task (Task 12) runs daily and hard-deletes `pending` signups whose confirm token is >14 days old. Combined with T-09-02 mitigations, caps attacker window at 14 days. Residual: 14-day spam window is live — accepted for v1; tighten to 24h post-launch if abused. |
| T-09-11 | Elevation of Privilege | Public router accidentally wired behind `get_current_user` | LOW | mitigate | Explicit test `test_public_signups_create::test_no_auth_required` asserts 200 on POST without any headers. |
| T-09-12 | Elevation of Privilege | CHECK constraint on notifications (D-04) allows both user_id and volunteer_id set | MEDIUM | mitigate | Migration 0010 adds `CHECK ((user_id IS NOT NULL AND volunteer_id IS NULL) OR (user_id IS NULL AND volunteer_id IS NOT NULL))`. Test `test_expired_pending_cleanup.py::test_notifications_xor` attempts to insert a row violating the constraint and asserts IntegrityError. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Boot-fix pass — repair every `signup.user` / `user.name` site so the app imports</name>
  <files>
    backend/app/magic_link_service.py,
    backend/app/emails.py,
    backend/app/celery_app.py,
    backend/app/routers/admin.py,
    backend/app/routers/magic.py,
    backend/app/routers/signups.py,
    backend/app/routers/roster.py,
    backend/app/routers/users.py
  </files>
  <action>
    Minimal surgical edits to unbreak the import chain. Do NOT redesign behavior
    anywhere in this task. Per D-05, admin.py changes are minimal rename only.

    **Per the 08-SUMMARY runtime-breakage list, fix these exact sites:**

    1. `magic_link_service.py` line ~100 inside `dispatch_email()`:
       `signup.user.email` → `signup.volunteer.email`
       `signup.user` None-check → `signup.volunteer`

    2. `emails.py` lines ~56, 78, 101, 125, 150 — all 5 BUILDERS:
       - `user = signup.user` → `v = signup.volunteer`
       - `user.name` → `f"{v.first_name} {v.last_name}"`
       - `user.email` → `v.email`
       - Any `user.id` for templating → skip (volunteers don't have notify_email etc.)

    3. `celery_app.py`:
       - line ~141 inside `send_email_notification`: `signup.user` → `signup.volunteer`;
         replace `user.name` with `f"{v.first_name} {v.last_name}"`.
       - lines ~155-166: the `if user.notify_email` guard — Volunteer has no such
         field. Per D-11, for the reminder BUILDERS pipeline keep sending
         unconditionally (Volunteer opts-in implicitly by signing up). For the
         Notification row creation: SKIP inserting the Notification row when the
         signup is volunteer-backed (add `if signup.volunteer_id is not None: skip db log`).
         Migration 0010 (Task 2) will change this, but for this task the guard
         pattern keeps the task pipeline non-crashing.
       - line ~281 `weekly_digest`: `by_user.setdefault(s.user_id, [])` →
         `by_volunteer.setdefault(s.volunteer_id, [])`, rename local vars.

    4. `routers/admin.py` — per the SUMMARY list, lines ~205, 283, 369, 451, 539,
       587, 652, 654, 959. Apply the minimal rename ONLY:
       - `signup.user` → `signup.volunteer`
       - `signup.user.email` → `signup.volunteer.email`
       - `user.name` → `f"{v.first_name} {v.last_name}"` (with appropriate local binding)
       - If any line references a User field that has no Volunteer analog
         (e.g. `user.created_at` in a CCPA export that was user-scoped), stub
         the endpoint to return `{"detail": "retired: Phase 12 will reimplement"}`
         with status 501, and add `# Phase 12: see 09-SUMMARY deviation notes`.
         Record which lines you stubbed.
       - The `promote_waitlist_fifo` admin cancel path calls `dispatch_email()`
         which is fixed in step 1; no further action here.

    5. `routers/magic.py` — the resend endpoint's `Signup.user.has(email=...)`
       join needs to become `Signup.volunteer.has(email=...)` (or equivalent
       query form). Inspect and adjust the query.

    6. `routers/signups.py` — per D-10, DELETE the old auth'd `POST /signups/`
       endpoint entirely. Keep the other routes (GET list, cancel, etc.) but
       swap `signup.user` → `signup.volunteer` where referenced. The cancel
       endpoint remains (organizer/admin use).

    7. `routers/roster.py` — `RosterRow.student_name` logic: replace
       `user.name` with `f"{v.first_name} {v.last_name}"`. Same pattern for
       any `.email` access.

    8. `routers/users.py` — remove or guard any `signup.user` / `user.signups`
       references. If a route becomes meaningless without the relationship
       (e.g. `GET /users/{id}/signups` which no longer makes sense), leave the
       route but return an empty list with a `# Phase 12:` comment.

    **Do not touch** test files in this task — Task 9 handles the un-skip pass.

    **Do not import** `PrereqOverride` anywhere new.

    **Commit strategy:** one commit per file or tight file group:
    - `fix(09): emails.py + magic_link_service.py signup.user -> volunteer`
    - `fix(09): celery_app.py reminder + weekly_digest volunteer rename`
    - `fix(09): routers/admin.py minimal signup.user rename (D-05)`
    - `fix(09): routers/signups.py + magic.py + roster.py + users.py volunteer rename; delete old POST /signups/`
  </action>
  <verify>
    <automated>
      cd /Users/andysubramanian/uni-volunteer-scheduler/backend &amp;&amp;
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD:/app -w /app
        uni-volunteer-scheduler-backend
        sh -c "python -c 'from app.main import app; print(len(app.routes))'"
    </automated>
  </verify>
  <done>
    `python -c "from app.main import app"` exits 0 with no ImportError, no
    AttributeError. The command prints a route count. `git grep -n "signup\\.user\\b"
    backend/app` returns zero results (tests not yet touched). The old auth'd
    POST /signups/ endpoint is deleted from routers/signups.py.
  </done>
</task>

<task type="auto">
  <name>Task 2: Alembic migration 0010 — notifications.volunteer_id + user_id nullable + CHECK constraint</name>
  <files>
    backend/alembic/versions/0010_phase09_notifications_volunteer_fk.py,
    backend/app/models.py
  </files>
  <action>
    Per D-04. Create a new Alembic migration downstream of
    `0009_phase08_v1_1_schema_realignment`:

    - Filename: `0010_phase09_notifications_volunteer_fk.py`
    - Revision id (slug form): `0010_phase09_notifications_volunteer_fk`
    - `down_revision = "0009_phase08_v1_1_schema_realignment"`

    **upgrade()**:
    1. `op.add_column("notifications", sa.Column("volunteer_id", postgresql.UUID(as_uuid=True), nullable=True))`
    2. `op.create_foreign_key("fk_notifications_volunteer_id", "notifications", "volunteers", ["volunteer_id"], ["id"], ondelete="CASCADE")`
    3. `op.alter_column("notifications", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)`
    4. `op.create_check_constraint(
           "ck_notifications_recipient_xor",
           "notifications",
           "(user_id IS NOT NULL AND volunteer_id IS NULL) OR (user_id IS NULL AND volunteer_id IS NOT NULL)"
       )`
    5. Add an index on `volunteer_id` for query performance.

    **downgrade()** (reverse order):
    1. Drop the index.
    2. Drop the CHECK constraint.
    3. `op.alter_column("notifications", "user_id", nullable=False)` — note:
       must purge any rows where `user_id IS NULL` first with a `DELETE`
       (dev data; no backfill per project convention).
    4. Drop the FK.
    5. Drop `volunteer_id` column.
    6. No enum to drop (none added), but follow the DROP TYPE sweep habit if
       any code path creates one — verify zero enums added in this migration.

    **models.py update:**
    - `Notification.user_id`: change `nullable=False` → `nullable=True`
    - Add `volunteer_id = Column(UUID(as_uuid=True), ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=True, index=True)`
    - Add relationship: `volunteer = relationship("Volunteer")`
    - Add a Python-level comment: `# CHECK constraint enforces exactly one of user_id/volunteer_id set`

    **Pattern reference:** follow the exact `postgresql.ENUM(..., create_type=False)`
    and enum-drop habits from migration 0009 even though this migration
    doesn't touch enums — keeping style consistent.

    Commit: `feat(09): alembic migration 0010 — notifications.volunteer_id + CHECK`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer"
        uni-volunteer-scheduler-backend
        sh -c "alembic upgrade head &amp;&amp; alembic downgrade -1 &amp;&amp; alembic upgrade head &amp;&amp;
               psql postgresql://postgres:postgres@db:5432/uni_volunteer -c '\\d notifications' | grep -E 'volunteer_id|ck_notifications_recipient_xor'"
    </automated>
  </verify>
  <done>
    Migration 0010 applies cleanly, downgrades one step cleanly, re-applies
    cleanly. `\\d notifications` shows `volunteer_id` column, `user_id`
    nullable, and the `ck_notifications_recipient_xor` CHECK constraint.
    `models.py` Notification class reflects both changes. No DuplicateObject
    on round-trip.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Phone normalization service + unit tests</name>
  <files>
    backend/app/services/__init__.py,
    backend/app/services/phone_service.py,
    backend/tests/test_phone_service.py
  </files>
  <behavior>
    - `normalize_us_phone("805-555-1234")` → `"+18055551234"`
    - `normalize_us_phone("(805) 555-1234")` → `"+18055551234"`
    - `normalize_us_phone("+1 805 555 1234")` → `"+18055551234"`
    - `normalize_us_phone("8055551234")` → `"+18055551234"`
    - `normalize_us_phone("not-a-phone")` → raises `InvalidPhoneError`
    - `normalize_us_phone("")` → raises `InvalidPhoneError`
    - `normalize_us_phone("555-1234")` (no area code) → raises `InvalidPhoneError`
      (too short; phonenumbers `is_valid_number` returns False)
    - `normalize_us_phone("+44 20 7946 0958")` → raises `InvalidPhoneError`
      (UK number, default_region="US" but function rejects non-US formats by
      post-parse country check: `parsed.country_code != 1`)
  </behavior>
  <action>
    **RED:** Create `backend/tests/test_phone_service.py` with the 8 cases
    above. Run and confirm failures (module doesn't exist yet). Commit:
    `test(09): failing phone_service unit tests`

    **GREEN:** Create `backend/app/services/__init__.py` (empty) and
    `backend/app/services/phone_service.py` implementing:

    ```python
    import phonenumbers
    from phonenumbers import NumberParseException

    class InvalidPhoneError(ValueError):
        """Raised when a phone string cannot be parsed to a valid US E.164 number."""

    def normalize_us_phone(raw: str) -> str:
        if not raw or not raw.strip():
            raise InvalidPhoneError("phone number is empty")
        try:
            parsed = phonenumbers.parse(raw, "US")
        except NumberParseException as exc:
            raise InvalidPhoneError(f"cannot parse phone number: {exc}") from exc
        if parsed.country_code != 1:
            raise InvalidPhoneError("only US (+1) phone numbers are accepted")
        if not phonenumbers.is_valid_number(parsed):
            raise InvalidPhoneError("phone number is not a valid US number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    ```

    Run tests, confirm all 8 pass. Commit: `feat(09): phone_service normalize_us_phone + InvalidPhoneError`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest tests/test_phone_service.py -xvs"
    </automated>
  </verify>
  <done>
    All 8 tests pass. Service is importable as
    `from app.services.phone_service import normalize_us_phone, InvalidPhoneError`.
    No raw phone string logged anywhere in the service (grep confirms zero
    `logger.` calls with phone in the service file).
  </done>
</task>

<task type="auto">
  <name>Task 4: Magic-link service refactor — purpose arg, ttl override, batch consume</name>
  <files>
    backend/app/magic_link_service.py,
    backend/tests/test_magic_link_signup_purpose.py
  </files>
  <action>
    Per D-06. Extend the existing service without deleting any existing
    behavior. Keep `check_rate_limit()` untouched.

    **`issue_token()` new signature** (per 09-RESEARCH.md Pattern 3):
    ```python
    def issue_token(
        db: Session,
        signup: Signup,
        email: str,
        *,
        purpose: MagicLinkPurpose = MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id: UUID | None = None,
        ttl_minutes: int | None = None,
    ) -> str:
        raw = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw)
        ttl = ttl_minutes if ttl_minutes is not None else settings.magic_link_ttl_minutes
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
        row = MagicLinkToken(
            token_hash=token_hash,
            signup_id=signup.id,
            email=email.lower(),
            expires_at=expires_at,
            purpose=purpose,
            volunteer_id=volunteer_id,
        )
        db.add(row)
        db.flush()
        return raw
    ```

    **`consume_token()` batch extension**: after the existing single-signup flip,
    if `token.purpose == SIGNUP_CONFIRM` AND `token.volunteer_id is not None`:
    ```python
    anchor_event_id = signup.slot.event_id
    sibling_signups = (
        db.query(Signup)
        .join(Slot, Slot.id == Signup.slot_id)
        .filter(
            Signup.volunteer_id == token.volunteer_id,
            Signup.status == SignupStatus.pending,
            Slot.event_id == anchor_event_id,
            Signup.id != signup.id,
        )
        .all()
    )
    for s in sibling_signups:
        s.status = SignupStatus.confirmed
    ```
    Keep `dispatch_email()` using `signup.volunteer.email` (fixed in Task 1).

    **Add a `SIGNUP_CONFIRM_TTL_MINUTES` constant = 20160** (14 days) at module
    scope. Public signup service (Task 6) will pass this explicitly.

    **Add `backend/app/config.py` setting (if not present): `frontend_url: str`**
    — used by the confirmation email builder to assemble the magic-link URL.
    Default to `http://localhost:5173` for dev.

    **New tests `test_magic_link_signup_purpose.py`** (new file, not an un-skip):
    - `test_issue_signup_confirm_token_sets_purpose_and_volunteer_id`
    - `test_issue_signup_confirm_token_ttl_14_days` (assert expires_at ~= now + 14d)
    - `test_consume_signup_confirm_batch_flips_all_pending_in_same_event`
    - `test_consume_signup_confirm_does_not_flip_other_events` (scope guard)
    - `test_consume_signup_confirm_does_not_flip_other_volunteers` (scope guard)
    - `test_consume_signup_confirm_idempotent` (second call returns `used`)

    These tests use the not-yet-un-skipped infrastructure — they build their
    own Volunteer + Slot + Signup via the new VolunteerFactory (add minimal
    factory inline if Task 9 hasn't landed yet, OR hold this task's test file
    as RED until Task 9; planner decision: land tests WITH inline volunteer
    creation to stay self-contained).

    Commits:
    - `feat(09): magic_link_service — purpose arg, ttl override, batch consume`
    - `test(09): magic_link signup_confirm purpose + batch tests`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest tests/test_magic_link_signup_purpose.py -xvs"
    </automated>
  </verify>
  <done>
    All 6 new tests pass. `issue_token()` accepts and stores `purpose` +
    `volunteer_id` + custom `ttl_minutes`. `consume_token()` batch-flips
    siblings scoped by volunteer_id + event_id. Existing magic-link tests (if
    un-skipped) still pass.
  </done>
</task>

<task type="auto">
  <name>Task 5: Volunteer service — upsert_volunteer by email</name>
  <files>
    backend/app/services/volunteer_service.py
  </files>
  <action>
    Per 09-RESEARCH.md Pattern 1. Create `upsert_volunteer(db, email, first_name,
    last_name, phone_e164)` using `pg_insert().on_conflict_do_update()` on the
    `email` unique index. Lowercase email before insert. Return the `Volunteer`
    row.

    ```python
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import func
    from sqlalchemy.orm import Session
    from ..models import Volunteer

    def upsert_volunteer(
        db: Session,
        email: str,
        first_name: str,
        last_name: str,
        phone_e164: str | None,
    ) -> Volunteer:
        stmt = (
            pg_insert(Volunteer)
            .values(
                email=email.lower().strip(),
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                phone_e164=phone_e164,
            )
            .on_conflict_do_update(
                index_elements=["email"],
                set_={
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "phone_e164": phone_e164,
                    "updated_at": func.now(),
                },
            )
            .returning(Volunteer.id)
        )
        result = db.execute(stmt)
        volunteer_id = result.scalar_one()
        db.flush()
        return db.get(Volunteer, volunteer_id)
    ```

    Tests for this service are embedded in the Task 8 public signup integration
    tests (same email creates once, reuses next time). No separate unit test.

    Commit: `feat(09): volunteer_service.upsert_volunteer via pg_insert on_conflict`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        uni-volunteer-scheduler-backend
        sh -c "python -c 'from app.services.volunteer_service import upsert_volunteer; print(upsert_volunteer.__doc__ or \"ok\")'"
    </automated>
  </verify>
  <done>
    Service importable. Function signature matches spec. Tests exercising it
    land in Task 8 (public signup integration tests).
  </done>
</task>

<task type="auto">
  <name>Task 6: Public signup service + orientation service + Pydantic schemas</name>
  <files>
    backend/app/services/public_signup_service.py,
    backend/app/services/orientation_service.py,
    backend/app/schemas.py
  </files>
  <action>
    **A. Add Pydantic schemas to `backend/app/schemas.py`** (additive — do NOT
    modify the existing `SignupRead.user_id` field; D-10 handles old router
    deletion, but `SignupRead` may still be imported elsewhere until Phase 12):

    ```python
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
        phone_e164: str | None
        created_at: datetime
        model_config = ConfigDict(from_attributes=True)

    class PublicSignupCreate(VolunteerCreate):
        slot_ids: list[UUID] = Field(min_length=1, max_length=20)

    class PublicSignupResponse(BaseModel):
        volunteer_id: UUID
        signup_ids: list[UUID]
        magic_link_sent: bool

    class PublicSlotRead(BaseModel):
        id: UUID
        slot_type: SlotType
        date: date
        start_time: datetime
        end_time: datetime
        location: str | None
        capacity: int
        filled: int  # = slot.current_count
        model_config = ConfigDict(from_attributes=True)

    class PublicEventRead(BaseModel):
        id: UUID
        title: str
        quarter: Quarter
        year: int
        week_number: int
        school: str
        module_slug: str | None
        start_date: date
        end_date: date
        slots: list[PublicSlotRead] = []
        model_config = ConfigDict(from_attributes=True)

    class PublicEventListQuery(BaseModel):
        quarter: Quarter
        year: int
        week_number: int
        school: str | None = None

    class OrientationStatusRead(BaseModel):
        has_attended_orientation: bool
        last_attended_at: datetime | None = None

    class TokenedManageRead(BaseModel):
        volunteer_id: UUID
        event_id: UUID
        signups: list[PublicSlotRead]  # joined with slot + status; use a new TokenedSignupRead if needed
    ```

    If `TokenedSignupRead` is cleaner than reusing `PublicSlotRead`, add it:
    `{signup_id, status, slot: PublicSlotRead}`.

    **B. `public_signup_service.py`**: orchestration layer for POST /public/signups.

    ```python
    def create_public_signup(
        db: Session,
        payload: PublicSignupCreate,
    ) -> PublicSignupResponse:
        # 1. Normalize phone (raises InvalidPhoneError → caller converts to 422)
        phone_e164 = normalize_us_phone(payload.phone)

        # 2. Upsert volunteer
        volunteer = upsert_volunteer(
            db, payload.email, payload.first_name, payload.last_name, phone_e164
        )

        # 3. Load slots, lock them, check capacity, create one Signup per slot
        signups = []
        for slot_id in payload.slot_ids:
            slot = (
                db.query(Slot)
                .filter(Slot.id == slot_id)
                .with_for_update()
                .first()
            )
            if slot is None:
                raise HTTPException(404, f"slot {slot_id} not found")
            if slot.current_count >= slot.capacity:
                raise HTTPException(409, f"slot {slot_id} is full")
            # Duplicate guard — catch IntegrityError → 409
            try:
                signup = Signup(
                    volunteer_id=volunteer.id,
                    slot_id=slot.id,
                    status=SignupStatus.pending,  # D-01
                )
                db.add(signup)
                slot.current_count += 1  # D-02: pending counts against capacity
                db.flush()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, f"already signed up for slot {slot_id}")
            signups.append(signup)

        # 4. Issue magic-link token anchored to first signup, 14-day TTL
        from ..magic_link_service import issue_token, SIGNUP_CONFIRM_TTL_MINUTES
        from ..models import MagicLinkPurpose
        raw_token = issue_token(
            db,
            signup=signups[0],
            email=volunteer.email,
            purpose=MagicLinkPurpose.SIGNUP_CONFIRM,
            volunteer_id=volunteer.id,
            ttl_minutes=SIGNUP_CONFIRM_TTL_MINUTES,
        )

        # 5. Enqueue confirmation email (Celery task — Task 10)
        from ..celery_app import send_signup_confirmation_email
        event_id = signups[0].slot.event_id
        send_signup_confirmation_email.delay(
            volunteer_id=str(volunteer.id),
            signup_ids=[str(s.id) for s in signups],
            token=raw_token,
            event_id=str(event_id),
        )

        db.commit()
        return PublicSignupResponse(
            volunteer_id=volunteer.id,
            signup_ids=[s.id for s in signups],
            magic_link_sent=True,
        )
    ```

    **C. `orientation_service.py`** (per D-03 and D-08):

    ```python
    from sqlalchemy.orm import Session
    from ..models import Signup, Slot, Volunteer, SignupStatus, SlotType

    def has_attended_orientation(db: Session, email: str) -> OrientationStatusRead:
        """All-time check (D-03). Returns identical shape regardless of email existence (D-08)."""
        row = (
            db.query(Signup)
            .join(Slot, Slot.id == Signup.slot_id)
            .join(Volunteer, Volunteer.id == Signup.volunteer_id)
            .filter(
                Volunteer.email == email.lower().strip(),
                Slot.slot_type == SlotType.orientation,
                Signup.status == SignupStatus.attended,
            )
            .order_by(Signup.checked_in_at.desc().nullslast())
            .first()
        )
        if row is None:
            return OrientationStatusRead(has_attended_orientation=False, last_attended_at=None)
        return OrientationStatusRead(
            has_attended_orientation=True,
            last_attended_at=row.checked_in_at,
        )
    ```

    Commits:
    - `feat(09): schemas — VolunteerCreate, PublicSignup*, PublicEvent*, OrientationStatusRead`
    - `feat(09): public_signup_service orchestration (upsert + per-slot + token + email enqueue)`
    - `feat(09): orientation_service.has_attended_orientation (all-time, enumeration-safe)`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        uni-volunteer-scheduler-backend
        sh -c "python -c 'from app.schemas import PublicSignupCreate, PublicEventRead, OrientationStatusRead;
                          from app.services.public_signup_service import create_public_signup;
                          from app.services.orientation_service import has_attended_orientation;
                          print(\"ok\")'"
    </automated>
  </verify>
  <done>
    All three modules importable. Pydantic schemas validate sample inputs.
    Services called with invalid input raise appropriate typed errors. No
    HTTP server yet — that's Task 7.
  </done>
</task>

<task type="auto">
  <name>Task 7: Public routers — events, signups, orientation + main.py wiring + rate limits</name>
  <files>
    backend/app/routers/public/__init__.py,
    backend/app/routers/public/events.py,
    backend/app/routers/public/signups.py,
    backend/app/routers/public/orientation.py,
    backend/app/main.py
  </files>
  <action>
    Per D-09. All endpoints mounted via `app.include_router(..., prefix="/api/v1")`.
    Each router file declares its own `router = APIRouter(prefix="/public", tags=["public"])`.

    **A. `backend/app/routers/public/__init__.py`** — empty, marks package.

    **B. `backend/app/routers/public/events.py`**:
    ```python
    from fastapi import APIRouter, Depends, HTTPException, Query
    from sqlalchemy.orm import Session
    from ... import models, schemas
    from ...database import get_db
    from ...deps import rate_limit

    router = APIRouter(prefix="/public", tags=["public"])

    @router.get("/events", response_model=list[schemas.PublicEventRead],
                dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))])
    def list_events(
        quarter: models.Quarter = Query(...),
        year: int = Query(..., ge=2020, le=2100),
        week_number: int = Query(..., ge=1, le=11),
        school: str | None = Query(default=None),
        db: Session = Depends(get_db),
    ):
        q = db.query(models.Event).filter(
            models.Event.quarter == quarter,
            models.Event.year == year,
            models.Event.week_number == week_number,
        )
        if school:
            q = q.filter(models.Event.school == school)
        events = q.order_by(models.Event.school, models.Event.start_date).all()
        # Hydrate slots with filled = current_count
        out = []
        for e in events:
            slots = db.query(models.Slot).filter(models.Slot.event_id == e.id).all()
            out.append({...hydrate PublicEventRead with PublicSlotRead(filled=slot.current_count)...})
        return out

    @router.get("/events/{event_id}", response_model=schemas.PublicEventRead,
                dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))])
    def get_event(event_id: UUID, db: Session = Depends(get_db)):
        event = db.get(models.Event, event_id)
        if event is None:
            raise HTTPException(404, "event not found")
        # Hydrate same as above
        ...
    ```

    **C. `backend/app/routers/public/signups.py`**:
    ```python
    router = APIRouter(prefix="/public", tags=["public"])

    @router.post("/signups", response_model=schemas.PublicSignupResponse, status_code=201,
                 dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))])
    def create_signup(body: schemas.PublicSignupCreate, db: Session = Depends(get_db)):
        try:
            return create_public_signup(db, body)
        except InvalidPhoneError as exc:
            raise HTTPException(422, detail=str(exc))

    @router.post("/signups/confirm",
                 dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))])
    def confirm_signup(token: str = Query(..., min_length=16), db: Session = Depends(get_db)):
        # Reuse existing magic_link_service.consume_token; map ConsumeResult to HTTP
        result = consume_token(db, token)
        if result.status == "ok":
            db.commit()
            return {"confirmed": True, "signup_count": result.count}
        if result.status == "used":
            return {"confirmed": True, "signup_count": 0, "idempotent": True}  # idempotent flip
        # expired | not_found | cancelled → 400 with clear message
        raise HTTPException(400, detail=f"token {result.status}")

    @router.get("/signups/manage", response_model=schemas.TokenedManageRead,
                dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))])
    def manage_signups(token: str = Query(..., min_length=16), db: Session = Depends(get_db)):
        # Resolve token WITHOUT consuming. Must be signup_confirm or signup_manage purpose.
        token_row = _lookup_token(db, token)  # helper in magic_link_service: hash lookup, no flip
        if token_row is None or token_row.expires_at < now_utc():
            raise HTTPException(400, "token invalid or expired")
        if token_row.purpose not in (MagicLinkPurpose.SIGNUP_CONFIRM, MagicLinkPurpose.SIGNUP_MANAGE):
            raise HTTPException(400, "token not valid for manage")
        anchor = db.get(Signup, token_row.signup_id)
        event_id = anchor.slot.event_id
        signups = (
            db.query(Signup).join(Slot)
            .filter(Signup.volunteer_id == token_row.volunteer_id,
                    Slot.event_id == event_id,
                    Signup.status.in_([SignupStatus.pending, SignupStatus.confirmed]))
            .all()
        )
        return TokenedManageRead(volunteer_id=token_row.volunteer_id, event_id=event_id, signups=[...])

    @router.delete("/signups/{signup_id}",
                   dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60))])
    def cancel_signup(signup_id: UUID, token: str = Query(..., min_length=16), db: Session = Depends(get_db)):
        token_row = _lookup_token(db, token)
        if token_row is None or token_row.expires_at < now_utc():
            raise HTTPException(400, "token invalid or expired")
        signup = db.get(Signup, signup_id)
        if signup is None:
            raise HTTPException(404, "signup not found")
        # T-09-04 mitigation: cross-volunteer token MUST be rejected
        if signup.volunteer_id != token_row.volunteer_id:
            raise HTTPException(403, "token does not own this signup")
        signup.status = SignupStatus.cancelled
        signup.slot.current_count = max(0, signup.slot.current_count - 1)
        db.commit()
        return {"cancelled": True, "signup_id": str(signup_id)}
    ```

    Add `_lookup_token(db, raw_token) -> MagicLinkToken | None` helper to
    `magic_link_service.py` — hashes the raw token and returns the row
    without flipping status. Used by manage + cancel (which must not consume).

    **D. `backend/app/routers/public/orientation.py`**:
    ```python
    router = APIRouter(prefix="/public", tags=["public"])

    @router.get("/orientation-status", response_model=schemas.OrientationStatusRead,
                dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))])
    def orientation_status(email: EmailStr = Query(...), db: Session = Depends(get_db)):
        # D-08: return same shape regardless of email existence; no 404
        return has_attended_orientation(db, str(email))
    ```

    **E. `main.py` wiring**:
    ```python
    from .routers.public import events as public_events
    from .routers.public import signups as public_signups
    from .routers.public import orientation as public_orientation
    app.include_router(public_events.router, prefix="/api/v1")
    app.include_router(public_signups.router, prefix="/api/v1")
    app.include_router(public_orientation.router, prefix="/api/v1")
    ```

    Commits:
    - `feat(09): magic_link_service._lookup_token helper (no-consume)`
    - `feat(09): routers/public/events — GET /public/events + /public/events/{id}`
    - `feat(09): routers/public/signups — POST + confirm + manage + DELETE`
    - `feat(09): routers/public/orientation — GET /public/orientation-status`
    - `feat(09): wire public routers into main.py at /api/v1 prefix`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        uni-volunteer-scheduler-backend
        sh -c "python -c 'from app.main import app;
                          routes = [r.path for r in app.routes];
                          public_routes = [r for r in routes if \"/public\" in r];
                          assert len(public_routes) &gt;= 7, public_routes;
                          print(public_routes)'"
    </automated>
  </verify>
  <done>
    App boots with 7+ public routes registered under `/api/v1/public`. Each
    route has a `rate_limit()` dependency. No route sits behind `get_current_user`.
    `_lookup_token` helper does not mutate state.
  </done>
</task>

<task type="auto">
  <name>Task 8: Email template + Celery task send_signup_confirmation_email</name>
  <files>
    backend/app/email_templates/signup_confirm.html,
    backend/app/celery_app.py,
    backend/app/emails.py
  </files>
  <action>
    Per D-12. Match the existing `confirmation.html` / `_render_html()` pattern.

    **A. `backend/app/email_templates/signup_confirm.html`** — HTML body using
    `string.Template` placeholders (`$name`, not Jinja `{{}}`) because the
    existing `_render_html()` uses `string.Template.safe_substitute()`:

    ```html
    <!-- backend/app/email_templates/signup_confirm.html -->
    <p>Hi $volunteer_first_name,</p>
    <p>Thanks for signing up to volunteer with SciTrek! Please confirm your signup by clicking the link below:</p>
    <p><a href="$confirm_url">Confirm my signup</a></p>
    <p>You signed up for:</p>
    <pre>$slot_list</pre>
    <p>You can manage or cancel your signup any time using the same link above (valid for 14 days).</p>
    <p>If this wasn't you, please ignore this email — no signup will be created without confirmation.</p>
    <p>— UCSB SciTrek</p>
    ```

    Extend `base.html` wrapper if the existing pattern requires it (inspect
    `confirmation.html` usage in `emails.py` and mirror).

    **B. Add a builder in `emails.py`** (co-located with existing builders):
    ```python
    def build_signup_confirmation_email(
        volunteer: Volunteer,
        signups: list[Signup],  # loaded with slot + event
        token: str,
        event: Event,
    ) -> tuple[str, str]:  # (subject, html_body)
        confirm_url = f"{settings.frontend_url}/signup/confirm?token={token}"
        slot_lines = []
        for s in signups:
            slot_lines.append(
                f"- {s.slot.slot_type.value.title()}: {s.slot.date} "
                f"{s.slot.start_time.strftime('%I:%M %p')} - {s.slot.end_time.strftime('%I:%M %p')} "
                f"@ {s.slot.location or event.school}"
            )
        html = _render_html("signup_confirm.html", {
            "volunteer_first_name": volunteer.first_name,
            "confirm_url": confirm_url,
            "slot_list": "\n".join(slot_lines),
        })
        subject = f"Confirm your SciTrek volunteer signup — {event.title}"
        return subject, html
    ```

    **C. New Celery task in `celery_app.py`** (per D-11, NO Notification row):
    ```python
    @celery_app.task(name="app.send_signup_confirmation_email")
    def send_signup_confirmation_email(
        volunteer_id: str,
        signup_ids: list[str],
        token: str,
        event_id: str,
    ) -> None:
        db = SessionLocal()
        try:
            volunteer = db.get(Volunteer, UUID(volunteer_id))
            signups = db.query(Signup).filter(Signup.id.in_([UUID(sid) for sid in signup_ids])).all()
            event = db.get(Event, UUID(event_id))
            if not volunteer or not signups or not event:
                logger.warning("send_signup_confirmation_email: missing entity, skipping")
                return
            subject, html = build_signup_confirmation_email(volunteer, signups, token, event)
            _send_email_via_sendgrid(to=volunteer.email, subject=subject, html=html)
            logger.info(
                "signup_confirmation_email_sent volunteer_id=%s event_id=%s signup_count=%d",
                volunteer_id, event_id, len(signups),
            )
            # Debug-only token echo so scripts/smoke_phase09.sh can grep the token
            # out of celery worker logs in dev mode (per Task 13). Gated on
            # settings.debug so production logs never leak raw tokens.
            if getattr(settings, "debug", False):
                logger.debug("signup_confirm_token_debug token=%s", token)
            # NO Notification row per D-11
        finally:
            db.close()
    ```

    Ensure Celery is configured in eager mode for tests (conftest already
    handles this — verify `task_always_eager = True` in test config).

    Commits:
    - `feat(09): email_templates/signup_confirm.html`
    - `feat(09): emails.build_signup_confirmation_email`
    - `feat(09): celery send_signup_confirmation_email task`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        uni-volunteer-scheduler-backend
        sh -c "python -c 'from app.celery_app import send_signup_confirmation_email;
                          from app.emails import build_signup_confirmation_email;
                          print(send_signup_confirmation_email.name, build_signup_confirmation_email.__name__)'"
    </automated>
  </verify>
  <done>
    Template file exists. Builder renders without error given test fixtures.
    Celery task is importable and registered. Task 11 integration tests will
    verify end-to-end dispatch in eager mode.
  </done>
</task>

<task type="auto">
  <name>Task 9: Test un-skip pass — Bucket A rename sweep, Bucket B admin fixes, Bucket C delete</name>
  <files>
    backend/tests/fixtures/factories.py,
    backend/tests/test_signups.py,
    backend/tests/test_check_in_endpoints.py,
    backend/tests/test_check_in_service.py,
    backend/tests/test_concurrent_check_in.py,
    backend/tests/test_models_magic_link.py,
    backend/tests/test_models_phase3.py,
    backend/tests/test_magic_link_service.py,
    backend/tests/test_magic_link_router.py,
    backend/tests/test_notifications_phase6.py,
    backend/tests/test_celery_reminders.py,
    backend/tests/test_roster_endpoints.py,
    backend/tests/test_admin.py,
    backend/tests/test_admin_phase7.py,
    backend/tests/test_contract.py
  </files>
  <action>
    Triage per 09-RESEARCH.md "74 Skipped Tests — Triage" table.

    **Prep: Add `VolunteerFactory` + update `SignupFactory`:**
    ```python
    # backend/tests/fixtures/factories.py
    class VolunteerFactory(SQLAlchemyModelFactory):
        class Meta:
            model = Volunteer
            sqlalchemy_session_persistence = "flush"
        id = factory.LazyFunction(uuid.uuid4)
        email = factory.Sequence(lambda n: f"volunteer{n}@example.com")
        first_name = factory.Sequence(lambda n: f"First{n}")
        last_name = factory.Sequence(lambda n: f"Last{n}")
        phone_e164 = "+15550001234"
        created_at = factory.LazyFunction(datetime.utcnow)
        updated_at = factory.LazyFunction(datetime.utcnow)

    # SignupFactory — REMOVE user/user_id, ADD volunteer/volunteer_id
    class SignupFactory(SQLAlchemyModelFactory):
        ...
        volunteer = factory.SubFactory(VolunteerFactory)
        volunteer_id = factory.LazyAttribute(lambda o: o.volunteer.id)
        slot = factory.SubFactory(SlotFactory)
        slot_id = factory.LazyAttribute(lambda o: o.slot.id)
        status = SignupStatus.pending
    ```

    Commit: `test(09): VolunteerFactory + SignupFactory volunteer rewire`

    **Bucket A — un-skip (remove pytestmark + rename):**
    For each file below, remove the `pytestmark = pytest.mark.skip(...)` line
    and sweep `signup.user` → `signup.volunteer`, `.name` → `f"{v.first_name} {v.last_name}"`,
    `SignupFactory(user=...)` → `SignupFactory(volunteer=...)`, `user_id=` → `volunteer_id=`:

    | File | Tests | Commit |
    |---|---|---|
    | test_signups.py | 8 | `test(09): un-skip test_signups — volunteer rename` |
    | test_check_in_endpoints.py | 9 | `test(09): un-skip test_check_in_endpoints` |
    | test_check_in_service.py | 8 | `test(09): un-skip test_check_in_service` |
    | test_concurrent_check_in.py | 10 | `test(09): un-skip test_concurrent_check_in` |
    | test_models_magic_link.py | 5 | `test(09): un-skip test_models_magic_link` |
    | test_models_phase3.py | 2 classes | `test(09): un-skip test_models_phase3 (checked_in + magic_link_purpose)` |
    | test_magic_link_service.py | 5 | `test(09): un-skip test_magic_link_service — volunteer rewire` |
    | test_magic_link_router.py | 6 | `test(09): un-skip test_magic_link_router` |
    | test_notifications_phase6.py | 6 | `test(09): un-skip test_notifications_phase6` |
    | test_celery_reminders.py | 4 | `test(09): un-skip test_celery_reminders` |
    | test_roster_endpoints.py | 1 | `test(09): un-skip test_roster_endpoints::test_organizer_fetches_roster` |

    **Bucket B — admin tests (fixed after Task 1 admin rename):**
    | File | Tests | Commit |
    |---|---|---|
    | test_admin.py | 2 (delete_user, cancel_signup_promotes_waitlist) | `test(09): un-skip test_admin 2 tests` |
    | test_admin_phase7.py | 3 (analytics, ccpa_export, ccpa_delete) | `test(09): un-skip test_admin_phase7 3 tests` |

    Per D-05, if an admin test was exercising behavior that Task 1 stubbed to
    501, mark THAT SPECIFIC test with `@pytest.mark.skip(reason="Phase 12: admin
    endpoint stubbed")` and document in 09-SUMMARY.md deviations.

    **Bucket C — delete:**
    - Delete `test_contract.py::test_createSignup_trailing_slash` (D-10).
    - The old POST /signups/ endpoint is already deleted in Task 1.
    Commit: `chore(09): delete test_createSignup_trailing_slash (old endpoint retired)`

    **Expected baseline after this task:**
    - Before Phase 09: 76 passed, 74 skipped, 0 failed
    - Target after Task 9: ~76 + ~73 un-skipped - 1 deleted (contract) +
      potentially 1-3 remaining skipped for stubbed admin = approximately
      **148 passed, ≤3 skipped, 0 failed**. Document EXACT number in
      09-SUMMARY.md after the pytest run.
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest -q --no-cov 2>&amp;1 | tail -5"
    </automated>
  </verify>
  <done>
    `pytest -q --no-cov` reports ≥148 passed, ≤3 skipped, 0 failed. Each
    remaining skip has a `# Phase 12: admin stubbed` reason. `test_createSignup_trailing_slash`
    is gone. `SignupFactory` no longer has `user`/`user_id` references.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 10: New public-endpoint integration tests (happy path + error paths + rate limit + token auth)</name>
  <files>
    backend/tests/test_public_events.py,
    backend/tests/test_public_signups_create.py,
    backend/tests/test_public_signups_confirm.py,
    backend/tests/test_public_signups_manage.py,
    backend/tests/test_public_orientation.py
  </files>
  <behavior>
    **test_public_events.py:**
    - `test_list_events_filters_by_quarter_year_week` — exact triple filter
    - `test_list_events_school_filter_narrows` — school narrows results
    - `test_list_events_missing_required_query_422` — no quarter → 422
    - `test_get_event_returns_slots_with_filled_capacity` — slot filled=current_count
    - `test_get_event_unknown_id_404`

    **test_public_signups_create.py:**
    - `test_new_email_creates_volunteer_and_signups` (R09-01, R09-02)
    - `test_same_email_upserts_volunteer_no_duplicate` (R09-01 upsert)
    - `test_invalid_phone_returns_422` (R09-05)
    - `test_duplicate_slot_for_same_volunteer_returns_409`
    - `test_full_slot_returns_409` (D-02 capacity check)
    - `test_unknown_slot_id_returns_404`
    - `test_no_auth_required` (T-09-11 — POST works with no headers)
    - `test_rate_limit_11th_request_returns_429` — hammer 11 POSTs from same
      test client (mock IP header); assert 11th = 429
    - `test_creates_exactly_one_magic_link_token_with_signup_confirm_purpose`
    - `test_email_is_enqueued` (celery eager; assert the task ran OR mock it)

    **test_public_signups_confirm.py:**
    - `test_confirm_valid_token_flips_all_pending_to_confirmed` (R09-03 batch)
    - `test_confirm_is_idempotent_second_call_same_result`
    - `test_confirm_expired_token_returns_400`
    - `test_confirm_unknown_token_returns_400`
    - `test_confirm_cancelled_signup_returns_400_or_no_op`

    **test_public_signups_manage.py:**
    - `test_manage_returns_only_tokens_volunteers_signups`
    - `test_manage_expired_token_returns_400`
    - `test_manage_scope_limited_to_token_event`
    - `test_cancel_one_with_owning_token_succeeds` (DELETE)
    - `test_cancel_one_decrements_slot_current_count`
    - `test_cross_volunteer_cancel_forbidden_403` (T-09-04)
    - `test_cancel_unknown_signup_404`

    **test_public_orientation.py:**
    - `test_orientation_status_true_when_past_attended_exists` (R09-04)
    - `test_orientation_status_false_when_no_history`
    - `test_orientation_status_unknown_email_returns_false_not_404` (D-08)
    - `test_orientation_status_rate_limit_6th_request_429`
    - `test_orientation_status_all_time_not_per_quarter` (D-03)
  </behavior>
  <action>
    **RED:** Create all 5 test files with the above tests. Use the TestClient
    pattern from existing `test_signups.py`. Use `VolunteerFactory`,
    `SlotFactory`, `EventFactory` as needed. For rate-limit tests, you may
    need to set a custom `X-Forwarded-For` header OR mock the rate_limit key
    function — inspect `app.deps.rate_limit()` for the key derivation.

    For time-travel in expired-token tests, use `freezegun.freeze_time` (add
    to requirements if missing — check first) OR directly mutate
    `token_row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)`
    and commit.

    Run tests — confirm RED (most fail because rate_limit state leaks across
    tests, or because of fixture shape issues). Commit:
    `test(09): failing integration tests for all public endpoints`

    **GREEN:** Fix any wiring issues in the routers/services from Tasks 6-7
    that the tests reveal. DO NOT weaken tests to make them pass — fix the
    production code. Likely issues:
    - Rate limit state leaks → add a test fixture that flushes Redis keys
      matching `ratelimit:*` between tests
    - Hydration of PublicEventRead.slots missing → adjust router code
    - Token lookup helper mutating state → verify helper is pure read

    Commit per fix: `fix(09): <what>` granular commits.

    Once all pass, final commit: `test(09): public endpoints green`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest tests/test_public_events.py tests/test_public_signups_create.py tests/test_public_signups_confirm.py tests/test_public_signups_manage.py tests/test_public_orientation.py -xvs"
    </automated>
  </verify>
  <done>
    All ~30 new tests pass. Rate-limit tests isolate state between runs. Phone
    validation, token authorization, batch confirm, and enumeration defense
    all have explicit test coverage. No test was weakened to make it pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 11: Expired-pending cleanup — Celery beat task + time-travel unit test</name>
  <files>
    backend/app/celery_app.py,
    backend/tests/test_expired_pending_cleanup.py
  </files>
  <behavior>
    - Task `expire_pending_signups()` runs daily via Celery beat.
    - Hard-deletes `Signup` rows where: `status == pending` AND the anchor
      `MagicLinkToken` with `purpose == signup_confirm` has `expires_at <
      now_utc()` AND was issued >14 days ago.
    - Decrements `slot.current_count` for each deleted signup.
    - Logs: `"expired_pending_signups_cleaned count=N"`.

    **Tests:**
    - `test_expire_pending_signups_deletes_old_pending`
    - `test_expire_pending_signups_leaves_confirmed_alone`
    - `test_expire_pending_signups_leaves_fresh_pending_alone` (token not yet expired)
    - `test_expire_pending_signups_decrements_slot_current_count`
    - `test_expire_pending_signups_does_not_touch_signups_without_signup_confirm_token`
    - `test_notifications_xor_constraint` (T-09-12 — insert row with both
      user_id and volunteer_id → IntegrityError from CHECK)
  </behavior>
  <action>
    **RED:** Create `test_expired_pending_cleanup.py` with 6 tests. Use
    `freezegun` or direct `expires_at` mutation for time travel. Run — all
    fail (task doesn't exist yet). Commit: `test(09): failing expired-pending cleanup tests`

    **GREEN:** Add to `celery_app.py`:

    ```python
    @celery_app.task(name="app.expire_pending_signups")
    def expire_pending_signups() -> dict:
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            # Find pending signups whose anchor signup_confirm token is expired
            stale = (
                db.query(Signup)
                .join(MagicLinkToken, MagicLinkToken.signup_id == Signup.id)
                .filter(
                    Signup.status == SignupStatus.pending,
                    MagicLinkToken.purpose == MagicLinkPurpose.SIGNUP_CONFIRM,
                    MagicLinkToken.expires_at < now,
                )
                .all()
            )
            count = 0
            for signup in stale:
                if signup.slot:
                    signup.slot.current_count = max(0, signup.slot.current_count - 1)
                db.delete(signup)
                count += 1
            db.commit()
            logger.info("expired_pending_signups_cleaned count=%d", count)
            return {"cleaned": count}
        finally:
            db.close()
    ```

    **MANDATORY pre-implementation FK check.** Before writing the task body,
    run this against the live dev db:

    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer \
      -c "\d magic_link_tokens" | grep -A2 "signup_id"
    ```

    Record the ondelete behavior in a code comment at the top of the task.
    Three cases:

    1. **ondelete = CASCADE:** hard-delete of Signup auto-drops the token row.
       The loop above works as written.
    2. **ondelete = RESTRICT or NO ACTION (default):** deleting Signup fails
       with a FK constraint violation. You MUST delete token rows first inside
       the loop:
       ```python
       for signup in stale:
           # Delete the token first to satisfy the FK constraint
           db.query(MagicLinkToken).filter(
               MagicLinkToken.signup_id == signup.id
           ).delete(synchronize_session=False)
           if signup.slot:
               signup.slot.current_count = max(0, signup.slot.current_count - 1)
           db.delete(signup)
           count += 1
       ```
    3. **ondelete = SET NULL:** token rows are orphaned (signup_id → NULL). The
       loop works but orphaned tokens accumulate — add a second sweep in the
       same task to delete tokens whose signup_id is NULL AND older than 14
       days.

    DO NOT guess or defer this check — every run of the cleanup task depends
    on the right choice. Add a test that intentionally expires a signup with
    an existing token and asserts the delete succeeds; this test catches a
    regression if anyone changes the FK later.

    **Celery beat schedule** — add to `celery_app.beat_schedule`:
    ```python
    "expire-pending-signups-daily": {
        "task": "app.expire_pending_signups",
        "schedule": crontab(hour=3, minute=0),  # 3am UTC daily
    },
    ```

    Run tests green. Commits:
    - `feat(09): expire_pending_signups Celery task + beat schedule`
    - `test(09): expired-pending cleanup + notifications XOR green`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest tests/test_expired_pending_cleanup.py -xvs"
    </automated>
  </verify>
  <done>
    All 6 tests pass. Beat schedule entry exists. Task is registered. Hard
    delete does not orphan `magic_link_tokens` rows (confirmed via test).
    notifications XOR CHECK is enforced (confirmed via IntegrityError test).
  </done>
</task>

<task type="auto">
  <name>Task 12: Integration smoke test — full flow in one pytest</name>
  <files>
    backend/tests/test_phase09_smoke.py
  </files>
  <action>
    Single integration test driving the entire public flow end-to-end against
    the docker test db + eager Celery:

    ```python
    def test_phase09_full_flow(client, db_session):
        # 1. Seed: 1 event + 1 orientation slot + 1 period slot
        event = EventFactory(quarter=Quarter.spring, year=2026, week_number=4, school="Carpinteria HS")
        orient_slot = SlotFactory(event_id=event.id, slot_type=SlotType.orientation, capacity=5)
        period_slot = SlotFactory(event_id=event.id, slot_type=SlotType.period, capacity=5)
        db_session.commit()

        # 2. Browse events for that week
        resp = client.get("/api/v1/public/events", params={
            "quarter": "spring", "year": 2026, "week_number": 4
        })
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert len(events[0]["slots"]) == 2

        # 3. Create signup for both slots
        resp = client.post("/api/v1/public/signups", json={
            "first_name": "Ada", "last_name": "Lovelace",
            "email": "ada@example.com", "phone": "805-555-1234",
            "slot_ids": [str(orient_slot.id), str(period_slot.id)],
        })
        assert resp.status_code == 201
        signup_ids = resp.json()["signup_ids"]
        assert len(signup_ids) == 2

        # 4. Extract raw token from DB (in real flow: from email; in test: from token_hash reverse lookup)
        # Since we can't reverse a hash, instead: capture the token via Celery eager task spy, OR
        # patch `send_signup_confirmation_email` to capture its args, OR
        # re-issue a fresh token against the first signup for test purposes.
        # Cleanest: monkeypatch the Celery task before POST, capture the raw token arg.
        # (Adjust per what the real implementation exposes.)

        # 5. POST /confirm
        resp = client.post(f"/api/v1/public/signups/confirm?token={captured_token}")
        assert resp.status_code == 200

        # Verify DB: both signups now confirmed
        signups_after = db_session.query(Signup).filter(Signup.id.in_([UUID(s) for s in signup_ids])).all()
        assert all(s.status == SignupStatus.confirmed for s in signups_after)

        # 6. GET /manage
        resp = client.get(f"/api/v1/public/signups/manage?token={captured_token}")
        assert resp.status_code == 200
        assert len(resp.json()["signups"]) == 2

        # 7. DELETE one signup
        resp = client.delete(
            f"/api/v1/public/signups/{signup_ids[0]}?token={captured_token}"
        )
        assert resp.status_code == 200

        # 8. GET /manage again — should show 1 cancelled + 1 confirmed (or list only the active one)
        resp = client.get(f"/api/v1/public/signups/manage?token={captured_token}")
        # Assert expected final state (adjust per manage endpoint's inclusion of cancelled rows)
    ```

    For token capture: monkeypatch `app.celery_app.send_signup_confirmation_email.delay`
    with a fixture that records `(args, kwargs)` including the token.

    Commit: `test(09): phase09 end-to-end smoke flow`
  </action>
  <verify>
    <automated>
      docker run --rm --network uni-volunteer-scheduler_default
        -v $PWD/backend:/app -w /app
        -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs"
        uni-volunteer-scheduler-backend
        sh -c "pytest tests/test_phase09_smoke.py::test_phase09_full_flow -xvs"
    </automated>
  </verify>
  <done>
    Single smoke test drives POST → confirm → manage → cancel successfully.
    Final DB state asserted at every step.
  </done>
</task>

<task type="auto">
  <name>Task 13: Curl smoke script — scripts/smoke_phase09.sh</name>
  <files>
    scripts/smoke_phase09.sh
  </files>
  <action>
    Manual verification script (not CI) for Andy to run against a live docker
    stack. Uses `curl`, `jq`, and reads the captured token from Mailhog/dev
    inbox OR from a helper endpoint (prefer the helper: add nothing; document
    that the script requires `docker logs` reading to extract the raw token
    from the Celery worker log since D-11 skips the Notification row).

    ```bash
    #!/usr/bin/env bash
    # scripts/smoke_phase09.sh — Phase 09 manual curl smoke
    set -euo pipefail
    BASE="${BASE:-http://localhost:8000/api/v1/public}"
    EMAIL="${EMAIL:-smoke+$(date +%s)@example.com}"

    echo "==> 1. Seed check: list events"
    curl -sS "$BASE/events?quarter=spring&year=2026&week_number=4" | jq '.[0] | {id, title, slots: (.slots | length)}'

    echo "==> 2. Extract first event's first two slot ids"
    EVENT_JSON=$(curl -sS "$BASE/events?quarter=spring&year=2026&week_number=4")
    SLOT1=$(echo "$EVENT_JSON" | jq -r '.[0].slots[0].id')
    SLOT2=$(echo "$EVENT_JSON" | jq -r '.[0].slots[1].id')
    echo "    slots: $SLOT1 $SLOT2"

    echo "==> 3. POST /signups"
    POST_RESP=$(curl -sS -X POST "$BASE/signups" \
      -H "Content-Type: application/json" \
      -d "{\"first_name\":\"Smoke\",\"last_name\":\"Test\",\"email\":\"$EMAIL\",\"phone\":\"805-555-1234\",\"slot_ids\":[\"$SLOT1\",\"$SLOT2\"]}")
    echo "$POST_RESP" | jq .
    VID=$(echo "$POST_RESP" | jq -r '.volunteer_id')
    SID1=$(echo "$POST_RESP" | jq -r '.signup_ids[0]')

    echo "==> 4. Extract magic-link token from celery worker logs"
    TOKEN=$(docker logs uni-volunteer-scheduler-celery_worker-1 2>&1 | grep -oE 'token=[A-Za-z0-9_-]+' | tail -1 | cut -d= -f2)
    if [ -z "$TOKEN" ]; then
      echo "FAIL: no token found in celery logs. Did send_signup_confirmation_email log token?"
      exit 1
    fi
    echo "    token: ${TOKEN:0:12}..."

    echo "==> 5. POST /signups/confirm"
    curl -sS -X POST "$BASE/signups/confirm?token=$TOKEN" | jq .

    echo "==> 6. GET /signups/manage"
    curl -sS "$BASE/signups/manage?token=$TOKEN" | jq '.signups | length'

    echo "==> 7. DELETE /signups/$SID1"
    curl -sS -X DELETE "$BASE/signups/$SID1?token=$TOKEN" | jq .

    echo "==> 8. GET /signups/manage (final)"
    curl -sS "$BASE/signups/manage?token=$TOKEN" | jq '.signups'

    echo "==> 9. Orientation status for smoke email"
    curl -sS "$BASE/orientation-status?email=$EMAIL" | jq .

    echo "==> DONE"
    ```

    Note: For token to be log-extractable, the `send_signup_confirmation_email`
    task in Task 8 must log the raw token at debug level. Add a `logger.debug(
    "signup_confirmation_token_preview token=%s", token)` line in that task
    GATED behind `settings.debug_mode` so it never leaks in production. Update
    Task 8 if this wasn't already done.

    Make the script executable: `chmod +x scripts/smoke_phase09.sh`.

    Commit: `chore(09): scripts/smoke_phase09.sh manual curl smoke`
  </action>
  <verify>
    <automated>
      bash -n /Users/andysubramanian/uni-volunteer-scheduler/scripts/smoke_phase09.sh &amp;&amp; test -x /Users/andysubramanian/uni-volunteer-scheduler/scripts/smoke_phase09.sh &amp;&amp; echo "script syntax ok and executable"
    </automated>
  </verify>
  <done>
    Script syntactically valid (`bash -n` passes), executable bit set,
    documented in 09-SUMMARY.md with usage example. Token-extraction fallback
    noted if Celery log scraping fails.
  </done>
</task>

<task type="auto">
  <name>Task 14: Verification gates — boot, alembic round-trip, pytest baseline, curl smoke</name>
  <files>
    .planning/phases/09-public-signup-backend/09-verification.txt
  </files>
  <action>
    Run every verification gate and record results to
    `09-verification.txt`. This is the evidence file for the verifier.

    **Gate 1: App boot**
    ```bash
    docker run --rm --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      uni-volunteer-scheduler-backend \
      sh -c 'python -c "from app.main import app; print(len([r for r in app.routes if \"/public\" in str(r.path)]))"'
    ```
    Expected: ≥7. Record output.

    **Gate 2: Alembic round-trip including 0010**
    ```bash
    docker run --rm --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" \
      uni-volunteer-scheduler-backend \
      sh -c 'alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic current'
    ```
    Expected: current = `0010_phase09_notifications_volunteer_fk`. No DuplicateObject.

    **Gate 3: pytest baseline**
    ```bash
    docker run --rm --network uni-volunteer-scheduler_default \
      -v $PWD/backend:/app -w /app \
      -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
      uni-volunteer-scheduler-backend \
      sh -c 'pytest -q --no-cov 2>&1 | tail -10'
    ```
    Expected: ≥148 passed, ≤3 skipped, 0 failed. Record actual number.

    **Gate 4: Curl smoke**
    Bring up the full stack (`docker-compose up -d`), wait for healthy, run:
    ```bash
    bash scripts/smoke_phase09.sh
    ```
    Record output.

    **Gate 5: psql shape inspection for notifications**
    ```bash
    docker exec uni-volunteer-scheduler-db-1 psql -U postgres -d uni_volunteer -c '\d notifications' | tee -a 09-verification.txt
    ```
    Assert: `volunteer_id` column present, `user_id` nullable, `ck_notifications_recipient_xor` constraint present.

    **Gate 6: No `signup.user` references in non-test code**
    ```bash
    docker run --rm -v $PWD/backend:/app -w /app uni-volunteer-scheduler-backend \
      sh -c 'grep -rn "signup\.user\b" app/ || echo "CLEAN"'
    ```
    Expected: `CLEAN`.

    Write all outputs to `.planning/phases/09-public-signup-backend/09-verification.txt`.

    Commit: `docs(09): verification gate evidence`
  </action>
  <verify>
    <automated>
      test -f /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-verification.txt &amp;&amp;
      grep -q "Gate 1" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-verification.txt &amp;&amp;
      grep -q "Gate 2" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-verification.txt &amp;&amp;
      grep -q "Gate 3" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-verification.txt &amp;&amp;
      grep -q "CLEAN" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-verification.txt &amp;&amp;
      echo "all gates recorded"
    </automated>
  </verify>
  <done>
    All 6 gates PASS and recorded in 09-verification.txt. Any gate failure
    blocks Task 15 (SUMMARY).
  </done>
</task>

<task type="auto">
  <name>Task 15: Write 09-SUMMARY.md — handoff for Phase 10</name>
  <files>
    .planning/phases/09-public-signup-backend/09-SUMMARY.md
  </files>
  <action>
    Follow the standard GSD SUMMARY template with frontmatter matching this
    plan's requirements + decisions + metrics. Mandatory sections:

    1. **What Shipped** — per task, what went in + commits
    2. **Verification Gate Results** — paste Gate 1-6 outputs
    3. **Test Baseline Delta** — before (76/74/0), after (actual), with the
       exact numbers for un-skipped, deleted, stubbed, new.
    4. **Deviations from Plan** — any task that diverged (e.g. admin stubs,
       token log scraping fallback).
    5. **Residual Risks** — reiterate threat model `accept` items: T-09-02
       distributed IPs, T-09-05 no audit on cancel, T-09-09 botnet DoS,
       T-09-10 14-day pending window.
    6. **Phase 10 Handoff** — THIS IS THE KEY SECTION. Phase 10 needs:
       - Exact endpoint shapes (paste the router function signatures)
       - Exact error response formats (422/404/409/403 JSON bodies with examples)
       - Rate limit behavior per endpoint (paste values)
       - Magic-link URL format (`$frontend_url/signup/confirm?token=...`)
       - Orientation-status enumeration-safety contract
       - Decision: cancelled signups visible in manage endpoint? (document)
       - Any fields the frontend should treat as opaque (ids)
    7. **Phase 11 Handoff** — things deferred: audit log on cancel, cancel-batch
       endpoint, signup_manage purpose token issuance (Phase 11 issues these).
    8. **Phase 12 Handoff** — admin stubs landed in Task 1 with `# Phase 12`
       comments; list the line numbers.
    9. **Self-Check** — checkbox list mirroring must_haves.

    Commit: `docs(09): Phase 09 SUMMARY + handoffs for Phases 10/11/12`
  </action>
  <verify>
    <automated>
      test -f /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-SUMMARY.md &amp;&amp;
      grep -q "Phase 10 Handoff" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-SUMMARY.md &amp;&amp;
      grep -q "Residual Risks" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-SUMMARY.md &amp;&amp;
      grep -q "Verification Gate Results" /Users/andysubramanian/uni-volunteer-scheduler/.planning/phases/09-public-signup-backend/09-SUMMARY.md &amp;&amp;
      echo "SUMMARY complete"
    </automated>
  </verify>
  <done>
    09-SUMMARY.md exists with all 9 sections. Phase 10 handoff has concrete
    endpoint shapes + error formats + rate limits. All deviations documented.
    Final commit landed.
  </done>
</task>

</tasks>

<verification>
Phase-level gates (run by Task 14; enumerated here for the verifier):

1. **Boot gate:** `python -c "from app.main import app"` exits 0.
2. **Alembic round-trip:** upgrade → downgrade base → upgrade head clean, ending at `0010_phase09_notifications_volunteer_fk`.
3. **pytest baseline:** ≥148 passed, ≤3 skipped, 0 failed.
4. **Curl smoke:** `scripts/smoke_phase09.sh` runs the full flow without error.
5. **Schema inspection:** `\d notifications` shows `volunteer_id` + `ck_notifications_recipient_xor`.
6. **signup.user cleanliness:** `grep -rn "signup\.user\b" backend/app/` returns no hits.
7. **New test coverage:** every public endpoint has ≥1 happy + ≥2 error path tests + rate-limit test where applicable.
8. **Threat model mitigations verified:** T-09-04 cross-volunteer cancel test, T-09-11 no-auth test, T-09-12 notifications XOR test all green.
</verification>

<success_criteria>
Phase 09 is complete when:

- [ ] App boots cleanly (Gate 1)
- [ ] Migration 0010 round-trips (Gate 2)
- [ ] pytest ≥148/≤3/0 (Gate 3) — exact number recorded in SUMMARY
- [ ] Curl smoke passes (Gate 4)
- [ ] All 7 public endpoints respond per spec with correct rate limits
- [ ] 74 skipped tests triaged: Bucket A un-skipped, Bucket B admin-fixed, Bucket C deleted
- [ ] Threat model mitigations each have a test (T-09-04, T-09-11, T-09-12 at minimum)
- [ ] Phone normalization rejects bad input with 422
- [ ] Expired-pending cleanup task + beat schedule landed
- [ ] notifications.volunteer_id FK + CHECK constraint in live DB
- [ ] Email template `signup_confirm.html` renders via existing `_render_html` pattern
- [ ] No `signup.user` references remain in `backend/app/`
- [ ] 09-SUMMARY.md includes Phase 10 handoff section with concrete endpoint shapes
- [ ] Commits: ~15-25 atomic commits on branch, each referencing `(09)` scope
- [ ] All 13 locked decisions (D-01..D-13) implemented without scope reduction
</success_criteria>

<output>
After completion, create `.planning/phases/09-public-signup-backend/09-SUMMARY.md`
(Task 15) and `.planning/phases/09-public-signup-backend/09-verification.txt`
(Task 14). Both are committed.
</output>
