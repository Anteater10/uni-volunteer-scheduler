# Roles and access — who can do what

The SciTrek scheduler has three roles: **volunteer** (participant), **organizer**, and **admin**.
Volunteers have no account at all. Organizers and admins are staff with real login accounts, an
email and a password, created by invitation from an admin.

**Volunteers have no account and never log in.** A volunteer is identified only by their email
address. They browse sessions at `/volunteer`, sign up, and then manage everything through magic
links emailed to them or by scanning the check-in QR code at the door. There is no volunteer
password, no volunteer dashboard, and no volunteer login page.

**Organizers** run events day to day. An organizer can create and edit events, generate and edit
slots, view rosters, check volunteers in, undo a mis-tapped check-in, close out a session
(marking attended or no-show), grant orientation credit at the door, promote someone off the
waitlist, send broadcasts, duplicate events, edit an event's signup form, and manage module
templates. Organizers see the Overview, Events, Operations, Modules, and Help sections.

**Admins** can do everything an organizer can, plus: manage staff users (invite, change role,
deactivate, CCPA export and delete), enter and edit quarters, archive quarters, view the quarter
retrospective, grant and revoke orientation credits from the admin page, download the CSV exports,
read the audit log, change site settings, and view copilot feedback.

**Organizers cannot reach admin-only pages.** Users, Audit Logs, Exports, Orientation Credits,
Quarters, and the quarter retrospective are admin-only. The navigation hides these links from
organizers and the server rejects the requests as well, so it is not just a hidden button.

**Organizers can only touch their own events.** Check-in, undo, resolve, and roster reads all
verify that the organizer owns the event. An organizer cannot read another organizer's roster or
venue code, or check in their volunteers. Admins bypass this and can act on any event.

The staff side of the app is **desktop-only by design**. Pages under `/admin` show a desktop-only
banner below tablet width, because rosters and event forms need the width. The exception is the
roster page, which is fully mobile-responsive because organizers use it on a phone at the
classroom door.

Staff accounts are **soft-deleted, never destroyed**. Deactivating a user stops them signing in
but keeps their history and their ownership of past events. A deactivated user can be found again
with "Show deactivated" in the Users list and reactivated.
