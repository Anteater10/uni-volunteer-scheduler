---
phase: 04
plan: 03
name: Signups endpoint integration + admin override endpoints
wave: 2
depends_on: [04-01, 04-02]
files_modified:
  - backend/app/routers/signups.py
  - backend/app/routers/admin.py
  - backend/app/schemas.py
  - backend/tests/test_signups_prereq.py
  - backend/tests/test_admin_prereq_overrides.py
autonomous: true
requirements:
  - POST /signups returns 422 PREREQ_MISSING when missing
  - ?acknowledge_prereq_override=true bypasses warning, logs audit
  - POST /admin/users/{id}/prereq-overrides creates override + audit log
  - DELETE /admin/prereq-overrides/{id} soft-delete + audit log
---

# Plan 04-03: Signups Endpoint + Admin Override

<objective>
Wire `_check_prereqs()` into `POST /signups` with a `422 PREREQ_MISSING` response and
an `acknowledge_prereq_override=true` bypass query flag. Add the two admin override
endpoints. Every bypass, create, and revoke writes an `AuditLog`.
</objective>

<must_haves>
- `POST /signups` calls `check_missing_prereqs` before creating the signup.
- When `missing` is non-empty AND `acknowledge_prereq_override` is not true:
  - Return HTTP 422 with body:
    ```json
    {
      "error": "PREREQ_MISSING",
      "code": "PREREQ_MISSING",
      "detail": "Missing prerequisites",
      "missing": ["orientation"],
      "next_slot": {"event_id": "...", "slot_id": "...", "starts_at": "..."}
    }
    ```
  - `next_slot` may be `null` if no future orientation slot exists.
- When `acknowledge_prereq_override=true` AND missing is non-empty:
  - Create the signup as normal.
  - Write an `AuditLog(action="prereq_override_self", user_id=<student>, meta={signup_id, missing_prereqs})`.
- When missing is empty: unchanged behaviour.
- `POST /admin/users/{user_id}/prereq-overrides` — admin-only, body `{module_slug: str, reason: str}`.
  - 400 if `len(reason) < 10`.
  - 404 if user or module_slug unknown.
  - Creates `PrereqOverride(created_by=<admin>)` and writes `AuditLog(action="prereq_override_admin_create", meta={override_id, user_id, module_slug, reason})`.
  - Returns the created row.
- `DELETE /admin/prereq-overrides/{override_id}` — admin-only soft-delete: sets `revoked_at=now()`. Writes `AuditLog(action="prereq_override_admin_revoke", meta={override_id})`. 404 if missing, 409 if already revoked.
</must_haves>

<tasks>

<task id="04-03-01" parallel="false">
<action>
Edit `backend/app/routers/signups.py` — modify the existing `POST /signups` handler:

1. Import `check_missing_prereqs` and `find_next_orientation_slot` from
   `backend.app.services.prereqs`.
2. After loading the target `Event` and validating slot capacity/state but BEFORE
   inserting the Signup row, if `event.module_slug` is set, call
   `missing = check_missing_prereqs(db, current_user.id, event.module_slug)`.
3. Read query flag `acknowledge_prereq_override: bool = Query(default=False)` in the
   endpoint signature.
4. If `missing` is non-empty and `acknowledge_prereq_override` is False:
   Raise `HTTPException(status_code=422, detail={"error": "PREREQ_MISSING", "code": "PREREQ_MISSING", "detail": "Missing prerequisites", "missing": missing, "next_slot": find_next_orientation_slot(db)})`.
   Use a custom response so `detail` is the object (FastAPI will wrap it — acceptable;
   tests assert on `response.json()["detail"]["code"] == "PREREQ_MISSING"` OR use a
   `JSONResponse` directly to keep the shape flat — planner picks `JSONResponse` so
   the top-level keys match the spec exactly).
5. If `missing` is non-empty and `acknowledge_prereq_override` is True: create the
   signup, then write an `AuditLog(action="prereq_override_self", user_id=current_user.id, meta={"signup_id": str(signup.id), "missing_prereqs": missing})`.

Preserve all existing signup logic (capacity, waitlist promotion, etc.).
</action>
<read_first>
- backend/app/routers/signups.py
- backend/app/services/prereqs.py
- backend/app/models.py (AuditLog)
</read_first>
<acceptance_criteria>
- `grep -q 'check_missing_prereqs' backend/app/routers/signups.py`
- `grep -q 'acknowledge_prereq_override' backend/app/routers/signups.py`
- `grep -q 'PREREQ_MISSING' backend/app/routers/signups.py`
- `grep -q 'prereq_override_self' backend/app/routers/signups.py`
- `cd backend && python -c "from backend.app.routers import signups"` exits 0
</acceptance_criteria>
</task>

<task id="04-03-02" parallel="false">
<action>
Edit `backend/app/routers/admin.py` — add two endpoints:

1. `POST /admin/users/{user_id}/prereq-overrides`
   - Admin auth dependency.
   - Pydantic body `PrereqOverrideCreate(module_slug: str, reason: constr(min_length=10))` — add to `backend/app/schemas.py`.
   - 404 if user missing or `module_slug` not in `module_templates`.
   - Create `PrereqOverride(user_id=user_id, module_slug=..., reason=..., created_by=current_admin.id)`.
   - Write `AuditLog(action="prereq_override_admin_create", user_id=current_admin.id, meta={override_id, user_id, module_slug, reason})`.
   - Return a `PrereqOverrideRead` Pydantic response.

2. `DELETE /admin/prereq-overrides/{override_id}`
   - Admin auth dependency.
   - 404 if not found.
   - 409 if already revoked.
   - Set `revoked_at = datetime.now(timezone.utc)`.
   - Write `AuditLog(action="prereq_override_admin_revoke", user_id=current_admin.id, meta={override_id})`.
   - Return 204 or the updated row.

Add `PrereqOverrideCreate` and `PrereqOverrideRead` schemas to
`backend/app/schemas.py`.
</action>
<read_first>
- backend/app/routers/admin.py
- backend/app/schemas.py
- backend/app/models.py
</read_first>
<acceptance_criteria>
- `grep -q 'prereq-overrides' backend/app/routers/admin.py`
- `grep -q 'PrereqOverrideCreate' backend/app/schemas.py`
- `grep -q 'PrereqOverrideRead' backend/app/schemas.py`
- `grep -q 'prereq_override_admin_create' backend/app/routers/admin.py`
- `grep -q 'prereq_override_admin_revoke' backend/app/routers/admin.py`
- `cd backend && python -c "from backend.app.routers import admin"` exits 0
</acceptance_criteria>
</task>

<task id="04-03-03" parallel="false">
<action>
Create `backend/tests/test_signups_prereq.py` covering:

1. **No module_slug** — event with `module_slug=None` → signup succeeds, no prereq check.
2. **No missing** — event with `module_slug="orientation"` (no prereqs) → signup succeeds.
3. **Missing prereqs returns 422** — event `module_slug="intro-bio"`, user has no attended orientation. Assert `response.status_code == 422` and the response JSON has `code=="PREREQ_MISSING"`, `missing==["orientation"]`, and `next_slot` is either a dict or null.
4. **Acknowledge bypass creates signup + audit log** — same setup but with
   `?acknowledge_prereq_override=true`. Assert 201 (or whatever POST /signups returns
   for success in this codebase), signup row exists, and one
   `AuditLog(action="prereq_override_self")` row exists with matching meta.
5. **Satisfied via attended orientation** — seed an attended orientation signup for
   the user first, then POST /signups for intro-bio → 201 succeeds, no audit log.
6. **Next slot populated** — create a future orientation Slot and assert
   `next_slot.slot_id` matches.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/routers/signups.py (after 04-03-01)
- backend/tests/test_signups*.py (existing fixture patterns)
</read_first>
<acceptance_criteria>
- File exists
- Contains `PREREQ_MISSING`
- Contains `acknowledge_prereq_override`
- Contains `prereq_override_self`
- `cd backend && pytest tests/test_signups_prereq.py -v` exits 0 with >= 6 tests
</acceptance_criteria>
</task>

<task id="04-03-04" parallel="false">
<action>
Create `backend/tests/test_admin_prereq_overrides.py` covering:

1. **Non-admin blocked** — regular user gets 403.
2. **Create happy path** — admin POSTs `{module_slug: "orientation", reason: "student unable to attend"}` → 200/201. Row exists, `created_by` is admin. AuditLog row exists.
3. **Reason too short** — reason of 5 chars → 400 or 422.
4. **Unknown module_slug** — → 404.
5. **Unknown user_id** — → 404.
6. **Revoke happy path** — DELETE → 204/200, row `revoked_at` set, AuditLog row.
7. **Double-revoke** — second DELETE → 409.
8. **Revoke unknown id** → 404.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/routers/admin.py (after 04-03-02)
- backend/tests/test_admin_*.py (existing patterns)
</read_first>
<acceptance_criteria>
- File exists
- Contains `prereq_override_admin_create`
- Contains `prereq_override_admin_revoke`
- `cd backend && pytest tests/test_admin_prereq_overrides.py -v` exits 0 with >= 8 tests
</acceptance_criteria>
</task>

</tasks>

<verification>
- Routers import: `cd backend && python -c "from backend.app.routers import signups, admin"` exits 0
- Signups prereq tests: `cd backend && pytest tests/test_signups_prereq.py -v` exits 0
- Admin override tests: `cd backend && pytest tests/test_admin_prereq_overrides.py -v` exits 0
- Full backend suite green: `cd backend && pytest -q` exits 0
- `/signups` OpenAPI schema updated: `cd backend && python -c "from backend.app.main import app; import json; s=app.openapi(); assert 'acknowledge_prereq_override' in json.dumps(s)"` exits 0
</verification>
