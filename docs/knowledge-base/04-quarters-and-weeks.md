# Quarters and weeks

A **quarter** in the SciTrek scheduler is an academic quarter that an admin has entered by hand:
the season (winter, spring, summer, or fall), the year, an optional session label, and the
quarter's start and end dates transcribed from the UCSB academic calendar. Quarters live in Admin
→ Quarters, reached from the "Manage quarters" drawer on the Overview page.

**Nothing about quarters is guessed or seeded.** The app does not assume an 11-week stride from
some anchor date, and it ships with zero quarters. Until an admin enters the current quarter,
quarter-dependent features are blocked: admins are redirected to the quarters setup page, and the
public browse page says "Schedule coming soon" rather than showing an error.

**Weeks are derived from the quarter's own dates.** Week 1 begins on the quarter's start date, and
weeks are numbered 1 through N where N comes from the length of the range. A normal 11-week
quarter and a 6-week summer session both work with no special casing, because the week count comes
from the dates rather than from a hardcoded 11. The public browse page will only navigate to weeks
1 through 26, which no real SciTrek quarter comes near — but a quarter entered with a range longer
than half a year would have weeks volunteers could not reach.

**Summer Session A and Session B are separate quarter rows**, distinguished by the label field.
Each numbers its own weeks, so Session A week 6 is followed by Session B week 1. The label is
empty for regular quarters, whose display name is just "Fall 2026".

**Quarters cannot overlap.** The database enforces this with an exclusion constraint on the date
range, so two quarters covering the same day are impossible even if two admins save at the same
moment. Start date must come before end date. The end date is inclusive — it is the quarter's last
day.

**A date can fall in no quarter at all.** The gap between two quarters belongs to neither, and the
app never quietly clamps a gap date into a neighboring quarter. On the public browse page a gap
shows a banner naming the next quarter and when it starts ("Summer 2026 · Session B starts Aug 3").
On the Overview page, quarter progress reads "Between quarters."

**Every event must fall inside an entered quarter.** Creating or editing an event whose date is not
covered by any quarter is rejected with a message like "No quarter covers 2026-09-14 — add it in
Admin → Quarters first." There is no way to create an uncategorized event. If you are setting up a
new term, enter the quarter before the events.

**Entering or editing a quarter relinks matching events automatically.** When an admin saves a
quarter, events whose dates fall inside it are linked to it and their week numbers recomputed. The
save returns a relink summary — how many events were linked, how many changed weeks, how many were
unlinked — and the UI shows those counts, so recategorizing events is never silent. Editing dates
asks for confirmation first, for the same reason.

**Relinking looks at an event's start date only.** An event that straddles a quarter boundary is
attributed entirely to the quarter its first day falls in. The comparison also runs in UTC rather
than Pacific, so an event starting late in the evening on a quarter's last day can be counted into
the following quarter. Both are edge cases, but they explain a surprising week number.

**Ended quarters are archived automatically.** A daily sweep at 03:30 UTC — roughly 8:30 pm Pacific
the evening before — archives every quarter whose end date has passed, so a quarter is normally in
the archive the same night its last day ends. Archiving is a tidy-up rather than the moment anything
changes: the quarter has already turned read-only by then, several hours earlier, as soon as its end
date passed in UTC. An admin can also archive it by hand once it has
ended. An archived quarter stays listed and stays reachable by deep link, and volunteers can still
browse it under "Archived quarters" on the public page, but the app skips archived quarters when
working out what week it currently is. Archiving can be undone with Restore — though a restored
quarter whose end date is still in the past will be re-archived by the next daily sweep, so restore
is for fixing a quarter's dates, not for keeping an ended quarter live.

**The admin side works one quarter at a time.** Admin → Overview and Admin → Events share a single
quarter selection. It is set with "View this quarter" in the quarters table or from the Quarter
dropdown on the Events page, and it sticks in that browser between pages and reloads — so changing
it in one place re-scopes the other. In the quarters table the row being looked at is badged
"Viewing" and the quarter containing today is badged "Current". With nothing chosen the app follows
the current quarter and labels the numbers with its name. **Archived quarters stay pickable on
purpose** — that is how a past term's rosters and statistics are revisited. The Events page also
offers "All quarters"; Overview always reports on exactly one.

**Only the quarter-shaped numbers on Overview follow that selection.** The per-quarter counts,
volunteer hours, attendance rate, and quarter progress all re-scope, and a blue strip at the top of
the page names the quarter they describe. The all-time totals, the week-over-week deltas, "This
week" and "Needs attention" (both of which always look at the days either side of today), and
"Recent activity" do not — they are about now, not about the quarter being examined. Two card
headings still read "this quarter" even when a past quarter is selected, so trust the strip at the
top of the page over those headings.

**A quarter that has ended becomes history rather than a workspace.** With an ended quarter
selected, the Events page stops offering to create events in it and says so — new events belong in
the current quarter.

**Once a quarter is archived or its end date has passed, the server refuses changes to anything
inside it.** Creating, editing or deleting its events, adding or changing their sessions, editing
their custom signup questions, and reopening a completed event are all rejected with "*[quarter
name]* has ended and is read-only." Moving an event *into* an ended quarter is refused the same way.
Two things deliberately stay open: closing out attendance, because an organizer legitimately
finishes a roster the morning after, and duplicating one of its events into a current quarter, which
is what makes last term's schedule useful as the starting point for this term's. See the events
document.

**A quarter turns read-only as soon as its end date is past — which is late afternoon Pacific on the
quarter's own last day, not the following morning.** The cutoff is worked out in UTC, so it falls
around 5pm Pacific in summer and 4pm in winter, while it is still the last day locally. Being
archived has the same effect, but archiving is a separate nightly tidy-up that runs several hours
after the cutoff has already passed: the date alone is enough. Plan on losing write access to a
quarter mid-afternoon on its final day.

**Deleting a quarter is blocked while events still reference it.** The delete fails with a conflict
rather than orphaning events. Move or delete the events first.
