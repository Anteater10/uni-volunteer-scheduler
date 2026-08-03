# Volunteers and identity

A **volunteer** (also called a participant) is a UCSB student who mentors in SciTrek classrooms.
Volunteers have **no account, no password, and no login page**. A volunteer is identified entirely
by their **email address**.

This is deliberate. Volunteers are high-churn and mostly sign up once or twice, so forcing account
creation cost far more signups than it was worth. Instead, a volunteer record is created or
matched by email the first time they sign up, and every action afterward is authorized by a
link emailed to them or by scanning the QR code at the classroom door.

Because **email is the identity**, it's also the join key for everything that stands apart from the
volunteer record — most importantly orientation credit and reminder preferences, both keyed by email
rather than by the record. A volunteer who signs up with a different email address is, as far as the
app is concerned, a different person: they won't see their orientation credit or their existing
signups.

A volunteer record holds their email, their name, and a phone number. The phone column allows
blanks, but in practice every volunteer has one, because signing up is the only way a record gets
created and the signup form requires it. It must be a valid **US number** — an international number
is rejected outright — and it's stored in a single normalized format regardless of how it was typed.
There is no SMS in the app today; the phone number and the SMS opt-in are reserved for future work
and nothing sends text messages.

**The most recent signup's spelling wins.** Signing up doesn't just match an existing record — it
overwrites the first name, last name, and phone number on it. So a volunteer who types their name
differently the second time has effectively renamed themselves on every past signup too. Email is
the only field that stays put.

**A volunteer record cannot be deleted.** There's no delete action anywhere in the app, and the
database refuses it while any signup row exists — including cancelled ones, since cancelling leaves
the row in place. Cancelling someone's signups does not unlock a deletion. This is protective on
purpose: attendance history is the source of truth for volunteer hours and orientation credit, and
deleting a volunteer outright would silently destroy it.

Volunteers control their own **reminder preferences** by email address, from the same link that
manages their signups. Reminders are opt-out — everyone gets them by default — and the toggle turns
off the tracked kickoff, 24-hour, and 2-hour reminders. It does **not** stop the older 24-hour and
1-hour reminder emails or the weekly digest, so a volunteer who opts out will still see some mail —
see the reminders document. Broadcasts ignore the setting by design too, because broadcasts are
operational instructions rather than promotional email.

One rough edge worth knowing: unlike the rest of the manage page, the reminder toggle stops loading
once the link's confirmation window has passed — the card shows an error while viewing signups on the
same page still works. There is no staff-side version of this setting, so the only way back to
the toggle is a newer link, which the volunteer gets the next time they sign up for something.

**Names are shown one way each side.** Staff see **full names** on rosters, because initials make
check-in at the door harder rather than safer. The public event page always shows first name plus
last initial, for everyone holding or past a seat; people on the waitlist aren't listed there at
all. Neither is configurable — there's no setting that changes how names are displayed.
