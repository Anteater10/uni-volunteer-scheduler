# Audit logs

The **audit log** records every important change in the system: who did it, what they did, what
they did it to, and when. It's admin-only.

**The Audit Logs tab is hidden by default.** The Overview page already shows recent activity, which
covers the everyday "what just happened" question, so the full log is opt-in. Turn the tab on with
the **show audit logs tab** setting from the settings card on the Overview page.

Once the tab is on, find it at **Admin → Audit Logs**. Use the filters at the top to narrow by who,
what, or when. The search box matches the person's name, the action, or the target of the action,
and combines with the kind filter and a date range. Click any row to see the full detail including
the raw data. The whole filtered log can be downloaded as CSV.

**What gets logged** includes: signup status changes (check-in, undo, close-out), orientation credit
grants and revocations, broadcasts sent (with the slot if it was scoped to one), quarter creation,
edits, archiving and restoring, staff user invitations, role changes, deactivations and
reactivations, CCPA exports and deletions, and event changes.

**The Overview activity feed shows the last 5 entries** as a quick glance. For anything older or
more specific, use the full log.

The audit feed is written in plain language rather than raw identifiers, so it reads as "Ana checked
in Jordan Lee" rather than a pair of database ids.
