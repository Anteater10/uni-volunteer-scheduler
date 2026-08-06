# Signups and the status lifecycle

A **signup** is one volunteer holding one shift, or one volunteer holding one orientation slot. A
shift is booked all or nothing, so a volunteer committed to a three-session shift has **one**
signup, not three. From confirmed onward a signup is never deleted — it carries a status instead,
because attendance history is what hours, credit, and reporting are built on. The one exception is
an unconfirmed signup that expires; see below.

There are seven signup statuses: **pending**, **confirmed**, **waitlisted**, **checked in**,
**attended**, **no-show**, and **cancelled**.

- **Pending** — the signup exists but hasn't been confirmed yet. It holds its seat while it waits.
- **Confirmed** — the volunteer holds the spot. This is the normal state between signing up and
  showing up.
- **Waitlisted** — the shift or orientation slot was full when they signed up. They're in line for
  a seat.
- **Checked in** — they've arrived, and the session hasn't been closed out yet.
- **Attended** — they were present and the organizer has closed out the session.
- **No-show** — they didn't turn up and the organizer has closed out the session.
- **Cancelled** — the spot was given up. A volunteer never cancels it themselves; they ask staff by
  email, and staff cancel it in the app.

**Attended, no-show, and cancelled are final.** Check-in, self check-in, and closing out a session
will never move a signup back out of one of them. Attended and no-show have exactly one deliberate
undo — **"Reopen event"**, for a session that was ended too early, which puts those volunteers back
on the live roster, and which only works while the event's quarter is still open. Cancelled has no
undo at all.

Everything before those three can still change:

- Pending can become confirmed or cancelled.
- Confirmed can become checked in, attended, no-show, or cancelled.
- Checked in can go back to confirmed (the organizer's undo for a mis-tap), or forward to attended
  or no-show, or be cancelled.
- Waitlisted can become pending (when an admin or organizer promotes them — the waitlist never moves
  on its own) or cancelled. A promoted volunteer confirms from there; see the waitlist document.
  Cancelled here comes from staff (a volunteer asks by email) or from the hourly check, which
  cancels anyone still waitlisted once the session's end time has passed.

**On a shift, the last three statuses are recorded per session rather than on the signup itself.**
The commitment stays pending, confirmed, waitlisted, or cancelled for its whole life; checked in,
attended, and no-show are recorded against each session separately, which is what lets a volunteer
be attended on Tuesday and no-show on Thursday under one booking. An orientation signup, having
only the one session, carries its outcome directly.

**Confirmed can go straight to attended** without a check-in. That's the walk-in case: the
volunteer turned up but nobody tapped them in, and the organizer marks them attended while closing
out the session. Without this the end-of-session screen would offer "attended" on every confirmed
row and then refuse to save it.

**A volunteer cannot cancel a signup themselves.** They email the SciTrek organizers (the address
configured in Site settings), and staff cancel it from the roster. **Cancelling a signup that held a
seat frees it, but nobody is promoted off the waitlist automatically** — this is true whether the
signup was confirmed or still pending, since both hold capacity. A staff member has to deliberately
promote someone off the waitlist if the seat should be filled; see the waitlist document.

Every cancellation emails the volunteer a cancellation notice, whoever asked for it. That's
deliberate: it's the volunteer's confirmation that the change they requested actually happened.

**Cancelling is one-way for that volunteer.** The cancelled signup stays on the books, and a
volunteer can only ever hold one signup per shift — so someone who cancels and then changes their
mind cannot re-book that same shift. They're turned away with "You've already signed up for this
session with that email", which is confusing in this situation but is what the app says. They can
still take a *different* shift on the same event, and there's no staff action that reinstates the
cancelled one. If a volunteer wants to move rather than drop out, they should say so in the same
email — staff can **move** the signup to a different shift on the event instead of cancelling and
re-signing them up.

## Confirming, and what happens when nobody does

**A signup submission gets one confirmation link, good for two weeks.** Clicking it confirms every
pending signup that volunteer has on that event, so a volunteer who took an orientation slot and a
shift in one go confirms both with one click. It will **not** confirm a seat that came from a **waitlist
promotion** — that seat has its own link in its own promotion email. If a volunteer's only pending
seat is a promoted one, their original signup link reports that it confirmed nothing and tells them
to use the promotion email instead.

**Confirming is an RSVP, not a gate.** A pending volunteer who simply turns up is confirmed
automatically as part of being checked in — at the door, whether they ever opened the email doesn't
matter.

**An unconfirmed signup eventually expires.** An automatic check runs every hour. When a pending
signup's confirmation link has run out and it has no other live link, the signup is **deleted** and
its seat is freed — the one case where a signup disappears instead of being cancelled. Freeing the
seat does not promote anyone off the waitlist; it simply stays open until a staff member deliberately
promotes someone. Nothing tells the volunteer their signup lapsed — but because the row is deleted
rather than cancelled, they *can* sign up for that same session again, unlike someone who cancelled.

**A waitlisted signup on a session that has come and gone is closed out automatically.** The same
hourly check marks any still-waitlisted signup as **cancelled** once its session's end time has
passed. No email goes out — they never held a seat, and the session is over. Without this, a waitlist
that never drained would leave people sitting in line for a session that already happened. Note the
difference from an unconfirmed pending signup, which is **deleted** rather than cancelled.

**A submission covering several units only carries one link, and only that one signup is swept.**
Where a volunteer took an orientation slot and a shift in one go, the other signup has no link of
its own, so if the volunteer never confirms it stays pending and keeps holding its seat until
somebody cancels it by hand. It's worth checking for stale pending rows on a full shift before
concluding the seat count is wrong.

**Confirmation links stop working for confirming, but keep working for everything else they do.**
Once the two weeks are up the volunteer can no longer use the link to confirm, but they can still
open it to view their signups and manage their reminder preferences. That's on purpose: someone who
confirmed on day one shouldn't lose access to their own signups two weeks later. Cancelling or moving
to another session was never something the link itself could do — that always goes through the
SciTrek organizers by email. The links are cleaned up quietly much later, once the volunteer has no
upcoming sessions left.

**A pending volunteer keeps an event from being marked complete.** Closing out a session only
resolves confirmed and checked-in volunteers — a pending one isn't offered on the end-of-session
screen at all — and an event counts as complete only once nobody is still expected. So an event
that looks entirely finished but still shows **"Ended — not closed out"** on the admin events list
usually has a pending signup sitting on it, most often a waitlist promotion nobody claimed.

Waiting for the hourly check to clear the pending signup isn't enough on its own: the event's
completed stamp is only recalculated when someone ends or reopens it. Once the pending row is gone,
the organizer's roster page will show the "Event complete" banner — use **Reopen event** there and
then **End event** once more, and the event files itself under Completed properly. Do this while the
event's quarter is still open: reopening is refused once the quarter has ended or been archived, and
an event left in that state stays badged the way it is.

## Volunteer records

Signups are attached to a **volunteer record keyed by email address**, and that record can't be
deleted. There's no delete-volunteer action anywhere in the app, and the database refuses it while
any signup row exists — cancelled ones included, since cancelling leaves the row in place. This is
deliberate: attendance history is the source of truth behind hours and orientation credit, and
deleting a volunteer outright would destroy it.

Every volunteer's answers to the event's signup form are stored per field against their signup, so
you can see what each person actually submitted even after the event's form has changed.
