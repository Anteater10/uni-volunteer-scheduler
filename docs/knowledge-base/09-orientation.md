# Orientation — the requirement and the credit

**Orientation is a hard requirement, not a warning.** A volunteer who has never been oriented for a
module's family must include an orientation session in the same signup, or the signup is rejected.
The server refuses it before writing anything, returning the error code
`ORIENTATION_REQUIRED` with the message "New volunteers must include an orientation session in
their signup." There is no self-attested bypass — the volunteer cannot tick a box claiming they've
done it.

On the volunteer's side this appears as a **steering modal**: instead of offering a way through, the
only action takes them back to the schedule to add an orientation session. Their slot selection and
anything they typed into the form are preserved while they do it.

**The one exception: an event that offers no orientation slots at all is exempt.** Requiring
orientation there would be impossible to satisfy, so the signup goes through and an organizer can
vouch for the volunteer at the door instead. In practice SciTrek almost always posts an orientation
for a module, so this should be rare — treat it as the 1% case, not a routine path.

Two more cases pass automatically. A signup that selects **only orientation slots** always passes —
that's a volunteer doing their orientation. And a volunteer who **already holds credit** for the
event's module family signs up freely, with no extra step.

**A signup covers one event at a time.** Selecting slots across two different events in a single
submission is rejected with `MULTIPLE_EVENTS`. The volunteer event page only ever submits its own
slots, so this is invisible in normal use; the rule closes a hole where the public endpoint could
be used to probe many volunteers' orientation status at once.

## Orientation credit

**Orientation credit is permanent.** Once a volunteer is oriented for a module family, they are
oriented forever — any quarter, any year. There is no expiry of any kind, and quarter boundaries do
not reset it. An earlier design scoped credit to the quarter it was earned in; that was reversed by
product decision.

Credit is keyed by **(volunteer email, module family)**. It is tied to the email address rather
than to a volunteer record, so credit survives even if the volunteer record is removed and later
recreated.

**Only an explicit credit record grants credit — and there are exactly two ways to get one.**

1. **Ending an orientation slot.** When an organizer closes out an orientation session, every
   volunteer marked attended gets a credit record automatically. This is the normal path.
2. **A manual grant.** An organizer can grant credit with one tap from the event roster ("vouched
   for" at the door), or an admin can grant it from Admin → Orientation Credits.

**Checking a volunteer in does not grant orientation credit.** Check-in only records that they
arrived. The credit is written when the slot is *ended*. If an orientation happened but nobody
appears to have credit for it, the likely cause is that the slot was never closed out.

**Revoking a credit genuinely removes it.** Nothing re-derives credit from the underlying signup, so
a revoked credit stays revoked until someone grants it again.

Credit records can note **which quarter the credit was earned in**. That is reference metadata for
the admin view and filters only — it never affects whether the credit counts. The grant form's
quarter picker is optional for this reason, and the helper text says so.

Orientation for SciTrek is held in **Chem 1005D** unless a slot says otherwise.
