# Exports and analytics

**Admin → Exports** is where admins download reporting as CSV. It is admin-only — organizers have
no route to it. Every report is **generated live from current data**, so there is no stale or cached
export to worry about.

**Each report panel has its own time-range picker.** There is no single control at the top of the
page: eight panels, eight independent ranges, and setting one leaves the other seven alone. Every
panel opens on **This quarter**, meaning the quarter that contains today, or the most recently ended
quarter if nothing is running right now. Those dates come from the real quarters an admin has
entered rather than a guessed calendar, and the preset is hidden entirely until at least one quarter
exists.

**Of the range buttons, only "This quarter" and "Custom range" actually narrow the data.** Two more
buttons sit alongside them showing raw labels — `last-quarter` and `last-12-months` — and they are
unfinished. Pressing either clears the date filter rather than setting one, so the panel then shows
**all-time** figures. If you need a past term or a rolling year, set it yourself with Custom range.

There are eight reports:

- **Volunteer hours** — hours credited per volunteer.
- **Attendance rates** — how often signups turned into attendance, per event.
- **No-show rates** — how often volunteers didn't turn up.
- **Event fill rate** — how full events were against their capacity.
- **Hours by school** — volunteer hours grouped by partner school.
- **Unique volunteers per quarter** — how many distinct people took part.
- **Cancellation rates** — how often signups were cancelled, per event.
- **Module popularity** — which modules drew the most signups.

**Five of the eight reports depend on sessions being closed out.** Volunteer hours, Attendance
rates, No-show rates, Hours by school, and Unique volunteers per quarter all count signups that
reached **attended** — or, for no-shows, the deliberate no-show mark. A session nobody ended leaves
its volunteers sitting at confirmed or checked-in, and those five see nothing. **Event fill rate,
Cancellation rates, and Module popularity work differently:** they count seats held rather than
attendance, so closing a session out never changes them.

**On a multi-session shift, every session counts separately.** Hours and attendance come from the
sessions a volunteer was actually marked attended at, not from the size of their commitment — so a
volunteer who booked a two-session shift and turned up once is credited once. Closing out only the
first day of a shift therefore under-reports the second.

**If hours or attendance look low, look for sessions that were never closed out.** The two report
types fail in different ways, which is worth knowing when you're diagnosing a number. Hours simply
go missing — an unresolved session contributes zero. Attendance rates instead quietly shrinks: its
percentage is attended against confirmed, attended and no-show, and a checked-in volunteer counts in
neither, so they drop out of both halves of the ratio. The percentage stays believable while the
underlying counts get smaller than reality.

**Held seats and filled seats are not the same thing.** Event fill rate and Module popularity count
confirmed, checked-in and attended signups. A volunteer who has been promoted off the waitlist but
hasn't clicked their confirmation link yet is still **pending**: their seat is genuinely held and
they appear on the roster, but they aren't counted as filled in those two reports. A busy event can
therefore read as slightly under-full while every seat is actually spoken for.

**For a per-event view rather than a program-wide one, use the Roster CSV download on the event
page.** That is the only per-event export with a button on it.

**Opening Exports writes to the audit log.** Each panel records its own read, so a single visit adds
around eight entries, plus one more for every CSV you download. That is the usual reason the audit
log looks busy after a reporting session.

**"Unique volunteers per quarter" groups by the season and year stamped on each event**, not by the
quarter rows in Admin → Quarters. Events are normally stamped when they are created, but anything
missing a season or year falls into an "unknown" bucket filed under its start year — so a row
reading "unknown" means events that need their dates or quarter checked, not volunteers nobody can
identify.

**The quarter you are viewing elsewhere in the admin area does not follow you into Exports.** The
Overview page and the Events list share one quarter selection; Exports ignores it and always starts
each panel from the current-or-most-recent quarter. If an Overview total and an Exports report
disagree, check they are looking at the same term before assuming the data is wrong.

For "how did that whole quarter go", use the **quarter retrospective** instead — it's the per-quarter
summary with events, signups, attendance, and no-shows in one place. Note that the retrospective
counts anyone who was present as attended, including people still sitting at checked-in, whereas
these analytics reports count only fully resolved attendance. The two can differ if sessions weren't
closed out.
