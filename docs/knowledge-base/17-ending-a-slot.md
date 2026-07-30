# Ending a slot (closing out a session)

When a session is over, the organizer **ends the slot** — the close-out step that marks every
volunteer either **attended** or **no-show**. This is the step that finishes a session, and it is
the step people most often forget.

The close-out screen lists everyone signed up for that slot and pre-fills each row from what
already happened during the session: people who were checked in default to attended. You adjust
anything that's wrong and save.

**Ending a slot is all-or-nothing.** If any single row can't be saved, the whole close-out is
rolled back and nothing changes — you won't get a half-finished session where some people are
resolved and others aren't.

**Attended and no-show are final in every normal flow**, so it's worth a glance at the list before
saving. There is exactly one way back: **Reopen event**, a supervised undo on the roster.

Reopening works on the **whole event**, not one person. It returns every resolved signup to the live
roster — no-shows to confirmed, attended people to checked-in if a real check-in was recorded, or to
confirmed if they were a walk-in marked attended at close-out — and clears the event's ✓ Completed
state so you can close it out again. Because it is event-wide, correcting one volunteer means
reopening and re-ending.

**Reopening does not take orientation credit back.** Credit is permanent per volunteer and module
family by design, and may predate this event, so a blanket revoke could destroy legitimate credit.
Credit granted wrongly is corrected in Admin → Orientation Credits.

Both ending and reopening write audit rows naming the staff member who did it.

**A volunteer who turned up but was never checked in can still be marked attended** here. That's
the walk-in case, and it's a normal thing to do — nothing is lost by forgetting to tap someone in
during the session.

**Ending an orientation slot is the moment orientation credit is granted.** Every volunteer marked
attended on an orientation slot earns a permanent orientation credit for that event's module
family, automatically. Nothing else in the system does this: checking someone in doesn't, and the
signup itself doesn't. **If an orientation happened but nobody has credit for it, the slot was
almost certainly never ended.**

You can also end a whole event at once rather than slot by slot. It grants orientation credit
exactly the same way for any orientation slots it covers.

**Once every slot in an event has been ended, the event itself reads as ✓ Completed** and can be
filtered that way in the events list. That flag is derived from the slots, so it appears on its own
and disappears again if the event is reopened.

Credit granted this way is deduplicated, so a volunteer who somehow ends up resolved twice doesn't
accumulate duplicate credits.
