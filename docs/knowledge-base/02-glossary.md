# Glossary — every term in one place

**Admin** — a staff member with full access: everything an organizer can do, plus user management,
site settings, exports, audit logs, orientation credits, and quarters.

**Attended** — a signup status meaning the volunteer was present and the organizer has closed out
the session. It is settled: no per-volunteer action changes it, and the only way back is **Reopen
event**, which undoes the whole event at once and only works while the event's quarter is still open.

**Broadcast** — a one-off operational email sent to the volunteers on an event, or on just one of
its shifts or orientation slots. It reaches people holding or past a confirmed spot — confirmed,
checked in, attended — and skips pending, waitlisted, no-show, and cancelled signups. Used for
things like "parking moved to Lot 22."

**Cancelled** — a signup status meaning staff cancelled it, at the volunteer's request by email or on
their own. A volunteer cannot cancel a signup themselves. Cancelling a signup that was holding a seat
frees it, but nobody is promoted off the waitlist automatically — a staff member has to do that
separately. Cancelled is final. The volunteer is emailed a cancellation notice either way.

**Check-in** — marking a volunteer as present at the door. Check-in happens per session (or per
orientation slot), inside a window of 30 minutes before it starts to 30 minutes after. Someone
holding a two-session shift is checked in twice, once on each day. Check-in by itself does not
grant orientation credit.

**Checked in** — a signup status meaning the volunteer has arrived but the session has not been
closed out yet. An organizer can undo a check-in back to confirmed if they tapped the wrong row.

**Commitment** — one volunteer holding one shift. Because a shift is booked all or nothing, a
commitment covers every session in that shift; attendance is still recorded per session, so a
commitment can be attended on one day and no-show on the next. Cancelling, promoting, and
waitlisting all act on the commitment, never on a single day of it.

**Completed event** — an event where every volunteer who was still expected has been marked
attended or no-show, so there is nothing left to close out. The app stamps the finish time on the
event, files it under Past events, and badges it "✓ Completed". An event with no signups at all
never becomes completed. See the events document.

**Confirmed** — a signup status meaning the volunteer holds the spot. This is the normal state
between signing up and showing up.

**Event** — one module taught at one school during one week of a quarter. An event owns its
orientation slots and its shifts, and carries the module reference, school, week number, and
quarter.

**Family key** — the grouping key that ties related modules together for orientation purposes, so
an intro module and an advanced module can share one orientation. Stored on the module; a new
module's family key starts out as its own slug.

**Magic link** — a link emailed to a volunteer that lets them confirm and view a signup, and manage
reminder preferences, without an account or password. It does not let them cancel or move a signup —
for that they email the SciTrek organizers and a staff member makes the change. Confirming is the
one-time part, and it has a deadline; the same link keeps working for viewing afterward, for any
session the volunteer is still due at. A seat won from a **waitlist promotion** carries a second,
separate confirm link in its own email, and only that one can claim it. See the magic-links document.

**Module** — a multi-session science experience delivered to a class. SciTrek modules usually run
five sessions, but the app stores a session count per module rather than assuming a number. In the
app a module is the reusable definition — slug, name, default capacity, duration, session count,
materials, default form fields, and family key — managed in Admin → Modules, and each real-world
delivery of it is an event. Every event must name a live module; modules also define module
families and default signup forms. They are not used to import events. (Older notes sometimes say
"module template" for the same thing.)

**Module family** — a set of modules that share one orientation requirement, grouped by family key.
Orientation credit is earned and checked per module family, never per module.

**No-show** — a signup status meaning the volunteer did not turn up and the organizer closed out
the session. Like attended, it is settled once saved; only **Reopen event** undoes it, and only while
the event's quarter is still open.

**Operations console** — the `/admin/operations` page, the day-of staff view. Four tabs: Today,
Upcoming, Past, and Reminders.

**Organizer** — a staff member who creates and runs events: rosters, check-in, broadcasts,
modules, orientation grants at the door.

**Orientation credit** — a permanent record that a volunteer has been oriented for one module
family. Once earned it never expires, in any quarter or year. Only an explicit credit record grants
it — attendance alone never implies it.

**Participant** — another word for volunteer. Both mean a UCSB student mentoring in a classroom.

**Pending** — a signup status meaning the signup exists but the volunteer has not clicked their
confirmation link yet. A pending signup holds its seat. A volunteer who signed up themselves has two
weeks to confirm; a volunteer promoted off a waitlist has three days. Once every confirmation link
on a pending signup has lapsed, an hourly sweep removes the signup outright and frees the seat.

**Quarter** — an academic quarter an admin has entered by hand: season, year, an optional session
label, and start and end dates. Weeks are numbered from the start date. Nothing is guessed or
seeded.

**Quarter retrospective** — the admin-only report of how a past quarter ran: which events
happened, and per-event signups, capacity, attended, and no-show counts.

**Reopen** — the supervised undo of ending an event. Organizers and admins get a "Reopen event"
button on a completed event, which puts its attended and no-show volunteers back on the live roster
and clears the event's completed stamp. Orientation credits already granted are deliberately left
alone. Reopening is refused once the event's quarter has ended or been archived, so it is an undo
that expires with the term.

**Resolve** (also "ending a slot") — the organizer action that closes out one session or one
orientation slot, marking each volunteer attended or no-show. Ending one session of a shift leaves
that shift's other sessions open and does not settle the commitment. Ending an **orientation** slot
is what actually grants orientation credit. Ending the last session anyone was still expected at
also marks the whole event completed.

**Roster** — the list of volunteers signed up for an event, used at the door for check-in and
grouped one section per session or orientation slot. A volunteer holding a multi-session shift
appears once under each of its sessions. Staff always see full names on the roster.

**Session** — one classroom meeting inside a shift: a date, a start and end time, an optional room,
and an optional name like "Period 1". A session is not bookable on its own and has no capacity of
its own — the seat is for the whole shift. Check-in and attendance happen per session.

**Shift** — a named bundle of one or more sessions, and the thing a volunteer actually books for
classroom work. A shift carries the capacity and the waitlist, and signing up for it is all or
nothing: one press commits the volunteer to every session in it. A shift never grants orientation
credit.

**Signup** — one volunteer holding one orientation slot, or (as a commitment) one shift. A signup
normally carries a status rather than being deleted, so cancelling or a no-show leaves a record.
The one exception is a pending signup nobody ever confirmed: the hourly expiry sweep deletes it
outright, and it disappears from the volunteer's manage page along with it.

**Slot** — a bookable unit with a date, a start and end time, a location, and a type. An
**orientation** slot is booked directly and carries its own capacity. A **period** slot is a
session inside a shift and is never booked on its own.

**Venue code** — a four-digit code tied to an event, carried in the check-in QR link as `?v=CODE`.
Required on every public check-in request so a stranger with a guessed email cannot read or alter
someone's schedule.

**Volunteer** — a UCSB student who mentors in classrooms. Identified only by email address; no
account, no password.

**Waitlisted** — a signup status meaning the shift or orientation slot was full when the volunteer
signed up. A shift's waitlist is one queue for the whole bundle, not one per session. The waitlist
never moves on its own: a freed seat stays open until an admin or organizer deliberately promotes
someone, which moves them to **pending** and emails them a link to confirm within three days. A
waitlisted signup does not hold a seat.

**Week number** — which week of its quarter an event falls in, counted from the quarter's start
date. Week 1 begins on the quarter's start date.
