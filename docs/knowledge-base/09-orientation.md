# Orientation — the requirement and the credit

**Orientation is a hard requirement, not a warning.** A volunteer who has never been oriented for a
module's family must include an orientation session in the same signup, or the signup is rejected.
The server refuses it before writing anything, and the volunteer is told "New volunteers must
include an orientation session in their signup." There is no self-attested bypass — the volunteer
cannot tick a box claiming they've done it.

On the volunteer's side this appears as a **steering modal**: instead of offering a way through, the
only action takes them back to the schedule to add an orientation session. Their selection and
anything they typed into the form are preserved while they do it.

**The one exception: an event that offers no orientation slots at all is exempt.** Requiring
orientation there would be impossible to satisfy, so the signup goes through and an organizer can
vouch for the volunteer at the door instead. In practice SciTrek almost always posts an orientation
for a module, so this should be rare — treat it as the 1% case, not a routine path.

Two more cases pass automatically. A signup that selects **only orientation slots** always passes —
that's a volunteer doing their orientation. And a volunteer who **already holds credit** for the
event's module family signs up freely, with no extra step.

**The requirement is checked when the signup is created, and never again.** It looks at what the
volunteer selected, not at whether they eventually attend — a waitlisted orientation slot satisfies
it just as well as a seat. The flip side is that a volunteer can end up holding module sessions with
no orientation behind them: staff cancelled the orientation for them, or it was a waitlist promotion
they never claimed. Nothing blocks them at the door, so an organizer either runs them through an
orientation or vouches for them from the roster.

**A signup covers one event at a time.** Selecting slots across two different events in a single
submission is refused with "A signup covers one event at a time." The volunteer event page only ever
submits its own slots, so this is invisible in normal use; the rule closes a hole where the public
signup form could be used to probe many volunteers' orientation status at once.

## Orientation credit

**Orientation credit is permanent.** Once a volunteer is oriented for a module family, they are
oriented forever — any quarter, any year. There is no expiry of any kind, and quarter boundaries do
not reset it. An earlier design scoped credit to the quarter it was earned in; that was reversed by
product decision.

Credit is keyed by **(volunteer email, module family)**. It is tied to the email address rather than
to a volunteer record, so it stands on its own: an admin can grant credit for an email that has
never signed up for anything, and the credit is waiting when that person does sign up. The
corollary is that a volunteer who signs up under a different email address arrives with no credit
and is treated as brand new.

**Only an explicit credit record grants credit — and there are exactly two ways to get one.**

1. **Ending an orientation slot.** When an organizer closes out an orientation session, every
   volunteer marked attended who doesn't already hold credit for that family gets a credit record
   automatically. This is the normal path. (Skipping people who already hold credit is intentional —
   it stops repeat orientations piling up duplicate records.)
2. **A manual grant.** An organizer can grant credit with one tap from the event roster ("vouched
   for" at the door), or an admin can grant it from Admin → Orientation Credits.

**An orientation slot on an event with no module attached grants nothing.** Credit only exists for a
specific module family, so with no module there's nothing to credit against. Ending the slot skips
those volunteers silently — no error, no record. The roster's "Grant orientation" button is the
honest one here: it refuses with a message telling you to set the module on the event first. If an
orientation was run and nobody has credit, check the event's module before anything else, then grant
by hand for the volunteers who attended.

**Checking a volunteer in does not grant orientation credit.** Check-in only records that they
arrived. The credit is written when the slot is *ended*. If an orientation happened but nobody
appears to have credit for it, the likely cause is that the slot was never closed out.

**Reopening an event does not take orientation credit back.** "Reopen event" returns volunteers to
the live roster, but any credit already granted stays granted — credit is permanent per volunteer
and family, and may well predate this event, so revoking in bulk could destroy legitimate credit.
Corrections are made one at a time from Admin → Orientation Credits.

**Revoking a credit genuinely removes it.** Nothing re-derives credit from the underlying signup, so
a revoked credit stays revoked until someone grants it again.

Credit records can note **which quarter the credit was earned in**. That is reference metadata for
the admin view and filters only — it never affects whether the credit counts. The grant form's
quarter picker is optional for this reason, and the helper text says so.

By SciTrek convention orientation is held in **Chem 1005D**. That's a program habit rather than
something the app knows: a slot's location is free text an organizer types in, and nothing fills it
in or checks it. Always go by what the slot itself says.
