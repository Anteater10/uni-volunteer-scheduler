# Glossary — every term in one place

**Admin** — a staff member with full access: everything an organizer can do, plus user management,
site settings, exports, audit logs, orientation credits, and quarters.

**Archived quarter** — a quarter past its end date, shown with an **Archived** chip. Quarters archive
themselves overnight once they end (around 3:30am the following night), and an admin can also archive
one by hand. An archived quarter becomes read-only history; **Restore** puts it back.

**Attended** — a signup status meaning the volunteer was present and the organizer has closed out
the session. Attended is final in normal use, but reversible for a whole event via **Reopen event**.

**Broadcast** — a one-off operational email sent to everyone on an event's roster, or to just one
slot's roster. Used for things like "parking moved to Lot 22."

**Completed event** — an event whose every slot has been ended, so all attendance is resolved. Shown
as **✓ Completed**, and filterable in the events list. Reversible with **Reopen event**.

**Cancelled** — a signup status meaning the volunteer gave up the spot, or staff cancelled it.
Cancelling a signup that holds a seat — confirmed or pending — frees it and automatically promotes
the next person off the waitlist, to pending, with a confirm link valid for 3 days. Cancelled is
final.

**Check-in** — marking a volunteer as present at the door. Check-in happens per slot, inside a
window of 30 minutes before the slot starts to 30 minutes after. Check-in by itself does not grant
orientation credit.

**Checked in** — a signup status meaning the volunteer has arrived but the session has not been
closed out yet. An organizer can undo a check-in back to confirmed if they tapped the wrong row.

**Confirmed** — a signup status meaning the volunteer holds the spot. This is the normal state
between signing up and showing up.

**Event** — one module taught at one school during one week of a quarter. An event owns slots and
carries the module reference, school, week number, and quarter.

**Family key** — the grouping key that ties related modules together for orientation purposes, so
an intro module and an advanced module can share one orientation. Stored on the module template as
`family_key`.

**Magic link** — the link emailed to a volunteer that lets them confirm, view, cancel, or swap a
signup without an account or password. The *confirm* click is one-shot and has a deadline (14 days,
or 3 days for a waitlist promotion); the same link then keeps working as their manage page, with no
expiry of its own, until it is cleaned up about 30 days after their last session.

**Module** — a five-session science experience delivered to a class. In the app a module is
represented by a module template, and each real-world delivery of it is an event.

**Module family** — a set of modules that share one orientation requirement, grouped by family key.
Orientation credit is earned and checked per module family, never per module.

**Module template** — the reusable definition of a module: slug, name, type, default capacity,
duration, session count, materials, default form fields, and family key. Templates define module
families and default signup forms. They are not used to import events.

**No-show** — a signup status meaning the volunteer did not turn up and the organizer closed out
the session. No-show is final.

**Operations console** — the `/admin/operations` page, the day-of staff view. Four tabs: Today,
Upcoming, Past, and Reminders.

**Organizer** — a staff member who creates and runs events: rosters, check-in, broadcasts,
module templates, orientation grants at the door.

**Orientation credit** — a permanent record that a volunteer has been oriented for one module
family. Once earned it never expires, in any quarter or year. Only an explicit credit row grants
it.

**Participant** — another word for volunteer. Both mean a UCSB student mentoring in a classroom.

**Pending** — a signup status meaning the volunteer holds the seat but has not clicked their confirm
link yet. Pending occupies capacity, so a slot can read as full while showing pending people. It
always carries a deadline: 14 days for someone who signed up for a free seat, 3 days for someone
promoted off the waitlist. If the deadline lapses, an hourly job deletes the signup and offers the
seat onward.

**Quarter** — an academic quarter an admin has entered by hand: season, year, an optional session
label, and start and end dates. Weeks are numbered from the start date. Nothing is guessed or
seeded.

**Quarter retrospective** — the admin-only report of how a past quarter ran: which events
happened, and per-event signups, capacity, attended, and no-show counts.

**Resolve** (also "ending a slot") — the organizer action that closes out a session, marking each
volunteer attended or no-show. Ending an **orientation** slot is what actually grants orientation
credit.

**Roster** — the list of volunteers signed up for an event or a slot, used at the door for
check-in. Staff always see full names on the roster.

**Signup** — one volunteer holding one slot. Once confirmed, a signup is never deleted; it carries a
status instead. A signup that was never confirmed is deleted outright if its confirm deadline lapses.

**Slot** — one bookable session inside an event: a date, a start and end time, a location, a
capacity, and a type (orientation or period). Slots are what volunteers actually sign up for.

**Venue code** — a four-digit code tied to an event, carried in the check-in QR link as `?v=CODE`.
Required on every public check-in request so a stranger with a guessed email cannot read or alter
someone's schedule.

**Viewing quarter** — the quarter the admin Overview and Events list are currently scoped to, shown
as a **Viewing** pill. Set it with **View this quarter** on Manage Quarters; the choice is remembered
between visits. Choose **All quarters** to stop scoping.

**Volunteer** — a UCSB student who mentors in classrooms. Identified only by email address; no
account, no password.

**Waitlisted** — a signup status meaning the slot was full when the volunteer signed up. When a
seat frees up the longest-waiting person is promoted automatically — to pending, and emailed a
confirm link valid for 3 days. They are not moved straight into the seat as confirmed.

**Week number** — which week of its quarter an event falls in, counted from the quarter's start
date. Week 1 begins on the quarter's start date.
