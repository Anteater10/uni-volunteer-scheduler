# Reminders

The app emails volunteers **reminders** about sessions they're signed up for. You can see what's
queued on the **Reminders** tab of the Operations console — both organizers and admins can open it —
grouped into three sections with a count for each.

**Reminders only go to confirmed signups.** A volunteer still waiting to click their confirmation
link, and a volunteer sitting on a waitlist, receive no reminders at all. That includes someone who
has just been offered a spot off the waitlist: until they confirm, the reminder emails skip them.

**Three of the reminders are the ones staff can see and hand-send.** These are what the Reminders tab
lists:

- **Kickoff** — Monday at 07:00 Pacific of the week the session falls in. A Thursday session gets
  its kickoff that same Monday morning.
- **24 hours before** — roughly a day before the session starts, subject line "Tomorrow: …".
- **2 hours before** — roughly two hours before the session starts.

These three are sent by a background job that wakes every 15 minutes, with a **15-minute tolerance**
built into each window so a slightly late run still sends rather than skipping.

**An older pair of reminder emails also still goes out, on top of those.** They predate the three
above and were never switched off:

- an older **24-hour** email, subject line "Reminder: volunteer slot for …", which in practice means
  a volunteer receives two day-before emails for the same session;
- an older **1-hour** email, sent shortly before every session. Each event carries an on/off flag
  for it, but the flag defaults to on and no screen exposes it, so in practice it is always on.

Neither of the older pair — nor the weekly digest below — appears on the Reminders tab, which
previews only the three tracked kinds.

Each individual reminder email is recorded against the signup once it's sent, so a retried or
double-fired background run never repeats that same email. The two day-before emails are recorded
separately from each other, though, which is why both arrive. The safe thing to tell a volunteer is
which emails exist and when, rather than that they'll get exactly one nudge per stage.

**Quiet hours apply to the three tracked reminders only.** Kickoff, 24-hour and 2-hour sends are
held back between 21:00 and 07:00 Pacific so a reminder doesn't arrive in the middle of the night.
The older 24-hour and 1-hour reminder emails and the weekly digest do not observe quiet hours.

**Turning reminders off stops the three tracked reminders.** Every volunteer gets reminders by
default, and a volunteer can turn them off for their email address from their manage page without
logging in or involving staff. That setting is honoured by the kickoff, 24-hour and 2-hour emails.
It is **not** honoured by the older 24-hour and 1-hour emails or by the weekly digest, so a
volunteer who opts out will still see some mail. If someone asks to stop receiving everything, say
so plainly rather than promising silence.

One caution about finding that switch: the unsubscribe link printed in the reminder emails
themselves doesn't work — it points at the manage page without the volunteer's token, so the page
refuses to load, and the formatted version of the email carries no link at all. The working switch
is on the manage page opened from the link in the **signup confirmation email**.

**Volunteers also get a weekly digest.** Every Monday at 08:00 UTC — about 1:00 AM Pacific, which is
inside the quiet-hours window and nowhere near the 07:00 kickoff — the app emails each volunteer a
plain list of the confirmed sessions they have in the next seven days. It's a heads-up summary,
separate from the per-session kickoff, 24-hour and 2-hour reminders.

**Staff can hand-send a reminder outside its window.** Each row on the Reminders tab has a **Send
now** action, available to organizers as well as admins, for the case where something urgent needs
saying and the scheduled moment has passed. Send now deliberately ignores quiet hours — that is the
point of it — but it still respects a volunteer's opt-out and still won't send the same reminder
twice. Every use is written to the audit log.

**There is a daily ceiling on reminder and broadcast email.** Signup confirmations,
waitlist-promotion offers and the weekly digest bypass it and aren't counted toward it. Once the
day's ceiling is reached, reminder and broadcast sends are dropped
silently rather than queued. If reminders simply stopped arriving partway through a busy day, this is
the first thing to check.

Reminders are about **slots**, not events, so a volunteer signed up for three sessions gets
reminders for each of them.

**Broadcasts ignore reminder preferences.** A broadcast is an operational instruction about a
session someone is coming to ("we've moved to Lot 22"), not promotional email, so it goes to the
roster regardless of the reminder opt-out. See the broadcasts document.
