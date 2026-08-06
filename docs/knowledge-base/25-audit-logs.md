# Audit logs

The **audit log** records who did something, what they did, what they did it to, and when. It's
admin-only.

**The Audit Logs tab is hidden by default.** The Overview page already shows recent activity, which
covers the everyday "what just happened" question, so the full log is opt-in. Turn the tab on with
the **Show Audit Logs tab** setting from the site settings card on the Overview page.

Once the tab is on, find it at **Admin → Audit Logs**. Filter by person with the **Actor** dropdown,
by time with the date-range picker, and narrow further with the search box. Click any row to open a
drawer with the full detail, including the raw data behind it.

**The search box does not match names.** It matches the underlying action name, the type and id of
the thing acted on, the actor's internal id, and the raw data attached to the entry — so typing
"Jordan Lee" finds nothing even when the log clearly shows that name. To find one person's activity,
use the Actor dropdown instead.

**Names and targets read as names, but many actions don't.** The log resolves people and things into
plain labels, so a target reads as "Jordan Lee's signup for Sound Waves, 2026-05-12". The action
column is only translated for actions that have a written-out label, and several everyday ones don't
have one. Every check-in, every undo of a check-in, every close-out, and every reopen of an ended
event all record the same underlying action and so all read as **"Transition"**. Open the row to see
what actually changed — the detail carries the before and after status.

**The Action dropdown lists a stale set of choices.** It is maintained by hand and has drifted: it
still offers the two CSV-import actions from a pipeline that no longer exists, and it is missing most
of what the app logs today — check-ins and close-outs, orientation credit grants and revocations,
broadcasts, quarter creation and archiving, form-field changes, event duplications, manual waitlist
promotions and waitlist reordering, site-settings changes, and password changes. Those entries are
all in the log and all findable; they just can't be picked from the dropdown. You can still filter to
one of them by adding it to the page address as `?kind=` followed by the action name (several names
separated by commas also works), or by using the search box, which matches those names directly.

**The filtered log downloads as CSV, capped at the 10,000 most recent matching rows.** Narrow the
date range first if you need a complete picture of a busy period.

**This is not a change-only log — reads are recorded too.** Loading the Overview page, the user list,
a user's detail, an event roster, an event's analytics, the audit log itself, and each panel of the
Exports page all write an entry. That is deliberate for an attendance system holding student data,
but it means the log is dominated by page views, and a quiet day still produces plenty of rows.

**What gets recorded** includes: signup status changes (check-in, undo, close-out, reopen),
cancellations, moves, manual waitlist promotions and waitlist reordering, orientation
credit grants and revocations, broadcasts sent (with the shift or slot when one was targeted), event
creation, edits, duplication and deletion, shift and session changes, slot changes, form-field
changes on an event or a module, quarter
creation, edits, archiving, restoring and deletion, site-settings changes, staff invitations, role
changes, deactivations and reactivations, password changes and first-time password setup, sign-ins,
and CCPA exports and deletions.

**Two things people expect to find are not there.** A volunteer clicking their own confirmation link
writes no entry — confirmations happen outside any staff session, and there is no actor to record.
And an event becoming complete has no entry of its own: what you'll find are the close-out
transitions that caused it.

**Automatic actions show the actor as "System".** The nightly sweep that archives ended quarters is
the common one — nobody pressed anything, so there is no person to name.

**The Overview activity feed shows the last 5 entries** as a quick glance. For anything older or
more specific, use the full log.
