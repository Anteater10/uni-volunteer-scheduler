# Signups and the status lifecycle

A **signup** is one volunteer holding one slot. A volunteer who takes three sessions of a module
has three signups.

**Once a signup has been confirmed, it is never deleted** — it carries a status instead, because
attendance history is what hours, credit, and reporting are built on. A signup that was *never*
confirmed is different: if its confirm deadline lapses, the hourly cleanup deletes it outright. See
"Pending has a deadline" below.

There are seven signup statuses: **pending**, **confirmed**, **waitlisted**, **checked in**,
**attended**, **no-show**, and **cancelled**.

- **Pending** — the volunteer holds the seat but hasn't clicked their confirm link yet. Pending
  occupies capacity, and it always carries a deadline.
- **Confirmed** — the volunteer holds the spot. This is the normal state between signing up and
  showing up.
- **Waitlisted** — the slot was full when they signed up. They're in line for a seat.
- **Checked in** — they've arrived, and the session hasn't been closed out yet.
- **Attended** — they were present and the organizer has closed out the session.
- **No-show** — they didn't turn up and the organizer has closed out the session.
- **Cancelled** — the spot was given up, by the volunteer or by staff.

**Cancelled is final. Attended and no-show are final in normal use, but reversible.** In every day-to-day
flow, a signup that reaches attended or no-show stays there. The one exception is **Reopen event** —
a supervised undo that returns a closed-out event's roster to the live state. It works at the event
level, not per person; you cannot walk back one individual's status. See
[17-ending-a-slot.md](17-ending-a-slot.md).

Everything before them can still change:

- Pending can become confirmed or cancelled.
- Confirmed can become checked in, attended, no-show, or cancelled.
- Checked in can go back to confirmed (the organizer's undo for a mis-tap), or forward to attended
  or no-show, or be cancelled.
- Waitlisted can become pending (when promoted) or cancelled.
- Attended and no-show can be reversed, but only by reopening the whole event. Reopening sends
  attended back to **checked in** if a real check-in was recorded, or to **confirmed** if the person
  was a walk-in marked attended at close-out. No-show always goes back to **confirmed**.

**Confirmed can go straight to attended** without a check-in. That's the walk-in case: the
volunteer turned up but nobody tapped them in, and the organizer marks them attended while closing
out the session. Without this the end-of-session screen would offer "attended" on every confirmed
row and then refuse to save it.

**Pending has a deadline, and it is enforced.** Every pending signup carries a confirm link with an
expiry:

| How they became pending | Time to confirm |
|---|---|
| Signed up for a seat that was free | **14 days** |
| Promoted off the waitlist | **3 days** |

Every hour, on the hour, a job looks for pending signups whose confirm links have all expired. It
**deletes** them, frees the seat, and offers it to the next person on the waitlist. The dropped
volunteer is not emailed and no cancelled record is left behind — the signup is simply gone.

That is the single most common explanation for *"I signed up but I'm not on the roster."* They never
clicked the link in their email, and the deadline passed. Since nothing is left behind, the only way
to get them back on is for them to sign up again, or for staff to add them.

**Cancelling a signup that holds a seat frees it and auto-promotes the waitlist.** This applies to
both confirmed and pending signups, since both occupy capacity. The longest-waiting volunteer on that
slot is promoted **to pending** and emailed a 3-day confirm link — not straight to confirmed. See
[11-waitlist.md](11-waitlist.md).

Signups are attached to a **volunteer record keyed by email address**, and the link is protective:
a volunteer with signups cannot be deleted. If you genuinely need to remove someone, their signups
have to be cancelled first. This is deliberate — deleting a volunteer outright would destroy the
attendance record behind their hours and their orientation credit.

Every volunteer's answers to the event's signup form are stored per field against their signup, so
you can see what each person actually submitted even after the event's form has changed.
