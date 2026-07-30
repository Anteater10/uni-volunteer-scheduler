# Venue codes and the check-in QR

Every event gets a **venue code**: a four-digit code the app generates for that event. It exists so
that door check-in can be quick for the people who are actually there and useless to anyone who
isn't.

**The code is created the first time staff open the event's roster or its check-in QR.** It isn't
assigned when the event is created — it appears on first use, and both the roster and the QR dialog
create it, because the QR dialog reads the roster to find the code. In practice that means the code
exists by the time anyone could scan a QR for the event. It also means a brand-new event has no code
yet, which matters only for a hand-typed link (see the last paragraph).

**Once a code exists, it never changes.** There is no rotate or reset control anywhere in the app,
so a code that has been printed, photographed, or shared stays valid for the life of the event.
Treat a venue code as "good enough to stop a remote stranger", not as a secret you can revoke.

**A copy of an event gets its own code.** Duplicating an event does not carry the original's venue
code across, so the copy starts without one and generates a fresh one on first use — the original's
printed QR will not work for the copy, and vice versa.

**The QR code carries the venue code for you.** Show it from the event detail page: Admin → Events
→ the event → **Check-in QR**. The link it encodes includes the code, so a volunteer who scans it
types nothing but their email address. The roster screen does not have a QR button, though it does
display the four digits on a card, so you can read the code off the roster if someone needs to type
it.

**Every public check-in request must present the correct venue code** — looking up a volunteer's
shifts, checking in a chosen shift, and checking in by email all require it. Without this, anyone
who guessed a volunteer's email address could read back their full name and their whole schedule,
and check them in remotely.

**The code is checked before the email is looked up.** That ordering matters: it means a wrong code
fails identically whether the email exists or not, so the check-in page can't be used to find out
which volunteers are signed up for an event.

**An event with no generated venue code cannot be checked into through the public QR flow.** That
request fails rather than being waved through. A missing code should never become an open door.

**Check-in requests are rate-limited** — roughly thirty attempts a minute from the public and double
that for signed-in staff. The count is per network connection, so a whole classroom on one shared
Wi-Fi shares that allowance and a busy door can bump into it. Combined with the four-digit code,
this is what makes guessing impractical.

**Old printed or bookmarked QR links stopped working** when venue codes were introduced, because
those links carry no code. A volunteer who opens one is told the link is missing its check-in code
and asked to scan the current QR — the message says to ask the organizer to re-show it "from the
roster screen", which is out of date: it is on the event detail page. Re-show the QR from there and
use the new one. It's worth reprinting anything laminated.

**There is also an older per-volunteer check-in page**, reached only by a direct link to one
person's signup, which asks the volunteer to type the four digits by hand. Nothing in the app sends
that link any more — the event QR replaced it — but the code is still required to check in through
it.
