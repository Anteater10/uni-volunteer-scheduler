# v1.2-prod Manual Smoke Checklist

> This is a manual smoke pass. The automated equivalent lives in
> `e2e/cross-role.spec.js`; run that first, then do this pass to catch UX /
> visual / copy regressions the headless runner does not flag.

Runs against the local docker stack end-to-end: admin (desktop), organizer
(phone), participant (phone incognito). Drive all three roles in one sitting.
Target duration: ~30 minutes. Use this before a milestone sign-off and on any
PR that changes a user-facing surface (routes, copy, forms, emails).

**Exit criteria (must all hold):**
- Every checkbox below ticked in one sitting.
- Zero manual DB nudges required.
- Zero failed network requests in any DevTools Network tab during the sweep.
- Zero console errors / warnings in any of the three browsers.

---

## Preconditions

Run these commands in order from the repo root. Each is copy-pasteable.

1. Fresh docker stack (wipes volumes):

   ```bash
   docker compose down -v
   docker compose build backend migrate
   docker compose up -d db redis
   docker compose run --rm migrate
   docker compose up -d backend celery_worker celery_beat mailpit
   ```

   Build **both** images. `backend` and `migrate` are separate services built
   from the same Dockerfile, so rebuilding only `backend` leaves `migrate`
   running yesterday's code — it then reports "will assume transactional DDL"
   and applies nothing, and the stack comes up against an un-migrated
   database with no error anywhere.

2. Seed the E2E data (creates the seed event, admin, organizer, attended
   volunteer):

   ```bash
   EXPOSE_TOKENS_FOR_TESTING=1 python3 backend/tests/fixtures/seed_e2e.py
   ```

3. Start the frontend dev server:

   ```bash
   cd frontend && npm run dev
   ```

   Entry: http://localhost:5173

4. Confirm Mailpit is reachable at http://localhost:8025 (inbox should be
   empty or near-empty).

5. Confirm backend health at http://localhost:8000/api/v1/health (or
   http://localhost:8000/docs).

6. Open three browser windows / tabs:

   - **Admin** — desktop viewport (1280×800). Log in at
     http://localhost:5173/login as `admin@e2e.example.com` / `Admin!2345`.
   - **Organizer** — phone viewport (375×812 via DevTools device mode, or a
     real phone on the same LAN). Log in as `organizer@e2e.example.com` /
     `Organizer!2345`.
   - **Participant** — incognito / private window at 375×812. No cookies, no
     login.

---

## Section 1 — Participant flow (phone, 375px)

Drive from the Participant incognito window.

- [ ] `/events` loads; week navigation visible; seeded event appears in the
      list; no console errors.
- [ ] Open event detail — orientation slots in their own section, then the
      shifts, each shift card listing its sessions with capacity and filled
      counts. There is no "Period N" row to pick on its own: a period is a
      session inside a shift now, and the shift is what you book.
- [ ] A shift card says how many sessions it commits you to ("2 sessions —
      signing up commits you to all of them"), and the summary that follows
      lists one line per shift, not one per session.
- [ ] Start signup for a shift with a **fresh** email (no prior attendance) —
      orientation warning modal fires.
- [ ] Repeat with the seeded `attended_volunteer_email` — orientation modal
      is suppressed (DB confirms prior attendance).
- [ ] Form validation — invalid email and invalid phone are both rejected
      with clear inline messages.
- [ ] Submit signup → success card renders; confirmation email arrives in
      Mailpit (http://localhost:8025) within 15s.
- [ ] Click the magic link in the Mailpit email → lands on `/signup/confirm`
      → "your signup is confirmed" banner shows.
- [ ] `/signup/manage?token=...` shows the signup read-only — no Cancel or
      swap controls — plus a notice to contact the SciTrek organizers by
      email for any change.
- [ ] Self check-in via `/check-in/:signupId` works inside the time window
      (flips status to checked in).
- [ ] No horizontal scroll on any page at 375px; all tap targets ≥44px; no
      stuck spinners; loading / empty / error states render correctly.

---

## Section 2 — Admin flow (desktop, 1280px)

Drive from the Admin desktop window.

- [ ] Login → `/admin` Overview shows live stats (Users, Events, Slots,
      Signups, Confirmed signups) and the Recent Activity feed renders.
- [ ] `/admin/audit-logs` — pagination works; kind filter, actor filter,
      date range, and keyword search all apply and combine.
- [ ] `/admin/users` — list loads; invite an organizer (new email) and see
      them appear; deactivate a user; CCPA export link is present.
- [ ] `/admin/portals` — list loads; open a portal detail page without
      errors.
- [ ] `/admin/modules` — list shows slug / name / capacity / duration;
      create, edit, and delete/archive flows all work.
- [ ] `/admin/imports` — route no longer exists; the sidebar has no Imports
      entry and `GET /api/v1/admin/imports` returns 404 (feature removed in
      PR #51).
- [ ] `/admin/exports` — volunteer hours, attendance, and no-show CSVs all
      download with real (non-empty) data.
- [ ] `Overrides` tab is **NOT** present in the admin sidebar (Phase 16
      retirement regression check).
- [ ] `/admin/events/:id` roster — a shift commitment is **one** row per
      volunteer showing every session's attendance alongside it, not one row
      per session. Orientation keeps its own group.
- [ ] Event create / edit — the shift builder adds a shift with at least one
      session; a shift with no sessions is refused, and once a shift has
      signups its sessions can no longer be added to or removed (the sessions
      are the deal the volunteer agreed to).
- [ ] On an event with a waitlisted signup, clicking **Promote** on the
      event page moves the volunteer to pending (not straight to confirmed)
      and a confirm-your-spot email arrives in Mailpit within 15s. A shift's
      waitlist is one queue for the whole bundle — promoting takes the seat
      for every session at once.
- [ ] Cancelling a shift commitment from the event page frees its seat and
      writes an "Admin cancelled a shift signup" row to `/admin/audit-logs`,
      naming the volunteer and the shift.
- [ ] Every admin page shows loading / empty / error states correctly.
- [ ] No console errors in DevTools across the full admin sweep.

---

## Section 3 — Organizer flow (phone, 375px)

Drive from the Organizer phone window.

- [ ] Login → lands on `/organizer` (phone-first dashboard), NOT on
      `/admin/events`.
- [ ] Dashboard shows Today / Upcoming / Past tabs; tapping switches tabs.
- [ ] "Open roster" button on an event card navigates to
      `/organizer/events/:id/roster`.
- [ ] Roster shows confirmed signups with tap-friendly check-in rows, grouped
      one section per session. A volunteer holding a two-session shift appears
      once under each session — check-in is per (commitment, session), so a
      Tuesday tap must not flip Wednesday's row.
- [ ] Tapping a row flips status to "checked in" optimistically (no reload
      required).
- [ ] "End slot" on one session of a multi-session shift records that
      session's attendance and leaves the other session's section live — its
      own "End slot" button still enabled.
- [ ] Organizer sidebar does **NOT** show Users, Audit Logs, or Exports
      (Phase 19 RBAC regression check).

---

## Section 4 — Cross-role loop

Drive all three windows in one sitting. Mirrors Scenario 1 from
`e2e/cross-role.spec.js`.

- [ ] **Admin** confirms the seed event exists at `/admin/events/:id`.
- [ ] **Participant** (incognito) signs up for a shift; confirms via the
      Mailpit magic link. One press produces one commitment covering every
      session in the shift.
- [ ] **Organizer** (phone) sees the new signup appear in the roster within
      ~6s (5s poll + buffer), or after a reload.
- [ ] **Organizer** checks the participant in; the row status chip flips to
      "checked in".
- [ ] **Admin** navigates to `/admin/audit-logs`, filters by the
      participant's email, and sees the expected audited entries
      (admin-initiated actions are audited; see note below).
- [ ] **Participant** visits `/signup/manage?token=...` and sees the signup
      marked checked in.

> Note: per 20-01 findings, only ADMIN-initiated actions write to the audit
> log (the public cancel endpoint was removed by the read-only-signups
> change). `signup.created` (public) and organizer check-in are NOT audited
> in v1.2-prod. The admin audit-log page must still be reachable and
> filterable without error.

---

## Section 5 — Regressions to watch

- [ ] No CSV-import copy anywhere in the UI (the import pipeline was
      removed in PR #51; modules are managed by hand on `/admin/modules`).
- [ ] No "student account", "student register", or "student login" copy
      anywhere in the UI (participants are account-less).
- [ ] All in-app links use `/organizer/*`; none use bare `/organize/*`
      except the single deliberate redirect catch-all in `App.jsx`.
- [ ] Magic-link email actually arrives in Mailpit (confirms dev mailer is
      pointed at Mailpit, not SES / SendGrid).
- [ ] No failed network requests in any DevTools Network tab across the
      full sweep (all green).
- [ ] No console errors or warnings in any of the three browsers across
      the full sweep.

---

## Sign-off

All boxes above checked in one sitting, no manual DB nudges, no failed
requests.

```
Smoke passed by: ________    Date: ________
```
