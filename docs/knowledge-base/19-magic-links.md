# Magic links and volunteer self-service

Volunteers have no account, so every action they take after signing up is authorized by a **magic
link** — a link emailed to them when they sign up.

When a volunteer signs up, the app emails them the link. The success screen they see in the browser
deliberately doesn't show the link or a token: it goes to their inbox, which is what proves the
email address is theirs.

With their magic link a volunteer can **confirm** the signup, **view** what they're signed up for,
**cancel** a signup, and **swap** to a different slot. They can also add the session to their
calendar from the confirmation page.

**One link, two jobs.** The same emailed link is both the confirm button and the volunteer's ongoing
manage page, and the two halves behave differently. Confusing them is the usual source of "does the
link still work?" questions.

| | Confirming | Managing (view / swap / cancel) |
|---|---|---|
| How many times | Once — the click is consumed | As often as they like |
| Deadline | Yes, see below | None enforced on the link itself |

**Confirming has a deadline.** How long depends on how the signup came about:

| How they got the link | Time to confirm |
|---|---|
| Signed up for a seat that was free | **14 days** |
| Promoted off the waitlist | **3 days** |

If they click after that, confirmation fails and they land on a "link expired" page. The pending
signup is separately deleted by the hourly cleanup — see
[10-signups-and-statuses.md](10-signups-and-statuses.md).

**Managing does not expire on a timer.** Once the signup is confirmed, the same link keeps working
as the volunteer's manage page. This is on purpose: a volunteer who signed up in week 1 needs to be
able to swap or cancel a week-8 session without asking anyone for a fresh link. The link stops
working when its token row is cleaned up, roughly 30 days after the volunteer's last session.

**So treat a magic link as a private credential.** Anyone holding it can view that volunteer's
sessions and cancel or swap their seats, for as long as the signup is live. Forwarded emails and
shared screenshots are the realistic risk, not brute force — the token itself is random and stored
only as a hash.

**Requesting a new link is rate-limited** per email address and per IP, so the endpoint can't be
used to spam someone. A volunteer who hits the limit is asked to wait and try again.

**Getting a lost link replaced is more limited than it looks.** There is no general "resend my
magic link" button:

- A volunteer can request a new link **only while their signup is still pending** — that is, only
  before they have confirmed. The replacement link is short-lived: **15 minutes**.
- Once confirmed, there is no self-service way to get the link back.
- The admin **Resend** button on a signup does *not* send a magic link. For a confirmed signup it
  sends a plain "you are signed up" notice with no link in it. For a waitlisted signup it sends
  nothing at all.

In practice, a confirmed volunteer who has lost their email cannot self-serve a swap or
cancellation. Staff do it for them from the roster.

**A magic link cannot be used to get around the orientation requirement.** The requirement is
enforced when the signup is created, not when it's confirmed, so confirming a link never smuggles
in a signup that wouldn't have been allowed in the first place.

**Cancelling through a magic link behaves exactly like staff cancelling.** The seat is freed and the
longest-waiting volunteer on that slot is promoted automatically — to **pending**, with their own
3-day confirm link, not straight to confirmed. See [11-waitlist.md](11-waitlist.md).

Volunteers also manage their **reminder preferences** by email address without logging in.
Reminders are on by default and can be turned off. Broadcasts ignore that preference, because
broadcasts are operational instructions rather than promotional email.

Separately from magic links, volunteers check in at the door by scanning the event's **QR code**,
which carries the event's venue code. That flow is described in the check-in and venue-code
documents.
