# Overview — what this app does

The SciTrek volunteer scheduler is the web app UCSB SciTrek uses to schedule university
volunteers into K-12 classroom sessions. Volunteers browse a week's sessions, pick the ones they
want, and sign up without creating an account. Staff create the sessions, manage who is coming,
check people in at the door, and report on hours and attendance afterward.

There are three kinds of people in the SciTrek scheduler. **Volunteers** (also called
participants) are UCSB students who mentor in classrooms; they have no account and no password.
**Organizers** are staff who run events and rosters. **Admins** are staff with organizer powers
plus user management, settings, exports, and audit logs.

The core objects in the SciTrek scheduler are quarters, events, slots, and signups. A **quarter**
is an academic quarter an admin has entered by hand. An **event** is one module at one school in
one week of that quarter. A **slot** is one bookable session inside that event — a specific date
and time with a capacity. A **signup** is one volunteer holding one slot.

Volunteers sign up **session by session**, not for a whole module. A volunteer may take as many
sessions of a module as they want, or just one. Slots are the bookable unit, so "I'll take
Wednesday only" is completely normal.

Before a volunteer can sign up for a module's regular sessions, they must have **orientation
credit** for that module's family — and if they don't, they must include an orientation session in
the same signup. This is a hard requirement enforced by the server, not a warning. See the
orientation document for the cases that pass automatically.

Volunteers never log in. Every action a volunteer takes after signing up — confirming, viewing,
cancelling, swapping, checking in — happens through a **magic link** emailed to them, or through a
QR code scanned at the door. Staff, by contrast, do log in with an email and password at `/login`.

The staff side of the SciTrek scheduler lives under `/admin` and is built for desktop screens.
Below tablet width every page inside the admin shell shows a desktop-only banner instead of the
page itself. The one staff surface that works on a phone is the **organizer roster** at
`/organizer/events/{id}/roster`, which is deliberately mounted outside the admin shell because
day-of check-in is a phone job done at a classroom door. The same roster reached through
`/admin/events/{id}/roster` sits behind the desktop-only banner like everything else in the shell,
so the `/organizer/...` link is the one to send someone who is out at a school.
