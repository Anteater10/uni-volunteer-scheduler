---
phase: 04
plan: 05
name: Student module timeline on MySignupsPage
wave: 3
depends_on: [04-03]
files_modified:
  - backend/app/routers/users.py
  - frontend/src/pages/MySignupsPage.jsx
  - frontend/src/components/ModuleTimeline.jsx
  - frontend/src/__tests__/ModuleTimeline.test.jsx
  - backend/tests/test_module_timeline.py
autonomous: true
requirements:
  - GET /me/module-timeline endpoint
  - Locked/unlocked/completed status per module
  - Override badge
  - Visual timeline on MySignupsPage
---

# Plan 04-05: Student Module Timeline

<objective>
Add a `GET /me/module-timeline` endpoint returning per-module status
(locked/unlocked/completed) with override visibility, and render it as a visual
timeline on `MySignupsPage`.
</objective>

<must_haves>
- `GET /me/module-timeline` — returns a list of objects:
  ```json
  [
    {
      "slug": "orientation",
      "name": "Orientation",
      "status": "completed",
      "override_active": false,
      "last_activity": "2026-04-01T10:00:00Z"
    }
  ]
  ```
- Status values:
  - `locked` — prereqs not met AND no active override AND user hasn't self-overridden
  - `unlocked` — prereqs met (or active override) but no `attended` signup
  - `completed` — user has at least one `attended` signup on this module
- `override_active: true` when an active `PrereqOverride` exists for that user+module
- `last_activity` — latest `created_at` among the user's signups on events of that module (null if none)
- Only modules the user has ANY signup history with OR that are prereqs for such modules are shown.
- Frontend `<ModuleTimeline>` component renders rows with icon, module name, status badge, last activity date. Locked rows dimmed with link to orientation. Override-active rows show a distinct badge.
- Keyboard-accessible, responsive.
</must_haves>

<tasks>

<task id="04-05-01" parallel="false">
<action>
Add a new endpoint `GET /me/module-timeline` in `backend/app/routers/users.py`:

1. Query all `module_templates` that the current user has interacted with:
   - The user has any Signup on an Event whose `module_slug` matches.
   - OR the module is a prereq of a module the user has interacted with.
2. For each module, compute `status`:
   - If user has a Signup with `status == attended` on an event with that `module_slug` → `completed`.
   - Else if `check_missing_prereqs(db, user.id, module_slug) == []` → `unlocked`.
   - Else → `locked`.
3. Compute `override_active` via `PrereqOverride` table.
4. Compute `last_activity` as `MAX(signup.created_at)` for matching signups.
5. Return sorted by name.

Add `ModuleTimelineItem` Pydantic schema to `backend/app/schemas.py`.
</action>
<read_first>
- backend/app/routers/users.py
- backend/app/schemas.py
- backend/app/services/prereqs.py
- backend/app/models.py
</read_first>
<acceptance_criteria>
- `grep -q 'module-timeline' backend/app/routers/users.py`
- `grep -q 'ModuleTimelineItem' backend/app/schemas.py`
- `cd backend && python -c "from backend.app.routers import users"` exits 0
</acceptance_criteria>
</task>

<task id="04-05-02" parallel="false">
<action>
Create `backend/tests/test_module_timeline.py` with tests:

1. **Empty timeline** — user with no signups → empty list.
2. **Completed module** — user attended orientation → returns `{slug: "orientation", status: "completed"}`.
3. **Locked module** — user signed up for intro-bio but never attended orientation → intro-bio shows `locked`.
4. **Unlocked module** — user attended orientation, signed up for intro-bio but status is `confirmed` → intro-bio shows `unlocked`.
5. **Override active** — admin override on intro-bio for user → `override_active: true` and status is `unlocked`.
6. **last_activity populated** — assert `last_activity` matches expected timestamp.
</action>
<read_first>
- backend/tests/conftest.py
- backend/app/routers/users.py (after 04-05-01)
</read_first>
<acceptance_criteria>
- File exists
- Contains `module-timeline` or `module_timeline`
- Contains `locked`
- Contains `completed`
- Contains `override_active`
- `cd backend && pytest tests/test_module_timeline.py -v` exits 0 with >= 6 tests
</acceptance_criteria>
</task>

<task id="04-05-03" parallel="false">
<action>
Create `frontend/src/components/ModuleTimeline.jsx`:

- Accepts `modules` prop (array from `/me/module-timeline`).
- Renders a list of rows. Each row shows:
  - Status icon (locked = lock icon dimmed, unlocked = unlock icon, completed = checkmark green).
  - Module name.
  - Status badge with text.
  - "Override active" badge when `override_active === true` (distinct styling, e.g. amber).
  - Last activity date (relative or ISO — planner picks relative via a simple "X days ago" or date string).
  - Locked rows: entire row dimmed (opacity), module name links to `/events?module=orientation` (or next_slot deeplink if available).
- Responsive: stacks vertically on mobile.
- Uses existing Tailwind classes consistent with phases 1-3.
</action>
<read_first>
- frontend/src/pages/MySignupsPage.jsx
- frontend/src/components/ (existing component patterns)
</read_first>
<acceptance_criteria>
- File exists
- Contains `locked`
- Contains `completed`
- Contains `unlocked`
- Contains `override`
- Import is valid: no JSX syntax errors
</acceptance_criteria>
</task>

<task id="04-05-04" parallel="false">
<action>
Edit `frontend/src/pages/MySignupsPage.jsx`:

1. Fetch `GET /me/module-timeline` on mount (use existing fetch pattern/hook from
   this codebase — probably `useEffect` + `fetch` or an API wrapper).
2. Render `<ModuleTimeline modules={...} />` in a section titled "Module Progress"
   below the existing signups list.
3. Loading/error states consistent with existing patterns.
</action>
<read_first>
- frontend/src/pages/MySignupsPage.jsx
- frontend/src/api/ (API call patterns)
</read_first>
<acceptance_criteria>
- `grep -q 'ModuleTimeline' frontend/src/pages/MySignupsPage.jsx`
- `grep -q 'module-timeline' frontend/src/pages/MySignupsPage.jsx`
- `cd frontend && npm run build` exits 0
</acceptance_criteria>
</task>

<task id="04-05-05" parallel="false">
<action>
Create `frontend/src/__tests__/ModuleTimeline.test.jsx` with Vitest + RTL:

1. **Renders completed module** — checkmark icon visible, name displayed.
2. **Renders locked module dimmed** — locked row has reduced opacity class.
3. **Override badge shown** — `override_active: true` → badge text visible.
4. **Empty state** — no modules → renders nothing (or "No modules yet").
</action>
<read_first>
- frontend/src/components/ModuleTimeline.jsx (after 04-05-03)
- frontend/vitest.config.*
</read_first>
<acceptance_criteria>
- File exists
- Contains `ModuleTimeline`
- `cd frontend && npx vitest run src/__tests__/ModuleTimeline.test.jsx` exits 0
</acceptance_criteria>
</task>

</tasks>

<verification>
- Backend tests: `cd backend && pytest tests/test_module_timeline.py -v` exits 0
- Frontend build: `cd frontend && npm run build` exits 0
- Frontend tests: `cd frontend && npx vitest run` exits 0
- Full backend suite: `cd backend && pytest -q` exits 0
</verification>
