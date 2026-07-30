# Events

An **event** in the SciTrek scheduler is one module taught at one school during one week of a
quarter. The event is the container; the actual bookable sessions inside it are **slots**. An
event carries a title, description, location, the module it delivers, the school, its quarter and
week number, and the staff member who created it.

Events are **created manually** by an organizer or admin in Admin → Events. There is no CSV import
of events — that surface was removed. To build a term's schedule you either create each event or,
much faster, duplicate an existing one.

**Every event must name a live module.** Creating or saving an event without a module slug is
rejected, and so is a slug that doesn't match a module currently in Admin → Modules. The module is
what scopes orientation credit, so an event with no module would have no orientation family to check
against. If a module you need isn't in the list, create it there first.

**Every event must fall inside an entered quarter.** If the event's dates are not covered by any
quarter an admin has entered, creating or saving it is rejected with "No quarter covers {date} —
add it in Admin → Quarters first". The event's quarter, year, and week number are then derived
from the quarter it links to, rather than typed in by hand.

An event can carry **signup-open and signup-close times**, and when they're set, public signups
outside them are refused with a message naming the boundary that was hit — "Signup opens at …" or
"Signup closed at …" — in Pacific Time. But no screen sets those times: the event form has no field
for them, so a window only gets onto an event programmatically or by being carried over when the
event was duplicated from one that had it. Most events have no window at all, which means signups
stay open until the event happens.
There is also a **max signups per volunteer** field on the event form, but **nothing enforces it
today** — it is stored and displayed, and no signup is ever refused because of it. A volunteer can
take every slot in an event regardless of what that field says. If a cap actually matters for an
event, the practical lever is capacity per slot.

**An event's visibility setting is enforced on every public surface.** The check allows exactly one
value — **public** — and it is applied in every place the public can reach an event: the
volunteer browse listing, the event page, the signup form, the anonymous slot reads behind them,
and the act of signing up itself. Anything
that is not public is skipped by the browse listing, answers "not found" on both its event page and
its signup form, and has a signup attempt refused as not found as well — the same answer a session
that doesn't exist would give.

**"Not public" covers more than an event set to Private.** Because the rule allows only the value
"public", an event whose visibility was never recorded at all is hidden everywhere too, rather than
being treated as public. An event created in the event form always has a value — the form offers
**Public** or **Private** and starts on Public — but an event that arrived some other way, such as
data loaded in from outside the app, can have none. That case shows as a dash rather than a value in
the Visibility row on the event's own page, which is the thing to check first if an event you expect
volunteers to see is missing from the browse page and its link returns "not found".

Two other controls narrow public exposure independently of visibility: the signup window (which
blocks signups outside it) and the site setting "hide past events from public" (which drops events
whose last slot has ended).

**Duplicating an event is the normal way to build out a term, and it is a prefilled create form
rather than a batch copy.** Reach it from the **Duplicate** button on a row in Admin → Events, or
from **Duplicate…** in the header of an event's own page. Pick a target quarter and target week, and
the ordinary event form opens underneath, prefilled from the original: same title (no "(copy)"
suffix — rename it yourself if you want one), description, location, school, module, and slots, with
every date shifted by the whole number of days between the source week and the target week. Times of
day and day-of-week are preserved. Everything is editable before you press **Create event** — which
is the point, because rooms, days, and times are exactly what changes between quarters, and the old
flow copied them blind across a whole batch of weeks. Changing the target quarter or week re-derives
the suggested dates and discards edits made so far, so choose where the copy lands before filling
anything in.

A few things about duplication worth knowing:

- It creates **one** event and then takes you to it. Copying a module into eight weeks means running
  it eight times, each time with a chance to fix the room.
- Organizers can duplicate from the events list; the button on an event's own page is shown to
  admins only.
- The source can be in a **past or archived quarter** — duplicating last term's event into this term
  is the intended use.
- If the target week already has an event for the same module you get a **heads-up note**, not a
  block. A second copy is sometimes legitimate, and the form is right there for you to judge.
- Nothing about attendance comes along: no signups, no waitlist, no check-ins, and the new event
  starts empty. Its **venue code is new too** — the copy does not inherit the original's door code.

Each event has a **signup form**. If the event has its own field list, that wins; otherwise
volunteers see the module's current default fields. Edit it from the form-fields drawer on the event
page. See the signup-forms document — the fallback is live rather than copied, which matters when
you edit a module default.

Each event has a **venue code**, a four-digit code used by the door check-in QR link. The QR carries
it as `?v=CODE`. A code is generated the first time an event's roster is opened, so a new or
duplicated event gets its own without anyone doing anything. An event with no code yet cannot be
checked into through the public QR flow — that failure is deliberate, so a missing code never
becomes an open door.

**Any organizer or admin can act on any event.** The staff gate is role-based, not
ownership-based: rosters, check-in, undo, and resolve all admit any organizer. The event records
who created it, but that is a record, not a permission — there is no way to transfer it and nothing
checks it. The boundary that actually matters is the set of admin-only surfaces: users, audit logs,
quarters, exports, and orientation credits. See the roles-and-access document.

**An event becomes "completed" on its own once nothing is left to close out.** There is no Complete
button. When an organizer ends the last session anyone was still expected at, the app stamps the
event as completed, badges it "✓ Completed" in the events list, and files it under Past events even
if its dates are still in the future. An event with no signups at all never completes, and an event
whose dates went by without anyone closing out attendance is badged "Ended — not closed out"
instead, which is the flag to look for when chasing missing attendance.

**Completing is reversible.** A completed event shows a green strip on its admin page and a banner
on the organizer roster, each with a **Reopen event** button available to organizers and admins.
Reopening puts the attended and no-show volunteers back on the live roster and clears the completed
stamp, so the event returns to Upcoming if its dates are still ahead. Orientation credits already
granted are deliberately **not** revoked — credit is permanent per volunteer and module family and
may well predate this event, so corrections go through Admin → Orientation Credits instead.
Reopening is refused once the event's quarter has ended or been archived, so a wrong outcome has to
be corrected while the term is still open.

**The events list is scoped to one quarter and shows everything in it by default.** The quarter
selection is shared with the Overview page (see the quarters document), and within it the time
filter starts on "All" rather than "Upcoming" — the quarter is the scope, narrowing to upcoming or
past is opt-in. Rows are always sorted by start date, whatever their status. With an ended quarter
selected the page turns into history: no "+ New event" button, an amber strip naming when the
quarter ended, and the time filter switches to "All events / Completed / Not closed out" so you can
chase whatever was never closed out.

**Events in an ended quarter are read-only.** Editing or deleting one is refused by the server with
"*[quarter name]* has ended and is read-only" — it is genuinely blocked rather than just hidden in
the UI, and there is no override. Duplicating still works, because the copy lands in a current
quarter rather than the closed one. Closing out attendance still works too, so a session nobody ever
finished can always be finished; the document on ending a slot covers that boundary. This starts the
moment the quarter's end date is past, which is late afternoon Pacific on the last day itself —
around 5pm in summer, 4pm in winter, because the cutoff is worked out in UTC. Archiving the quarter
has the same effect but happens later that night, so the date alone is what closes the door.

Everything about an event can be reconfigured after creation — title, location, dates, and its
slots — from the event page itself, without going back to the events list.
