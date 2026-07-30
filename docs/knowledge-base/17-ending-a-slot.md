# Ending a slot (closing out a session)

When a session is over, the organizer **ends the slot** — the close-out step that marks every
volunteer either **attended** or **no-show**. This is the step that finishes a session, and it is
the step people most often forget.

**The close-out screen lists only the slot's confirmed and checked-in volunteers.** Anyone
waitlisted, cancelled, or already resolved is left out, because there is no attendance decision to
make for them. Volunteers still sitting at **pending** are also left out, and that one is worth
knowing: a pending volunteer cannot be resolved here at all, so tap them in on the roster first —
the tap confirms them — or their unresolved row will keep the session looking open.

**Everyone who was not checked in is pre-filled as a no-show.** Checked-in volunteers pre-fill as
attended and every other listed volunteer pre-fills as no-show, so saving without touching anything
marks every un-tapped volunteer absent. The prefill is a shortcut for the common case where check-in
was done properly at the door, not a record of what happened — read the list before you save. The
screen says as much, and it will not let you save until every row carries a decision. A row that
appears while the dialog is already open stays unmarked, which is what keeps the Save button
disabled until you look at it.

**Ending a slot is all-or-nothing.** If any single row can't be saved, the whole close-out is
rolled back and nothing changes — you won't get a half-finished session where some people are
resolved and others aren't.

**A volunteer who turned up but was never checked in can still be marked attended** here. That's
the walk-in case, and it's a normal thing to do — as long as their signup is confirmed, nothing is
lost by forgetting to tap them in during the session.

**Attended and no-show cannot be changed one person at a time.** There is no per-row undo once a
slot is ended, so it's worth a glance at the list before saving. The one way back is reopening the
whole event, which works only while the event's quarter is still open.

**Whether a slot has been ended is worked out from its volunteers, not stored on the slot.** The app
calls a session ended when every volunteer it still expects has been resolved, which is why a single
leftover pending row leaves the slot — and with it the event — looking open indefinitely.

You can also end a whole event at once rather than slot by slot. It grants orientation credit
exactly the same way for any orientation slots it covers.

**Completing an event is not a separate action — it is what happens when nothing is left open.** The
moment the last expected volunteer on the event is resolved, the app stamps the event with a
completion date and files it under past events, which is how a finished event stops looking like an
upcoming one in the admin lists. Ending the event's final session is therefore also the act of
completing the event. An event that never had any signups never completes, and waitlisted or
cancelled signups never hold completion up.

**A completed event can be reopened, while its quarter is still open.** Both the roster's "Event
complete" banner and the event detail page's completed strip offer **Reopen event**, available to
organizers and admins, which puts everyone back on the live roster: volunteers with a real arrival
time return to checked in, everyone else returns to confirmed, and the completion date is cleared. An
event whose dates have already passed then reads as ended but not closed out, which is the honest
description of where it now stands. This is the fix for ending a session an hour too early, not a
routine step.

**Two things will refuse a reopen.** An event that was never ended has nothing to undo, and the app
says so — "Only an event that has been ended can be reopened" — rather than pretending. And **once
the event's quarter has ended or been archived, reopening is refused**: that history is closed, and
the refusal reads "*[quarter name]* has ended and is read-only." Closing out attendance is
deliberately still allowed in an ended quarter, so a session nobody ever finished can always be
finished; it is only the undo that expires.

**The undo expires earlier in the day than people expect.** Reopening stops working the moment the
quarter's end date is past, and because that cutoff is worked out in UTC it lands in the late
afternoon Pacific on the quarter's own last day — around 5pm in summer, 4pm in winter. Archiving the
quarter has the same effect but runs hours later that night, so waiting for the archive is not the
deadline to plan around. If a no-show needs correcting on the last day of a quarter, do it in the
morning.

**Reopening does not take orientation credit back.** Credit is permanent for a person and a module
family by design and may well predate this event, so a blanket removal could destroy credit someone
legitimately earned elsewhere. If a credit was granted in error, an admin removes it individually
from Admin → Orientation Credits.

**Ending an orientation slot is the moment orientation credit is granted.** Every volunteer marked
attended on an orientation slot earns an orientation credit for that event's module family,
automatically. Nothing else in the system does this: checking someone in doesn't, and the signup
itself doesn't. **If an orientation happened but nobody has credit for it, the slot was almost
certainly never ended.**

**This only works if the event is attached to a module.** Credit is recorded against a module family,
and the app finds that family through the event's module — so ending an orientation slot on an event
with no module attached grants nothing at all, and says nothing about it. If credit is missing and
the slot really was ended, check that the event has its module set.

Credit granted this way is deduplicated, so a volunteer who somehow ends up resolved twice doesn't
accumulate duplicate credits. It never expires on its own, but an admin can revoke any single credit
from Admin → Orientation Credits.
