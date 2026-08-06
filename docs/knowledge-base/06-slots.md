# Shifts, sessions, and orientation slots

An event holds two kinds of bookable thing: **orientation slots** and **shifts**. An orientation
slot is a single mentor orientation, booked on its own. A shift is the classroom work: a named
bundle of one or more **sessions**, booked as a unit. Volunteers sign up for orientation slots and
for shifts — never for a single classroom session on its own.

A **shift** is what a volunteer commits to. It has a name the staff choose ("Tuesday + Thursday
mornings", "Week 3 afternoons"), a capacity, and an ordered list of sessions. Signing up for a
shift is **all or nothing**: one press books every session in it, and the volunteer is expected at
all of them. This is deliberate — a class needs the same mentors back each time, and letting people
take Tuesday without Thursday is what the shift model exists to prevent.

A **session** inside a shift is one classroom meeting: a date, a start and end time, an optional
room, and an optional name like "Period 1". Sessions are ordered within their shift, and that order
is what the volunteer sees on the event page and what the roster is grouped by. A session cannot be
booked by itself and has no capacity of its own — the seat count lives on the shift, because the
seat is for the whole bundle.

An **orientation slot** stands alone: one date, time, room, and capacity, booked directly. Only
orientation slots satisfy the orientation requirement, and ending an orientation slot is what
grants permanent orientation credit for the module family. A shift never grants orientation credit,
however many sessions a volunteer attends on it.

**Capacity and the waitlist belong to the shift, not to its sessions.** A shift with a capacity of
six has six mentors across all of its sessions. A seat is held from the moment a signup is made: an
unconfirmed (pending) commitment counts against a shift's capacity exactly like a confirmed one,
because holding the seat is the whole point of the confirmation window. Waitlisted commitments do
not count. When a shift is full, further signups for it are waitlisted rather than rejected, and
the waitlist is **one queue for the whole bundle** — there is no per-session waitlist to be in.

**A freed seat on a shift stays open until staff fill it.** When someone holding a shift is
cancelled, or an unconfirmed commitment lapses and is swept away, the seat is simply freed — nobody
is promoted off the waitlist automatically. An admin or organizer has to deliberately promote
someone from the event roster, and the promoted volunteer moves to *pending*, not straight to
confirmed: they get an emailed link and three days to claim the seat. Nobody can be promoted into a
shift whose **last** session has already finished, but a shift that met yesterday and meets again
tomorrow can still be promoted into — there is still work to turn up for. See the waitlist
document.

**Raising a shift's capacity opens new seats; it doesn't fill them.** The volunteers already on
that shift's waitlist stay waitlisted until a staff member promotes them, one at a time, from the
event roster. A shift's capacity cannot be lowered below the number of seats already taken — the
server refuses rather than throwing anyone out.

**Shifts and their sessions are built when the event is built.** A shift must have at least one
session; a shift with none is refused, because it is not bookable and nobody could be checked in to
it. Staff add shifts, rename them, reorder them, and add or remove sessions from the event page,
one at a time — there is no bulk generator today.

**Once a shift has signups, its sessions are frozen.** Sessions cannot be added to or removed from
a shift anyone is holding or waitlisted for: the sessions are the deal the volunteer agreed to, and
quietly adding a Thursday to a Tuesday commitment would commit them to work they never chose. An
existing session can still be **rescheduled** — moved to a new time or room — and everyone on the
shift is emailed about the change. Deleting a shift outright is refused while anyone is holding or
waiting for it; deleting an unbooked one takes its sessions with it. A shift's last remaining
session cannot be deleted, because that would leave the shift unbookable.

**Shifts and slots in an event whose quarter has ended or been archived cannot be added, edited, or
deleted.** The server refuses with "*[quarter name]* has ended and is read-only," exactly as it does
for the event itself and for its custom signup questions. Closing out attendance on such a session
is the deliberate exception and still works.

**Check-in and attendance are per session, even though the booking is per shift.** A volunteer who
committed to a two-session shift is checked in twice — once on each day — and can end up attended
on one session and no-show on the other. The roster reflects this: one commitment appears once
under each of its sessions, so the organizer taps the person in front of them on the day they are
in front of them.

The **check-in window** for a session runs from 30 minutes before its start time to 30 minutes
after, and the same window applies to an orientation slot. Outside that window the door check-in
page tells the volunteer when the session opens or that it has closed, rather than letting them
check in. Volunteers arrive early, which is exactly why the window opens half an hour ahead.

**Closing out happens one session at a time.** When a session is over the organizer ends it and
marks each volunteer attended or no-show. Ending one session of a shift does not touch that shift's
other sessions and does not settle the commitment — the volunteer is still expected back. Ending
the last session anyone was still expected at marks the whole event completed. Ending an event in
one press closes out every session still open, applying the same answer to each; where the days
really did differ, close them out individually instead.

**Volunteer hours come from the sessions actually attended**, not from the size of the commitment.
A volunteer who booked a two-session shift and attended one of them is credited for the one.

A shift is also the finest unit a **broadcast** can target. A broadcast reaches the volunteers on
the event who are confirmed, checked in, or attended; pending, waitlisted, no-show, and cancelled
signups are skipped. An organizer can narrow it to a single shift — which reaches everyone
committed to that shift, on all of its sessions — or to a single orientation slot. That picker only
appears when the event has two or more bookable units.

For SciTrek in practice: volunteers meet at **Chem 1204 fifteen minutes before a module session
starts**, and orientation is held in **Chem 1005D** unless the slot says otherwise.
