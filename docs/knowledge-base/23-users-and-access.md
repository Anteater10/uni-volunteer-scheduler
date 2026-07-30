# Managing staff users

Staff accounts — organizers and admins — are managed by admins in **Admin → Users**. Volunteers
never appear here, because volunteers have no account.

**Inviting a new staff member:** go to Users, click "Invite new user", and enter their name, email,
and role (admin or organizer). They receive an email with a link where they **set their own
password** and are signed straight in — you never see or choose their password. **The invitation
link lasts 7 days**; if it lapses before they use it, just re-invite them.

**The invite email is sent on a best-effort basis.** The account is created first and the email goes
out afterwards; if sending fails, the account still exists. So a new user appearing in the list is
not proof they received anything. If someone says the invite never arrived, re-invite them rather
than assuming the address was wrong.

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
was ever set — so either route gets them in. Re-inviting is still the tidier answer, but a reset is
not a dead end.

**Changing someone's role** is done from their row in the Users list. The role decides everything
about what they can reach: organizers cannot open Users, Audit Logs, Exports, Orientation Credits,
Quarters, or the quarter retrospective, and the server enforces that as well as the navigation
hiding the links.

**Deactivating a user who has left** stops them signing in but keeps their history and their
ownership of past events. Open their drawer and click Deactivate. Deactivated users are hidden from
the list by default — use "Show deactivated" at the top to find them again, and Reactivate to
restore access. Accounts are never destroyed by deactivation.

**Four guard rails stop an admin locking everyone out**, each of them refused with a clear message
rather than silently ignored. You cannot deactivate your own account, deactivate the last active
admin, demote your own admin account, or demote the last active admin. There is always at least one
admin who can still sign in.

**CCPA data requests** are handled from the Users list. "CCPA Data Export" downloads everything the
system holds on that person. "CCPA Delete Account" permanently anonymizes their data — and an admin
cannot run it against their own account. Both actions are recorded in the audit log.

Every one of these actions — invite, role change, deactivate, reactivate, CCPA export, CCPA delete,
password set and password change — is written to the **audit log** with who did it and when.

**There is no email-domain restriction in force.** The settings table has a field for an allowed
email domain, left over from an earlier design, but nothing reads it and nothing in the admin UI
exposes it. An invitation to any address will be accepted, so treat who you invite as a matter of
care rather than something the app will catch.
