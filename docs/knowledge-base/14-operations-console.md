# The Operations console

**Operations** at `/admin/operations` is the day-of staff view — the page you keep open while
sessions are running. Both organizers and admins can use it, and it is where an organizer lands:
an organizer who opens the admin area is sent straight here, because the Overview page is
admin-only. It has four tabs: **Today**, **Upcoming**, **Past**, and **Reminders**.

**Today, Upcoming, and Past** are three views of the schedule, and they're mutually exclusive: an
event that runs today shows only under Today, even after its end time passes, and never
double-appears under Past. The selected tab is kept in the address, so a refresh or a shared link
opens the same view.

**Each of those views lists events, not sessions.** A card gives the event's title, its date and
time range, and its location, with buttons to open the roster or the event's details. There are no
signup, capacity, or fill numbers anywhere on Operations — per-session counts live on the roster
and on the event detail page. If you are chasing an under-filled session, Operations tells you
which events are coming, not which ones need people.

**The Reminders tab previews the reminder emails the system is going to send, for the next seven
days only.** It is a calculated preview rather than a stored queue — nothing on this tab has been
written down in advance — so it shows the near term rather than the whole quarter, and it only
covers volunteers who have confirmed their signup. Rows are grouped by kind rather than shown as
one flat time-sorted list. There are three groups — **Kickoff**, **24 hours before**, and **2 hours
before** — each with a count and a plain-language note explaining when it fires. Only those three
tracked kinds appear here: the older 24-hour and 1-hour reminder emails and the weekly digest are
sent without ever showing on this tab. See the reminders document for the exact timing rules.

**Rows that will not send are shown anyway, labelled.** A row reads *scheduled*, *already sent*, or
*opted out*. Showing the last two is deliberate: an admin asking "why didn't this person get the
email?" gets the answer on the same screen instead of having to guess.

**Any row that hasn't gone out yet also has a "Send now" button**, for admins and organizers alike,
which fires that one reminder immediately after a confirmation step. It exists for the case where
something urgent comes up outside the hours the system will normally send in — roughly 9pm to 7am
Pacific — and that overnight hold is the only rule it skips. A volunteer who has turned reminders off
still gets nothing, and an already-sent reminder cannot be sent twice: the button is greyed out for
those rows, and an opt-out is refused with a message saying so. Use it for one person, not as a way to
blast a whole event; a broadcast is the tool for that.

Operations replaced two older pages. The organizer schedule used to live at `/admin/preview` and
reminders at `/admin/reminders`; both of those addresses now redirect here, so old bookmarks still
work.

**Quarters are not on this page, and neither is quarter scoping.** Entering or editing a quarter
happens roughly once a term, so it lives in the "Manage quarters" drawer on the admin Overview page
rather than taking up a navigation tab. Picking a quarter there re-scopes the Overview statistics
and the Events list — but never Operations, which always shows the live schedule regardless of which
quarter is selected. That is the point of the page: on the day of a session you want what is
happening now, not what a chosen term looks like in aggregate.

**On a phone, use the Today page instead.** The staff menu has a separate **Today** page — a
mobile view of today's sessions that links straight into each event's roster. It exists because
the admin pages are desktop-only, and Today is how an organizer standing at a school reaches the
roster without opening a laptop.

For an organizer, the normal day looks like: open Operations → Today, open the event that's
running, work from the roster to check people in as they arrive, and end each slot once the session
is over.
