# What the app does not do

This document exists so that questions about missing features get an honest "no" instead of a
plausible invention.

**There is no SMS or text messaging.** The database has a phone number field and an SMS opt-in flag
reserved for future work, but nothing sends text messages. All notifications are email.

**There is no CSV import of events.** That admin surface was removed. Events are created manually,
or by duplicating an existing event. Modules still exist as the reusable definitions behind events,
but their job is defining module families for orientation credit and holding default signup forms —
not importing schedules. Any documentation that describes a quarterly CSV module import is out of
date.

**There is no single sign-on.** OIDC/SAML sign-in exists in the code but is not configured, so staff
sign in with an email and password. Volunteers don't sign in at all.

**There are no portals.** An earlier feature grouped events into curated public tabs at their own
links. It has been removed outright — no page, no menu entry, no stored data, nothing left behind.
The word still turns up in old notes and old planning documents; there is nothing in the app it
refers to any more.

**Volunteers have no accounts, no passwords, and no dashboard.** Everything a volunteer does after
signing up goes through a magic link emailed to them, or the QR code at the door. There is nothing
for a volunteer to log into.

**There is no volunteer self-service cancel or swap.** The link in a volunteer's email is read-only:
it lets them confirm, view their signups, and manage reminder preferences, nothing more. A volunteer
cannot cancel or move a signup themselves. To change or cancel anything, they email the SciTrek
organizers (the address configured in Site settings), and an organizer applies the change. The
waitlist works the same way — cancels, capacity raises, and the hourly cleanup free seats but promote
nobody; only a staff promotion moves a volunteer off the waitlist.

**There is no per-user timezone.** Every time a volunteer or a staff member sees is Pacific,
matching the single venue, and nobody can choose a different one.

**Cancelling cannot be undone.** Once a signup is cancelled it stays cancelled — the volunteer signs
up again if slots are still open. Attendance is different: closing out an event is reversible with
**Reopen event**, which puts attended and no-show volunteers back on the live roster, for as long as
the event's quarter is still open. The document on ending a slot covers what reopening restores and
what it deliberately leaves alone.

**There is no message centre inside the app.** Notifications reach volunteers and staff by email;
there is no inbox in the app to check. A Notifications screen does exist at a URL, but it appears in
no menu, nothing links to it, and nothing writes to it any more — so it is always empty. Treat it as
unfinished rather than as a place to send anyone.

**There is no per-event "notify participants" button.** Mass email to the volunteers on an event goes
out as a **broadcast**, and that is the only working path. A second, unfinished one survives in the
plumbing with no page and no button anywhere, and it errors out rather than completing — so if
someone remembers being told an event page could email its own participants directly, the answer to
give them is the broadcast.

**Nothing tells a volunteer that a waitlist offer expired.** A promotion holds the seat for three
days; if the volunteer doesn't confirm in time, the seat is freed and the volunteer's own signup is
removed outright — no email explains it, no trace of it is left in their manage view, and the seat
does not move to anyone automatically. A staff member has to promote someone else off the waitlist by
hand. This is the honest answer to "why did this volunteer's signup disappear?" Promotions themselves
are *not* silent: a staff promotion off the waitlist always emails a confirmation link. The waitlist
document covers that flow.

**Calendar entries don't sync.** A volunteer can add sessions to their calendar from the app or from
the file attached to their confirmation email, but both produce a fixed entry. If the session later
moves, nothing updates what's already in their calendar. Use a broadcast to tell them.

**Quarters are never guessed.** The app ships with no quarters and derives nothing from an assumed
11-week calendar. Until an admin enters a quarter, quarter-dependent features are blocked rather
than estimated.

**No program data is seeded.** No sample quarters, events, modules, or volunteers. The only account
that exists after setup is the first admin, created from the email and password chosen at install
time.
