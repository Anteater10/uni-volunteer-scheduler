# Managing staff users

Staff accounts — organizers and admins — are managed by admins in **Admin → Users**. Volunteers
never appear here, because volunteers have no account.

**Inviting a new staff member:** go to Users, click "Invite user", and enter their name, email,
and role (admin or organizer). They receive an email with a link where they **set their own
password** and are signed straight in — you never see or choose their password. **The invitation
link lasts 7 days.** If it lapses before they use it, don't try to re-invite: the account already
exists, so a second invite is refused with "A user with that email already exists". Point them at
**"Forgot password"** on the login page instead — it works even for someone who never set a
password.

**The invite email is sent on a best-effort basis.** The account is created first and the email goes
out afterwards; if sending fails, the account still exists. So a new user appearing in the list is
not proof they received anything. If someone says the invite never arrived, send them to "Forgot
password" on the login page — a re-invite is refused because the account already exists.

**Staff manage their own passwords.** A signed-in staff member changes their password from their
own Settings page — the form asks for the current password first, even though they're already
logged in, so that walking up to an unlocked laptop isn't enough to take the account. Changing it
signs out every other session. Passwords must be at least 8 characters.

**A staff member who is locked out uses "Forgot password" on the login page.** If the address
belongs to active staff, they're emailed a reset link that lasts **one hour**. The page always
reports the same thing whether or not the address has an account, so it can't be used to find out
who works here. Reset requests are limited to three per email address and ten per network address
per hour — and a request that trips the limit still reports success and sends nothing, which is why
"I asked for three resets and got no email" is expected rather than a fault.

**"Forgot password" also works for someone who never finished their invite.** An invite link and a
reset link land on the same set-password page, and the reset path doesn't care whether a password
was ever set — so it is the recovery route (re-inviting is refused, because the account already
exists). One trap: the email must match how it was originally typed. An account invited with
capital letters in the address has to be entered the same way at login, and a reset request for it
can silently never arrive. There is no in-app fix — the email on an account can't be edited by
anyone, and inviting the same address in different casing is refused as a duplicate — so the
working answer is to sign in typing the address exactly as it was invited. Invite new staff with
all-lowercase addresses to avoid this.

**Both kinds of link are single-use, and setting a password invalidates every other one.** Once
someone sets a password — by either route — every outstanding reset link and invite link for that
account stops working, including the one they just used. A second click on the same link is refused
with "This link has already been used or is no longer valid." So a staff member who asked for two
resets must use the newest email, and someone who completes their invite will find a reset link they
requested earlier now refused. Changing a password from the Settings page has the same effect on any
outstanding links. The fix is always to request a fresh one, never to hunt for the older email.

**Changing someone's role** is done from their row in the Users list. The role decides everything
about what they can reach: organizers cannot open Users, Audit Logs, Exports, Orientation Credits,
Quarters, or the quarter retrospective, and the server enforces that as well as the navigation
hiding the links.

**Deactivating a user who has left** hides them from the Users list, blocks their password resets
and invite links, and removes them from the last-admin safety count — their history and their
events stay intact. Open their drawer and click Deactivate; use "Show deactivated" at the top to
find them again, and Reactivate to restore access. Accounts are never destroyed by deactivation.
Be aware of one gap: **deactivation does not currently end their ability to sign in.** An account
that already has a password can still log in with it, and keeps its role, until that hole is
closed — so treat deactivating a departed staff member as bookkeeping, not as revoking access.

**Four guard rails stop an admin locking everyone out**, each of them refused with a clear message
rather than silently ignored. You cannot deactivate your own account, deactivate the last active
admin, demote your own admin account, or demote the last active admin. There is always at least one
admin who can still sign in.

**CCPA data requests** are handled from the Users list. "CCPA Data Export" downloads their account
record, their signups (matched by email), the audit-log entries they performed, and their
notifications — signup form answers and orientation credits are not part of the file. "CCPA Delete
Account" permanently anonymizes the **staff account** — name, email, and password are blanked — and
an admin cannot run it against their own account. A volunteer record under the same email is a
separate thing and is left untouched. Both actions are recorded in the audit log.

Every one of these actions — invite, role change, deactivate, reactivate, CCPA export, CCPA delete,
password set and password change — is written to the **audit log** with who did it and when.

**There is no email-domain restriction in force.** The settings table has a field for an allowed
email domain, left over from an earlier design, but nothing reads it and nothing in the admin UI
exposes it. An invitation to any address will be accepted, so treat who you invite as a matter of
care rather than something the app will catch.
