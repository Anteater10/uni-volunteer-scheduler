# Venue codes and the check-in QR

Every event has a **venue code**: a four-digit code the app generates for that event. It exists so
that door check-in can be quick for the people who are actually there and useless to anyone who
isn't.

**The QR code carries the venue code for you.** Show the event's QR from the roster screen; the
link it encodes includes the code as `?v=CODE`. A volunteer who scans it types nothing but their
email address.

**Every public check-in request must present the correct venue code** — looking up a volunteer's
shifts, checking in a chosen shift, and checking in by email all require it. Without this, anyone
who guessed a volunteer's email address could read back their full name and their whole schedule,
and check them in remotely.

**The code is checked before the email is looked up.** That ordering matters: it means a wrong code
fails identically whether the email exists or not, so the check-in page can't be used to find out
which volunteers are signed up for an event.

**An event with no generated venue code cannot be checked into through the public QR flow.** That
request fails rather than being waved through. A missing code should never become an open door.

**Check-in requests are rate-limited** — a modest number per minute from the public and a higher
allowance for signed-in staff. Combined with the four-digit code, this is what makes guessing
impractical.

**Old printed or bookmarked QR links stopped working** when venue codes were introduced, because
those links have no `?v=` on them. If a saved link fails, re-show the QR from the roster screen and
use the new one. It's worth reprinting anything laminated.
