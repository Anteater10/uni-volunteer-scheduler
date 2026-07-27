# Managing staff users

Staff accounts — organizers and admins — are managed by admins in **Admin → Users**. Volunteers
never appear here, because volunteers have no account.

**Inviting a new staff member:** go to Users, click "Invite new user", and enter their name, email,
and role (admin or organizer). They receive an email with a link to sign in — no password is set by
you or by them at that point. **The invitation link expires in 15 minutes**, so send it when they're
ready to use it, and just re-invite if it lapses.

**Changing someone's role** is done from their row in the Users list. The role decides everything
about what they can reach: organizers cannot open Users, Audit Logs, Exports, Orientation Credits,
Quarters, or the quarter retrospective, and the server enforces that as well as the navigation
hiding the links.

**Deactivating a user who has left** stops them signing in but keeps their history and their
ownership of past events. Open their drawer and click Deactivate. Deactivated users are hidden from
the list by default — use "Show deactivated" at the top to find them again, and Reactivate to
restore access. Accounts are never destroyed by deactivation.

**CCPA data requests** are handled from the Users list. "CCPA Data Export" downloads everything the
system holds on that person. "CCPA Delete Account" permanently anonymizes their data. Both actions
are recorded in the audit log.

Every one of these actions — invite, role change, deactivate, reactivate, CCPA export, CCPA delete
— is written to the **audit log** with who did it and when.

A site setting can restrict staff accounts to a **single allowed email domain**, so invitations
outside your institution's domain are refused.
