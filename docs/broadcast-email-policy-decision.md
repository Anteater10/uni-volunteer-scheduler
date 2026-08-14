# Decision — broadcasts ignore the reminder opt-out

**Decided:** 2026-08-13 · **By:** Andy Subramanian (project owner) · **W5.6**
**Status:** active · **Pinned by:** `backend/tests/test_broadcast_optout_policy.py`

## The asymmetry

`volunteer_preferences.email_reminders_enabled` defaults to `true` and can be set
to `false` by the volunteer from the manage page, with no login, via
`PUT /public/preferences?manage_token=…`.

| Mail | Honours the opt-out? | Where |
|---|---|---|
| Reminder emails | **yes** | `reminder_service` checks it in three places |
| Staff broadcasts | **no** | `broadcast_service` selects on signup status alone |

Broadcast recipients are everyone whose signup is `confirmed`, `checked_in` or
`attended` (shift commitments: `confirmed`). Cancelled, waitlisted and pending
rows are excluded. **Holding a spot is the only membership test, and that is the
whole basis of this decision.**

## Why broadcasts are not suppressible

A broadcast is operational mail to people who are currently expected to turn up
somewhere. The real messages are "the room moved to Chem 1179", "wear closed-toe
shoes", "tomorrow is cancelled — do not come".

Suppressing those would strand a volunteer who is still on the roster: they
opted out of *reminders about a commitment they already know about*, not out of
*being told the commitment changed*. A volunteer who drives to a cancelled event
because the system respected their reminder preference is a worse outcome than
one unwanted email — and it is a failure the volunteer could not have predicted
from the checkbox they ticked.

The opt-out is also not a blunt instrument in practice: cancelling the signup
removes the person from every future broadcast for that event, because
membership follows status. There is a way out, and it is the honest one.

## Legal basis

US CAN-SPAM, which is the regime that applies here (UCSB, US recipients, no EU
marketing list).

CAN-SPAM's opt-out requirement attaches to **commercial** messages — content
whose primary purpose is advertising or promoting a product or service.
**Transactional or relationship messages are exempt from it**, including messages
that provide information about a transaction the recipient has entered into or
that deliver updates about an ongoing relationship. A shift a volunteer signed up
for is exactly that relationship, and a room change is exactly such an update.
The exempt category still must not use deceptive headers or a misleading subject
line, and broadcasts do neither: they send from the configured SciTrek address
with a staff-written subject, and every send is audited with its subject and
recipient count.

This is not a lawyer's opinion. It is the reasoning being relied on, recorded so
that it can be checked rather than reconstructed.

## The trigger that invalidates this — read before reusing broadcasts

**The exemption is about content, not about the channel.** It holds only while
broadcasts carry operational information to people holding a spot. It stops
holding the moment a broadcast is used to promote something — "come to our
fundraiser", "sign up for next quarter", "donate", "tell your friends".

If broadcasts are ever wanted for that, do not widen this decision. Either:

1. add a separate promotional path with its own consent flag and a working
   unsubscribe link in the footer, or
2. re-decide this record, in writing, with the new content in front of you.

Two specific changes must re-open this document:

- **Recipient selection widening** beyond "holds a spot" — e.g. including
  cancelled volunteers, waitlisted volunteers, or every volunteer who ever
  attended anything. Membership-by-current-commitment is what makes the mail
  relationship mail. `test_broadcast_recipients_are_chosen_by_status_alone`
  fails if this drifts.
- **Any recruitment or fundraising content**, whoever sends it and however
  operational the subject line looks.

## What was considered and rejected

| Option | Why not |
|---|---|
| Honour the opt-out for broadcasts too | Strands volunteers who are still on a roster. The failure is silent for staff and expensive for the volunteer. |
| Add an unsubscribe footer to broadcasts anyway | Offers a control that must not work — clicking it either lies or creates the stranding above. A dead unsubscribe link is worse than none. |
| Split broadcasts into "urgent" and "normal", suppressing the second | Staff decide the label under time pressure on an event day. Mislabelling "cancelled" as normal is a single dropdown away. |
| Do nothing and leave it undocumented | The status quo before this record. It reads as an oversight, and the next reviewer either "fixes" it or re-derives the reasoning from scratch. |
