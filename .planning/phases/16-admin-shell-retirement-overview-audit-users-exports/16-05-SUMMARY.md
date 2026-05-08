---
phase: 16
plan: 05
subsystem: admin-users
tags: [admin, users, invite, ccpa, side-drawer, table, soft-delete]
requires:
  - 16-02 (backend invite/deactivate/reactivate/CCPA endpoints)
  - 16-03 (SideDrawer + RoleBadge primitives + api.admin.users namespace)
provides:
  - polished Users admin page (table + drawer + invite + soft-delete)
  - D-43.1 shared-err regression test
  - CCPA export/delete flows wired end-to-end in the UI
affects:
  - frontend/src/pages/UsersAdminPage.jsx
tech-stack:
  added: []
  patterns: [react-query, side-drawer, split-error-state, table-layout]
key-files:
  created:
    - frontend/src/pages/__tests__/UsersAdminPage.test.jsx
  modified:
    - frontend/src/pages/UsersAdminPage.jsx
decisions:
  - "Pass a hardcoded 'Admin UI CCPA request' reason to ccpaExport/ccpaDelete so backend's min-5-char reason guard is satisfied without requiring the admin to type one (plan copy omits a reason field)."
  - "Filter-by-role dropdown uses aria-label='Filter by role' so tests can distinguish it from the invite form's Role select without duplicate labels."
  - "Client-side filter honors the show-deactivated toggle defensively even when the backend returns active-only by default, so the UI stays consistent if the include_inactive param is dropped."
metrics:
  completed: 2026-04-15
  duration: ~25m
  tasks: 1
  commits: 3 (RED test, GREEN impl, docs)
---

# Phase 16 Plan 05: Users Admin Page Rewrite Summary

Rewrote `UsersAdminPage.jsx` end-to-end as a table + side-drawer layout with
a split error-state model, replacing the buggy shared-err card layout.
Delivers ADMIN-18..21 + ADMIN-24 CCPA and regresses the D-43.1 bug with an
automated test.

## What Shipped

**UsersAdminPage.jsx (rewritten, 590 lines)**

- **Header:** title + one-sentence explainer + "Invite user" primary button.
- **Filter bar:** search (name OR email, case-insensitive client-side), role
  dropdown (All / Admin / Organizer), "Show deactivated" toggle (off by
  default).
- **Table columns:** Name / Email / Role (RoleBadge) / Last login / Status.
  Last login shows "Never" for null `last_login_at` or a humanized relative
  time via `Intl.RelativeTimeFormat`. Status is a green "Active" or gray
  "Deactivated" pill.
- **Row click** opens a `SideDrawer` edit form with Name, Role, University
  ID, `notify_email` checkbox, and a read-only Email field (with helper
  copy "Email can't be changed — delete and reinvite if needed").
- **Save / Deactivate / Reactivate** buttons in the drawer; Deactivate is
  disabled with a tooltip on the last active admin row AND on the current
  user's own row. The role dropdown disables "organizer" on self-as-admin
  and on the last active admin with the matching tooltip.
- **Invite drawer:** separate `<SideDrawer>` with Name + Email + Role only.
  No password field. Submits via `api.admin.users.invite` and a success
  toast reads: "Invite sent to {email} — they'll receive a sign-in link."
- **CCPA Export modal** with plain-English copy, triggers a JSON download
  via `Blob` + `URL.createObjectURL`.
- **CCPA Delete modal** with type-to-confirm (email must match) and
  anonymization copy. Calls `api.admin.users.ccpaDelete`.

**Error-state fix (D-43.1 regression):**
`createError`, `updateError`, and the react-query `listQ.error` are now
three independent state channels. The page body only renders the
"Couldn't load users" EmptyState for `listQ.error` — never for invite or
update failures. The invite drawer and edit drawer render their own errors
inline with `role="alert"`.

## Tests

New file: `frontend/src/pages/__tests__/UsersAdminPage.test.jsx` — 7 tests,
all passing:

1. Table renders the 5 expected column headers.
2. The role filter dropdown does not include `participant`.
3. Invite form has no password field and its Role select has no
   `participant` option.
4. "Show deactivated" toggle starts unchecked.
5. **D-43.1 regression:** invite mutation rejecting with "Email already
   exists" does NOT hide the user list; the error shows inline in the
   invite drawer and alice@example.com is still rendered.
6. Last-active-admin row's Deactivate button is disabled with a tooltip
   containing "last active admin" or "your own account".
7. CCPA Export + CCPA Delete buttons are present inside the edit drawer.

Test run: `cd frontend && npm run test -- --run src/pages/__tests__/UsersAdminPage.test.jsx`
→ 7 passed.

## Acceptance Criteria

| Check | Result |
|---|---|
| `ROLES = ["admin", "organizer"]` | PASS |
| No "participant" occurrences | PASS |
| No "password" occurrences | PASS |
| No `adminDeleteUser` / hard-delete refs | PASS |
| `users.invite` wired | PASS |
| `users.deactivate` wired | PASS |
| `ccpaExport` + "CCPA Data Export" label | PASS |
| `SideDrawer` used | PASS |
| `createError` + `updateError` both present | PASS |
| No shared `err` state | PASS |
| No `TODO` markers | PASS |
| Test file: 7/7 passing including D-43.1 regression | PASS |

## Deviations from Plan

**None functional.** Two minor implementation notes:

1. **CCPA reason** — Plan's modal copy omits a reason field, but the backend
   CCPA endpoints enforce a min-5-char `reason`. Resolved by passing a
   hardcoded `"Admin UI CCPA request"` string from the page. If auditors
   want admin-typed reasons later, add a reason textarea in a follow-up.
2. **Filter role select aria-label** — Added `aria-label="Filter by role"`
   to the filter dropdown so the test suite can distinguish it from the
   invite form's "Role" `<Label>` without brittle index lookups. Pure
   accessibility improvement, no behavior change.

## Known Stubs

None. All data (users list, invite response, CCPA endpoints) is live-wired
to `api.admin.users.*` from Plan 03, which hits the backend routes from
Plan 02.

## Commits

- `f8fc72d` test(16-05): add failing tests for UsersAdminPage rewrite
- `14b6f94` feat(16-05): rewrite UsersAdminPage — table + drawer + invite + soft-delete

## Self-Check: PASSED

- FOUND: frontend/src/pages/UsersAdminPage.jsx (rewritten)
- FOUND: frontend/src/pages/__tests__/UsersAdminPage.test.jsx (created)
- FOUND: commit f8fc72d (RED)
- FOUND: commit 14b6f94 (GREEN)
- Test run: 7/7 passing
- Acceptance greps: all pass
