# Slots

A **slot** is one bookable session inside an event: a date, a start and end time, an optional
location, a capacity, and a type. Slots — not events — are what volunteers actually sign up for.
An event with five classroom sessions has five slots, and a volunteer may take one, some, or all
of them.

There are two **slot types**. A **period** slot is a regular classroom session. An **orientation**
slot is a mentor orientation. The distinction matters a great deal: orientation slots are what
satisfy the orientation requirement, and ending an orientation slot is what grants permanent
orientation credit for the module family.

Each slot has a **capacity** and a running **current count** of taken seats. A seat is held from
the moment a signup is made: an unconfirmed (pending) signup counts against capacity exactly like a
confirmed one, because holding the seat is the whole point of the confirmation window. Waitlisted
signups do **not** count. When the count reaches capacity, further signups for that slot are
waitlisted rather than rejected.

**A freed seat is offered down the waitlist immediately.** When someone who was holding a seat
cancels, or an unconfirmed signup lapses and is swept away, the longest-waiting person on that slot
is promoted — and the loop keeps going until the slot is full or the waitlist is empty, so one
cancellation can promote several people. A promoted volunteer moves to *pending*, not straight to
confirmed: they get an emailed link and three days to claim the seat, and if they don't, the seat
passes down the line on the next hourly sweep. Nobody is promoted into a session that has already
finished. See the waitlist document.

**Raising a session's capacity fills the new seats from the waitlist straight away.** Editing a slot
to a higher capacity promotes the longest-waiting volunteers until the new capacity is reached or the
waitlist runs out — each one moved to *pending* with their own three-day confirm email, exactly as if
a seat had been cancelled. Lowering a capacity never removes anyone: the seats already held stay
held, and the session simply sits over its new number until someone cancels.

Slots are added, edited, and deleted **one at a time** from the event page. Because each slot
carries its own date, time, and location, one event can span several days in different rooms. There
is no bulk generator in the UI — the app carries a recurrence facility behind the scenes, but no
screen reaches it, so building a multi-session event means adding each session by hand.

**Slots in an event whose quarter has ended or been archived cannot be added, edited, or deleted.**
The server refuses with "*[quarter name]* has ended and is read-only," exactly as it does for the
event itself and for its custom signup questions. Closing out attendance on such a session is the
deliberate exception and still works.

The **check-in window** for a slot runs from 30 minutes before its start time to 30 minutes after.
Outside that window the door check-in page tells the volunteer when the shift opens or that it has
closed, rather than letting them check in. Volunteers arrive early, which is exactly why the
window opens half an hour ahead.

Slots are the unit of **closing out** a session too. When a session is over the organizer ends
that slot and marks each volunteer attended or no-show. Ending one slot does not touch the others
in the same event — though ending the last one anyone was still expected at marks the whole event
completed.

Slots are also the finest unit a **broadcast** can target. A broadcast reaches the volunteers on the
event who are confirmed, checked in, or attended; pending, waitlisted, no-show, and cancelled
signups are skipped. An organizer can narrow it to a single slot, and because slots have no name
field the picker labels them by type, date, time, and location. That picker only appears when the
event has two or more slots — with one slot there is nothing to choose between.

For SciTrek in practice: volunteers meet at **Chem 1204 fifteen minutes before a module session
starts**, and orientation is held in **Chem 1005D** unless the slot says otherwise.
