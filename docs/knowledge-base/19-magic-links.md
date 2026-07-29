# Magic links and volunteer self-service

Volunteers have no account, so every action they take after signing up is authorized by a **magic
link** — a one-time link emailed to them.

When a volunteer signs up, the app emails them a link. The success screen they see in the browser
deliberately doesn't show the link or a token: it goes to their inbox, which is what proves the
email address is theirs.

With their magic link a volunteer can **confirm** the signup, **view** what they're signed up for,
**cancel** a signup, and **swap** to a different slot. They can also add the session to their
calendar from the confirmation page.

**Magic links expire and are single-use.** A manage or cancel link lasts about **15 minutes** from
when it's requested; the initial **confirmation link is the exception — it lasts two weeks**,
matching how long an unconfirmed signup is held before it lapses. Each link is consumed when used,
so a link that leaks later is worthless. Requesting new links is rate-limited per email address, so
the endpoint can't be used to spam someone.

**A volunteer who loses their email can be sent another link.** Staff can resend it from the admin
side, and there's a resend path for volunteers too.

**A magic link cannot be used to get around the orientation requirement.** The requirement is
enforced when the signup is created, not when it's confirmed, so confirming a link never smuggles
in a signup that wouldn't have been allowed in the first place.

**Cancelling through a magic link behaves exactly like staff cancelling.** The seat is freed and the
longest-waiting volunteer on that slot is promoted to confirmed automatically.

Volunteers also manage their **reminder preferences** by email address without logging in.
Reminders are on by default and can be turned off. Broadcasts ignore that preference, because
broadcasts are operational instructions rather than promotional email.

Separately from magic links, volunteers check in at the door by scanning the event's **QR code**,
which carries the event's venue code. That flow is described in the check-in and venue-code
documents.
