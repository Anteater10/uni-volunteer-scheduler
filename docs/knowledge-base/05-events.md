# Events

An **event** in the SciTrek scheduler is one module taught at one school during one week of a
quarter. The event is the container; the actual bookable sessions inside it are **slots**. An
event carries a title, description, location, the module it delivers, the school, its quarter and
week number, and the staff member who owns it.

Events are **created manually** by an organizer or admin in Admin → Events. There is no CSV import
of events — that surface was removed. To build a term's schedule you either create each event or,
much faster, duplicate an existing one.

**Every event must fall inside an entered quarter.** If the event's dates are not covered by any
quarter an admin has entered, creating or saving it is rejected with "No quarter covers {date} —
add it in Admin → Quarters first." The event's quarter, year, and week number are then derived
from the quarter it links to, rather than typed in by hand.

An event controls **when signups are allowed** through its signup-open and signup-close times.
Public signups outside that window are rejected with a message naming the window in Pacific Time.
An event can also cap **how many slots one volunteer may take** within it.

Events have a **visibility** setting. Public events appear on the volunteer browse page at
`/volunteer`. Staff always see all events regardless of visibility, and the site setting
"hide past events from public" controls whether events whose last slot has ended stay visible to
volunteers.

**Duplicating an event** is the normal way to build out a term. The duplicate drawer lists sibling
events in the same quarter and module so you can see which weeks are already covered and avoid
double-booking, and it targets real quarter rows with their real week counts — including summer
sessions individually.

Each event has its own **signup form**. By default the form comes from the module's default
fields, but an event can override it with its own field list. Edit it from the form-fields
drawer on the event page. Volunteers' answers are stored per field against their signup.

Each event has a **venue code**, a four-digit code used by the door check-in QR link. The QR
carries it as `?v=CODE`. An event with no generated code cannot be checked into through the public
QR flow — that failure is deliberate, so a missing code never becomes an open door.

**Organizers can only act on events they own.** Roster reads, check-in, undo, and resolve all
verify ownership, so one organizer cannot read or alter another organizer's event. Admins can act
on any event.

Everything about an event can be reconfigured after creation — title, location, dates, and its
slots — from the event page itself, without going back to the events list.
