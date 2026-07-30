# Rosters

The **roster** is the list of volunteers signed up for an event, and it's where organizers do most
of their work. Open an event from Operations or from Admin → Events to reach it.

Roster rows are **grouped by slot**, and each slot header names the weekday and date, the kind of
session, its times, and where it is — so a multi-day event reads as separate sessions rather than
one long list. Statuses are shown so they're readable at a glance rather than as another run of
grey text.

**Staff always see full names on the roster.** There is a privacy setting for how names appear on
the public event page, but the staff-side roster is deliberately exempt: initials make check-in at
the door harder without making anything safer.

Each volunteer's **answers to the event's signup form** appear on their roster row, so anything you
need at the door should be a form field rather than something collected by email.

From the roster an organizer can:

- **Check a volunteer in**, and **undo** a mis-tap.
- **End a slot** or the whole event, marking people attended or no-show.
- **Grant orientation credit** with one tap — the "vouched for at the door" case.
- **Promote someone off the waitlist**, including deliberately over capacity. The person you promote
  goes to **pending** and gets the same 3-day confirm email as an automatic promotion.
- **Cancel a signup**, which frees the seat and auto-promotes the next person waiting — to pending,
  with their own 3-day confirm link.
- **Reopen an event** that has been closed out, if attendance was recorded wrongly.
- **Send a broadcast** to everyone on the event, or to just one slot's volunteers.
- **Show the check-in QR code** for the door.
- **Reorder the waitlist** (admins).

There is a **mobile-responsive roster page** for use at the classroom door. The rest of the admin
side is desktop-only, but this page works properly on a phone because that's where it's used.

**Any organizer can open any event's roster.** Access is checked by role, not by who created the
event: every admin and every organizer can read a roster, its attendance summary, its check-in
screen and its venue code. Only volunteers and the public are refused.

This is deliberate. Organizers are a trusted staff role and the staff event list is global — every
organizer already sees every event in the list. An ownership rule meant an organizer could open an
event, read its details fine, and then hit a 403 on its roster. Nothing in the product could hand
ownership over either, so an organizer could only ever run events they had personally created. The
boundary that actually matters is the set of **admin-only** routes: user management, audit logs,
quarter configuration, and exports.

Every event still records who created it, and roster actions are written to the audit log with the
staff member who took them, so shared access does not mean anonymous access.
