# Magic links and volunteer self-service

Volunteers have no account, so every action they take after signing up is authorized by a **magic
link** — a link emailed to them that stands in for a password.

When a volunteer signs up, the app emails them a link. The success screen they see in the browser
deliberately doesn't show the link: it goes to their inbox, which is what proves the email address
is theirs.

With their magic link a volunteer can **confirm** the signup, **view** what they're signed up for,
**cancel** a signup, and **swap** to a different session in the same event.

**There is only one kind of link, and it covers all of that.** The link in the signup email is the
same link used for viewing, cancelling and swapping later — there is no separate short-lived
"manage" link to request. One link is issued per signup batch and it is scoped to that volunteer and
that event, so it shows and controls every session they took in that event and nothing else.

**A link carries a confirmation deadline, and how long depends on how the signup came about.** A
link from a fresh public signup gives **14 days** to confirm. A link from a **waitlist promotion**
gives **3 days**, because the seat is being held out of circulation while the promoted volunteer
decides and the next person in line is waiting on the answer.

**Once a volunteer has confirmed, their link keeps working indefinitely.** The deadline governs the
act of confirming and nothing else: a volunteer who confirmed on day one can still open that same
link on day forty to see their signups, cancel one, or swap sessions. This is deliberate. The old
behaviour punished the wrong people — a confirmed volunteer lost control of their own signups on day
fifteen, which meant seats going unfilled because nobody could release them.

**A link whose deadline passed without ever being confirmed is refused.** Someone in that position
sees an "this link has expired" page rather than their signup list, and there is nothing to rescue:
the unconfirmed signup is swept away shortly afterwards anyway (see below). So "expired link" in
practice means "you never confirmed", not "you confirmed and then waited too long".

**Only the confirmation step is single-use.** Clicking to confirm consumes that step; clicking it
again reports the signup as already confirmed rather than failing. Viewing, cancelling and swapping
are not consumed and can be repeated as often as the volunteer likes. The practical consequence is
worth being straight about: a link that leaks stays usable by whoever holds it, so it should be
treated like a password and never forwarded. As a safeguard, cancelling through a link emails the
volunteer a cancellation notice, so a cancellation they didn't make lands in their inbox
immediately.

**One click confirms the whole batch.** A volunteer who took three sessions in one event gets one
link, and confirming it confirms all three. They are never asked to confirm session by session.

**A link stops existing in one of two ways.** It disappears with its signup, which is what happens
when an unconfirmed signup is swept away or a signup is deleted; or an automatic cleanup removes an
already-expired link once the volunteer has nothing upcoming at all and their last session finished
more than 30 days ago. Nothing is cleaned up while a volunteer still has a session ahead of them, or
while their link is still inside its confirmation window.

**An unconfirmed signup is deleted, not just marked lapsed.** An hourly sweep looks for signups
still waiting on confirmation whose links have all run out, deletes them, frees the seat, and offers
it to the next person on the waitlist. Nothing tells the volunteer this happened, and no record of
the signup remains in their manage view — so a volunteer who says "my signup vanished" most likely
never confirmed in time. See the signups-and-statuses and troubleshooting documents.

**Signing up and using a link are both rate-limited** by network address, so the signup form can't
be hammered to flood an inbox and a link can't be brute-forced by guessing.

**A volunteer who has lost their email cannot currently be sent a fresh link from inside the app.**
There is no working resend button on either the volunteer or the staff side today, and signing up
again for the same session is refused as a duplicate. Someone in that position needs to contact
SciTrek staff directly.

**A magic link cannot be used to get around the orientation requirement.** The requirement is
enforced when the signup is created, not when it's confirmed, so confirming a link never smuggles
in a signup that wouldn't have been allowed in the first place.

**Cancelling through a magic link behaves like staff cancelling.** The seat is freed, the volunteer
gets a cancellation email, and the longest-waiting volunteer on that session is offered the spot —
offered, not simply moved in, because a promotion now asks that volunteer to confirm within three
days. The waitlist document explains that flow.

Volunteers also manage their **reminder preferences** from the manage page, by email address,
without logging in. Reminders are on by default and can be turned off there. One rough edge to be
aware of: unlike cancelling and swapping, the reminder toggle still requires a link that is inside
its confirmation window, so a volunteer opening an old link can cancel a session but may find the
reminder switch refuses to load. Broadcasts ignore the reminder preference either way, because
broadcasts are operational instructions rather than promotional email.

Separately from magic links, volunteers check in at the door by scanning the event's **QR code**,
which carries the event's venue code. That flow is described in the check-in and venue-code
documents.
