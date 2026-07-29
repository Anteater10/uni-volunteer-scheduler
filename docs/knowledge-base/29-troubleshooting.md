# Troubleshooting — what the errors and oddities mean

## "New volunteers must include an orientation session in their signup"

The volunteer has no orientation credit for this module's family, and the event offers an
orientation slot, so they must add it. This is a hard rule with no bypass. Either they add the
orientation session to the same signup, or a staff member grants them credit (one tap on the roster,
or Admin → Orientation Credits). If they *have* done orientation but the app disagrees, see "credit
is missing" below.

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

## "Slots now full" when a volunteer submits

Someone else took the last seat between the volunteer loading the page and submitting. The page
returns them to the schedule with the current availability so they can pick again.

## The signup page says signups are closed

The event's signup window has closed, or hasn't opened yet. The message names the window in Pacific
Time. Adjust the signup open and close times on the event if that's wrong.

## A volunteer's check-in link or QR doesn't work

Three likely causes. **The window:** check-in only opens 30 minutes before a session and closes 30
minutes after. **A missing venue code:** old printed or bookmarked QR links from before venue codes
don't carry `?v=` and no longer work — re-show the QR from the roster screen. **An event with no
generated venue code** fails closed on purpose; the QR from the roster screen is the fix.

## "Wrong venue code"

The scanned or typed code doesn't match the event. Re-show the QR from the roster screen rather than
reusing an old printout. The code is checked before anything else, so this error tells you nothing
about whether the email is signed up — that's intentional.

## Broadcast says wait / rate limited

You've hit 5 broadcasts in an hour for that event. The limit is per event even if you're targeting
individual slots. Wait, then send.

## A volunteer can't be deleted

They have signups. That block is deliberate: signups are the record behind their hours and
orientation credit. Cancel their signups first if you genuinely need to remove them.

## Reports show fewer hours or lower attendance than expected

Sessions that were never closed out leave volunteers at confirmed or checked-in rather than
attended, and the Exports reports only count resolved attendance. Look for sessions with no
close-out. The quarter retrospective counts checked-in people as attended, which is why the two can
disagree.

## A volunteer says they can't see their signups or their orientation credit

Almost always a **different email address**. Identity is the email, so a signup made with a personal
address and a check made with a university address look like two different people. Have them use the
address they originally signed up with.

## The admin pages say they're desktop-only

They are, below tablet width — rosters and event forms need the room. The exception is the roster
page, which works properly on a phone because that's where it's used at the door.

## No quarters are entered

The public page says "Schedule coming soon" and admins are sent to the quarters setup page. Enter
the current quarter and the app comes to life. Nothing is seeded by default, on purpose.

## The Audit Logs tab isn't there

It's hidden by default. Turn on "show audit logs tab" from the settings card on the Overview page.

## A staff member can't sign in

If they've forgotten their password, the **"Forgot password" link on the login page** emails them a
reset link that lasts one hour — it only works for active staff, so a deactivated account has to be
reactivated first. If they were recently invited and the link no longer works, the invite lasted
7 days and has lapsed: re-invite them from Admin → Users. The invite link is also where the password
gets set, so someone who never used theirs has no password to reset.

## A volunteer's signup disappeared

If it was never confirmed, it expired. A new signup sits at **pending** until the volunteer clicks
the confirmation link, and that link lasts two weeks — a signup still pending after that is removed
automatically overnight and its seat is freed. This is the one case where a signup vanishes rather
than showing as cancelled. The volunteer can simply sign up again.
