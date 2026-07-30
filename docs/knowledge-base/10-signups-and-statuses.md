# Signups and the status lifecycle

A **signup** is one volunteer holding one slot. A volunteer who takes three sessions of a module
has three signups. Signups are never deleted — they carry a status instead, because attendance
history is what hours, credit, and reporting are built on.

There are seven signup statuses: **pending**, **confirmed**, **waitlisted**, **checked in**,
**attended**, **no-show**, and **cancelled**.

- **Pending** — the signup exists but hasn't been confirmed yet.
- **Confirmed** — the volunteer holds the spot. This is the normal state between signing up and
  showing up.
- **Waitlisted** — the slot was full when they signed up. They're in line for a seat.
- **Checked in** — they've arrived, and the session hasn't been closed out yet.
- **Attended** — they were present and the organizer has closed out the session.
- **No-show** — they didn't turn up and the organizer has closed out the session.
- **Cancelled** — the spot was given up, by the volunteer or by staff.

**Attended, no-show, and cancelled are final.** Once a signup reaches one of those three it cannot
be moved anywhere else. Everything before them can still change:

- Pending can become confirmed or cancelled.
- Confirmed can become checked in, attended, no-show, or cancelled.
- Checked in can go back to confirmed (the organizer's undo for a mis-tap), or forward to attended
  or no-show, or be cancelled.
- Waitlisted can become pending (when promoted) or cancelled.

**Confirmed can go straight to attended** without a check-in. That's the walk-in case: the
volunteer turned up but nobody tapped them in, and the organizer marks them attended while closing
out the session. Without this the end-of-session screen would offer "attended" on every confirmed
row and then refuse to save it.

**Cancelling a confirmed signup frees the seat and auto-promotes the waitlist.** The longest-waiting
volunteer on that slot moves straight to confirmed. See the waitlist document.

Signups are attached to a **volunteer record keyed by email address**, and the link is protective:
a volunteer with signups cannot be deleted. If you genuinely need to remove someone, their signups
have to be cancelled first. This is deliberate — deleting a volunteer outright would destroy the
attendance record behind their hours and their orientation credit.

Every volunteer's answers to the event's signup form are stored per field against their signup, so
you can see what each person actually submitted even after the event's form has changed.
