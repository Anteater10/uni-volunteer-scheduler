---
phase: 21-orientation-credit-engine
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/alembic/versions/0014_orientation_credit.py
  - backend/app/models.py
  - backend/app/schemas.py
  - backend/app/services/orientation_service.py
  - backend/app/services/audit_log_humanize.py
  - backend/app/routers/admin.py
  - backend/app/routers/organizer.py
  - backend/app/routers/public/orientation.py
  - backend/app/main.py
  - backend/tests/test_orientation_credit_service.py
  - frontend/src/lib/api.js
  - frontend/src/components/OrientationWarningModal.jsx
  - frontend/src/pages/public/EventDetailPage.jsx
  - frontend/src/pages/AdminEventPage.jsx
  - frontend/src/pages/admin/OrientationCreditsSection.jsx
  - frontend/src/pages/admin/AdminLayout.jsx
  - frontend/src/App.jsx
autonomous: true
requirements_addressed:
  - ORIENT-01
  - ORIENT-02
  - ORIENT-03
  - ORIENT-04
  - ORIENT-05
  - ORIENT-06
  - ORIENT-07
  - ORIENT-08
must_haves:
  truths:
    - "Volunteer who attended any prior orientation for a module family does not see the warning modal"
    - "Volunteer with no prior attendance for the family still sees warning (unchanged for newbies)"
    - "Organizer can grant orientation credit from roster; audit row written"
    - "Admin can list, grant, revoke orientation credits; audit rows written"
    - "Revoked credits do not suppress the warning modal"
    - "ORIENTATION_CREDIT_EXPIRY_DAYS env var trims eligibility when set"
  artifacts:
    - path: "backend/alembic/versions/0014_orientation_credit.py"
      provides: "family_key column on module_templates + orientation_credits table with indexes"
    - path: "backend/app/services/orientation_service.py"
      provides: "has_orientation_credit + grant_orientation_credit + revoke_orientation_credit + family_for_event"
    - path: "backend/app/routers/organizer.py"
      provides: "POST /organizer/events/{event_id}/signups/{signup_id}/grant-orientation"
    - path: "backend/app/routers/admin.py"
      provides: "GET/POST/DELETE /admin/orientation-credits endpoints"
    - path: "frontend/src/pages/admin/OrientationCreditsSection.jsx"
      provides: "Admin table + grant form + per-row revoke"
---

<objective>
Ship cross-week/cross-module orientation credit: domain model, service, backend endpoints, participant modal rewire, organizer one-tap grant, admin CRUD section. Every grant/revoke writes audit. Back-compat: legacy `has_attended_orientation` helper keeps its signature so callers who do not care about family continue to work.
</objective>

<tasks>

<task id="1" name="alembic-migration">
<read_first>
- backend/alembic/versions/0013_add_type_session_count_fix_orientation_duration.py — slug revision pattern + enum leak discipline
- backend/app/models.py lines 494-513 — ModuleTemplate shape
</read_first>
<action>
Create backend/alembic/versions/0014_orientation_credit.py:
- revision = "0014_orientation_credit", down_revision = "0013_add_type_session_count_fix_orientation_duration"
- upgrade():
  1. Create `orientationcreditsource` enum with values `attendance`, `grant`.
  2. Add nullable `family_key` column (String) to `module_templates`.
  3. Backfill `family_key = slug` for existing rows.
  4. Create `orientation_credits` table:
     - id UUID PK default gen_random_uuid()
     - volunteer_email String(255) NOT NULL
     - family_key String NOT NULL
     - source orientationcreditsource NOT NULL
     - granted_by_user_id UUID FK users(id) ON DELETE SET NULL, nullable
     - granted_at timestamptz NOT NULL server_default now()
     - revoked_at timestamptz nullable
     - notes Text nullable
     - created_at / updated_at timestamptz NOT NULL server_default now()
  5. Index `ix_orientation_credits_email_family` on (volunteer_email, family_key).
  6. Index `ix_orientation_credits_email` on (volunteer_email).
- downgrade():
  1. Drop indexes.
  2. Drop table orientation_credits.
  3. Drop family_key column.
  4. Drop enum `orientationcreditsource` (no leak — CLAUDE.md rule).
</action>
<acceptance_criteria>
- `alembic upgrade head` succeeds against the dev DB.
- Existing ModuleTemplate rows have `family_key = slug` after upgrade.
- `orientation_credits` table exists with indexes.
</acceptance_criteria>
</task>

<task id="2" name="models">
<read_first>
- backend/app/models.py (existing enum + model patterns)
</read_first>
<action>
In backend/app/models.py:
- Add enum `OrientationCreditSource` (str, enum.Enum) with values `attendance`, `grant`.
- Add column `family_key = Column(String, nullable=True)` on `ModuleTemplate`.
- Add model `OrientationCredit` with columns matching the migration + relationship to User (granter).
</action>
<acceptance_criteria>
- `from app.models import OrientationCredit, OrientationCreditSource` works.
- `ModuleTemplate.family_key` attribute accessible.
</acceptance_criteria>
</task>

<task id="3" name="schemas">
<read_first>
- backend/app/schemas.py OrientationStatusRead (line 579)
</read_first>
<action>
In backend/app/schemas.py:
- Extend `OrientationStatusRead` with `source: Optional[Literal["attendance", "grant"]] = None`.
- Add `OrientationCreditRead(ORMBase)`: id, volunteer_email, family_key, source, granted_by_user_id, granted_by_label (computed server-side), granted_at, revoked_at, notes.
- Add `OrientationCreditCreate(BaseModel)`: volunteer_email (EmailStr), family_key (str), notes (Optional[str]).
</action>
<acceptance_criteria>
- Schemas import cleanly.
</acceptance_criteria>
</task>

<task id="4" name="service">
<read_first>
- backend/app/services/orientation_service.py
</read_first>
<action>
Extend services/orientation_service.py:
- Keep old `has_attended_orientation(db, email)` — delegates to `has_orientation_credit(db, email, family_key=None)`.
- Add `has_orientation_credit(db, email, family_key=None) -> OrientationStatusRead`:
  - Look up signup-based attendance filtered by family_key (join Slot.event → ModuleTemplate.slug → family_key or slug).
  - Look up explicit `orientation_credits` rows matching email (+ family_key) where `revoked_at IS NULL`.
  - Respect `ORIENTATION_CREDIT_EXPIRY_DAYS` env var: if set, drop rows older than N days.
  - Source priority: "attendance" > "grant" (attendance wins when both present; return most-recent timestamp).
- Add `grant_orientation_credit(db, email, family_key, granted_by_user_id, notes=None) -> OrientationCredit`.
- Add `revoke_orientation_credit(db, credit_id) -> OrientationCredit` (sets revoked_at).
- Add `family_for_event(db, event_id) -> str | None`.
</action>
<acceptance_criteria>
- Old callers compile unchanged.
- Tests in Task 10 pass.
</acceptance_criteria>
</task>

<task id="5" name="public-orientation-endpoint">
<read_first>
- backend/app/routers/public/orientation.py
</read_first>
<action>
In backend/app/routers/public/orientation.py:
- Add new `GET /public/orientation-check?email=...&event_id=...` returning `OrientationStatusRead` including `source`. Computes family from event, falls back to "any family" (legacy behavior) when event_id omitted.
- Keep legacy `GET /public/orientation-status?email=...` unchanged.
- Both rate-limited at 5/min/IP.
</action>
<acceptance_criteria>
- Both endpoints respond.
</acceptance_criteria>
</task>

<task id="6" name="organizer-router">
<read_first>
- backend/app/main.py — router include pattern
- backend/app/deps.py — require_role
</read_first>
<action>
Create backend/app/routers/organizer.py:
- POST `/organizer/events/{event_id}/signups/{signup_id}/grant-orientation`
  - require_role(organizer, admin) + ensure_event_owner_or_admin
  - Resolves family_key from event_id
  - Fetches signup → volunteer → email
  - Calls `grant_orientation_credit`
  - Writes audit `orientation_credit_grant`
- Include router in `backend/app/main.py` under `/api/v1`.
</action>
<acceptance_criteria>
- Endpoint reachable.
- Audit row appears.
</acceptance_criteria>
</task>

<task id="7" name="admin-endpoints">
<read_first>
- backend/app/routers/admin.py (pattern for admin-only endpoints)
- backend/app/services/audit_log_humanize.py
</read_first>
<action>
In backend/app/routers/admin.py, add:
- GET `/admin/orientation-credits` — list with optional filters (email, family_key, active_only).
- POST `/admin/orientation-credits` body: `OrientationCreditCreate` → grant_orientation_credit (source=grant). Audit `orientation_credit_grant`.
- DELETE `/admin/orientation-credits/{credit_id}` → revoke_orientation_credit. Audit `orientation_credit_revoke`.
In backend/app/services/audit_log_humanize.py, add labels for `orientation_credit_grant` ("Granted orientation credit") and `orientation_credit_revoke` ("Revoked orientation credit"), and resolve entity_type=`OrientationCredit` to a label like `email (family)`.
</action>
<acceptance_criteria>
- Three endpoints work end-to-end; audit rows include meaningful labels.
</acceptance_criteria>
</task>

<task id="8" name="frontend-api-and-modal">
<read_first>
- frontend/src/lib/api.js
- frontend/src/components/OrientationWarningModal.jsx
- frontend/src/pages/public/EventDetailPage.jsx line ~583
</read_first>
<action>
- Add to `api.js`: `orientationCheck(email, eventId)`, `admin.orientationCredits.{list, create, revoke}`, `organizer.grantOrientation(eventId, signupId)`.
- Rewire EventDetailPage to call `api.public.orientationCheck(email, eventId)` instead of `orientationStatus`. Suppress modal when `has_credit: true`.
- Update OrientationWarningModal — allow it to optionally accept `source` to tailor copy (no behavioral change; still a soft warning).
</action>
<acceptance_criteria>
- Participant signup flow suppresses modal for volunteers with credit.
- Frontend unit tests still pass.
</acceptance_criteria>
</task>

<task id="9" name="admin-section-page">
<read_first>
- frontend/src/pages/admin/TemplatesSection.jsx — side-drawer CRUD pattern
- frontend/src/pages/admin/AdminLayout.jsx nav list
- frontend/src/App.jsx route table
</read_first>
<action>
- Create `frontend/src/pages/admin/OrientationCreditsSection.jsx` with: table, grant form, per-row "Revoke" confirm dialog. Uses api.admin.orientationCredits.
- Register route `/admin/orientation-credits` in `App.jsx` (admin-only).
- Add nav item to `AdminLayout.jsx` (admin-only).
- Add "Grant orientation credit" button on the `AdminEventPage.jsx` roster rows (admin-accessible proxy for organizer action — the domain model allows admins to grant directly).
</action>
<acceptance_criteria>
- Page renders list + grant + revoke.
- Route navigable from sidebar.
</acceptance_criteria>
</task>

<task id="10" name="tests">
<read_first>
- backend/tests/test_public_orientation.py patterns
- backend/tests/fixtures/{factories,helpers}.py
</read_first>
<action>
Create backend/tests/test_orientation_credit_service.py covering:
(a) same-week same-module attended → credit present, source=attendance.
(b) cross-week same-module → credit present.
(c) cross-module (different family) → no credit.
(d) grant_orientation_credit → credit present, source=grant.
(e) revoke → credit absent.
(f) expiry env var (monkeypatch env; check a credit older than N days is ignored).
</action>
<acceptance_criteria>
- All 6 tests pass.
</acceptance_criteria>
</task>

<task id="11" name="run-and-commit">
<action>
- Run alembic upgrade head inside docker stack.
- Run pytest for backend.
- Run frontend vitest.
- Commit atomically by logical unit (migration, models/schemas, service, routers, frontend, tests, section page).
</action>
<acceptance_criteria>
- Tests pass or clearly-documented failures in 21-SUMMARY.md.
- Commits land on branch v1.3 with `(21)` scope tags.
</acceptance_criteria>
</task>

</tasks>
