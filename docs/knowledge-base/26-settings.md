# Settings

There are three different kinds of settings in the app: **site settings** that apply everywhere,
**event settings** that apply to one event, and each staff member's own **user settings**.

## Site settings (admin)

Site settings live on the settings card on the Overview page, which is admin-only. The card offers
exactly two switches:

- **Hide past events from public browse** — when on, events whose last slot has ended drop off the
  volunteer browse listing. Staff and organizer views always show past events regardless.
- **Show Audit Logs tab** — off by default. The Overview activity feed covers the common case, so
  the full audit log is opt-in.

**"Hide past events" only affects the browse listing.** A direct link to a past event still opens
normally with the toggle on, which is what you want — volunteers who bookmarked a session, or who
are following a link from an email, can still see what they signed up for.

**Two further site settings exist in the data but nothing reads them.** One is a default privacy
mode for how volunteer names appear, the other an allowed email domain for staff invitations. Neither
has a control anywhere in the app, and neither changes any behavior even if it is set: the public
event page always shows first name plus last initial, and staff invitations to any email domain are
accepted. Don't go looking for these switches, and don't rely on them for privacy or access control.

## Event settings

Each event carries its own settings, edited from the event page in Admin → Events:

- Title, description, location, visibility on the public browse page, the cap on how many slots one
  volunteer may take, the module, and the slots themselves — all editable after creation.
- **The signup form** — the event's own field list, which overrides the module's default.

**The school field does not save on an existing event.** It's in the form and it accepts what you
type, but the change is dropped on the way to the server, so the event keeps its original school. Set
the school when the event is created; if an existing event has the wrong one, the practical fix today
is to recreate it (duplicating it into the same week is the fast way).

**Signup open and close times are enforced, but there is no field for them.** When an event has a
window set, public signups outside it are refused with a message naming the window in Pacific Time.
Nothing in the event form sets that window, though — the only way one gets onto an event is
programmatically, or by being carried over when the event was duplicated from another. Most events
have no window at all, which means signups stay open until the event happens.

**The older 1-hour pre-session reminder is on for every event and can't be turned off from the UI.**
Each event carries its own on/off setting for that email and it defaults to on, but there is no
switch for it anywhere in the app. The reminders document lists which reminder emails exist.

## User settings

Each signed-in staff member has their own settings page, reached from **Settings** in the account
menu. On a desktop it opens inside the admin area so the sidebar stays put; on a phone it opens
standalone, because the admin shell is desktop-only. Both are the same page.

It's a single column of cards, top to bottom: who you're signed in as, **Your details** (display
name and optional university ID), **Notifications** (one switch — "Email me about my events", which
stops event email to you and doesn't touch what volunteers receive), Save, then **Password**, then
the copilot's memory of you, then a read-only **Account** block showing your email and role, and
finally a **Log out** button. The password form asks for your current password first, and changing it
signs out any other session using the account. Email and role are admin-changeable only, because
they're what identify you in the audit log.

**The copilot memory card is on this page too**, under "What the copilot has learned about you" —
including the button that clears it. It only appears when the copilot is switched on for the
installation. See the copilot document for what it keeps and why.

Nothing on this page is program-wide; it only affects the person signed in.

## Time

**Times you see and times volunteers are told are Pacific**, matching the single venue — displayed
times, reminder emails, signup-window messages, and check-in windows. There is no per-user timezone
setting. The background jobs that run on a clock are scheduled in **UTC**, though, which shifts the
ones people think of as nightly: the quarter archive runs at 03:30 UTC, which is early evening
Pacific, not overnight. The sweep that clears unconfirmed signups runs at the top of every hour, so
its timing rarely matters. That distinction only comes up when you're waiting for one of them.
