# What the app does not do

This document exists so that questions about missing features get an honest "no" instead of a
plausible invention.

**There is no SMS or text messaging.** The database has a phone number field and an SMS opt-in flag
reserved for future work, but nothing sends text messages. All notifications are email.

**There is no CSV import of events.** That admin surface was removed. Events are created manually,
or by duplicating an existing event. Module templates still exist, but their job now is defining
module families for orientation credit and holding default signup forms — not importing schedules.
Any documentation that describes a quarterly CSV module import is out of date.

**There is no single sign-on.** OIDC/SAML sign-in exists in the code but is not configured, so staff
sign in with an email and password. Volunteers don't sign in at all.

**There are no portals.** An earlier feature for grouping events into public tabs is no longer
reachable in the app.

**Volunteers have no accounts, no passwords, and no dashboard.** Everything a volunteer does after
signing up goes through a magic link emailed to them, or the QR code at the door. There is nothing
for a volunteer to log into.

**There is no per-user timezone.** Everything is Pacific Time, matching the single venue.

**There is no per-person undo of attendance.** Cancelled is final, full stop. Attended and no-show
can be reversed, but only by **reopening the whole event** — there is no way to walk back one
individual's status, and no way to reopen a single slot. A mis-tapped check-in *can* be undone per
person, but only before close-out.

**There is no way to revoke orientation credit by reopening an event.** Credit is permanent by
design; corrections go through Admin → Orientation Credits.

**Calendar entries don't sync.** A volunteer can add a session to their calendar, but if the session
later moves, their calendar entry won't update. Use a broadcast to tell them.

**Quarters are never guessed.** The app ships with no quarters and derives nothing from an assumed
11-week calendar. Until an admin enters a quarter, quarter-dependent features are blocked rather
than estimated.

**Nothing is seeded.** No sample quarters, events, modules, or volunteers.
