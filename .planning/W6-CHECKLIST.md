# W6 — what to test

localhost:5173 · admin@e2e.example.com / Admin!2345

## Pages open without errors

- [ ] Public: browse events, event detail, login, forgot password, manage signups
- [ ] Admin: events, operations, event detail, roster, modules, reminders, quarters, users, audit logs, exports, orientation credits, help, settings
- [ ] Organizer: today, roster
- [ ] Copilot drawer
- [ ] Bad URL shows 404, logged-out admin URL bounces to login
- [ ] All of the above at phone width

## Flows actually work

- [ ] Create event with shifts, publish it
- [ ] Sign up as a volunteer, email arrives, confirm link works
- [ ] Magic link, then cancel a shift
- [ ] Fill a shift, next person waitlists, cancel one, promotion email fires
- [ ] Max shifts per volunteer = 1, try to book two, refusal reads right
- [ ] Check in from roster, and self check-in by QR
- [ ] Export roster CSV
- [ ] Broadcast (last, to yourself)

## Broken

-
