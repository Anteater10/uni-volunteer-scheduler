---
phase: 07-admin-dashboard-polish
plan: 03
type: execute
wave: 1
depends_on: ["07-01"]
files_modified:
  - backend/app/routers/admin.py
  - backend/app/schemas.py
  - frontend/src/pages/admin/ExportsSection.jsx
  - frontend/src/lib/api.js
  - frontend/src/App.jsx
autonomous: true
requirements:
  - ANALYTICS-HOURS
  - ANALYTICS-ATTENDANCE
  - ANALYTICS-NOSHOW
  - CSV-EXPORT
must_haves:
  truths:
    - "GET /admin/analytics/volunteer-hours returns [{user_id, name, hours, events}] for a date range"
    - "GET /admin/analytics/attendance-rates returns [{event_id, name, confirmed, attended, no_show, rate}] for a date range"
    - "GET /admin/analytics/no-show-rates returns [{user_id, name, rate, count}] for a date range"
    - "GET /admin/events/{id}/attendance.csv returns attendance CSV"
    - "GET /admin/analytics/volunteer-hours.csv returns volunteer hours as CSV"
    - "Frontend Exports section renders each analytics view as a sortable table with Export CSV button"
    - "Volunteer hours = sum of slot_duration_minutes across status='attended' signups"
  artifacts:
    - path: "backend/app/routers/admin.py"
      provides: "Three analytics endpoints + two CSV export endpoints"
    - path: "frontend/src/pages/admin/ExportsSection.jsx"
      provides: "Sortable analytics tables with CSV download buttons"
  key_links:
    - from: "frontend/src/pages/admin/ExportsSection.jsx"
      to: "backend/app/routers/admin.py::volunteer_hours"
      via: "GET /admin/analytics/volunteer-hours"
      pattern: "/admin/analytics/"
---

<objective>
Build three analytics endpoints (volunteer hours, attendance rates, no-show rates) with matching CSV exports, plus an event-level attendance CSV. The frontend Exports section renders each as a sortable table with date range filters and Export CSV buttons.

Purpose: Success criterion #5 requires CSV export of volunteer hours and attendance rates for grant reporting.
Output: Three analytics JSON endpoints, corresponding CSV endpoints, event attendance CSV, and a frontend Exports section with sortable tables.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07-admin-dashboard-polish/07-CONTEXT.md
@.planning/codebase/CONVENTIONS.md
@backend/app/routers/admin.py
@backend/app/models.py
@backend/app/schemas.py
@frontend/src/lib/api.js

<interfaces>
SignupStatus enum: confirmed, waitlisted, cancelled. Phase 3 adds checked_in, attended, no_show.
Volunteer hours calculation: sum of (slot.end_time - slot.start_time) in minutes for signups with status='attended', grouped by user.
Attendance rate: attended / (confirmed + attended + no_show) per event.
The existing admin router already has event analytics and CSV export — the new analytics endpoints are aggregate cross-event views.
Context decision: query on each request (no pre-aggregation), add index hints if slow.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add analytics endpoints to backend</name>
  <files>backend/app/routers/admin.py, backend/app/schemas.py</files>
  <read_first>
    - backend/app/routers/admin.py (full file — existing analytics section)
    - backend/app/models.py (Signup, Slot, Event, User, SignupStatus)
    - backend/app/schemas.py (existing schemas)
  </read_first>
  <action>
    1. In `backend/app/schemas.py`, add analytics response schemas:
       ```python
       class VolunteerHoursRow(BaseModel):
           user_id: str
           name: str
           hours: float
           events: int

       class AttendanceRateRow(BaseModel):
           event_id: str
           name: str
           confirmed: int
           attended: int
           no_show: int
           rate: float

       class NoShowRateRow(BaseModel):
           user_id: str
           name: str
           rate: float
           count: int
       ```

    2. In `backend/app/routers/admin.py`, add three analytics endpoints:

       `GET /analytics/volunteer-hours`:
       - Accept `from_date` and `to_date` query params (optional, datetime).
       - Query: join Signup → Slot → Event, filter status='attended' (or fallback to 'confirmed' if attended not yet in enum), optionally filter by slot start_time within date range.
       - Group by user_id. Sum slot duration as `(slot.end_time - slot.start_time)` in hours. Count distinct events.
       - Return `List[VolunteerHoursRow]`.
       - NOTE: If SignupStatus.attended does not exist yet (phase 3 adds it), use a graceful fallback — check if the enum value exists, otherwise use confirmed as proxy. Document this in a comment.

       `GET /analytics/attendance-rates`:
       - Accept `from_date` and `to_date` query params.
       - Query: for each event (optionally filtered by date range on event start), count signups by status (confirmed, attended, no_show).
       - Rate = attended / (confirmed + attended + no_show) if denominator > 0, else 0.
       - Return `List[AttendanceRateRow]`.

       `GET /analytics/no-show-rates`:
       - Accept `from_date` and `to_date` query params.
       - Query: for each user, count no_show signups and total terminal-status signups (attended + no_show).
       - Rate = no_show / total if total > 0, else 0.
       - Return `List[NoShowRateRow]`.

       All three endpoints require admin role and log the action.

    3. Add CSV export endpoints:

       `GET /events/{event_id}/attendance.csv`:
       - Columns: user_name, email, status, checked_in_at, attended_at.
       - Query all signups for the event's slots, join user.
       - Require admin or organizer role + event ownership check.

       `GET /analytics/volunteer-hours.csv`:
       - Same data as JSON endpoint, CSV format.
       - Require admin role.
  </action>
  <verify>
    <automated>grep -q "volunteer-hours" backend/app/routers/admin.py && grep -q "attendance-rates" backend/app/routers/admin.py && grep -q "no-show-rates" backend/app/routers/admin.py && grep -q "VolunteerHoursRow" backend/app/schemas.py</automated>
  </verify>
  <acceptance_criteria>
    - Three analytics JSON endpoints exist under `/analytics/`
    - Two CSV export endpoints exist (event attendance, volunteer hours)
    - All endpoints require admin role
    - All endpoints accept from_date/to_date filters
    - Volunteer hours calculated as sum of slot duration for attended signups
  </acceptance_criteria>
  <done>Five analytics/export backend endpoints added.</done>
</task>

<task type="auto">
  <name>Task 2: Create frontend Exports section with sortable tables</name>
  <files>frontend/src/pages/admin/ExportsSection.jsx, frontend/src/lib/api.js, frontend/src/App.jsx</files>
  <read_first>
    - frontend/src/lib/api.js (existing admin namespace, downloadBlob)
    - frontend/src/pages/admin/AdminLayout.jsx (nav structure)
    - frontend/src/App.jsx (placeholder route for exports)
    - frontend/src/components/ui/index.js (available primitives)
  </read_first>
  <action>
    1. In `frontend/src/lib/api.js`, add analytics functions to the `api.admin` namespace:
       - `analytics: { volunteerHours(params), attendanceRates(params), noShowRates(params) }`
       - `exports: { volunteerHoursCsv(params), attendanceRatesCsv(params) }`
       Use `request()` for JSON, `downloadBlob()` for CSV.

    2. Create `frontend/src/pages/admin/ExportsSection.jsx`:
       - Tabbed or accordion layout with three sections: Volunteer Hours, Attendance Rates, No-Show Rates.
       - Each section has:
         - Date range filter (from/to date inputs).
         - "Load" button to fetch data.
         - Sortable table (click column header to sort asc/desc — implement simple client-side sort state).
         - "Export CSV" button.
       - Volunteer Hours table columns: Name, Hours, Events.
       - Attendance Rates table columns: Event, Confirmed, Attended, No-Show, Rate (%).
       - No-Show Rates table columns: Name, Rate (%), Count.
       - Use Card, Button, Input, Label, Skeleton, EmptyState primitives.
       - Handle loading/error/empty states.

    3. In `frontend/src/App.jsx`, replace the exports placeholder route with `<ExportsSection />`.
  </action>
  <verify>
    <automated>test -f frontend/src/pages/admin/ExportsSection.jsx && grep -q "volunteerHours\|volunteer-hours" frontend/src/lib/api.js && grep -q "ExportsSection" frontend/src/App.jsx</automated>
  </verify>
  <acceptance_criteria>
    - ExportsSection renders three analytics tables
    - Each table is sortable by clicking column headers
    - Date range filter present for each section
    - CSV export button triggers download for each section
    - Responsive rendering
  </acceptance_criteria>
  <done>Frontend Exports section with sortable analytics tables and CSV downloads created.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → analytics endpoints | Admin-only; compute-heavy queries |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-04 | Denial of Service | Analytics queries on large datasets | mitigate | Queries run on request (no pre-aggregation per context decision); if slow, add index on (signup.status, slot.start_time). CSV exports capped at reasonable row counts. |
| T-07-05 | Information Disclosure | Volunteer hours expose user activity | accept | Admin-only access; data needed for grant reporting per success criteria |
</threat_model>

<verification>
- `grep -q "volunteer-hours" backend/app/routers/admin.py`
- `grep -q "attendance-rates" backend/app/routers/admin.py`
- `grep -q "VolunteerHoursRow" backend/app/schemas.py`
- `test -f frontend/src/pages/admin/ExportsSection.jsx`
- `grep -q "ExportsSection" frontend/src/App.jsx`
</verification>

<success_criteria>
Plan complete when three analytics endpoints return correct aggregated data, CSV exports work for volunteer hours and event attendance, and the frontend Exports section renders sortable tables with download buttons.
</success_criteria>

<output>
After completion, create `.planning/phases/07-admin-dashboard-polish/07-03-SUMMARY.md`
</output>
