# The quarter retrospective

The **quarter retrospective** answers "how did that quarter actually run?" It's admin-only, because
it exposes attendance data.

Reach it from **Admin → Quarters**: past and archived quarters get a **View events** link on their
row. Current quarters don't, since the report is about a term that's finished — though an admin can
open it for any quarter by id, which is useful for reviewing a quarter shortly *before* archiving it.
Most quarters get there on their own: a quarter is archived automatically by a nightly sweep once its
end date has passed, so the retrospective is normally how you look back at a term rather than
something you have to set up.

The page shows the quarter's display name, an Archived chip if it's archived, and its date range and
week count underneath. Then four headline numbers — **events ran, signups, attended, no-shows** — with
two of them carrying a second line: Signups also shows the quarter's total **capacity**, and Attended
also shows the **attendance rate**. Below that is a per-event table listing **week, event, date,
signups, attended, no-shows**, ordered by when each event started, with each row linking to the
event's own page.

**Which signups are counted:** pending, confirmed, checked in, attended, and no-show. **Waitlisted
and cancelled signups are excluded** — they never held a seat that was used. Pending is in that list
because a pending signup does hold its seat, which includes anyone promoted off the waitlist who
never got round to confirming.

**Attended here includes checked-in volunteers.** Someone who was tapped in but whose session was
never closed out was still present, so the retrospective counts them as attended. This is a
deliberate difference from the Exports reports, which count only fully resolved attendance. If the
two disagree, the gap is sessions that were never ended.

The attendance rate is attended divided by signups, and reads as zero for a quarter with no signups
rather than as an error. Because the denominator keeps unresolved pending and confirmed signups, a
quarter with sessions nobody closed out reads lower than it really was — the same rough edge that
makes the Exports numbers look thin.

**Membership is by the quarter each event is linked to**, not by re-deriving dates. So if an admin
edits a quarter's dates and events get relinked, the retrospective follows the new linkage.

**The report is read-only, and it ignores the quarter you're viewing elsewhere.** Opening a
retrospective doesn't change what the Overview page or the Events list are scoped to — it's a
per-quarter page you reach by its own link. Nothing on it can be edited; corrections have to be made
on the events themselves.
