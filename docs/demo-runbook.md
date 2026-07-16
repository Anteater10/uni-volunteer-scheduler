# Demo-day runbook — 2026-07-02 recruiter demo

Local three-role demo: **participant** (public, no login), **organizer**, **admin**.
All times below are PDT; the containers run UTC.

## URLs

| Surface | URL |
|---|---|
| App (built SPA) | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Mailpit (all emails land here) | http://localhost:8025 |

## Accounts

- Admin — `admin@e2e.example.com` / `Admin!2345`
- Organizer — `organizer@e2e.example.com` / `Organizer!2345`
- Participants are account-less: sign up with any email, confirm via the
  email that lands in Mailpit.

## Startup

```bash
cd ~/Desktop/uni-event-scheduler
docker compose up -d          # db, redis, mailpit, backend, celery worker+beat
docker ps                     # expect 7 containers incl. uvs-frontend on :3000
```

If `uvs-frontend` is missing (it does not belong to compose):

```bash
docker run -d --name uvs-frontend -p 3000:80 --restart unless-stopped uvs-frontend
```

Health check: http://localhost:8000/api/v1/health, then load
http://localhost:3000/volunteer — the Summer 2026 · Week 2 grid should render.

## Reset to the golden state

The golden dump lives at the repo root: `uvs-demo-golden.sql` (taken
2026-07-01 after the final reseed; procedure rehearsed and verified).

```bash
cd ~/Desktop/uni-event-scheduler
docker exec uni-event-scheduler-db-1 psql -U postgres -c "DROP DATABASE uni_volunteer WITH (FORCE);"
docker exec uni-event-scheduler-db-1 psql -U postgres -c "CREATE DATABASE uni_volunteer;"
docker exec -i uni-event-scheduler-db-1 psql -U postgres -d uni_volunteer < uvs-demo-golden.sql
docker compose restart backend celery_worker celery_beat
# clear Mailpit
curl -s -X DELETE http://localhost:8025/api/v1/messages
```

## Timing traps (read before the demo)

- **Public signup segment:** the Week-2 landing view thins out during the
  day — the Astronomy (7/02) card disappears at **11:45 AM** because its last
  slot ends then (past-event hiding is correct product behavior). After that,
  Week 2 shows only the full Biology card. Either run the signup segment in
  the morning, click **View next week** and sign up on a Week-3 event
  (Goleta Chemistry 7/07 or Adelante Physics 7/09, both have open seats), or
  toggle *Hide past events* OFF in the admin Site Settings card.
- **Week chips:** the public hero says "Summer 2026 · Week 2"; the admin
  Overview progress bar says "Week 3 of 11". Known dual-anchor drift (the
  rolling anchor is locked by Andy) — don't show the two side by side.

## Scripted beats that work

1. **Browse → sign up → confirm (participant, phone width, incognito):**
   sign up with a fresh email on an open slot → open Mailpit → click the
   confirm link (lands on `:3000/signup/confirm`, succeeds) → *Manage
   signups* from the same email.
   - If the recruiter re-submits the same email/slot, the toast now says
     "already signed up" (fixed) — a nice validation moment, not an error.
2. **Cancel → waitlist auto-promote (admin, the centerpiece):** open the
   Biology @ Isla Vista event (7/03, 6/6 full, 3 waitlisted). Cancel a
   confirmed signup → the roster auto-refreshes and waitlist #1 flips to
   confirmed. Mailpit shows **two** emails: the cancellation and the
   **"You're in from the waitlist"** promotion email (wired tonight —
   previously silent). Rehearsed end-to-end 2026-07-01.
   - Nuance: the promotion email says "confirm your spot" but the volunteer
     is already confirmed — clicking its link is a safe no-op. Don't dwell
     on the email body copy.
3. **Slot swap (participant view):** Physics @ Adelante (7/09) has two
   sessions (5/8 and 3/8) — swap between them from Manage signups.
4. **Organizer roster + check-in (organizer, phone width):** login organizer
   → Dashboard shows Astronomy @ McKinley under *Today* → **Open roster** →
   one-tap check-in works at ANY time (no window). 9 confirmed volunteers to
   play with. Events are seeded as organizer-owned (fixed tonight), so
   *View details* and *Add a question* work too.
   - Quirk: the dashboard card's clock time renders the raw UTC timestamp in
     local form (shows "3:30 PM" for the 8:30 AM session). The roster page
     shows correct times — don't read event times off the dashboard cards.
5. **Participant self-check-in (only if you want the full loop):**
   self/QR check-in is window-gated (15 min before slot start → 30 min
   after). All seeded slots are morning slots, so for an afternoon demo run:

   ```bash
   docker compose exec backend python -m scripts.seed_live_event
   ```

   This creates/refreshes **"LIVE Check-in Test Event"** with a slot that
   started 5 minutes ago (window stays open ~25 min; re-run to refresh).
   Then: open its roster as organizer FIRST (this mints and persists the
   4-digit venue code — fixed tonight), and have the volunteer's
   `/check-in/<signup-id>` URL ready — no email or page links to it.
   Note: the LIVE event appears on the public browse page while it exists.

## Things not to click / show

- **/admin/copilot-feedback** — the copilot is feature-flagged off in this
  build (no FAB, nav item now hidden too), but the URL still resolves to an
  empty analytics page.
- **Exports:** lead with `attendance-rates.csv` (has rows);
  `volunteer-hours.csv` is header-only because no attendance is recorded yet.
  Frame as "future events, no attendance data yet."
- **Users page** shows only the 2 staff accounts — volunteers are
  account-less by design (good talking point, not a bug).
- **Audit logs** accumulate rows from your own admin navigation; a reset to
  the golden dump clears them.

## Known-good state

- Backend suite: 799+ passed; frontend: 277 passed (post-fix runs tonight).
- `demo_email.sh` still pauses the celery worker as a workaround for the
  enqueue-before-commit race — that race was fixed tonight, so the pause is
  redundant (harmless to keep using the script).
