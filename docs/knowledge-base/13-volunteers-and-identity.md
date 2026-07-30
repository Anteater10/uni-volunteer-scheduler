# Volunteers and identity

A **volunteer** (also called a participant) is a UCSB student who mentors in SciTrek classrooms.
Volunteers have **no account, no password, and no login page**. A volunteer is identified entirely
by their **email address**.

This is deliberate. Volunteers are high-churn and mostly sign up once or twice, so forcing account
creation cost far more signups than it was worth. Instead, a volunteer record is created or
matched by email the first time they sign up, and every action afterward is authorized by a
one-time link emailed to them or by scanning the QR code at the classroom door.

Because **email is the identity**, it's also the join key for everything that has to outlive a
volunteer record — most importantly orientation credit, which is keyed by email and module family
so it survives even if the volunteer record is removed and recreated later. A volunteer who signs
up with a different email address is, as far as the app is concerned, a different person: they
won't see their orientation credit or their existing signups.

A volunteer record holds their email, their name, and optionally a phone number. Phone numbers are
normalized to a standard format on the way in. There is no SMS in the app today — the phone field
and the SMS opt-in are reserved for future work and nothing sends text messages.

**A volunteer with signups cannot be deleted.** The link between them is protective on purpose:
attendance history is the source of truth for volunteer hours and orientation credit, so deleting
a volunteer outright would silently destroy that record. To remove someone, their signups have to
be cancelled first.

Volunteers control their own **reminder preferences** by email address. Reminders are opt-out —
everyone gets them by default — and a volunteer can turn them off. Broadcasts ignore this setting,
because broadcasts are operational instructions rather than promotional email.

Staff always see **full names** on the roster. There is a privacy setting that governs how names
appear on the public event page, but the staff-side roster shows full names because initials make
check-in at the door harder rather than safer.
