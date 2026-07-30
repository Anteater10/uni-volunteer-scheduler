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
from the dates rather than from a hardcoded 11.

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

**Past quarters can be archived.** Archiving is only allowed once the quarter has ended.
An archived quarter stays listed and stays reachable by deep link, and volunteers can still browse
it under "Archived quarters" on the public page, but the app skips archived quarters when working
out what week it currently is. Archiving can be undone with Restore.

**Deleting a quarter is blocked while events still reference it.** The delete fails with a conflict
rather than orphaning events. Move or delete the events first.
