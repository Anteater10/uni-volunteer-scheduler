# Rosters

The **roster** is the live check-in list for an event, and it's where organizers do most of their
day-of work. Open an event from Operations or from Admin → Events, then open its roster.

Roster rows are **grouped by slot**, and each slot header names the kind of session (orientation or
module), its times, and where it is — so a multi-day event reads as separate sessions rather than one
long list. **The header does not show the weekday or the date**, only clock times, so on an event
that runs across several days two sessions at the same hour look alike; the sections are in
chronological order, so use their order to tell the days apart. The event detail page's version of
the same list does label the day, if that's what you need.

**Each slot header also carries that session's progress** — "2 / 7 checked in", where the second
number is how many volunteers the session expects. Once the session has been ended the header swaps
to its outcome instead, "5 attended · 2 no show", and shows an **Ended** tag.

**A roster row shows the volunteer's name, their shift time, and a status chip — nothing else.**
Their answers to the event's signup form are not on the roster. Those appear under each volunteer's
name on the **event detail page**, so if there's something you need at the door, plan to have that
page open rather than expecting the roster to carry it.

**Rows are alphabetical within each slot and stay put as people check in.** The order deliberately
doesn't depend on status or on when someone was tapped, because a list that reshuffles under your
thumb during check-in is how you tap the wrong person.

**The cards at the top of the page count expected attendees.** "Total signups" is the whole event's
count of people it expects — pending, confirmed, checked in, and already resolved — and deliberately
excludes waitlisted and cancelled signups so they can't inflate the check-in progress bar. Those rows
are still listed, with their own status chips; they're just not part of the total. Beside it sit a
checked-in count, a waitlist count, and the event's four-digit venue code.

**Opening the roster is what creates the event's venue code** if the event doesn't have one yet.
It is the only thing in the app that generates one, which is why the check-in QR dialog also loads
the roster behind the scenes.

**Staff always see full names on the roster.** The public event page shows each volunteer as a
first name and last initial, but the staff-side roster deliberately shows the full name: initials
make check-in at the door harder without making anything safer.

**The roster refreshes itself every few seconds** while you have it in front of you, so a volunteer
who self-checks-in by scanning the QR appears as checked in without anyone reloading the page.

**Once every session is ended the roster shows an "Event complete" summary** with the attended and
no-show totals, a note when orientation credit was granted, and a **Reopen event** button for the
case where a session was closed out too early. See the document on ending a slot for what reopening
does.

**From the roster you can:**

- **Check a volunteer in**, and **undo** a mis-tap by tapping the same row again.
- **End a slot** (or an orientation, or the whole event), marking people attended or no-show.
- **Send a broadcast** to everyone on the event — or, on an event with more than one session, to just
  one slot's volunteers.
- **Add a question** to the event's signup form, for something you realised you needed to ask.

**From the event detail page — not the roster — you can:**

- **Show the check-in QR** for the door.
- **Promote someone off the waitlist**, including deliberately over capacity.
- **Cancel a signup**, which frees the seat but does not promote anyone — the seat just stays open
  until a staff member deliberately promotes someone off the waitlist.
- **Grant orientation credit** to one volunteer directly — the "vouched for at the door" case.
- **Reorder the waitlist** — admins only, and only on a slot with at least two people waiting.
- **Download the roster as a CSV.**

**Promoting someone off the waitlist always goes through pending, never straight to confirmed.**
Whether an organizer promotes the longest-waiting person or reaches further down the list, the
volunteer is moved to **pending** and emailed a link to confirm the spot, which holds their seat for
three days. They are on the roster the whole time, but as pending rather than confirmed — and a
pending row cannot be closed out, so tap them in if they turn up before they've clicked. The waitlist
document covers the rest of that flow.

**Granting orientation credit by hand is done per volunteer from the event detail page**, and
organizers can do it. What organizers cannot reach is **Admin → Orientation Credits**, the admin-only
page that lists every credit and is the only place a credit can be revoked. The ordinary path to
credit is neither of these: mark the volunteer attended when ending the orientation slot.

There is a **mobile-responsive roster page** for use at the classroom door. The rest of the admin
side is desktop-only, but this page works properly on a phone because that's where it's used. On a
phone, reach it through the **Today** page in the staff menu, which lists today's sessions and
links straight to each roster.

**Any organizer or admin can open any event's roster.** The roster is staff-only — it carries names
and the venue code — but it is not restricted to whoever created the event: the staff event list is
shared and nothing in the app can transfer an event to another organizer, so an owner-only rule would
have locked organizers out of events they were actually running.
