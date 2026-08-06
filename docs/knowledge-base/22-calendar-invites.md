# Calendar invites

Volunteers can put the sessions they've signed up for onto their own calendar. There are three ways
that happens, and they cover different amounts of the schedule.

**The confirmation email carries a calendar file for every session at once.** Attached to the signup
confirmation email is a file called `scitrek-sessions.ics` holding one entry per session the
volunteer actually booked. Opening the attachment adds the whole commitment to Google Calendar,
Apple Calendar or Outlook in one action — there is no web link that can carry more than one event, so
the attachment is the only route that does all of them together. The email points it out in a line
just under the list of sessions. Waitlisted sessions are left out of the file, and an all-waitlisted
signup gets no attachment at all — so nothing in that email mentions a calendar.

**The signup success screen offers per-session buttons.** Right after signing up, each booked session
in the list gets its own **Google Calendar** button, which opens a pre-filled Google Calendar page in
a new tab for that one session. When only one session was booked, a single full-width **Add to Google
Calendar** button appears instead. Below the list, **Download .ics (Apple / Outlook)** saves one file
covering every booked session. A footnote points at the emailed attachment for people who'd rather do
it in one go.

**A waitlisted session shows a waitlist badge instead of a calendar button**, and it stays out of the
downloaded file too. It isn't on the volunteer's schedule yet, so putting it on their calendar would
be misleading. If every session was waitlisted, the calendar controls don't appear at all.

**The event page itself also offers calendar buttons, to anyone viewing it.** Below an event's
details on the public browse side sit an **Add to Google Calendar** button and a **Download .ics**
button. They aren't tied to any signup: they export whichever sessions are ticked in the signup form
at that moment, and with nothing ticked they fall back to the event's orientation session or its
first session. Handy for a volunteer who wants a session on their calendar before or after signing
up — but it exports what's ticked, not what they booked.

**The magic-link pages carry no calendar buttons.** The confirmation page a volunteer reaches from
their emailed link shows the confirmation banner and their manage list, and neither offers a
calendar control. A volunteer who dismissed the success screen and wants everything they booked on
their calendar in one go has to use the file attached to their confirmation email, or re-tick their
sessions on the event page and download from there.

There is one calendar entry **per session** — a volunteer who booked a three-session shift gets
three entries, each with its own date, start and end time, and location. Where a session doesn't
carry its own location, the entry falls back to the event's location and then to the school. Entries
are titled with the event name, orientation sessions are labelled as such so they're easy to tell
from classroom sessions, and the description carries the event's description plus a link back to its
page. Sessions show up as busy time rather than free.

**Only the original signup confirmation email carries the attachment.** The email a volunteer gets
when a spot opens up for them off the waitlist has no calendar file — it is a "confirm this spot"
message, and until they confirm there is nothing to put on a calendar. There is no second attachment
after they confirm, and the manage page has no calendar control of its own, so a volunteer promoted
off the waitlist has no way to get a calendar entry from the app for that session. If they ask, the
honest answer is to add it by hand from the details on their manage page.

**Times are written as absolute instants in UTC**, which is the standard form every calendar client
converts into whatever timezone the viewer is actually in. So a volunteer whose phone is set to
Eastern time still sees the session at the correct hour. This replaced an older approach that wrote
bare local times, which came out wrong whenever the device that made the file disagreed with the
device reading it.

**Adding the same session twice does not create a duplicate.** Each entry carries an identifier that
is stable for that event and session, and the emailed file and the in-app download use the same
identifiers — so a volunteer who opens the attachment *and* uses the download ends up with each
session exactly once, updated rather than doubled.

**The downloaded file sets two pop-up alarms; the emailed file does not.** The `.ics` a volunteer
downloads from the success screen asks their device to remind them the day before and an hour before.
Those pop-ups come from their own calendar app, not from SciTrek — a useful thing to know when
someone asks why they got a reminder at an odd time or why turning off SciTrek reminder emails didn't
stop them. The file attached to the confirmation email carries no alarms.

Calendar entries are **generated on request** from the state of the signup at that moment. There's no
sync: if a session is later moved, an already-added calendar entry does not update itself. Tell
volunteers about changes with a **broadcast**.
