# Troubleshooting — what the errors and oddities mean

## "New volunteers must include an orientation session in their signup"

The volunteer has no orientation credit for this module's family, so they must add the event's
orientation session to the same signup. Either they add it themselves, or a staff member grants them
credit (**Grant orientation** on their row in the event page's roster table, or Admin → Orientation
Credits). If they *have* done orientation but the app disagrees, see "credit is missing" below.

**The requirement is narrower than it looks.** It only bites when someone is signing up for a
teaching session and hasn't included an orientation in the same submission. Signing up for an
orientation on its own always passes, and so does any signup for an event that offers no orientation
slot at all — on those events the requirement is advisory only, because there is nothing on the event
that would satisfy it.

## "A signup covers one event at a time"

The submission touched slots from two different events. The normal event page never does this, so
this usually means an odd link or a stale tab. Sign up for one event at a time.

## "No quarter covers {date} — add it in Admin → Quarters first"

You're creating or editing an event with dates that fall outside every quarter an admin has entered
— often the gap between terms, or a term nobody has entered yet. Enter the quarter first, then save
the event. There's no way to create an uncategorized event.

## Someone did orientation but has no credit

The orientation slot was almost certainly **never ended**. Checking people in does not grant
orientation credit — closing out the slot does. End the slot (attendance can still be marked at that
point), or grant the credit manually.

The other possibility is a **module family mismatch**: the orientation credited a different family
than the module checks against. Confirm the event's module slug still matches a live module, and
that the two modules involved actually share a family key — credit earned in one family never
counts for another.

## The waitlist promote button says the slot is full

That's expected — the slot being full is the whole reason anyone is waitlisted, and automatic
promotion already claims any seat that frees up. To promote this specific person you have to
deliberately confirm going **over capacity**.

## A promoted volunteer says they're in, but the roster shows them as pending

This is the promotion flow working, not a fault. A promotion — automatic or manual — moves the
volunteer to **pending** and emails them a link with **3 days** to confirm. The seat is held for them
the whole time and they appear on the roster, but the status stays pending until they click. If they
tell you they're coming and you'd rather not wait, just **tap them in at the door** — a staff check-in
confirms them on the way through.

If they don't confirm in time, the signup is removed and the seat is offered to the next person on the
waitlist — as long as the session hasn't happened yet. A seat freed after the session is over is
simply released, with nobody promoted into it, because a "confirm your spot" email for a finished
session would only cause confusion. Nothing tells the person who lapsed, and their signup disappears
rather than showing as cancelled, so "I got an email saying a spot opened up and now I can't find it"
means the 3 days ran out. They can sign up again if a seat is free.

## A volunteer says the confirm link didn't confirm anything

The app shows a **"Nothing to confirm"** page with a reason, and the three reasons need different
answers. *"You're on the waitlist for this slot — we'll email you if a spot opens up."* means they
were never promoted: their session was full when they signed up, nothing is wrong, and there is no
email to hunt for. *"This link didn't confirm a seat. Your spot came from a waitlist promotion — use
the confirm link in that email instead."* means they clicked their original signup email when the seat
they hold came from a promotion; the promotion email is the one with the working button, and if they
can't find it, tapping them in at the door confirms them anyway. *"There's nothing to confirm — this
signup has already been resolved."* means staff already checked them in or closed the session out.

Clicking a link that was already used still reports the signup as confirmed rather than failing, so
"it says confirmed" on a second click is not a fault either.

## An event stays "Ended — not closed out" after every session was ended

Look for a **pending** volunteer on the roster. An event only counts as complete when nobody is still
expected, and a pending signup counts as expected — but the close-out screen only lists confirmed and
checked-in people, so there's no way to mark that row attended or no-show. Ending the slot again just
opens a close-out screen with nobody on it.

Three ways out: **tap the pending volunteer in** before ending the session (that confirms them, and
then they appear on the close-out screen normally), **cancel their signup** if they aren't coming, or
leave it — once their confirmation link lapses the automatic sweep removes the signup, and the event
completes on its own.

## The signup page says signups are closed

The event has a signup window and it has closed, or hasn't opened yet. The message names the window
in Pacific Time. **There's no field for that window in the event form**, so there's nothing to adjust
from the UI — most events have no window at all, and one that does got it programmatically or carried
it over from the event it was duplicated from.

## A volunteer's check-in link or QR doesn't work

Three likely causes. **The window:** self check-in only opens 30 minutes before a session starts and
closes 30 minutes after it starts. (Staff taps have no window — if the volunteer is standing there,
just tap them in.)
**A missing venue code:** old printed or bookmarked QR links from before venue codes don't carry
`?v=` and no longer work — re-show the QR with the **Check-in QR** button on the event page. **An
event with no generated venue code** fails closed on purpose; opening its roster generates one, and
then the QR from the event page works.

## "Wrong venue code"

The scanned or typed code doesn't match the event. Re-show the QR from the **Check-in QR** button on
the event page rather than reusing an old printout — the roster screen shows the numeric code but not
the QR. The code is checked before anything else, so this error tells you nothing about whether the
email is signed up — that's intentional.

## Broadcast says wait / rate limited

You've hit 5 broadcasts in a clock hour for that event. The limit is per event even if you're
targeting individual slots, and the bucket is a fixed hour on the clock rather than a rolling window
— so the count resets at the top of the hour, not an hour after the first send. Wait, then send.

## The copilot says "Stream failed: HTTP 429"

Two different ceilings produce that, and the message doesn't say which. **Your own pace:** each
person can send 10 messages a minute; wait a minute and carry on. **The shared daily allowance:** the
copilot has an installation-wide budget for the day, and once it's used up nobody can chat until the
next day. Because it's shared, one person working the copilot hard can use up the day for everyone —
so if a minute's wait doesn't help and colleagues see the same thing, that's what happened.

## Something can't be deleted

Three deletions are deliberately blocked. **A staff user who still owns events** — reassign or delete
those events first; their signups are never the reason. **A slot that still has signups** — cancel or
move them first, because signups are the record behind hours and orientation credit. **Anything
inside a quarter that has ended or been archived** — its events, their sessions, and their custom
signup questions are read-only history, and the refusal reads "*[quarter name]* has ended and is
read-only." There is no override; if the dates were genuinely wrong, fix the quarter's dates so the
event falls inside an open one.

Volunteers themselves have no delete button at all — Admin → Users lists staff accounts only, so a
volunteer never appears there. The CCPA export and delete actions on that page act on a **staff**
account: delete anonymizes the staff record and leaves the attendance history in place. There is no
equivalent one-click erase for a volunteer record.

## Reports show fewer hours or lower attendance than expected

Sessions that were never closed out leave volunteers at confirmed or checked-in rather than attended.
**Five of the eight Exports reports count only resolved attendance** and will read low because of it:
Volunteer hours, Attendance rates, No-show rates, Hours by school, and Unique volunteers per quarter.
Look for sessions with no close-out. **Event fill rate, Cancellation rates and Module popularity
count held seats instead**, so a missing close-out is never the explanation for those three — don't
go hunting for one.

The quarter retrospective counts checked-in people as attended, which is why it and the Exports
reports can disagree.

## A volunteer says they can't see their signups or their orientation credit

Almost always a **different email address**. Identity is the email, so a signup made with a personal
address and a check made with a university address look like two different people. Have them use the
address they originally signed up with.

## The admin pages say they're desktop-only

They are, below 768px — rosters and event forms need the room. **The exception is the day-of check-in
pair:** a phone-sized "Today" schedule and the roster screen it links to both live outside the admin
area on purpose, because day-of check-in is a phone job. Organizers get a **Today** button in the
bottom bar on a phone that goes straight there.

Two things trip people up. The same roster also has an address inside the admin area, and that copy
*is* desktop-gated — so a roster that refuses to open on a phone means an admin link was followed
rather than the Today one. And **an admin signed in on a phone gets a bottom bar of admin
destinations, all of which are desktop-only** — there's no Today button for them. On a phone, an
admin's practical options are to get the link from an organizer, bookmark the Today page, or use a
laptop or tablet.

## No quarters are entered

The public page says "Schedule coming soon" and admins are sent to the quarters setup page. Enter
the current quarter and the app comes to life. Nothing is seeded by default, on purpose.

## The Audit Logs tab isn't there

It's hidden by default. Turn on **Show Audit Logs tab** from the site settings card on the Overview
page.

## A staff member can't sign in

If they've forgotten their password, the **"Forgot password" link on the login page** emails them a
reset link that lasts one hour — it only works for active staff, so a deactivated account has to be
reactivated first. If they were recently invited and the link no longer works, the invite lasted
7 days and has lapsed: re-invite them from Admin → Users. The invite link is also where the password
gets set, so someone who never used theirs has no password to reset.

**Reset and invite links are single-use.** Setting a password kills every outstanding link for that
account, including the one just used — a second click is refused with "This link has already been
used or is no longer valid." If someone asked for two resets, only the newest email works, and
anyone who has already set a password needs a fresh link rather than an older email.

## A volunteer's signup disappeared

If it was never confirmed, it expired. A signup sits at **pending** until the volunteer clicks their
link: **two weeks** for a fresh signup, **3 days** for one that came from a waitlist promotion. A
sweep runs **every hour** and removes pending signups whose links have all lapsed, freeing the seat
and offering it to the next person on the waitlist. This is the one case where a signup vanishes
rather than showing as cancelled, and nothing emails the volunteer to say so. They can sign up
again — the deletion leaves nothing behind to block it — as long as the event's signup window, if it
has one, is still open. There is no staff-side way to add a signup for them by hand.
