# Settings

There are three different kinds of settings in the app: **site settings** that apply everywhere,
**event settings** that apply to one event, and each staff member's own **user settings**.

## Site settings (admin)

Site settings are edited from the settings card on the Overview page. They are admin-only.

- **Default privacy mode** — how volunteer names appear on the **public** event page: full names,
  initials only, or anonymous. This does not affect the staff-side roster, which always shows full
  names because initials make check-in harder at the door.
- **Allowed email domain** — restricts staff accounts to one email domain, so invitations outside
  your institution are refused.
- **Hide past events from the public page** — when on, events whose last slot has ended drop off the
  volunteer browse page. Staff and organizer views always show past events regardless.
- **Show the Audit Logs tab** — off by default. The Overview activity feed covers the common case,
  so the full audit log is opt-in.

## Event settings

Each event carries its own settings, edited from the event page in Admin → Events:

- Title, description, location, and its slots — all reconfigurable after creation without going back
  to the events list.
- **Signup open and close times** — public signups outside this window are refused, with a message
  naming the window in Pacific Time.
- **A cap on how many slots one volunteer may take** within the event.
- **Visibility** — whether the event shows on the public browse page.
- **The signup form** — the event's own field list, which overrides the module's default.
- **Whether the short pre-session reminder is enabled.**

## User settings

Each signed-in staff member has their own settings page at `/settings`, reached from the account
menu. That's where they manage their own profile and password rather than anything program-wide.

**Time is Pacific throughout the app.** Reminders, signup windows, check-in windows, and displayed
times are all Pacific, matching the single venue — there is no per-user timezone setting.
