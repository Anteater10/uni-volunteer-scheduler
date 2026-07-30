# Waitlist and promotion

When a slot is full, further signups for it become **waitlisted** rather than rejected. The
volunteer has still given their details and consented; they're simply in line. Their position is
shown to them, counting from 1.

**The waitlist is first-come, first-served.** Order is by when the signup was created, and that
ordering drives the position a volunteer sees, automatic promotion, and the waitlist panel on the
event page. The organizer's check-in roster is the exception: it's sorted alphabetically within
each session and shows no waitlist positions at all, because at the door you're looking someone up
by name rather than working down a queue.

## Promotion offers the seat — it doesn't hand it over

**A promoted volunteer goes to pending, not straight to confirmed.** They get an email with a link
and have **three days** to click it and claim the spot. Until they do, the signup sits at pending.

**The promotion email carries its own confirm link, and only that link can claim the seat.** The link
from their original signup email will not do it: clicking that one reports that it confirmed nothing
and tells them to use the confirm link in the promotion email instead. That is deliberate — the
promotion email is the only message that told them a seat was being offered, so it is the only place
they can accept it. If they can't find the email, a staff check-in at the door confirms them anyway.

This is the part most likely to surprise someone who used the app earlier in the year, when a
promotion flipped the signup to confirmed on the spot. The reason it changed: a promotion is
something the system or a staff member does, not something the volunteer asked for at that moment.
Weeks can pass between joining a waitlist and a seat opening up, and in that time people make other
plans. Silently confirming them produced volunteers who were on the roster, counted as coming, and
had no idea — and organizers who couldn't tell a real attendee from a stale one.

**The pending seat is genuinely held.** It counts against the session's capacity, the volunteer
appears on the roster, and they're listed on the public event page. Nobody else can take the seat
while the three days run.

## Every promotion sends the same email

**However a seat comes free, the next person gets the same confirm-your-spot email.** There is one
promotion email and every path uses it:

- A volunteer cancels through their own link, or staff cancel for them.
- A volunteer swaps to a different session, freeing the seat they came from.
- An organizer or admin promotes one specific waitlisted person by hand.
- Staff **move** or **swap** a waitlisted volunteer onto a session that has room.
- Staff **raise a session's capacity**, opening seats for the people already in line.
- The automatic hourly check frees a seat by clearing a signup nobody confirmed.

The email's subject is "A spot opened up — confirm your SciTrek signup for *[event]*". It names the
session with its date, time, and location, says to confirm within three days, and gives one button:
**Confirm my spot**. It also tells them they can use the same link to cancel if they can't make it,
and that the link keeps working as their manage page after they confirm.

This uniformity is new. Earlier in the year several of these paths promoted people and sent them
nothing at all, so if someone asks why a volunteer was never told about a promotion from a few months
back, that's usually the answer.

**One path deliberately skips the offer: a waitlisted volunteer who swaps themselves onto a session
that has room.** Clicking swap on their own manage page *is* their consent, so they land **confirmed**
straight away and no confirm-your-spot email is sent. Every other path is somebody else deciding on
their behalf, which is exactly why it becomes an offer instead. If staff make that same move for
them, they land at pending and wait on the email — the same visible move on the roster, two different
statuses, and the difference is who did it. (A volunteer swapping a seat they already hold — pending,
confirmed, or checked in — keeps that status; it is the seat they *left* that gets offered down the
waitlist. A session they were already marked attended for is not theirs to move: only staff can
relocate that.)

## If they don't confirm, the offer lapses

**Three days after the email, an unclaimed offer is withdrawn and the seat moves down the line.**
An automatic check runs every hour and cleans up promotions nobody claimed, so a seat is reclaimed
within about an hour of the deadline passing.

What happens then, stated plainly because it matters when someone asks:

- The unconfirmed signup is **deleted**, not marked cancelled. There is no trace of it left in the
  volunteer's own view of their signups.
- The seat is freed and **the next person on the waitlist is promoted**, with their own fresh
  three-day clock and their own email. That chain keeps going, one link per hour, until someone
  claims the seat or the waitlist runs out.
- **Nothing tells the lapsed volunteer.** No email says the spot was withdrawn.
- Their old link no longer works. If they click it they're told the link has expired.

So when a volunteer says "I got an email saying a spot opened up but the link doesn't work", the
answer is almost always that more than three days passed and the spot went to the next person in
line. They can sign up again — they'll take a seat if one is free, or rejoin the waitlist.

**Sessions that have already ended don't promote anyone, on any path.** Automatic promotion skips an
ended session silently — the seat simply stays free. A staff member who tries to promote, move, or
swap someone onto a session whose end time has passed gets an error instead, rather than the
volunteer getting a "confirm your spot" email for a session that already happened. This holds however
the seat came free, including a cancellation entered by hand days later.

**A waitlisted signup on a session that has come and gone is closed out automatically.** The hourly
check marks any still-waitlisted signup as **cancelled** once its session's end time has passed. No
email goes out — they never held a seat, and the session is over. Without this, a waitlist that never
drained would leave people sitting in line for a session that already happened. Note the difference
from an unconfirmed pending signup, which is **deleted** rather than cancelled.

## Manual promotion

**Manual promotion lets an organizer jump the queue.** From the event roster an organizer can
promote one specific waitlisted volunteer instead of taking the next in line. Since the slot is
usually still full, this asks for confirmation to go **over capacity** — putting an extra person in
a real room is a real decision, so it has to be made deliberately rather than happening by
default. Without the over-capacity option the button would simply fail every time it was used.

A manual promotion works exactly like an automatic one: the volunteer lands at pending and gets the
same three-day confirm email. That's fine for someone standing in front of you, because **checking
a volunteer in confirms them automatically** — a pending volunteer who shows up and gets checked in
doesn't need to find the email first.

**Admins can reorder a waitlist** from the event page, which rewrites the queue so the order you
set becomes the order used for promotion. You must submit the whole current waitlist for the slot —
no additions, no omissions.

## Other things to know

A waitlisted signup can also just be **cancelled**, by the volunteer through their manage link or
by staff. The email that goes out then says they've been **removed from the waitlist**, not that a
signup was cancelled — they never held a seat, so the seat-holder wording would be misleading.

**Waitlisted volunteers are excluded from broadcasts.** A broadcast goes to people holding or past
a confirmed spot — confirmed, checked in, and attended — because broadcasts are operational
instructions for people who are actually coming. They are also excluded from the quarter
retrospective's signup counts.

**A waitlisted orientation slot still satisfies the orientation requirement.** A new volunteer who
includes an orientation session in their signup meets the requirement even if that orientation
lands on the waitlist. The requirement is checked against what they selected, before any seat is
assigned.
