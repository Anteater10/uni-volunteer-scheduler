# How do I…? — task guides

## How do I set up a new quarter?

Enter the quarter **before** you create any events for it. Go to Overview → "Manage quarters", add
the season, year, an optional session label (used for Summer Session A and B), and the start and
end dates from the UCSB academic calendar. The form previews how many weeks that gives you and when
week 1 starts. Saving links any existing events whose dates fall inside it and tells you how many
were linked or moved weeks.

## How do I create an event?

Go to Admin → Events and create it. The event needs a **module** and **dates that fall inside an
entered quarter** — if no quarter covers those dates the save is refused and you'll need to enter the
quarter first. School is optional. Then add the slots: one per session, each with its own date, time,
location, and capacity.

If a similar event already exists, **duplicating it is much faster** — see the next guide.

## How do I duplicate an event?

**Duplicate** sits on each row of the Admin → Events list (organizers can use it there too), and
**Duplicate…** sits in the header of an event's own page for admins. Either one opens the same
window.

**A duplicate is a prefilled create form, not a one-click copy.** Pick the **target quarter** and
**target week** at the top, and everything below — title, description, location, school, visibility,
the per-volunteer cap, the module, and every slot with its type, times, room and capacity — arrives
already filled in from the original, fully editable. Adjust whatever needs adjusting and press
**Create event**. That's the point of the redesign: rooms and times rarely carry over unchanged, and
you get to fix them before the event exists rather than after.

A few things worth knowing:

- **Dates shift by whole days**, keeping the weekday and the time of day. Week 3 of one quarter
  becomes week 3 of another, on the same weekday, at the same hour.
- **Changing the target quarter or week discards your edits** and re-fills the form from the original.
  Pick where it's going first, then edit.
- If that week already has an event for the same module you'll see a **"Heads up"** note. It's advice,
  not a block — sometimes two really is what you want.
- The target list only offers quarters that are still open — neither archived nor past their end
  date — because creating an event inside a closed quarter is refused by the server. You can still
  duplicate *from* an event in a finished or archived quarter, which is the usual way last year's
  schedule gets rebuilt.
- **The title comes across verbatim**, with no "(copy)" added. Rename it in the form if two
  identically-named events would confuse people.
- **Nothing about people comes across** — no signups, no waitlist, no check-ins, no attendance. The
  new event's venue code is generated fresh the first time someone opens its roster.

Saving takes you straight to the new event's page.

## How do I check volunteers in on the day?

Open Admin → Operations → Today, open the event that's running, and work from the roster. On a phone
— which is the usual device at a school — organizers get a **Today** button in the bottom bar that
goes to the same schedule and the same roster without the desktop-only admin shell in the way. Tap
each volunteer as they arrive. **Staff taps aren't time-limited** — you can check people in early, late, or
the next morning if the day got away from you. A volunteer who never clicked their confirmation link
can still be tapped in; the tap confirms them on the way through.

For self check-in, show the event's QR code with the **Check-in QR** button on the **event page**
(Admin → Events → the event), and volunteers enter their email and tap the shift they're there for.
The roster screen shows the numeric venue code but not the QR. **Self check-in is the path with the
time window:** it opens 30 minutes before a session starts and closes 30 minutes after.

## How do I close out a session once it's over?

**End the session from the roster screen** — each slot group has its own **End slot** button (**End
orientation** for orientation slots), and **End event** at the top does the whole thing at once. The
close-out screen lists everyone not yet resolved, pre-filled from check-in state: checked-in
volunteers are pre-marked attended, everyone else no-show. Adjust anyone who needs it and save.

It's all-or-nothing per session — you have to decide every row before Save turns on. **Do not skip
this** — hours, attendance reports, and orientation credit all depend on it.

Once every session is ended, the event shows as complete on the roster and in the Events list.
Attendance isn't permanent after all: see the next guide.

## How do I fix a wrong no-show or a mis-tapped check-in?

If you only checked someone in by mistake, tap them again on the roster to undo it — they go back to
confirmed.

If the session has already been closed out, use **Reopen event**. It appears in the "Event complete"
banner on the roster screen and in the completed strip on the event page. Reopening puts **everyone**
on the event back on the live roster — real check-ins keep their timestamps and return to checked-in,
and anyone marked no-show goes back to confirmed — so you can re-tap and end the session again with
the right outcome. There's no way to unresolve one person on their own.

Three caveats. Reopening is only offered once the whole event reads as complete, so if some session is
still showing as open you'll need to finish closing it out first. **Reopening stops being possible
once the event's quarter has ended or been archived** — closed history stays closed, so fix a wrong
outcome during the quarter rather than after it. And **reopening does not take back orientation
credit** — credit is permanent by design and may well have been earned before this event. Correct
credit in Admin → Orientation Credits.

## How do I give someone orientation credit?

Two ways. **From the event page:** open the event in Admin → Events, find them in its roster table,
and use **Grant orientation** on their row — this is the "I vouch for them" case. Note this is the
event page's table, not the phone-friendly roster screen used at the door, which has no such button.
**From the admin page:** go to Admin → Orientation Credits and grant credit for their email and the
module family. The quarter picker there is optional and is only recorded for reference; credit never
expires either way.

Normally you shouldn't need to do either: ending an orientation slot grants credit automatically to
everyone marked attended.

## How do I promote someone off the waitlist?

You always need to — the waitlist never moves on its own. Cancelling a confirmed volunteer, raising a
session's capacity, and the hourly cleanup all free seats, but none of them promote anyone; the seat
just sits open until a staff member acts.

Open the event in Admin → Events and click **Promote** on the row of the person you want in the event
page's roster table — usually the longest-waiting person, though you can promote anyone waiting.
Since the slot is normally still full, this asks you to confirm going over capacity — that's a real
decision about a real room, so it's deliberate rather than automatic.

**A promotion is an offer, not a seat.** The volunteer is moved to **pending** and emailed a link with
**3 days** to confirm. Their seat is held while they decide, and they show on the roster the whole
time. If they don't confirm, the signup is removed and the seat is freed again — it doesn't pass to
anyone automatically, so promote the next person by hand if the seat should be filled. So a promoted
volunteer who hasn't clicked yet is expected to look half-finished on the roster; that's the flow
working, not a fault.

## How do I email everyone coming to a session?

Use **Message volunteers** on the event page. Leave the picker on **All slots** to email the
whole event, or pick one slot to email just that session's volunteers. The preview shows the
recipient count before you send. Confirmed, checked-in, and attended volunteers receive it;
waitlisted and cancelled people don't. You can send 5 broadcasts per event per clock hour — the count
resets at the top of the hour rather than an hour after your first send.

## How do I invite a new organizer or admin?

Admin → Users → **"Invite user"**. Enter their name, email, and role. They get an email with a link
where they set their own password and are signed straight in — you never handle their password. The
invite link lasts **7 days**; if it lapses, re-invite them.

## How do I change my password, or reset one I've forgotten?

Signed in: open your Settings page and change it there — the form asks for your current password,
and changing it signs out any other sessions. Locked out: use **"Forgot password" on the login
page**, which emails a reset link (valid for one hour) if the address belongs to active staff. If
you never set a password because your invite lapsed, ask an admin to re-invite you — the invite
link is where the password gets set.

**Reset and invite links are single-use.** Setting a password stops every outstanding link for that
account from working, the one just used included, so always use the newest email and request a fresh
link rather than digging out an older one.

## How do I deactivate someone who has left?

Admin → Users, open their drawer, click Deactivate. They can't sign in any more but their history
and their events stay intact. Use "Show deactivated" to find them later and Reactivate if needed.

## How do I export a report?

Admin → Exports (admin only). **Each report panel has its own time-range picker** — set the range on
the panel you want, then use its Download CSV button. Everything is generated live. Only "This
quarter" and "Custom range" actually filter; the two buttons showing raw labels next to them are
unfinished and return all-time data. For a whole-quarter summary instead, use Admin → Quarters →
View events on that quarter.

## How do I handle a CCPA data request?

Admin → Users, find their row. "CCPA Data Export" downloads everything held on them. "CCPA Delete
Account" permanently anonymizes their data — it asks you to type a confirmation first. Both are
logged.

Note that Admin → Users lists **staff accounts only**. A volunteer who has never been a staff member
doesn't appear there, and there is no equivalent one-click tool for a volunteer record.

## How do I archive a finished quarter?

You usually don't have to — **a nightly sweep archives any quarter whose end date has passed**. It
runs at 03:30 UTC, which is early evening Pacific, so a quarter that ended today is normally archived
the same evening rather than literally overnight. Don't treat the sweep as the deadline for editing,
though: a quarter turns read-only as soon as its end date is past, which is late afternoon Pacific on
its last day — hours before the sweep runs. To archive one immediately, use Archive on its row
in Admin → Quarters (allowed once the quarter has ended). An archived quarter still appears in the
list, stays reachable by link, and volunteers can still browse it under "Archived quarters" — it's
just skipped when working out what week it currently is. Restore undoes it, but an ended quarter will
be re-archived by the next nightly sweep unless its dates change.

## How do I change what questions volunteers answer when signing up?

For one event, open the form-fields drawer on the event page. For every future event of a module,
use **Edit form fields** on the module in Admin → Modules — note that button only appears once the
module has been saved, so a brand-new module needs creating first and editing second. An event's own
form always wins over the module default. Changing a form does not alter answers already submitted.
