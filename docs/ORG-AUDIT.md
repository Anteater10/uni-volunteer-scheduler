# Organizer role audit (Phase 19)

**Date started:** 2026-04-16
**Owner:** Andy
**Branch:** `v1.2-final`

This is the paper trail for Phase 19. It records what was broken on the organizer
surface before the audit, what changed, and which items are still open.

---

## Scope

Phase 19 covers every flow an organizer touches: login, dashboard landing,
event detail, roster / check-in on a phone, end-of-event cleanup.

Phase 19 does NOT cover:
- Admin-only surfaces (Phase 16/17/18 shipped those).
- Participant surfaces (Phase 15).
- Cross-role integration tests (Phase 20).

## Starting state (pre-19)

Inherited from v1.0 + today's RBAC work (commits `e07542a`, `61825a4`):

- `/organize/events/:id/roster` — legacy typo route from Phase 3; the real
  intent was `/organizer/...` (matches the role name). Both paths were live.
- No `/organizer` dashboard — logging in as an organizer landed on
  `/admin` and was redirected to `/admin/events` by `AdminIndexRoute`.
- Organizer reuses the admin shell (`AdminLayout`) with RBAC hiding
  `users`, `audit-logs`, `exports`. That covers the shared surface but leaves
  the organizer without a purpose-built phone-first dashboard.
- `OrganizerRosterPage` from Phase 3 exists but has not been polished for
  venue use: small tap targets, no visible polling indicator, no
  `attended` / `no_show` actions from the roster UI, no conflict handling
  between organizer check-in and self check-in.
- No end-of-event prompt for unmarked attendees.
- No dedicated organizer WCAG AA / 375px audit pass.

## Plans

| Plan | Scope | Status |
|---|---|---|
| 19-01 | Route normalize (`/organize` → `/organizer` redirect) + this audit doc | **Done** 2026-04-16 |
| 19-02 | Organizer dashboard (`/organizer` — phone-first, Today/Upcoming/Past tabs, lists all events) | **Done** 2026-04-16 |
| 19-03 | Roster polish — tap targets, 5s poll indicator, optimistic UI, `attended`/`no_show`, first-write-wins | **Deferred to v1.3** |
| 19-04 | End-of-event "N unmarked" prompt; confirm event create/edit stays admin-only | **Deferred to v1.3** |
| 19-05 | WCAG AA + 375px audit + one ORG-14 audit-surfaced feature | **Deferred to v1.3** |

## Phase 19 close-out (2026-04-16)

Rescoped. The organiser is a scoped admin role: same shell, hidden nav items
(Users / Audit Logs / Exports), plus a phone-first `/organizer` landing that
lists every event and links into the existing roster page. There is no
per-event organiser ownership, and admins don't do hands-on check-in — so
the nice-to-haves for the roster page (tap targets, poll indicator,
`attended`/`no_show`, end-of-event prompt, WCAG AA audit, ORG-14 feature)
don't block the v1.2-prod milestone. They move to v1.3 alongside the latent
downgrade-enum Alembic bug and the other deferrals.

Phase 20 (cross-role integration) can start.

## 19-01 changes

- `frontend/src/App.jsx`: legacy `organize/events/:eventId/roster` route now
  renders `<RedirectOrganizeRoster />`, which 301-equivalents to
  `/organizer/events/:eventId/roster` (preserves `eventId`, uses
  `<Navigate replace>` so back-button doesn't loop).
- `frontend/tests/OrganizerRosterPage.test.jsx`: test now mounts the page
  at the canonical `/organizer/events/:eventId/roster` path.
- `e2e/organizer-check-in.spec.js`: Playwright scenario navigates to the
  canonical path; a comment records the redirect for posterity.

No backend changes — the roster path is a pure frontend concern.

## 19-02 changes

**Product decision:** organisers see *all* events, not a filtered "assigned-to-me"
list. There is no per-event organiser ownership in the data model and no plans
to add one.

- New page `frontend/src/pages/organizer/OrganizerDashboard.jsx`: phone-first
  layout with three scope tabs (`Today` / `Upcoming` / `Past`, default `Today`).
  Each event renders as a card with a large "Open roster" primary button
  (min-height 44px for touch), plus a secondary "View details" link to the
  admin detail page. Uses `api.events.list()` which the backend already
  authorises for both admin and organiser.
- `App.jsx`: `/organizer` now renders `<OrganizerDashboard />` instead of
  redirecting to `/admin/events`.
- `App.jsx` — `AdminIndexRoute`: an organiser hitting the `/admin` index now
  redirects to `/organizer` (their home) instead of `/admin/events`.
- `OrganizerDashboard.test.jsx`: 3 tests covering today-scope default, tab
  switching to Upcoming, and the empty state.

## Out-of-scope follow-ups

- Historical planning docs (`.planning/phases/03-.../03-04-...PLAN.md`,
  `.planning/phases/13-.../13-01-PLAN.md`) still reference `/organize/`.
  These are frozen phase artefacts and are not updated; future readers
  should treat them as of-the-time-of-writing.
- `.planning/REQUIREMENTS-v1.2-prod.md` line 120 still lists the legacy
  path in ORG-01's in-scope routes. Left intact because the requirements
  doc is the input contract, not a live artefact.
