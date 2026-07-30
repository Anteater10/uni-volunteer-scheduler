# Waitlist and auto-promotion

When a slot is full, further signups for it become **waitlisted** rather than rejected. The
volunteer has still given their details and consented; they're simply in line. Their position is
shown to them, counting from 1.

**The waitlist is first-come, first-served.** Order is by when the signup was created, and that
ordering is used consistently everywhere — for the position a volunteer sees, for automatic
promotion, and for the organizer's list.

**Auto-promotion happens whenever a held seat frees up.** The longest-waiting person on that slot
is promoted immediately and automatically. Nobody has to notice the seat freeing up for this to
work. All of these trigger it:

- a volunteer cancels through their manage link
- staff cancel a signup
- a volunteer swaps to a different session
- staff move a volunteer to a different session
- the hourly cleanup removes someone who never confirmed

**A promoted volunteer does not go straight to confirmed. They go to pending.** They are emailed a
"confirm your spot" link and **they have 3 days to click it**. Only clicking makes them confirmed.

This is deliberate: promotion is something the system or a staff member did, not something the
volunteer asked for. They signed up days or weeks ago for a slot that was full, and their plans may
have changed. So they are asked, not assumed.

**A pending promotion still holds the seat.** The seat is not available to anyone else during those
3 days — the slot's count includes pending people. This is the usual explanation for a roster that
looks full while showing someone as Pending.

**If the 3 days lapse, the seat moves on.** An hourly job removes the unconfirmed signup, frees the
seat, and offers it to the next person on the waitlist with a fresh 3-day clock of their own. That
chain continues until somebody confirms or the waitlist runs out. Nobody is emailed about being
dropped — see [10-signups-and-statuses.md](10-signups-and-statuses.md).

One exception: if the session has **already ended**, the unconfirmed signup is still removed but the
seat is not offered onward. There is no point emailing someone a 3-day confirmation for an event
that already happened.

Because auto-promotion already claims any seat that frees up, a slot's waitlist normally only
exists while the slot is genuinely full. That has a consequence for the manual override below.

**Manual promotion lets an organizer jump the queue.** From the event roster an organizer can
promote one specific waitlisted volunteer instead of taking the next in line. Since the slot is
usually still full, this asks for confirmation to go **over capacity** — putting an extra person in
a real room is a real decision, so it has to be made deliberately rather than happening by
default. Without the over-capacity option the button would simply fail every time it was used.

Manual promotion works exactly like automatic promotion in one important way: the volunteer you
promote goes to **pending** and gets the same 3-day confirm email. Promoting somebody by hand does
not put them on the roster as confirmed, and it does not skip the email. If they never click, the
hourly job removes them just the same.

**Admins can reorder a waitlist** from the event page, which rewrites the queue so the order you
set becomes the order used for automatic promotion. You must submit the whole current waitlist for
the slot — no additions, no omissions.

A waitlisted signup can also just be **cancelled**, by the volunteer through their manage link or
by staff.

**Waitlisted volunteers are excluded from broadcasts.** A broadcast goes to people holding or past
a confirmed spot — confirmed, checked in, and attended — because broadcasts are operational
instructions for people who are actually coming. They are also excluded from the quarter
retrospective's signup counts.

**A waitlisted orientation slot still satisfies the orientation requirement.** A new volunteer who
includes an orientation session in their signup meets the requirement even if that orientation
lands on the waitlist.
