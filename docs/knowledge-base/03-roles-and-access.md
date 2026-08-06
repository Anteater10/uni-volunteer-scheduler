# Roles and access — who can do what

The SciTrek scheduler has three working roles: **volunteer** (participant), **organizer**, and
**admin**. Volunteers have no account at all. Organizers and admins are staff with real login
accounts, an email and a password, created by invitation from an admin — the invite link is where
the new staff member sets their own password.

**Volunteers have no account and never log in.** A volunteer is identified only by their email
address. They browse sessions at `/volunteer`, sign up, and then manage everything through magic
links emailed to them or by scanning the check-in QR code at the door. There is no volunteer
password, no volunteer dashboard, and no volunteer login page.

**Organizers** run events day to day. An organizer can create and edit events, generate and edit
slots, duplicate an existing event into another week, view rosters, check volunteers in, undo a
mis-tapped check-in, close out a session (marking attended or no-show), grant orientation credit at
the door, promote someone off the waitlist, send broadcasts, edit an event's signup form, download
an event's roster as a CSV, and manage modules. In the staff sidebar an organizer
sees Events, Operations, Modules and Settings, plus Copilot feedback when the copilot is switched
on. The Overview dashboard is admin-only.

**Admins** can do everything an organizer can, plus: manage staff users (invite, change role,
deactivate, CCPA export and delete), enter and edit quarters, archive quarters, view the quarter
retrospective, grant and revoke orientation credits from the admin page, reorder a shift's or
slot's waitlist,
download the program-wide analytics CSVs, read the audit log, and change site settings.

**Organizers cannot reach admin-only pages.** Users, Audit Logs, Exports, Orientation Credits,
Quarters, and the quarter retrospective are admin-only. The navigation hides these links from
organizers and the server rejects the requests as well, so it is not just a hidden button. Site
settings are admin-only to change, and no organizer screen shows them.

**Organizers are not limited to their own events.** Check-in, undo, closing out a session, roster
reads and venue codes are all gated on being staff, not on who created the event — any organizer
can open any event's roster and run it. That is deliberate. The staff event list is global, nothing
in the app can transfer ownership of an event, and the old ownership rule meant an organizer
covering for a colleague could read an event's details and then be refused at its roster. The
boundary that matters is the admin-only page list above, not per-event ownership.

Two places where the same action is gated differently in different corners of the app, worth
knowing so an organizer isn't told the wrong thing: **duplicating an event** works for organizers
from the row of actions in Admin → Events, but the `Duplicate…` button on an individual event's own
page is shown to admins only. And **copilot feedback** is visible to organizers as well as admins,
not admin-only.

**The Help page is short, practical, and filtered by role.** Reach it from the account menu at the
top right of any staff page — the same menu that holds Settings and Logout. Each card answers one
common question in a paragraph. Admins get the full set, including how to invite a user, read the
audit log, export a CSV, handle a CCPA data request and deactivate someone who has left.
Organizers get a shorter page titled **Organizer Help** with only the cards they can act on:
checking volunteers in on the day, closing out a session once it's over, promoting someone off the
waitlist, why the admin site is desktop-only, and who to contact about a backend problem. Cards
about admin-only tabs are hidden from organizers rather than shown and then refused. Help is not in
the sidebar — the account menu is the only way in.

The staff side of the app is **desktop-only by design**. Every page under `/admin` shows a
desktop-only banner below tablet width, because rosters and event forms need the width — the roster
page included, and Help too. The live roster does reach a phone, but through a separate page rather
than the `/admin` copy of it: an organizer standing at a school opens the **Today** page from the
staff menu and taps through to the session. The operations console and roster documents describe
that route.

Staff accounts are **deactivated, not deleted** — the Users page offers no delete. Deactivating a
user keeps their history and their ownership of past events, and they can be found again with "Show
deactivated" in the Users list and reactivated. One gap to know about: deactivation does not
currently end the account's ability to sign in — see the managing-staff-users document.

**A fourth role exists in the stored data, and it is not the volunteer identity.** If the
university's single sign-on is configured, a first-time SSO login creates an account with the role
**participant**. Those accounts are hidden from the Users list and can reach no staff page. They
are not how volunteers are represented — a volunteer who signs up for sessions is a separate kind
of record with no account and no role at all, described in the volunteers-and-identity document.
