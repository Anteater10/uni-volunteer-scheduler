# Phase 09: Public Signup Backend — Research

**Researched:** 2026-04-09
**Domain:** FastAPI public endpoints, magic-link refactor, volunteer upsert, phonenumbers, Celery email pipeline
**Confidence:** HIGH — all findings sourced directly from the live codebase (no training-data assumptions on design decisions)

---

## Summary

Phase 08 landed the schema and left the app intentionally broken at 11 specific call sites (`signup.user`, `signup.user.email`, etc.). Phase 09's first job is to repair those breaks so the app can boot. The second job is to build the new public surface (7 endpoints + phone normalization + magic-link refactor). The two jobs are sequenced because all 74 skipped tests depend on the boot-fix work.

The existing magic-link service (`magic_link_service.py`) is close but not ready: `issue_token()` takes a single `Signup`, sets no `purpose`, and uses `signup.user.email` inside `dispatch_email()`. The refactor is medium-sized — about 30–40 lines change — but must be done carefully because the signal tests (`test_check_rate_limit_*`) are still running and must stay green. The email pipeline uses SendGrid (not Resend despite a TODO comment), with a dedup table (`sent_notifications`) and a per-`kind` guard. The Celery task `send_email_notification` is not suitable for the new magic-link email as-is; the cleanest path is a new Celery task `send_signup_confirmation_email` that fires outside the dedup path.

Per-IP rate limiting already exists in `app.deps.rate_limit()` — a Redis-backed FastAPI dependency. It is wired only to specific routes today; the public signup endpoint must opt in.

**Primary recommendation:** Treat Phase 09 as three sequential sub-phases in a single plan: (1) boot-fix — repair `signup.user` references so the app boots and 74 tests can be un-skipped; (2) service layer — `volunteer_service.py`, `phone_service.py`, refactored `magic_link_service.py`; (3) public router — new `backend/app/routers/public.py` with 7 endpoints registered in `main.py`.

---

## Project Constraints (from CLAUDE.md)

- Backend tests run inside Docker on `uni-volunteer-scheduler_default` network — never against localhost postgres.
- Alembic revision IDs use descriptive slug form (e.g., `0009_phase08_v1_1_schema_realignment`).
- `alembic/env.py` pre-widens `version_num` to `VARCHAR(128)` — do not remove.
- Phase 5.07 LLM CSV extraction is blocked and out of scope.
- Stack: FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery + Redis.
- `phonenumbers>=8.13,<9` is already in `requirements.txt` (added in Phase 08).

---

## Standard Stack

All libraries below are already installed. No new `pip install` is needed.

### Core (already in requirements.txt)
| Library | Version | Purpose |
|---------|---------|---------|
| fastapi | current | Router framework |
| sqlalchemy | current | ORM + query layer |
| pydantic v2 | current | Request/response validation |
| phonenumbers | >=8.13,<9 | Phone normalization (added Phase 08) |
| redis | current | Rate-limit counters |
| celery | current | Async email dispatch |
| sendgrid | current | Email delivery (NOTE: code says "TODO: swap for Resend" but SendGrid is what's wired) |

[VERIFIED: backend/requirements.txt + app/celery_app.py]

### Not needed
- `slowapi` / `fastapi-limiter` — NOT in use. Rate limiting is hand-rolled in `app.deps.rate_limit()`. Do not add a competing library.
- `phonenumbers` — already installed; do not re-add.

---

## Architecture Patterns

### Recommended Project Structure for Phase 09

```
backend/app/
├── routers/
│   └── public.py           # NEW — all /api/v1/public/* endpoints
├── services/
│   ├── volunteer_service.py # NEW — upsert_by_email()
│   └── phone_service.py     # NEW — normalize_phone(), raises typed error
├── magic_link_service.py    # MODIFIED — add purpose arg, remove signup.user refs
├── emails.py                # MODIFIED — send_signup_confirmation() builder
├── celery_app.py            # MODIFIED — new task + fix signup.user refs
├── schemas.py               # MODIFIED — new public schemas
└── main.py                  # MODIFIED — register public router
```

### Pattern 1: Volunteer Upsert by Email

The `volunteers` table has `UNIQUE(email)`. The canonical upsert is:

```python
# Source: app/models.py — Volunteer model
def upsert_volunteer(db: Session, email: str, first_name: str, last_name: str, phone_e164: str | None) -> Volunteer:
    """
    ON CONFLICT(email) DO UPDATE: update name + phone if changed.
    Returns the Volunteer row (existing or newly created).
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = (
        pg_insert(Volunteer)
        .values(email=email.lower(), first_name=first_name, last_name=last_name, phone_e164=phone_e164)
        .on_conflict_do_update(
            index_elements=["email"],
            set_={"first_name": first_name, "last_name": last_name, "phone_e164": phone_e164,
                  "updated_at": func.now()},
        )
        .returning(Volunteer.id)
    )
    result = db.execute(stmt)
    volunteer_id = result.scalar_one()
    db.flush()
    return db.get(Volunteer, volunteer_id)
```

Alternatively: `db.query(Volunteer).filter_by(email=email.lower()).first()` then create-or-update. Either works. The `pg_insert` path is atomic under concurrent submissions from the same email.

### Pattern 2: Per-Slot Signup Creation (batch)

```python
# One Signup row per slot_id — do not create a single Signup for the batch
for slot_id in slot_ids:
    slot = db.query(Slot).filter_by(id=slot_id).with_for_update().first()
    # capacity check: if slot.current_count >= slot.capacity → 409 or skip
    signup = Signup(volunteer_id=volunteer.id, slot_id=slot.id, status=SignupStatus.registered)
    db.add(signup)
    slot.current_count += 1
    db.flush()
```

**Status decision for Phase 09:** The ROADMAP says signups start as `registered` and flip to `confirmed` on token consume. The existing `SignupStatus` enum has `pending` (not `registered`). The planner must decide: use `pending` (existing value, matches the Phase 3 check-in state machine's "pending→confirmed" transition) or add `registered` to the enum (needs a new Alembic migration). Research recommendation: use `pending` — the word "registered" appears only in the ROADMAP prose, not in the schema. Adding a new enum value requires another `autocommit_block` ALTER TYPE migration. Using the existing `pending` avoids migration risk and the Phase 3 state machine already handles `pending→confirmed` in `consume_token()`.

[VERIFIED: app/models.py SignupStatus enum; app/magic_link_service.py consume_token() line 68]

### Pattern 3: Magic-Link Refactor — Minimum Viable Changes

Current `issue_token()` signature:
```python
def issue_token(db: Session, signup: Signup, email: str) -> str:
```
It creates a `MagicLinkToken` row but does NOT set `purpose` or `volunteer_id`. It also links a single `signup_id`.

For Phase 09, the token must cover a **batch** of signups (one token confirms all slots from one submission). The `MagicLinkToken` model still has `signup_id` as a FK (not nullable). The cleanest refactor:

Option A — Token tied to one "anchor" signup, but confirms all signups created at the same time sharing the same `volunteer_id + event`:
- Issue token against the first signup in the batch
- `consume_token()` finds all signups for that volunteer + event in `pending` status and flips them all
- No schema change needed (signup_id column stays)

Option B — Add a batch token table (new migration, new model)
- Too heavy for Phase 09; defeats the "no new migrations" goal

**Recommendation:** Option A. Token is anchored to the first signup in the batch. `consume_token()` is extended to accept a `purpose` and look up all sibling signups when `purpose == signup_confirm`.

Minimum changes to `magic_link_service.py`:
1. `issue_token()`: add `purpose: MagicLinkPurpose = MagicLinkPurpose.SIGNUP_CONFIRM` and `volunteer_id: UUID | None = None` params; set on the row.
2. `consume_token()`: when purpose is `signup_confirm`, after confirming the anchor signup, also confirm all other `pending` signups where `volunteer_id == token.volunteer_id AND slot.event_id == anchor.slot.event_id`.
3. `dispatch_email()`: replace `signup.user.email` with `signup.volunteer.email`.

[VERIFIED: app/magic_link_service.py — full file read; app/models.py MagicLinkToken lines 420–444]

### Pattern 4: Rate Limiting (already exists)

```python
# Source: app/deps.py — rate_limit() function
from ..deps import rate_limit

@router.post("/signups", dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))])
def public_create_signup(...):
    ...
```

`rate_limit()` is a Redis-backed per-IP + path counter. It raises 429 when the limit is exceeded. Settings keys: `rate_limit_max_requests` (default 100) and `rate_limit_window_seconds` (default 60). For the public signup endpoint, override to stricter values (10 per minute per IP recommended).

The magic-link service also has its own email-keyed + IP-keyed rate limit (`check_rate_limit()`) in `magic_link_service.py` — this already applies to `/auth/magic/resend`.

[VERIFIED: app/deps.py lines 37–57; app/magic_link_service.py lines 78–95]

### Pattern 5: Celery Email Dispatch for Public Signups

The existing `send_email_notification` task routes by `kind` using `BUILDERS` dict, but `BUILDERS` expects a `Signup` with a `user` relationship (not `volunteer`). All five builders use `signup.user.email`, `signup.user.name` etc.

Two options:
- Option A: Update all BUILDERS to use `signup.volunteer` — this is required anyway for the boot-fix.
- Option B: Add a new task specifically for the signup confirmation email that takes explicit args.

**Recommendation:** Do Option A first (boot-fix), then for the new "confirm your signup" email, add a new `send_signup_confirmation_email` task that takes `volunteer_id + signup_ids + token + event_id` as string args (not model references — Celery tasks must be serializable). This avoids stuffing the batch-confirmation into the dedup `kind` pattern, which is designed for one-signup-at-a-time reminders.

Email provider note: The code has `TODO(resend): swap SendGrid client for Resend SDK` in `celery_app.py`. The actual provider is SendGrid via `SendGridAPIClient`. Phase 09 should use the existing `_send_email_via_sendgrid()` helper and not attempt the Resend migration.

[VERIFIED: app/celery_app.py lines 68–89, 140–141]

### Pattern 6: Email Template System

The system uses Python's `string.Template` with `safe_substitute()` and file-based HTML templates in `backend/app/email_templates/`. Files: `base.html`, `confirmation.html`, `cancellation.html`, `reminder.html`, `reschedule.html`.

The magic-link email (`send_magic_link()` in `emails.py`) is currently inline HTML — no template file. For the Phase 09 "Confirm your signup" email, two approaches:
- Inline HTML (like the existing `send_magic_link`) — simpler, no new template file
- Template file (like `confirmation.html`) — consistent with the pattern, easier to maintain

**Recommendation:** Create `email_templates/signup_confirm.html` using the existing `_render_html()` pattern. Variables needed: `volunteer_name`, `event_title`, `slot_list` (multi-line), `confirm_url`, `manage_url`.

TTL note: `magic_link_ttl_minutes` in `config.py` is currently 15 minutes. The REQUIREMENTS spec says "~14 days (until end of module)". This setting must be overridden for signup-confirm tokens. Approach: pass an explicit `expires_at` to `issue_token()` rather than reading the global setting — or add a `ttl_minutes` override param.

[VERIFIED: app/emails.py; app/config.py line 38; app/email_templates/ directory listing]

### Anti-Patterns to Avoid

- **Don't call `db.commit()` inside `issue_token()`** — it uses `db.flush()` correctly; caller commits. Keep this pattern.
- **Don't use `signup.user` anywhere in new code** — the relationship was removed in Phase 08. Every reference to it in old code is a runtime break site.
- **Don't import `PrereqOverride` from models** — the model is deleted. `services/prereqs.py` has an import guard; don't add new direct imports.
- **Don't register the public router behind `get_current_user`** — these endpoints are loginless.
- **Don't add fastapi-limiter or slowapi** — the existing `rate_limit()` in `deps.py` is sufficient.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Phone parsing/normalization | Custom regex | `phonenumbers` library (already installed) | Handles E.164, country codes, edge cases (extensions, letters, etc.) |
| Rate limiting | Another Redis counter | `app.deps.rate_limit()` (already exists) | Reinventing creates two competing systems |
| Token hashing | Raw storage | SHA-256 via `_hash_token()` in `magic_link_service.py` (already exists) | Only the hash is stored — the raw token lives only in the email URL |
| Email dedup | Manual flag columns | `sent_notifications` table with `INSERT ON CONFLICT DO NOTHING` (already exists) | Exactly-once delivery under concurrent Celery workers |
| ORM upsert | SELECT + INSERT in two steps (race condition) | `pg_insert().on_conflict_do_update()` (Postgres-native) | Atomic under concurrent signups from the same email |

---

## Existing Code Map: What to Fix vs. What to Build

### Boot-Fix Sites (must fix first — app will not start without these)

| File | Line(s) | Current code | Fix |
|------|---------|--------------|-----|
| `magic_link_service.py` | 100 | `email = signup.user.email if signup.user else None` | `email = signup.volunteer.email if signup.volunteer else None` |
| `emails.py` | 56, 78, 101, 125, 150 | `user = signup.user` (all five BUILDERS) | `user = signup.volunteer` — but `Volunteer` has `first_name`/`last_name` not `name`. All builders use `user.name`. Need `f"{v.first_name} {v.last_name}"` |
| `celery_app.py` | 141 | `user = signup.user` | `user = signup.volunteer` (same name field issue) |
| `celery_app.py` | 281 | `by_user.setdefault(s.user_id, [])` in `weekly_digest` | Replace with `s.volunteer_id` |
| `celery_app.py` | 155 | `if user.notify_email:` | `Volunteer` has no `notify_email` field — always send, or add a check |
| `celery_app.py` | 158–166 | Creates `Notification(user_id=user.id, ...)` | `Notification` still has `user_id FK`. Volunteers are not Users. Either skip the Notification row for volunteer emails or make `user_id` nullable on `notifications`. |

**Critical discovery — `Notification` table FK:** The `Notification` model has `user_id = Column(ForeignKey("users.id"), nullable=False)`. This means the existing `send_email_notification` Celery task cannot log volunteer emails to the notifications table without either (a) making `user_id` nullable or (b) skipping the DB log for volunteer emails. This needs a decision before the planner runs.

**Recommendation:** For Phase 09, skip the `Notification` row for volunteer emails (log to Celery logger instead). Making `user_id` nullable is a schema change (new migration) and is deferred to Phase 11 or 12.

[VERIFIED: app/models.py Notification table line 305; app/celery_app.py lines 141, 155–166]

### Magic-Link Service: Specific Refactor

Current `issue_token()`:
```python
def issue_token(db: Session, signup: Signup, email: str) -> str:
    ...
    row = MagicLinkToken(
        token_hash=token_hash,
        signup_id=signup.id,
        email=email.lower(),
        expires_at=expires_at,
    )
```

Refactored for Phase 09:
```python
def issue_token(
    db: Session,
    signup: Signup,
    email: str,
    *,
    purpose: MagicLinkPurpose = MagicLinkPurpose.SIGNUP_CONFIRM,
    volunteer_id=None,
    ttl_minutes: int | None = None,
) -> str:
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    ttl = ttl_minutes or settings.magic_link_ttl_minutes
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

Current `consume_token()` flips `signup.status` from `pending` to `confirmed` for the single signup linked to the token. For Phase 09 batch-confirm:
```python
# After flipping the anchor signup, also flip siblings:
if purpose == MagicLinkPurpose.SIGNUP_CONFIRM and row.volunteer_id:
    event_id = signup.slot.event_id
    sibling_signups = (
        db.query(Signup)
        .join(Slot)
        .filter(
            Signup.volunteer_id == row.volunteer_id,
            Signup.status == SignupStatus.pending,
            Slot.event_id == event_id,
        )
        .all()
    )
    for s in sibling_signups:
        s.status = SignupStatus.confirmed
```

[VERIFIED: app/magic_link_service.py — full file; app/models.py MagicLinkToken]

### 74 Skipped Tests — Triage

All 74 tests are file-level or individual `@pytest.mark.skip` with the same reason. The grouping into three buckets:

**Bucket A — Trivial rename (use `signup.volunteer` + `VolunteerFactory`): un-skip in Phase 09**

These tests test currently-healthy behavior that just needs the factory and relationship pointer updated.

| File | Tests | Change needed |
|------|-------|---------------|
| `test_signups.py` | 8 | `SignupFactory(user=...) → SignupFactory(volunteer=...)` + `signup.user → signup.volunteer` |
| `test_check_in_endpoints.py` | 9 | Same factory + relationship swap; check-in state machine itself is unchanged |
| `test_check_in_service.py` | 8 | Same (creates Signup with `user_id=` directly) |
| `test_concurrent_check_in.py` | 10 | Same; tests concurrency of check-in, not user auth |
| `test_models_magic_link.py` | 5 | Creates Signup with `user_id=`; swap to `volunteer_id=` |
| `test_models_phase3.py` | 2 classes | `TestSignupCheckedInTransition`, `TestMagicLinkTokenPurpose` — same swap |
| `test_magic_link_service.py` | 5 | `_make_pending_signup` creates `SignupFactory(user=user...)` — swap to volunteer |
| `test_magic_link_router.py` | 6 | `resend` endpoint uses `Signup.user.has(email=...)` — router must also be fixed |
| `test_roster_endpoints.py` | 1 | `Signup(user_id=participant.id...)` → `Signup(volunteer_id=volunteer.id...)` |

**Bucket B — Requires new public router in Phase 09 (new tests, not un-skips)**

- `test_contract.py::test_createSignup_trailing_slash` — tests `POST /signups/` with trailing slash. After Phase 09, the old `POST /signups/` endpoint is still the organizer/user endpoint (now broken). Either: (a) fix the old endpoint too in Phase 09, or (b) the public replacement is `POST /public/signups`. This test needs a decision: does it test the old auth'd endpoint (rewire to volunteer) or the new public endpoint?

**Bucket C — Admin tests requiring `signup.user` (repair the router, not just the test)**

| File | Tests | What's broken |
|------|-------|---------------|
| `test_admin.py::test_admin_delete_user` | 1 | `admin.py` at multiple lines accesses `signup.user` |
| `test_admin.py::test_admin_cancel_signup_promotes_waitlist` | 1 | Same — admin cancel uses `promote_waitlist_fifo` which calls `dispatch_email` → `signup.user` |
| `test_admin_phase7.py::test_analytics_volunteer_hours_shape` | 1 | Analytics endpoint uses `signup.user` |
| `test_admin_phase7.py::test_ccpa_export_returns_user_data` | 1 | CCPA export references `signup.user` |
| `test_admin_phase7.py::test_ccpa_delete_preserves_signups` | 1 | CCPA delete references `signup.user` |

The 5 admin tests require fixing `admin.py` lines (listed in SUMMARY). The SUMMARY says Phase 09 fixes `signup.user` sites, but `admin.py` is complex and Phase 12 is supposed to retire most of admin. **Decision needed:** Fix admin.py's `signup.user` references in Phase 09 (boot-fix scope) or defer to Phase 12? The app cannot boot until they're fixed regardless.

**Recommendation:** Fix the minimum admin.py lines needed for the app to boot (swap `signup.user` → `signup.volunteer`, adjust `.name` access to `f"{v.first_name} {v.last_name}"`). Do not refactor admin.py further — that's Phase 12 scope. The 5 admin tests can then be un-skipped.

**Notification-related tests:**

| File | Tests | Category |
|------|-------|----------|
| `test_notifications_phase6.py` | 6 | Reminder pipeline uses `signup.user` in BUILDERS — Bucket A, fixed when emails.py is fixed |
| `test_celery_reminders.py` | 4 | Same — uses `signup.user` via send_email_notification → BUILDERS |

These un-skip naturally once `emails.py` BUILDERS are fixed.

**Factory fix required:** `SignupFactory` in `factories.py` still has `user = factory.SubFactory(UserFactory)` and `user_id = factory.LazyAttribute(...)`. This must be replaced with a new `VolunteerFactory`. Every Bucket A test needs this.

[VERIFIED: backend/tests/fixtures/factories.py; all skip-annotated test files]

---

## New Schemas Required

All new schemas go into `backend/app/schemas.py`. The existing `SignupRead` uses `user_id: UUID` — it should not be changed (the old auth'd endpoint still exists until Phase 12). New schemas are separate.

| Schema | Fields | Notes |
|--------|--------|-------|
| `VolunteerCreate` | `first_name`, `last_name`, `email: EmailStr`, `phone: str` | Phone is raw string; normalization happens in service layer, not schema |
| `VolunteerRead` | `id: UUID`, `email`, `first_name`, `last_name`, `phone_e164`, `created_at` | |
| `PublicSignupCreate` | `first_name`, `last_name`, `email: EmailStr`, `phone: str`, `slot_ids: List[UUID]` | |
| `PublicSignupResponse` | `volunteer_id: UUID`, `signup_ids: List[UUID]`, `magic_link_sent: bool` | Returned from `POST /public/signups` |
| `PublicSlotRead` | `id: UUID`, `slot_type: SlotType`, `date: date`, `start_time: datetime`, `end_time: datetime`, `location: str | None`, `capacity: int`, `filled: int` | |
| `PublicEventRead` | `id: UUID`, `title: str`, `quarter: Quarter`, `year: int`, `week_number: int`, `school: str`, `module_slug: str | None`, `start_date: datetime`, `end_date: datetime`, `slots: List[PublicSlotRead]` | |
| `OrientationStatus` | `has_attended_orientation: bool`, `last_attended_at: datetime | None` | |

Note: `SignupRead.user_id` stays untouched in Phase 09 — the field is stale but removing it breaks the existing (still-auth'd) signup router and tests. Phase 12 cleans it up.

[VERIFIED: app/schemas.py — full file; app/models.py Quarter, SlotType enums]

---

## Orientation-Status Query

The orientation check is: "does this volunteer (by email) have any `attended` signup on an `orientation` slot, all-time (not per-quarter)?"

The ROADMAP spec says `GET /public/volunteers/{email}/orientation-status?module_slug=` but the REQUIREMENTS v1.1 says "orientation as soft warning" checked by looking up past `attended` orientation signups under the same email. The scoping (per-quarter vs all-time) is listed as an open item in REQUIREMENTS.

**Recommended SQL (pseudocode):**
```sql
SELECT s.id, s.timestamp
FROM signups s
JOIN volunteers v ON v.id = s.volunteer_id
JOIN slots sl ON sl.id = s.slot_id
WHERE v.email = :email
  AND sl.slot_type = 'orientation'
  AND s.status = 'attended'
  [AND sl.event_id IN (SELECT id FROM events WHERE module_slug = :module_slug)]  -- if per-module
ORDER BY s.timestamp DESC
LIMIT 1
```

If `module_slug` filter is omitted → all-time across all modules.
If `module_slug` filter is included → only orientation for that module.

**Decision needed from Andy:** All-time or per-module? The REQUIREMENTS text says "orientation this quarter or a prior orientation covering this module?" — the modal copy implies "per-module" is the spirit. But "all-time" is simpler to implement and covers the common case (orientation is orientation). Recommend: implement `module_slug` as optional filter; if not provided, all-time.

The endpoint in the scope spec has two different URL forms:
- ROADMAP: `GET /public/volunteers/{email}/orientation-status?module_slug=`  
- Phase scope in objective: `GET /api/v1/public/orientation-status?email=`

Email in path vs. query param is a privacy consideration (email in path → appears in server logs and Referer headers). Use query param: `GET /public/orientation-status?email=&module_slug=`.

[VERIFIED: app/models.py SignupStatus, SlotType; REQUIREMENTS-v1.1-accountless.md]

---

## Event Week-Filter Query

`GET /public/events?quarter=&year=&week=&school=`

Query:
```sql
SELECT e.*, s.*
FROM events e
LEFT JOIN slots s ON s.event_id = e.id
WHERE e.quarter = :quarter
  AND e.year = :year
  AND e.week_number = :week
  [AND e.school = :school]
ORDER BY e.school, e.start_date, s.date, s.start_time
```

**What if no filter is provided?**

Two options:
- Return 400 (quarter + year + week are required): safest, prevents dumping all events
- Return current week's events: convenient for the frontend

**Recommendation:** Require `quarter` + `year` + `week` as required query params. Return 422 if any is missing. Rationale: the frontend browse page always knows what week it's showing; "no filter" would dump all events which is useless for public display. The school filter stays optional for narrowing.

**Capacity field naming:** The scope specifies `capacity`, `filled`, `slot_type` on slot results. `Slot.current_count` is the live "filled" count. The public schema should rename it: `filled: int = slot.current_count`.

[VERIFIED: app/models.py Event, Slot; REQUIREMENTS-v1.1-accountless.md Q3, Q4]

---

## Phone Normalization Service

`phonenumbers` is already installed. Standard usage:

```python
# Source: phonenumbers library (training knowledge; verify against docs if behavior is unexpected)
import phonenumbers
from phonenumbers import NumberParseException

def normalize_phone_e164(raw: str, default_region: str = "US") -> str:
    """Parse raw phone string → E.164. Raises ValueError on invalid input."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except NumberParseException as exc:
        raise ValueError(f"Invalid phone number: {raw}") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Phone number not valid: {raw}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
```

The FastAPI endpoint converts `ValueError` → 422 via Pydantic validation or an explicit `HTTPException(status_code=422)`. The cleanest approach: call `normalize_phone_e164()` in the service layer and raise `HTTPException(status_code=422, detail=str(e))`.

[VERIFIED: backend/requirements.txt has phonenumbers>=8.13,<9; ASSUMED: phonenumbers API surface matches training knowledge — verify against phonenumbers docs if unusual behavior]

---

## Security Domain

### Trust Boundaries

| Input | Controlled by | Risk |
|-------|--------------|------|
| `email` | Public (unauthenticated) | Primary attack surface for enumeration and spam |
| `phone` | Public | SSRF-ish risk if passed to external lookup services — not applicable here since we parse locally |
| `slot_ids` | Public | Overbooking attack, replay |
| `token` | Public (from email link) | Token guessing, replay, expiry bypass |

### Threat Model Notes for the Planner

**Threat 1: Mass fake volunteer creation (signup spam)**

Attack: attacker POSTs `POST /public/signups` thousands of times with random emails, filling slots.

Controls to implement:
- Per-IP rate limit via `rate_limit()` dependency on the endpoint (e.g., 10/minute per IP)
- Email-keyed rate limit: the existing `check_rate_limit()` in `magic_link_service.py` limits to 5 magic-link emails per email per hour — apply when issuing the confirm token
- No CAPTCHA in this phase (frontend concern, Phase 10)
- Note: there is no email verification before the signup is created. Signups land as `pending` until the confirm link is clicked. Unconfirmed (pending) signups hold capacity. If spam fills slots with fake emails, nobody can get in. Mitigation: consider only counting `confirmed` (not `pending`) against capacity. **This is an open design decision.**

**Threat 2: Confirm someone else's signup via token guessing**

Attack: attacker brute-forces the token URL to confirm/manage someone's signup.

Controls already in place:
- Tokens are `secrets.token_urlsafe(32)` — 256 bits of entropy. Brute force is computationally infeasible.
- Only the SHA-256 hash is stored in the DB; raw token is never logged.
- `consumed_at` prevents replay: a used token returns `ConsumeResult.used`.
- Tokens expire (currently 15 min — must be raised to ~14 days for signup confirm).

**Threat 3: Volunteer enumeration via orientation-status endpoint**

Attack: `GET /public/orientation-status?email=victim@student.ucsb.edu` leaks whether a person has ever volunteered.

Mitigations:
- The endpoint returns `{has_attended_orientation: false}` for any unknown email — same shape as a known email with no history. An attacker cannot distinguish "never signed up" from "signed up but not attended orientation".
- However, repeated probing can confirm "this email has attendance records" when `true` is returned. This is an acceptable information disclosure for a volunteer scheduler (attendance is not sensitive health data).
- Rate limiting the orientation-status endpoint is sufficient (5 requests/minute per IP).

**Threat 4: Duplicate signup for the same slot**

The `signups` table has `UNIQUE(volunteer_id, slot_id)` (constraint `uq_signups_volunteer_id_slot_id`). A duplicate insert raises an `IntegrityError`. The router must catch this and return 409 (Conflict) rather than 500.

[VERIFIED: app/models.py Signup.__table_args__; app/deps.py rate_limit(); app/magic_link_service.py check_rate_limit()]

---

## Common Pitfalls

### Pitfall 1: `Volunteer.name` vs. `User.name`

**What goes wrong:** The `Volunteer` model has `first_name` and `last_name` fields. The `User` model had a single `name` field. Every email builder in `emails.py` does `user.name`. After the boot-fix swap to `signup.volunteer`, the code will crash with `AttributeError: 'Volunteer' object has no attribute 'name'`.

**How to avoid:** Replace `user.name` with `f"{volunteer.first_name} {volunteer.last_name}"` in all 5 BUILDERS and in the Celery `weekly_digest` task. Also update `RosterRow.student_name` logic in `roster.py`.

**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'name'` or `AttributeError: 'Volunteer' object...` in logs.

[VERIFIED: app/models.py Volunteer (lines 93–108) vs User (line 122)]

### Pitfall 2: `Notification` table requires `user_id` (not nullable)

**What goes wrong:** The `send_email_notification` Celery task always creates a `Notification` row with `user_id=user.id`. Volunteers are not Users. The `notifications.user_id` FK is `nullable=False`. Passing a Volunteer's id will cause a FK violation at runtime.

**How to avoid:** In the new `send_signup_confirmation_email` Celery task, do NOT create a `Notification` row. Log to the Celery logger (`logger.info(...)`) instead. The existing `sent_notifications` dedup table is optional for the confirmation email since it fires only once per submission.

[VERIFIED: app/models.py Notification line 305; app/celery_app.py lines 155–166]

### Pitfall 3: `MagicLinkToken.signup_id` is NOT nullable

**What goes wrong:** `magic_link_tokens.signup_id` is `NOT NULL` (see models.py line 425). If Phase 09 tries to issue a token without a signup (e.g., for the manage-link separately), the insert will fail.

**How to avoid:** The Phase 09 token must be anchored to at least one signup. Issue one token after creating the first signup in the batch, passing that signup's id as the anchor. Sibling signups are found at consume-time via `volunteer_id + event_id`.

[VERIFIED: app/models.py MagicLinkToken line 425]

### Pitfall 4: Slot `current_count` drift under concurrent public signups

**What goes wrong:** If two requests submit for the same slot simultaneously, both read `current_count < capacity`, both increment, and the slot is overbooked.

**How to avoid:** Lock the slot row with `.with_for_update()` before reading `current_count`, same as the existing `create_signup` in `routers/signups.py`. The locking pattern is already established — follow it exactly.

[VERIFIED: app/routers/signups.py lines 60–65]

### Pitfall 5: `magic_link_ttl_minutes = 15` in config

**What goes wrong:** The signup confirmation email expires in 15 minutes (the old account-confirm use case). A volunteer who doesn't check email immediately cannot confirm their signup.

**How to avoid:** Pass explicit `ttl_minutes` to the refactored `issue_token()`. For `signup_confirm` tokens, use 14 days (20160 minutes) or compute `expires_at = slot.date + 1 day` (whichever is sooner). Do not change the global config setting — it still applies to resend rate limiting logic and other uses.

[VERIFIED: app/config.py line 38; REQUIREMENTS-v1.1-accountless.md "Token lifetime ~14 days"]

### Pitfall 6: `weekly_digest` task uses `s.user_id`

**What goes wrong:** `celery_app.py` line 281 does `by_user.setdefault(s.user_id, [])`. After Phase 08, signups no longer have `user_id`. This crashes the weekly_digest task at runtime.

**How to avoid:** Update to `s.volunteer_id` and skip the Notification log step (same as Pitfall 2). The weekly_digest email content also references `slot.event.location` — that relationship is fine.

[VERIFIED: app/celery_app.py lines 279–291]

---

## Code Examples

### Phone Normalization (phonenumbers)

```python
# backend/app/services/phone_service.py
import phonenumbers
from phonenumbers import NumberParseException

def normalize_phone_e164(raw: str, default_region: str = "US") -> str:
    """Parse any US phone format to +1XXXXXXXXXX (E.164).
    Raises ValueError with a human-readable message on bad input."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except NumberParseException as exc:
        raise ValueError(f"Cannot parse phone number '{raw}'") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: '{raw}'")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
```

### Public Router Skeleton

```python
# backend/app/routers/public.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import rate_limit

router = APIRouter(prefix="/public", tags=["public"])

@router.post("/signups", dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60))])
def public_create_signup(body: schemas.PublicSignupCreate, db: Session = Depends(get_db)):
    ...

@router.get("/events", response_model=list[schemas.PublicEventRead])
def public_list_events(
    quarter: models.Quarter = Query(...),
    year: int = Query(...),
    week: int = Query(...),
    school: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    ...
```

Registration in `main.py`:
```python
from .routers import public as public_router
app.include_router(public_router.router, prefix="/api/v1")
```

### VolunteerFactory (for tests)

```python
# backend/tests/fixtures/factories.py — add this class
from app.models import Volunteer

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
```

`SignupFactory` must be updated:
```python
class SignupFactory(SQLAlchemyModelFactory):
    ...
    volunteer = factory.SubFactory(VolunteerFactory)
    volunteer_id = factory.LazyAttribute(lambda o: o.volunteer.id)
    # Remove: user, user_id
```

---

## State of the Art

| Old Approach | Current Approach | Impact for Phase 09 |
|--------------|------------------|---------------------|
| `signup.user` (User FK) | `signup.volunteer` (Volunteer FK) | All boot-fix sites must swap |
| Single signup per POST | Batch: one POST, N signups, one token | `issue_token()` anchors to first signup |
| 15-minute magic-link TTL | 14-day TTL for signup-confirm | Override via `ttl_minutes` param |
| `purpose` field unused (defaults to `email_confirm`) | `signup_confirm` and `signup_manage` now valid values | Set purpose explicitly |

---

## Environment Availability

No new external dependencies. All tools confirmed available in the existing Docker stack.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| phonenumbers | Phone normalization | Yes | >=8.13,<9 (requirements.txt) | — |
| Redis | Rate limiting, Celery broker | Yes (docker-compose) | — | — |
| Celery + SendGrid | Email dispatch | Yes | celery_app.py wired | — |
| Postgres 16 | All DB operations | Yes (docker-compose) | 16 | — |

**Missing:** Resend SDK is NOT installed despite the `TODO(resend)` comment in `celery_app.py`. Do not attempt Resend migration in Phase 09 — use the existing SendGrid path.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (backend), vitest (frontend) |
| Config file | `backend/conftest.py` (session scope, transactional fixtures) |
| Quick run command | `docker run --rm --network uni-volunteer-scheduler_default -v $PWD/backend:/app -w /app -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" uni-volunteer-scheduler-backend sh -c "pytest -q -x"` |
| Full suite command | Same without `-x` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command |
|-----|----------|-----------|-------------------|
| R09-01 | POST /public/signups creates Volunteer (new email) | integration | `pytest tests/test_public_signups.py::test_new_email_creates_volunteer -xvs` |
| R09-02 | POST /public/signups upserts same Volunteer (repeat email) | integration | `pytest tests/test_public_signups.py::test_same_email_upserts_volunteer -xvs` |
| R09-03 | Confirm token flips all signups registered → confirmed; expired/used rejected | integration | `pytest tests/test_public_signups.py::test_confirm_token -xvs` |
| R09-04 | orientation-status true when prior attended orientation exists | integration | `pytest tests/test_public_signups.py::test_orientation_status -xvs` |
| R09-05 | Phone normalization: E.164 round-trip; 422 on bad input | unit | `pytest tests/test_phone_service.py -xvs` |
| R09-06 | 74 previously skipped tests pass | integration | `pytest -q --no-cov` — target: 150 passed, 0 skipped |
| R09-07 | GET /public/events filters by quarter+year+week | integration | `pytest tests/test_public_events.py -xvs` |

### Wave 0 Gaps (test files that don't exist yet)

- `backend/tests/test_public_signups.py` — covers R09-01 through R09-04
- `backend/tests/test_public_events.py` — covers R09-07
- `backend/tests/test_phone_service.py` — covers R09-05

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `phonenumbers.parse(raw, "US")` + `is_valid_number()` + `format_number(...E164)` is the correct call sequence | Phone Normalization | Wrong API → 422 never fires or fires incorrectly; verify against phonenumbers docs |
| A2 | `SignupStatus.pending` should be the initial status for public signups (not a new `registered` enum value) | Pattern 2 | If planner chooses `registered`, a new Alembic migration is required before any code can land |
| A3 | `Notification.user_id` is nullable=False and therefore volunteer emails should skip the Notification row | Pitfall 2 | If there's a workaround, the notifications table could log volunteer emails too |
| A4 | Token expiry of 14 days (20160 minutes) is correct for `signup_confirm` | Pitfall 5 | If Andy wants a different lifetime (e.g., event-relative), the `ttl_minutes` param must be computed differently |
| A5 | All-time orientation attendance (not per-quarter) should be the default scope for the orientation-status check | Orientation Query | If per-quarter is correct, the query needs `quarter`/`year` params too |
| A6 | The public `DELETE /public/signups/{signup_id}?token=...` endpoint (Phase 11 deliverable) can be omitted from Phase 09 | Phase scope | If it's needed in Phase 09, it increases scope |

---

## Open Questions (need answers before planning)

1. **Status for newly-created public signups: `pending` or new `registered` enum value?**
   - What we know: `SignupStatus.pending` already exists; Phase 3 state machine expects `pending → confirmed`
   - What's unclear: ROADMAP prose says "registered" status — did Andy intend a new enum value?
   - Recommendation: Use `pending` (avoid migration); Andy confirms or overrides

2. **`Notification` row for volunteer emails: skip or make `user_id` nullable?**
   - What we know: `notifications.user_id` is NOT NULL FK to `users.id`; volunteers are not users
   - What's unclear: Is there a phase where this should be fixed?
   - Recommendation: Skip Notification rows in Phase 09; add nullable FK in later migration if audit trail needed

3. **Orientation-status scope: all-time or per-module?**
   - What we know: v1.1 requirements say "orientation this quarter or a prior orientation covering this module"
   - What's unclear: "covering this module" suggests module_slug filter; "this quarter" suggests per-quarter
   - Recommendation: Implement as optional `module_slug` filter; if omitted, all-time

4. **Does `POST /public/signups` count `pending` signups against capacity?**
   - What we know: the existing authenticated signup router counts both `confirmed` and `pending` against capacity
   - What's unclear: if a spammer fills slots with fake emails that never confirm, real volunteers are locked out
   - Recommendation: Count only `confirmed` against capacity for public signups; `pending` signups do not hold a spot (flip-on-confirm increases count at confirm time)

5. **Admin.py boot-fix scope in Phase 09 vs Phase 12:**
   - What we know: admin.py has 9+ lines accessing `signup.user` and the app won't boot without fixing them
   - What's unclear: should Phase 09 do minimal fixes to admin.py or leave it for Phase 12?
   - Recommendation: Phase 09 does the minimal swap (`signup.user → signup.volunteer`, `user.name → f"{v.first_name} {v.last_name}"`); Phase 12 does structural refactoring/deletion

---

## Sources

### Primary (HIGH confidence — verified by direct code read)
- `backend/app/magic_link_service.py` — complete file map, issue/consume signatures, dispatch_email breakage
- `backend/app/emails.py` — all 5 BUILDERS use `signup.user`; template system uses `string.Template` + file-based HTML
- `backend/app/celery_app.py` — SendGrid provider, dedup pattern, `signup.user` in weekly_digest
- `backend/app/routers/signups.py` — existing POST /signups, capacity logic, `with_for_update()` pattern
- `backend/app/routers/magic.py` — existing /auth/magic/{token} consume endpoint
- `backend/app/models.py` — Volunteer, Signup, MagicLinkToken, MagicLinkPurpose, Notification models
- `backend/app/deps.py` — `rate_limit()` implementation, `log_action()`
- `backend/app/schemas.py` — existing schema surface
- `backend/app/config.py` — settings including `magic_link_ttl_minutes = 15`
- `backend/tests/fixtures/factories.py` — `SignupFactory` still uses `user`/`user_id`; `VolunteerFactory` does not exist
- `backend/conftest.py` — test session setup, transactional pattern, Celery eager mode
- All 74 skip-annotated test files — directly verified skip reasons and factory usage patterns
- `.planning/phases/08-schema-realignment-migration/08-SUMMARY.md` — boot-fix site list
- `.planning/phases/08-schema-realignment-migration/08-VERIFICATION.md` — confirmed schema state
- `.planning/REQUIREMENTS-v1.1-accountless.md` — locked decisions
- `.planning/ROADMAP.md` — Phase 09 scope

### Tertiary (ASSUMED — training knowledge not verified this session)
- phonenumbers API call sequence (`parse()`, `is_valid_number()`, `format_number()`) — see A1 in Assumptions Log

---

## Metadata

**Confidence breakdown:**
- Boot-fix sites: HIGH — every file directly inspected
- Magic-link refactor: HIGH — full service + model files read
- Schema changes needed: HIGH — models.py confirmed
- 74 test triage: HIGH — all test files inspected
- Phone normalization API: MEDIUM — library installed but API call sequence not verified against live docs
- Security analysis: HIGH — rate-limit code, token entropy, DB constraints all verified

**Research date:** 2026-04-09
**Valid until:** 2026-05-09 (stable codebase; re-check if any Phase 08 hotfixes land)
