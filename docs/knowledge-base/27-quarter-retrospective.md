# The quarter retrospective

The **quarter retrospective** answers "how did that quarter actually run?" It's admin-only, because
it exposes attendance data.

Reach it from **Admin → Quarters**: past and archived quarters get a **View events** link on their
row. Current quarters don't, since the report is about a term that's finished — though an admin can
open it for any quarter by id, which is useful for reviewing a quarter shortly *before* archiving it.

The page shows the quarter's display name, an Archived chip if it's archived, four headline numbers
— **events ran, signups, attended, no-shows** — and a per-event table. Each row gives that event's
signups against capacity, its attended count and its no-show count, and links to the event's own
page.

**Which signups are counted:** pending, confirmed, checked in, attended, and no-show. **Waitlisted
and cancelled signups are excluded** — they never held a seat that was used.

**Attended here includes checked-in volunteers.** Someone who was tapped in but whose session was
never closed out was still present, so the retrospective counts them as attended. This is a
deliberate difference from the Exports reports, which count only fully resolved attendance. If the
two disagree, the gap is sessions that were never ended.

The attendance rate is attended divided by signups, and reads as zero for a quarter with no signups
rather than as an error.

**Membership is by the quarter each event is linked to**, not by re-deriving dates. So if an admin
edits a quarter's dates and events get relinked, the retrospective follows the new linkage.
