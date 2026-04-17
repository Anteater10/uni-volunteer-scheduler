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
   docker compose up -d db redis
   docker compose run --rm migrate
   docker compose up -d backend celery_worker celery_beat mailpit
   ```

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

5. Confirm backend health at http://localhost:8000/api/v1/healthz (or
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
- [ ] Open event detail — slots grouped by orientation / period with capacity
      and filled counts displayed.
- [ ] Start signup for a period slot with a **fresh** email (no prior
      attendance) — orientation warning modal fires.
- [ ] Repeat with the seeded `attended_volunteer_email` — orientation modal
      is suppressed (DB confirms prior attendance).
- [ ] Form validation — invalid email and invalid phone are both rejected
      with clear inline messages.
- [ ] Submit signup → success card renders; confirmation email arrives in
      Mailpit (http://localhost:8025) within 15s.
- [ ] Click the magic link in the Mailpit email → lands on `/signup/confirm`
      → "your signup is confirmed" banner shows.
- [ ] `/signup/manage?token=...` shows the signup with per-row Cancel and a
      Cancel-all button.
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
- [ ] `/admin/templates` — list shows slug / name / capacity / duration;
      create, edit, and delete/archive flows all work.
- [ ] `/admin/imports` — upload a sample quarterly template CSV; preview
      shows "N events will be created, M skipped"; confirm commits
      atomically.
- [ ] `/admin/exports` — volunteer hours, attendance, and no-show CSVs all
      download with real (non-empty) data.
- [ ] `Overrides` tab is **NOT** present in the admin sidebar (Phase 16
      retirement regression check).
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
- [ ] Roster shows confirmed signups with tap-friendly check-in rows.
- [ ] Tapping a row flips status to "checked in" optimistically (no reload
      required).
- [ ] Organizer sidebar does **NOT** show Users, Audit Logs, or Exports
      (Phase 19 RBAC regression check).

---

## Section 4 — Cross-role loop

Drive all three windows in one sitting. Mirrors Scenario 1 from
`e2e/cross-role.spec.js`.

- [ ] **Admin** confirms the seed event exists at `/admin/events/:id`.
- [ ] **Participant** (incognito) signs up for a period slot; confirms via
      the Mailpit magic link.
- [ ] **Organizer** (phone) sees the new signup appear in the roster within
      ~6s (5s poll + buffer), or after a reload.
- [ ] **Organizer** checks the participant in; the row status chip flips to
      "checked in".
- [ ] **Admin** navigates to `/admin/audit-logs`, filters by the
      participant's email, and sees the expected audited entries (cancel
      and admin-initiated actions are audited; see note below).
- [ ] **Participant** visits `/signup/manage?token=...` and sees the signup
      marked checked in.

> Note: per 20-01 findings, only ADMIN-initiated actions and public cancel
> write to the audit log. `signup.created` (public) and organizer check-in
> are NOT audited in v1.2-prod. The admin audit-log page must still be
> reachable and filterable without error.

---

## Section 5 — Regressions to watch

- [ ] CSV import copy everywhere says **"quarterly"**, not "yearly" (admin
      imports UI, template help text, any in-app docs).
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
