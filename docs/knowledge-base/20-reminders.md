# Reminders

The app sends volunteers three kinds of **reminder email** about sessions they're signed up for.
You can see what's queued on the **Reminders** tab of the Operations console, grouped by kind with
a count for each.

- **Kickoff** — sent Monday at 07:00 Pacific, for sessions happening that week.
- **24h before** — sent 24 hours before the session starts.
- **2h before** — sent 2 hours before the session starts.

Reminders are sent by a background job that wakes up regularly, and the timing has a **15-minute
tolerance** built in so a slightly late run still sends rather than skipping.

**Quiet hours are respected**: reminders aren't sent between 21:00 and 07:00 Pacific. All times in
the reminder system are Pacific Time, matching the single venue.

**Reminders are opt-out.** Every volunteer gets them by default, and a volunteer can turn them off
for their email address without logging in. Nothing about that setting requires staff involvement.

**A volunteer never gets the same reminder twice.** The system records each reminder it sends for
each signup, and that record is what prevents duplicates — so a retried job or a double-fired
schedule can't produce a second copy.

**Broadcasts ignore reminder preferences.** A broadcast is an operational instruction about a
session someone is coming to ("we've moved to Lot 22"), not promotional email, so it goes to the
roster regardless of the reminder opt-out. See the broadcasts document.

Reminders are about **slots**, not events, so a volunteer signed up for three sessions gets
reminders for each of them.
