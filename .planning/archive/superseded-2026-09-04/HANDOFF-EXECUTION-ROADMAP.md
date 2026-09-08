# Handoff execution roadmap

**Written:** 2026-07-28 · **Verified against:** `fix/ai-copilot` (PR #52)
**Audience:** whoever executes this. Written to be worked through top to bottom.

Every `file:line` below was read on `fix/ai-copilot`. If you are on a branch
without PR #51 and #52 merged, line numbers in `backend/app/config.py`,
`backend/app/copilot/**` and `docs/knowledge-base/**` may drift; everything else
is untouched by those PRs.

---

## Contents

- [How to read this](#how-to-read-this)
- [What "zero known issues" means](#what-zero-known-issues-means)
- [Timeline](#timeline)
- [Stage 0 — Close the blind spots](#stage-0--close-the-blind-spots)
- [Stage 1 — Broken now (P0)](#stage-1--broken-now-p0)
- [Stage 2 — Silently wrong](#stage-2--silently-wrong)
- [Stage 3 — Volunteer record, Phase B, cleanup](#stage-3--volunteer-record-phase-b-cleanup)
- [Stage 4 — Runtime verification](#stage-4--runtime-verification)
- [Stage 5 — Real conditions](#stage-5--real-conditions)
- [Stage 6 — Hardening (devops)](#stage-6--hardening-devops)
- [Dependency spine](#dependency-spine)
- [Blocked on Andy](#blocked-on-andy)
- [Where the risk is](#where-the-risk-is)
- [If you have to cut](#if-you-have-to-cut)

---

## How to read this

**Confidence markers.** Trust these; they are not decoration.

- ✅ **verified** — reproduced or read directly during the audit session. Fix with confidence.
- ⚠️ **reported** — found by an audit, quoted with `file:line`, *not* independently reproduced. **Confirm before fixing.** Three audit runs died mid-execution and were relaunched, so single-sourced claims deserve mild suspicion.
- ⛔️ **blocked** — needs a decision from Andy. See [Blocked on Andy](#blocked-on-andy).

**Effort:** S = under an hour · M = a few hours · L = a day or more.

### Two things to know before you start

**1. Most of this is propagation, not design.** The correct implementation
usually already exists in the repo:

| Broken | Correct version already present |
|---|---|
| `_fmt_when` prints raw UTC | `_fmt_slot_time`, 30 lines above it |
| `ui/Modal` can't scroll on a phone | `FormModal` has `p-4 max-h-[92vh] overflow-y-auto` |
| 4 copilot tools use ISO weeks | `create_module_from_template` converts correctly |
| `SideDrawer`/`FormModal` have no focus trap | `useFocusTrap` works; `ui/Modal` uses it |
| 9 tables don't paginate | `components/admin/Pagination.jsx` |
| Exports fail silently | `AdminEventPage.jsx:325-338` does it right |

This is why the fix work is fast. Copy what's there.

**2. The test suite is not evidence of correctness.** Backend 1037 pass,
frontend 409 pass, zero failures. **4 of 4** bugs verified by hand were hidden by
a test mocking the exact broken seam:

| Bug | The mock that hid it |
|---|---|
| `api.slots` doesn't exist | `EventsSection.test.jsx:489-491` mocks the namespace |
| Confirm-approve never parks the call | every test calls `store_pending` itself |
| Embedding provider default is wrong | tests monkeypatch `_get_embedding_provider` |
| Agent loop has no LLM adapter | tests monkeypatch `_get_agent_llm` |

Treat green as **"no regressions,"** never as "it works."

---

## What "zero known issues" means

You cannot prove software has no issues. You can close the four ways an issue
stays unknown:

| How issues hide | What closes it | Stage | Status |
|---|---|---|---|
| Nobody read that code | Audits | — | **mostly done** |
| A test mocked the broken part | Mock-honesty sweep | 0 | **not done** |
| Nobody ever ran it | Runtime walkthrough | 4 | **not done** |
| Only breaks under real conditions | Load, real devices, real mail clients | 5 | **not done** |

One of four is done. Every P0 in this document came from *reading code*, and
every one was invisible to 1446 passing tests. **Nobody has clicked through this
application during the audit at all.**

So: zero known issues = all items fixed **+ blind spots closed** **+ verified in
a browser, not a test runner.**

---

## Timeline

| Target | Time | What you get |
|---|---|---|
| **Handoff-ready** | ~1 week | Stages 0–3. No core flow throws or lies. |
| **Zero known issues** | ~3 weeks | Stages 0–5. Verified at runtime. |
| **Production-hardened** | +1 week (devops) | Stage 6. |

Zero known issues is **not reachable in one week.** The fixes are fast — Stage 1
is mostly one-liners. *Verification* is the cost, and verification is the entire
difference between "I fixed the list" and "I know it works."

If one week is immovable: do Stages 0–3, hand off, and carry Stage 4 as a
documented known-gap. That is a respectable handoff. Claiming Stages 4–5 happened
when they didn't is what becomes an incident.

---

# Stage 0 — Close the blind spots

**~1 day, mostly parallel. Do this before writing any fix code.**

Stage 0 can *change Stage 1's contents*. Finding a fifth P0 after Day 1 is
declared done is how a plan loses credibility.

### S0.1 — Mock-honesty sweep ⛔️ **largest single gap** · L
The audit that would have answered "how many more bugs are hidden by mocks" was
started and cancelled. Re-run it. Scope:
- tests that monkeypatch/mock the exact seam they claim to test
- hollow assertions (`assert x is not None`, status-code-only checks)
- the 11 skipped backend tests — what each one hides
- fixtures encoding wrong assumptions (**suspected:** ISO `week_number` values where the real range is 1–11, which is why K7 passes tests)

Record is 4 for 4. This sweep is the only thing between you and a fifth.

### S0.2 — Establish whether e2e runs at all · M
`e2e/cross-role.spec.js` claims 5 scenarios × 6 browser projects. Unknown:
whether it runs today, what stack/seed data it needs, and whether specs assert
real outcomes or only that pages render. Until answered, **e2e is not evidence.**

### S0.3 — Reproduce every ⚠️ item · M
~35 items below are audit-reported, not personally verified. Confirm each
`file:line` before fixing. Cheap, and stops you "fixing" what isn't broken.

### S0.4 — Data-integrity audit — **nobody has done this** · L
K3 (a unique constraint permitting a permanently-broken state) was found by
accident while chasing something else. Assume siblings exist. Look at:
- constraints that permit invalid states
- `Event.location` vs `Slot.location` vs `Event.school` — which is authoritative? Emails print `Where: TBD` when `Event.location` is empty (`emails.py:84,92`), and the event detail page never displays it. ⚠️ unverified how often it's populated
- orphans: cancelled signups still holding `slot.current_count`; `SentNotification` rows after `expire_pending_signups` hard-deletes
- the `alembic` downgrade `DuplicateObject` bug — confirm it really is downgrade-only
- whether any migration has run against production-shaped data

### S0.5 — Get the four blocked answers ⛔️
See [Blocked on Andy](#blocked-on-andy). Nothing downstream closes without them.

**Gate:** Stage 1's list is final; no further P0s expected from code reading.

---

# Stage 1 — Broken now (P0)

**~1 day.** Six items. Five are one-to-three-line fixes. Do all before anything else.

### K1 — Admin cannot add, edit or delete event slots ✅ · S
`api.slots` **does not exist.** `lib/api.js` exports slots only as flat keys —
`createSlot` :561, `updateSlot` :562, `deleteSlot` :563. There is no `slots:` key
in the exported object. But `applySlotDiff` calls:

```js
// pages/admin/EventsSection.jsx
1013:  api.slots.create(eventId, slotFormToApiPayload(s))
1019:  api.slots.update(s.id, slotFormToApiPayload(s))
1023:  api.slots.delete(id)
```

and it runs from the event save handler at `:1080`.

**Result:** `TypeError: Cannot read properties of undefined (reading 'create')` on
every slot change. **This is the core admin task and it is entirely broken.**

**Fix:** add a `slots:` namespace to `api.js`, or point the three call sites at
the flat keys. Then fix `EventsSection.test.jsx:489-491`, which mocks a shape the
real module never had — that mock is the only reason this shipped.

### K2 — A default deploy gets a copilot that retrieves nothing ✅ · S
`config.py:109` defaults `corpus_embedding_primary = "jina"` with
`jina_api_key = ""` (:115). Every chunk in the DB is `local-bge` — confirmed 147
of 147. `retrieval/hybrid.py:54,63` filters `embedding_provider = :provider` on
**both** the dense and the FTS CTE, so both halves return zero rows.

Not "degrades to keyword search" — returns **nothing**, silently, and the model
answers uncited from general knowledge.

Works locally only because `backend/.env` sets `local`, and that file is
gitignored. Note the string mapping: config `'local'` → provider `name =
"local-bge"` (`corpus/embeddings.py:111`) → matches the DB. Config `'jina'`
matches nothing.

**Fix:** default to `local`, **and** add a startup check comparing the setting
against `SELECT DISTINCT embedding_provider FROM corpus_chunks` so it can never
be silent again.

### K3 — Cancelling permanently bars a volunteer from that slot ✅ · M
- `models.py:346-348` — `UniqueConstraint("volunteer_id", "slot_id")`, no status predicate
- `check_in_service.py:50` — `SignupStatus.cancelled: set()` — terminal, no transitions out
- cancel sets status rather than deleting the row (`public/signups.py:252`)

Cancel → sign up again → `IntegrityError` → 409 → the UI says *"You've already
signed up for this session with that email — check your inbox for the
confirmation link"* (`EventDetailPage.jsx:973`). False, and there is no link to
check. `cancellation.html:10` promises the opposite: *"you can sign up again if
slots are available."*

**Fix:** make the constraint status-aware (partial unique index excluding
`cancelled`), or allow `cancelled → pending` and reuse the row — either needs a
`check_in_service` transition and a `current_count` bump. **Also send the
cancellation email**: `emails.send_cancellation` and `cancellation.html` already
exist and are wired only to the admin path (`admin.py:932`). Volunteer-side
feedback today is a toast that auto-dismisses in 3500ms.

This is the one bug guaranteed to generate mail to `chem-scitrekmanager@ucsb.edu`.

### K4 — Nine emails print raw UTC timestamps as the shift time ✅ · S
```python
# emails.py:68-69
def _fmt_when(slot: models.Slot) -> str:
    return f"{slot.start_time} to {slot.end_time}"
```
`Slot.start_time` is `DateTime(timezone=True)` (`models.py:294`), so this renders
`2026-04-16 16:00:00+00:00 to 2026-04-16 19:00:00+00:00`. Used by confirmation,
cancellation, reminder_24h, reminder_1h, reschedule, kickoff, pre_24h, pre_2h and
waitlist_promote (`emails.py:91,116,141,168,195,239`).

**Fix:** use `_fmt_slot_time` (`emails.py:30-41`) — it already converts to the
venue timezone and is currently used by exactly one email (`:455`). Add the date,
which `_fmt_when` omits entirely. **One swap fixes nine builders.**

### K5 — Two primary organizer actions are unreachable on a phone ⚠️ · S
`components/ui/Modal.jsx:34-48` — the backdrop has **no padding** and the panel is
`mt-[15vh]` with **no `max-height` and no `overflow-y-auto`**:
- `BroadcastModal.jsx:324-352` — Cancel/Send scroll off the bottom
- `ResolveEventModal.jsx:174` — Save unreachable on the End-orientation flow

Both are day-of organizer actions, performed on a phone, at a school.

**Fix:** copy `p-4` and `max-h-[92vh] overflow-y-auto` from `FormModal.jsx:28,35`.
✅ Confirmed `FormModal` has all three and `ui/Modal` has none. Below 448px
`ui/Modal` is also full-bleed with clipped corners.

### K6 — An admin on a phone has no working navigation destination ✅ · S
`components/Layout.jsx:22-29` — all three `adminNavItems` point at `/admin`,
`/admin/users`, `/admin/audit-logs`, every one inside the shell
`AdminLayout.jsx:217` gates behind `DesktopOnlyBanner` at 768px
(`DesktopOnlyBanner.jsx:19-24`). `organizerNavItems` still has `/admin/events`
(1 of 3 unfixed).

The comment at `Layout.jsx:8-15` **documents this exact bug being fixed** for
organizers. It was applied to two of three items in one of two lists.

**Fix:** point the admin mobile nav at phone-built surfaces
(`/organizer/today`, `/settings`). Note `/admin/audit-logs` is hidden by default
(`AdminLayout.jsx:152,158`), so that tab targets a surface the sidebar considers
off. Also ⚠️ `OrganizerRosterPage.jsx:155-156` sets the mobile roster's Back link
into the gated shell — an admin on a phone taps Back and hits the wall.

**Gate:** no known code path throws or returns nothing on the happy path.

---

# Stage 2 — Silently wrong

**~1.5 days.** Nothing here crashes. Everything here states something false.

### K7 — Every week-aware copilot tool asks an impossible question ✅ · M
`Event.week_number` is a **quarter-relative** week, clamped to the quarter length
(~11): `quarter_service.py:51-53` → `(d - q.start_date).days // 7 + 1`. The tools
pass an **ISO** week (1–52).

| Tool | Effect |
|---|---|
| `list_modules.py:24-29` | filters `week_number == 22` — row cannot exist. Always `{"modules": []}` |
| `signup_stats_for_week.py:31-38` | always the all-zeros payload (`:43-49`) → narrated as "no signups that week" |
| `find_understaffed_modules.py:63` | renders quarter week 3 as `2026-W03` — **January** |
| `find_module_by_name.py:41` | same |
| `signup_trend.py:71` | same |

`create_module_from_template.py:59-71` gets it **right**, with a comment
explaining the distinction. So a module the copilot creates is invisible to
`list_modules` on the very next turn.

**Fix:** convert at the tool boundary in one shared helper. Then check fixtures
(see S0.1) — suspected to use ISO values, which is why this passes tests.

### K8 — `max_signups_per_user` is settable, persisted, and never enforced ⚠️ · M
`models.py:251`; set in `EventsSection.jsx:628`; copied on duplication
(`event_duplication_service.py:350`). `create_public_signup` never reads it. A
volunteer can take 8 periods on an event capped at 2. An admin sets a limit and
believes it applies.

### K9 — Volunteers get four reminder emails; the opt-out covers two ⚠️ · S
Two pipelines both on beat (`celery_app.py:542-566`) with **different dedup keys**
on `sent_notifications(signup_id, kind)`, so both fire:
- `send_reminders_24h` every 300s → kind `reminder_24h` (`celery_app.py:285-315`)
- `check_and_send_reminders` every 900s → kind `reminder_pre_24h` (`reminder_service.py:171`)

Plus `reminder_1h` and `reminder_pre_2h`. Four nudges where
`ReminderPreferencesCard.jsx:91-92` promises three.

And the legacy pair never checks preferences: `reminder_service.send_reminder`
checks `prefs.email_reminders_enabled` (`:225-227`), but `send_reminders_24h`/`_1h`
filter only on status and `reminder_*_sent_at IS NULL`
(`celery_app.py:299-309,341-353`). **Turning reminders off still delivers the 24h
and 1h emails.**

**Fix:** drop `send-reminders-24h` and `send-reminders-1h` from `beat_schedule`
— `check_and_send_reminders` already covers kickoff/24h/2h. One edit fixes the
double-send **and** the broken toggle.

### K10 — Past slots stay bookable ⚠️ · S
`public/events.py:61-127` (`_build_event_response`) returns every slot with no
`end_time` filter; `get_event` (:189) applies no visibility filter.
`EventDetailPage.jsx:1089-1093` compares only against `signup_open_at` /
`signup_close_at`, both nullable. `create_public_signup`
(`public_signup_service.py:48-69`) checks only the event window, never whether the
slot has ended. An event whose Monday periods have passed still renders live
Sign-up buttons, and the signup succeeds.

The `HIDE-01` filter (`public/events.py:166-179`) only hides an event from the
*list* once its **last** slot ends, and only when `hide_past_events_from_public`
is on.

### K11 — Error branches that render first-run setup cards ⚠️ · M
- **`QuartersManager.jsx:257-263` has no `listQ.error` branch.** On a failed fetch `rows = []` (:90), so :215 renders the "Enter your quarters" setup card and :260 says *"No quarters yet — add the current quarter to unlock scheduling."* An admin who already entered quarters is told to re-enter them.
- `AdminEventPage.jsx:499-513` — `formSchemaQ` has no error branch; on failure `schema = []` and the card asserts *"None yet — name, email, and phone are always collected."* A false claim about the live signup form.
- `EventsSection.jsx:550-554,766-780` — `modulesQ` error unhandled; the required Module dropdown silently shows only the placeholder and submit blocks with "Pick a module", with no hint the fetch failed.
- `AuditLogsPage.jsx:166-169`, `OrientationCreditsSection.jsx:89` — `actorsQ`/`templatesQ` errors unhandled; filter dropdowns render empty, unexplained.

### K12 — Exports fail silently ⚠️ · S
`AuditLogsPage.jsx:171-173` calls `downloadBlob` with no `await` and no
`try/catch`; it is async and throws on non-2xx (`api.js:155,167-171`). A failed
export is an unhandled rejection and the button appears dead. Same bug ×9 in
`ExportsSection.jsx:60`, which also has no success toast and (`:72-73`) an error
state with no Retry. `AdminEventPage.jsx:325-338` does it correctly — copy that.

### K13 — Destructive actions with no confirmation ⚠️ · S
- **`UsersAdminPage.jsx:578-586`** — `variant="danger"` **Deactivate** → `:303` → `deactivateM.mutate`. Revokes someone's login, immediately, in the same drawer as a **type-to-confirm** CCPA delete (`:615-666`). Worst inconsistency in the app.
- **Clone event** (`EventsSection.jsx:1194-1199`) — creates a live event on one click, and has no `disabled={cloneM.isPending}`, so a double-click creates two.
- **Grant orientation credit** (`AdminEventPage.jsx:743-744`) — a permanent grant, one unguarded tap, while `ResolveEventModal.jsx:128-132` tells organizers credit is revocable only by an admin.
- `UserSettingsPage.jsx:210-212` — **Log out** fires immediately while the same page holds a dirty profile form (:153-157 shows "You have unsaved changes").

✅ Correctly gated already: event delete, signup cancel, end slot/event, module
archive, credit revoke, quarter archive/delete.

### K14 — The most destructive action has the weakest dialog ⚠️ · S
Delete event — event + slots + signups — is guarded by
`EventsSection.jsx:978-1003`, a bare `<div className="fixed inset-0 z-50">` with
**no `role="dialog"`, no `aria-modal`, no Escape handler, no focus trap, no
backdrop-click close.** Meanwhile `ui/Modal` — which has all of those — guards
*module archive*.

Also: `AdminEventPage.jsx:719,757` are the only two `window.confirm` sites in the
codebase, and `:757` cancels a volunteer's signup. `TemplatesSection.jsx:375,380`
collect form input via `window.prompt` ×2.

### K15 — One Escape keypress discards unsaved work ⚠️ · S
`lib/useFocusTrap.js:28-34` calls `preventDefault()` but **not
`stopPropagation()`**, and its listener bubbles; `SideDrawer.jsx:25` listens on
`window`. So a `Modal` opened inside or alongside an open `SideDrawer` closes
**both** on one Escape:
- `FormFieldsDrawer.jsx:379-390` — discards all unsaved `workSchema` edits
- `TemplatesSection.jsx:714` (archive confirm over the edit drawer)
- `UsersAdminPage.jsx` (CCPA modal over the edit drawer)
- `OverviewSection.jsx:359` → `QuartersManager` archive/delete/date-change modals

✅ `useFocusTrap` has exactly **one** consumer: `ui/Modal.jsx:13`. `SideDrawer`
(6 sites) and `FormModal` (3 sites) — where every long admin form lives — have no
trap and no focus restore, so Tab escapes behind the overlay and closing drops
focus to `<body>`.

**Gate:** no known surface states something false.

---

# Stage 3 — Volunteer record, Phase B, cleanup

**~3 days.**

## 3a. The volunteer's durable record

For an account-less product **the email *is* the app** between signup and
arrival. It is the least-finished surface in the codebase.

### K16 — The manage link in every reminder is a dead end ⚠️ · M
`emails.py:227` builds `f"{base}/signup/manage?signup_id={signup.id}"` — **no
token.** The comment at `:223-226` admits only the hash is stored.
`ManageSignupsPage.jsx:62` reads **only** `token`, and with none renders (:92-104)
*"We couldn't load this page — check your connection and try again"*: a network
error for a missing-credential problem.

✅ Worse: `reminder.html` (all 10 lines) contains **no `$manage_url` at all** —
only the plain-text bodies include it (`emails.py:257,285,310`). HTML readers get
no self-service link in any reminder. `broadcast_service.py:289` returns the URL
with no token either.

**Fix:** issue a fresh `SIGNUP_MANAGE` token in `_manage_url_for_signup`
(`magic_link_service.issue_token` already returns the raw token — see
`public_signup_service.py:229`), add the link to `reminder.html`, and give
`ManageSignupsPage` a real missing/expired-token state with a "send me a new
link" action. Note `public/signups.py:87,224` already return
`"token invalid or expired"` and the UI never surfaces it.

### K17 — Expired magic link is a closed loop ⚠️ · M
`ConfirmSignupPage.jsx:56-72` collapses expired/invalid/missing into one message:
*"Magic links are good for 14 days. Open the event again and re-submit your
signup to get a new one."* Re-submitting hits the unique constraint → 409 →
*"check your inbox for the confirmation link"*, i.e. the link that just expired.
There is **no public resend endpoint.** `admin.py:902` exists but is staff-only
**and** for a `pending` signup falls into the `else` branch and sends a
**cancellation** email (`:932`).

**Fix:** rate-limited `POST /public/signups/resend`. **Depends on K3.**

### K18 — Pending signups hold a seat, get no email, then vanish ⚠️ · M
Created `pending` and immediately `slot.current_count += 1`
(`public_signup_service.py:212-220`). Reminders require `confirmed`
(`celery_app.py:303`), so no kickoff, no 24h, no 2h. At 14 days
`expire_pending_signups` (`celery_app.py:492-535`) **hard-deletes** the row with
no email. Nothing ever nudges them to confirm.

And `signup_confirm.html:12` says *"If this wasn't you, please ignore this email
— no signup will be created without confirmation."* Factually wrong: the row
exists and is holding a seat.

### K19 — Cancel, swap and waitlist tell the volunteer nothing durable ⚠️ · M
- cancel sends no email (K3)
- `services/swap_service.py` contains **no** `send_email`/`delay` call at all; `reschedule.html` exists and is wired only to the admin move path (`admin.py:897`)
- waitlist position feeds the manage page (`ManageSignupsPage.jsx:292-299`) and a toast, but the confirmation email lists slots with **no waitlist marker** (`emails.py:450-457`) — a waitlisted volunteer's only durable record says they signed up, with no hint they're #4
- `waitlist_promote` reuses `confirmation.html` verbatim with only the subject changed (`emails.py:337-343`), so a promotion reads as a duplicate confirmation

### K20 — Every volunteer email is branded for the wrong product ✅ · S
`email_templates/base.html` has `TODO(brand)` ×2 (:9,:11) and `TODO(copy)` (:18),
and brands everything **"University Volunteer Scheduler"** (:12). Everything wraps
in it (`emails.py:64-65`), so **every** email is mis-branded. `Layout.jsx:94`
renders "Volunteer Scheduler" on every public page.
`OrientationWarningModal.jsx:45,71,76` writes "Sci Trek" (two words).

`emails.py` also carries `TODO(copy)` at :154,:181,:376,:404 and `TODO(brand)` at
:379,:390; the legacy `send_magic_link` path still says *"This link expires in 15
minutes"* (:392), which matches no live TTL.

Template status: `signup_confirm.html` is the **only complete one** (SciTrek
branded, correct 14-day TTL) — and its :12 is factually wrong (K18).
`confirmation.html`, `cancellation.html`, `reminder.html`, `reschedule.html` all
carry `TODO(copy)` at :1.

### K21 — The 2-day cancellation notice does not exist in the codebase ✅ · S copy / M enforce
Zero grep hits for `2 day|two day|48 hour|notice_days|cancellation_notice` across
all of `backend/app` and `frontend/src`. Not enforced in `cancel_signup`, not in
the cancel modal (`ManageSignupsPage.jsx:364-366`), not in `cancellation.html`,
not in the event description (`EventDetailPage.jsx:574-581`).

Add to: the cancel modal, the pre-24h email, and the event description.

> ⛔️ **Blocked:** whether a late cancellation or no-show carries any consequence.
> Deliberately omitted from `docs/knowledge-base/35-cancellation-notice.md`
> rather than guessed. That document cannot be finished without an answer.

### K22 — Copy that contradicts the server ⚠️ · S
- `SelfCheckInPage.jsx:38,140` says check-in opens **15 minutes** before; `check_in_service.py:28-29` is **30**. (`EventCheckInPage.jsx:9-11` is correct.)
- **No email contains a check-in link.** Routes exist (`App.jsx:97-98`) but are reachable only from an organizer-displayed QR (`CheckInQRModal`). A volunteer standing outside the van cannot self-check-in without the organizer's screen.
- `OrientationWarningModal.jsx:93` — *"I haven't — show me orientation events"* → `handleOrientationNo` (`EventDetailPage.jsx:1054-1059`) sets `highlightOrientation` and returns to browse. But the advisory variant only renders when the event has **no** orientation slots (`:1512`), so it returns to the same page with nothing to highlight. The label promises a search the app can't perform.
- Volunteers have **no way to see their own orientation credit** before hitting the blocking modal. `/public/orientation-status` exists (`public/orientation.py:27`) and `api.public.orientationStatus` (`api.js:414/615`) is called from nowhere.

## 3b. Phase B — make the agent layer real

Everything here is code that **has never executed.** ✅ `_get_agent_llm` raises
`NotImplementedError` (`router.py:582-594`) and `copilot_agent_loop_enabled` is
off, so the whole tool layer is reachable only through a monkeypatch.

> **Do K7 first.** Wiring the loop to tools that always return empty makes it
> worse, not better.

### K23 — Flag-on returns a bare 500 ✅ · S
`router.py:559` calls `_get_agent_llm()` synchronously inside the endpoint,
before the `StreamingResponse` is built. So the flag is not "off by default,
harmless" — the next dev flips it and every message returns HTTP 500, with the
drawer showing `Stream failed: HTTP 500` and no clue. Return 503 with a real
message, or refuse at boot. ~10 lines.

### K24 — B0.1: the adapter · L
Structured tool-calling adapter behind `_get_agent_llm`. All candidate free
models must support `tools` — the filter documented in `config.py` is mandatory
for exactly this reason.

### K25 — B0.2/B0.3: make confirmation work end to end ✅ · M
- `agent/loop.py:149-156` yields `ConfirmationRequestEvent` and `return`s — it **never calls `store_pending`.** `store_pending` is only called from `agent/tools/base.py:87-94` inside `invoke()`, which the live loop does not use (it uses `_begin`/`_complete`). So `POST /confirm/{id}` with `approved=True` → `_PENDING.get(call_id)` is `None` → `ConfirmationNotFound` → **404.** Reject works (it only stamps the audit row, `router.py:761-771`); **approve never has.**
- Even fixed, the turn dead-ends: `loop.py:156` returns, `_agent_sse_stream` (`router.py:637-659`) persists an assistant message with `content=""` and emits `done`, and `CopilotDrawer.decide` (`:132-151`) throws the response away — it only deletes the card. **The user clicks Confirm, the card vanishes, and nothing is ever said about whether it worked.** The LLM never learns the result either, so it can't continue ("I moved them, here's the new roster"). There is no resume-the-turn path anywhere.
- Replace the in-process `_PENDING` dict with Redis/DB (B0.3) so pending calls survive a worker restart.

Then **delete the hand-parking** from `test_router_confirm.py:86,131,184` so tests
exercise the real path.

### K26 — Write tools that report success without acting ✅ · S
```python
# send_reminder_email.py:32-38   nudge_understaffed_module.py:33-35
def _dispatch(email: str, template: str) -> bool:
    """Side-effect seam. Tests monkeypatch this; prod wiring is TBD."""
    return True
```
The tool then reports `sent_count: 47` through a confirmation card the user just
approved. **A stub that lies about success is worse than one that raises** — and
this is the one place where "unfinished" is indistinguishable from "working" at
the UI.

⚠️ And `nudge_understaffed_module.py:50-59` builds recipients as "any Volunteer
with any non-cancelled signup anywhere in scope" — for an admin, **the entire
volunteer table.** `module_id` is used only to look up the title; the docstring
(:9-11) admits no recipient policy was pinned. Harmless while `_dispatch` is a
no-op; **a mass-mail incident the day someone wires SMTP.**

> **Fix the recipient set before wiring SMTP.** Use the **below-6** understaffed
> threshold.

### K27 — Tool-layer correctness ⚠️ · M
- `find_understaffed_modules.py:40-42` — **no date/week/quarter filter at all.** Returns every historical module that ever ran under capacity, plus every zero-slot event (`fill_rate = 0.0` when `slots_total == 0`, :60 — so skeleton events created by `create_module_from_template`, which creates no slots, are **always** flagged understaffed).
- `move_participant.py:52-59` — picks the destination slot with an unordered `.first()` and **ignores slot capacity.** Nondeterministic, can overfill.
- `create_module_from_template.py:96` and `move_participant.py:60` only `flush()`. They are durably committed only as a side effect of `audit_log.update_status`'s `db.commit()` (`audit_log.py:107`). If `update_status` raises `CallNotFound` it calls `db.rollback()` (:105) and **silently discards the tool's write.**

### K28 — A single bad tool argument kills the turn ⚠️ · M
`loop.py:158-173` catches handler exceptions, emits `ErrorEvent`, and `return`s.
Combined with `_iso_week.parse_iso_week` raising `ValueError` on anything not
`YYYY-Www` (`_iso_week.py:16`), `get_module_roster.py:53-55` passing an
LLM-supplied status string straight into an enum comparison (`LookupError` on a
typo), and schemas that don't enumerate valid values (`get_module_roster.py:84` is
just `{"type": "string", "nullable": true}`) — one model typo produces
`tool 'list_modules' failed: ValueError` and **ends the conversation turn.**

A ReAct loop should feed the error back as a tool result so the model can retry.

### K29 — The agent loop drops every guardrail ⚠️ · M
`prompts.py:22-52` is the careful prompt (KB-is-authoritative, don't invent, be
concise) and is what `create_session` persists as message #1
(`router.py:174-195`). But `loop.py:188-204` builds a **completely separate**
three-line prompt. With the flag on:
- none of rules 3–7 apply
- rule 1 ("you have NO live access to the database") is now false but is still in the persisted DB row and replayed by `/sessions/{id}` — **session history lies about what the model was told**
- `system_prompt_hash` on the session row describes a prompt that wasn't used, so Phase 35 eval grouping is wrong for agent turns

### K30 — Token budget doesn't see agent turns ⚠️ · S
`guardrails.enforce_daily_token_budget` sums
`CopilotMessage.prompt_tokens/completion_tokens` (`guardrails.py:63-79`). But
`_agent_sse_stream` persists the assistant row with **no telemetry at all**
(`router.py:642-648` — no tokens, no `model_id`, no `latency_ms`), and
`tasks/extract_profile.py:46-50` records nothing. So the daily ceiling meters
only the non-agent chat path, while the ReAct loop (up to 6 tool calls plus a
summariser per turn) and every unattended extraction spend the same free-tier key
**off-books.**

### K31 — Turn profile extraction off until Phase B settles ⛔️ · S
An unattended Celery job on the **same free rate limit as chat** — it can 429 a
real user's message for reasons they cannot see.

⚠️ Also: `memory/extractor.py:150-177` persists whatever the LLM returns
verbatim, gated only by a HIGH-severity PII check. `MAX_PROFILE_WORDS = 500`
exists **only inside the prompt string** (:83) and is never enforced. So model
chatter ("Sure! Here is the updated profile:…"), a refusal, or a paraphrase gets
stored and then injected into every future session's system prompt via
`profile_block.load_profile_block`. `close_session` even enqueues extraction for
zero-message sessions (`router.py:249-253`), feeding the model `"(no messages)"`
and writing the reply. Users can view and wipe the profile
(`CopilotMemorySettings.jsx`, mounted at `UserSettingsPage.jsx:203-205`) but
cannot **edit** it or opt out — for model-generated prose about them, "edit" is
the missing affordance.

### K32 — The copilot drawer can trap the user ⚠️ · S
`CopilotDrawer.jsx:42-49` intercepts close and opens `SessionRatingModal` whenever
any assistant turn exists. The modal has no Skip by design
(`SessionRatingModal.jsx:6-9`), and `POST /sessions/{id}/rating` is insert-only,
409ing on a second submission (`router.py:892-895`). The drawer never unmounts
(`CopilotFab.jsx:34`), so `sessionId` and `messages` survive close/reopen.

Sequence: chat → close → rate → reopen → chat → close → modal → **409** →
`SessionRatingModal.jsx:53-55` throws → `onSubmitted` never fires → **the drawer
cannot be closed.** Reproducible in under a minute of normal use.

Related: `post_message` never checks `sess.closed_at` (`router.py:496-516`), so
post-close messages append to a closed, already-extracted session that
`sweep_idle_sessions` will never re-close.

### K33 — `/admin/feedback/*` is readable by organizers ⚠️ · S
`router.py:938,959` gate with `_require_admin_or_organizer`, not admin-only, and
`aggregates.bottom_messages` (`aggregates.py:131-163`) has no user filter. So any
organizer can `GET /api/v1/copilot/admin/feedback/bottom-messages` and read other
staff's verbatim assistant **and** user messages plus thumbs-down comments. The
nav item is admin-gated (`AdminLayout.jsx:84-87`), so it looks correct in the UI.

Listed here rather than in Stage 6 because it is a wrong-role **feature**
boundary, not a hardening nit.

## 3c. Dead weight, then consistency

Deletion first — it shrinks everything after it.

### K34 — Delete three dead pages; clears 29% of the copy debt ✅ · S
`pages/AdminDashboardPage.jsx`, `pages/PortalsAdminPage.jsx`, `pages/PortalPage.jsx`
have **zero references anywhere** in the codebase (verified by grep across all of
`frontend/src`, excluding their own definitions). `AdminDashboardPage` holds **14
of the 48** `TODO(copy)` markers and links to `/admin/portals`, which is not a
route and would 404. `PortalsAdminPage` contains a full delete-with-confirm flow
no user can reach.

⛔️ **Also decide: `/admin/imports`.** Eight live endpoints
(`admin.py:2230,2244,2266,2276,2288,2298,2314,2335`) for the CSV module-import
pipeline, with **zero references to `imports` anywhere in `frontend/src`.** The
surface was removed in `ae93606`. Delete the endpoints, or build the UI?

### K35 — Dead client and endpoint surface ⚠️ · M
~25 unused `api.js` exports: flat aliases shadowed by nested ones
(`listEvents`/`getEvent`/… :552-557, `adminListUsers`/… :587-591,
`getModuleTemplates`/… :660-663), `createSlot`/`deleteSlot`/`generateSlots`
(:561,563,564), event-questions CRUD (:570-573), `resendMagicLink` (:567),
portal attach/detach (:582,583), `admin.signups.promote/move/resend` (:729-731),
`admin.users.create/delete` (:708,710), `admin.notify` (:725),
`templates.bulkDelete` (:789), `listBroadcasts` (:692,841),
`public.orientationStatus` (:615), `public.checkInByEmail` (:636).

Backend with no UI — keep-or-cut each: per-event `attendance.csv`
(`admin.py:1292`), `notifications/recent` (:2352), **broadcast history**
(`broadcasts.py:97` — currently unviewable), admin promote/move/resend
(:690,816,902).

⚠️ Latent break: `state/authContext.jsx:38` calls `await api.register(payload)`
and exposes `register` through the context (:56). **No `register` exists in
`api.js` and no `/auth/register` route exists.** No caller today; breaks
instantly if one appears.

⚠️ `AdminLayout.jsx:198-202` passes `user` and `onSignOut` to `AdminTopBar`,
which accepts only `{crumbs, centerSlot}` (`AdminTopBar.jsx:12`). Both silently
dropped, and `handleSignOut` (:168-171) — the only code that navigates to
`/login` after logout — is **never called.**

### K36 — Tables ⚠️ · M
`components/admin/Pagination.jsx` has exactly **two** consumers
(`AuditLogsPage.jsx:359`, `TemplatesSection.jsx:657`); nine other tables ignore
it. **No table anywhere is sortable** (zero grep hits for `sortBy|setSort|onSort`)
and **none has a sticky header**, so on any long table the column headers scroll
away permanently.

Unbounded and most likely to hurt:
- `OrientationCreditsSection.jsx:278` — grows monotonically forever, one row per credit granted
- `EventsSection.jsx:1160` — `api.events.list()` with no limit, filtered client-side; highest-volume admin table

⚠️ `AuditLogsPage.jsx:163` passes `keepPreviousData`, a react-query **v4** option,
on v5 (`package.json:18`) — silently ignored, so every page change drops to the
skeleton instead of holding the previous page.

Also only `UsersAdminPage.jsx:215-219` gives its scroll container
`tabIndex={0} role="region" aria-label`; the other ten `overflow-x-auto` wrappers
are keyboard-unreachable scroll regions.

### K37 — Pick one of each ⚠️ · L
| Concern | Variants | Recommended winner |
|---|---|---|
| Overlays | **4** — `ui/Modal` ×13, `SideDrawer` ×6, `FormModal` ×3, hand-rolled ×2 | `ui/Modal` (only one with a focus trap) |
| Notifications | **3** — toast (20 files), ~18 component-local error states, ad-hoc banners | toast + `ui/ErrorState` |
| Page headers | **3** — `AdminPageHeader` ×8, `ui/PageHeader` ×10, raw `<h1>` ×3 | one; they differ in title size (30px vs 28px vs 24px) **and** action-slot API (`children` vs `action`) |
| Buttons | **2** — `ui/Button` ~200 sites, raw `<button>` ~57 | `ui/Button` |
| Date helpers | 3× `relativeTime`, 3× `fmtDateTime`, mixed locales | one module in `lib/` |

New event opens a `FormModal`, new module a hand-rolled div, edit module a
`SideDrawer`, archive module a `ui/Modal`, delete event a hand-rolled div —
**five overlay implementations reachable from two adjacent admin pages.**
`EventsSection.jsx` is effectively a parallel design system: 16 raw buttons and
four different button treatments, none of them `ui/Button`.

### K38 — Loading and empty states ⚠️ · S each
**Missing loading:** `EventsSection.jsx:1145-1146` (bare `<p>Loading…</p>` where
the table goes), `OrganizerDashboard.jsx:155-156`, `ExportsSection.jsx:58-63`
(9 panels, no pending state, button stays clickable through a slow CSV).

**Missing empty:** `OrganizerRosterPage.jsx:427` (zero signups renders nothing
after the progress bar; stats read `0/0`), `EventsSection.jsx:1154-1157` (same
"No events match." for a filtered miss and a genuinely empty first-run system,
with no create action — `AdminEventPage.jsx:568-572` does it properly),
`UsersAdminPage.jsx:212-213` (no body, no clear-filters action).

**Other:** `AdminRemindersPage.jsx:112-121` errors with no retry control.
`AuditLogsPage.jsx:175-182` — Copy-to-clipboard has an empty `catch {}` and no
toast, so where clipboard is denied it is a visible no-op.

### K39 — Fix the instruction files that teach wrong rules ✅ · S
- `CLAUDE.md:73` — says CSV module import is quarterly; that surface was removed
- `PRODUCT-BRIEF.md:31,342,343` — says orientation is a soft warning, not a hard block
- `.planning/DEPLOY-ROADMAP-v2.md:28,29,38` — repeats both, and references `ImportsSection.jsx` and `ProfilePage.jsx`, **both deleted**

The current, verified rules: orientation is a **hard requirement at signup time**
(must include an orientation slot in the same signup if no credit; advisory only
when the event offers no orientation slots); credit is permanent, keyed
`(volunteer_email, family_key)`; waitlist is FIFO auto-promoting straight to
confirmed; understaffed is **below 6 mentors**; cancellation notice is **2 days**;
there is **no CSV import** — events are created manually or by duplication.

This is part of *why* the copilot was wrong, and it misleads every new session
and any human reading the brief.

## 3d. Accessibility and motion

### K40 — Accessibility ⚠️ · S each
Highest impact first:

- **Error toasts are announced politely, or not at all.** `ui/Toast.jsx:19-21` hardcodes `role="status" aria-live="polite"` for **all** kinds including `error` — and error toasts are the only channel for 409-duplicate, slots-full and 429 (`EventDetailPage.jsx:952,974,982,986`), auto-dismissing after 3500ms (`state/toast.js:34`). Errors need `role="alert"` / `aria-live="assertive"` and should not auto-dismiss. Worse: the host returns `null` when empty (`Toast.jsx:13`), so the live region is **created in the same tick as its content** — screen readers commonly miss that, meaning toasts are likely never announced. Needs a persistently-mounted wrapper. (Behaviour with real AT: unverified.)
- **Toasts are keyboard-inaccessible** — `Toast.jsx:23` puts `onClick` on a plain `div`: not focusable, no key handler, no dismiss button.
- **Focus trap + restore on `SideDrawer` and `FormModal`** (K15).
- **Mouse-only row activation:** `UsersAdminPage.jsx:235-243` — `<tr onClick>` with no `role`, `tabIndex` or `onKeyDown`, **and no other affordance in the row.** Opening the edit drawer is mouse-only. (`TemplatesSection.jsx:583` and `AuditLogsPage.jsx:306` have real buttons as fallback.)
- **No focus move to the first invalid field** on submit (`EventDetailPage.jsx:997-1001`); the four identity fields (`:1403-1447`) and every dynamic field (`renderFormField` :863-890) pass neither `aria-invalid` nor `aria-describedby`. `SelfCheckInPage.jsx:215-222` does it correctly — copy that.
- **`EventsSection.jsx` `EventForm`:** every `<label>` is unassociated — no `htmlFor`, input is a sibling (`:661-670,679-695,706-725,765-770,866-925`). `aria-label` covers SR users, but **clicking a label doesn't focus its field** on the app's longest form. `NewModuleDialog` (`:497-517`) has neither `htmlFor` nor `aria-label` — effectively unlabeled. The Events search input (`:1128`) has only a placeholder.
- **`index.css` has no focus rules at all** (71 lines, no `:focus-visible`, no `outline`). Focus styling is per-component: `focus-visible` ring on `ui/Button`/`Input`/`Chip`, plain `focus:` in six places (fires on mouse click too), and **nothing** on ~57 raw buttons.
- **Tabs are decorative ARIA:** `OperationsPage.jsx:56-79` and `OrganizerDashboard.jsx:128-152` declare `role="tablist"`/`role="tab"`/`aria-selected` with **no `role="tabpanel"`, no `aria-controls`, no `id`, no arrow-key handler.** AT announces "tab, 1 of 4" and arrow keys do nothing.
- **36×36px tap targets** at `ResolveEventModal.jsx:145,157` — the per-volunteer marking control, on a phone, with `gap-1` (4px) between them.
- No skip-to-content link (`Layout.jsx:89-155`). `ui/Modal` has no `aria-describedby` (`:38-49`), so destructive-consequence body text isn't in the description.
- `DesktopOnlyBanner.jsx:5` uses `role="status"` for a static page-replacement message — it will be announced as a live update on every resize past 768px.

✅ **Already good, don't regress:** no unlabeled icon-only button anywhere (all
have `aria-label`); `useFocusTrap` is correct and complete; availability badges
pair colour with text (`EventDetailPage.jsx:177-208`); capacity is stated
numerically before the bar (:289); selection count is in an `sr-only`
`aria-live="polite"` region (:1125); tap targets are consistently `min-h-11` on
public pages.

### K41 — Motion ✅ · M
26 of 124 `.jsx` files mention any transition, and **no animation library is
installed.** This starts from near zero, not from polishing existing motion.

Do it last and cheaply. Pick one approach (CSS + Tailwind is sufficient) and
apply it only where motion carries meaning: modal/drawer enter-exit, toast
in-out, list add/remove after a mutation, skeleton→content. Respect
`prefers-reduced-motion`. **Resist animating anything else this close to
handoff.**

### K42 — Mobile leftovers ⚠️ · S
- **Bottom-nav overlap.** `ui/BottomNav.jsx:12` is `fixed bottom-0 … md:hidden` with `min-h-14` (56px) plus `env(safe-area-inset-bottom)`. `Layout.jsx:153` gives `pb-20 md:pb-8` **only on non-wide routes**; `/organizer/*` and `/admin/*` are `wideRoute` (:55) and get `pb-8`. On `/organizer/today` that is 32 + 24 = 56px against a ≥56px nav plus safe-area — **zero-to-negative clearance**; the last card sits under the nav.
- **Timezone drift.** `SignupSuccessCard.jsx:33,40`, `EventCheckInPage.jsx:17` and `SelfCheckInPage.jsx:86,192` call `toLocaleTimeString` with **no `timeZone`** (and coerce naive strings by appending `"Z"`), while the page they came from pins `America/Los_Angeles` (`EventDetailPage.jsx:78`) and says *"Times shown in Pacific Time"* (:1168). A student travelling or with a mis-set clock sees one time on the page and a different one on the confirmation card.
- `useIsDesktop` listens only to `resize` (`DesktopOnlyBanner.jsx:25`) — no `matchMedia`/`orientationchange`. iOS Safari does fire resize on rotate, so probably fine (unverified on device).

**Gate:** feature-complete against everything currently known. **This is
handoff-ready.** If the week is immovable, stop here and carry Stages 4–5 as
documented gaps.

---

# Stage 4 — Runtime verification

**~4 days.** ⛔️ **This is the stage that finds new things.** Nothing in Stages
0–3 involves running the application.

### S4.1 — Walk every page in a browser · L
All 40+ routes from `App.jsx`, as each role, on desktop **and** a real phone
viewport. For each: does it load, does it show real data, do the controls do what
they claim. Playwright MCP is available — drive it, screenshot each state, diff
against expectation.

**This is where "confusing" and "in the wrong place" get found.** Code review
structurally cannot find those.

### S4.2 — Walk every flow end to end, with real side effects · L
Not unit-tested paths — actual journeys, with Mailpit open:
- browse → slots → identity → confirm → reminder → manage → cancel → **re-signup** (K3)
- orientation-required block → pick orientation → signup → credit persists to a later event
- waitlist → someone cancels → FIFO promote → promotion email arrives and reads correctly (K19)
- magic link → let it expire → recover (K16, K17)
- admin: create event → **add slots** (K1) → duplicate → roster → end slot → export
- organizer on a phone: today → roster → check-in → broadcast (K5, K6)
- copilot: ask → cite → **approve a write and see the result** (K25)

### S4.3 — Open every email in a real mail client · M
Not Mailpit's preview. Gmail web, Gmail iOS, Apple Mail, Outlook. Nine builders,
six templates. Check times (K4), branding (K20), manage link (K16), layout.
**Email is the app for an account-less product**, and it renders differently
everywhere.

### S4.4 — Adversarial and edge input · M
Double-submit; back-button mid-flow; two tabs; expired token; slot fills between
render and submit; network drop mid-submit; server 500; clock skew. Non-ASCII
names, very long names, `+`-addressed emails.

### S4.5 — Turn every P0 into a regression test · M
Each Stage 1 bug gets a test that would have caught it — **and delete the mocks
that hid them** (`EventsSection.test.jsx:489-491`,
`test_router_confirm.py:86,131,184`). Add an integration test asserting hybrid
retrieval returns rows under the **default** config (K2). A regression test for a
bug that actually shipped is worth ten coverage tests.

**Gate:** every route and flow executed by a human or browser agent; every email
seen in a real client.

---

# Stage 5 — Real conditions

**~2 days.**

- **Load.** The unbounded tables (K36) with a full quarter of data, 500+ rows. And 30 volunteers hitting one event simultaneously: does `slot.current_count` stay correct? Does waitlist FIFO hold under concurrency? **K3's constraint change touches these same rows** — test them together.
- **Cross-browser.** Safari especially: date parsing and `toLocaleTimeString` differ, and K42 is already a timezone bug.
- **Real devices.** An actual iPhone, not a resized window — `env(safe-area-inset-bottom)`, the 36px tap targets (K40), the bottom-nav overlap (K42).
- **Copilot under contention.** Free-tier limits with 3 staff chatting at once. PR #52's retry sweep helps but has never met genuine contention.
- **Data volume.** A full quarter: 11 weeks × modules × slots × signups. Do exports finish? Does the roster render?

**Gate:** works with realistic data, on real devices, under concurrent use.

---

# Stage 6 — Hardening (devops)

**~1 week, not yours.** Listed so you know the handoff is complete.

**Blocking a deploy regardless of owner:**
- no `/health` endpoint — returns 404 today (`/docs` is 200)
- secrets: the only working configuration is a **gitignored `backend/.env` on Andy's laptop.** Needs a committed `backend/.env.example` and real secret management. Must document `CORPUS_EMBEDDING_PRIMARY=local` (K2), the `COPILOT_*` model vars, and that `copilot_agent_loop_enabled` stays off until K23–K25 land.
- no model-cache volume in `docker-compose.yml` — BGE (~130MB) and the reranker (~278MB) re-download on every rebuild
- single ~606KB JS bundle, no code splitting (build warns)

**Standard, non-blocking:**
- CORS, CSP, security headers
- global API rate limiting (only copilot chat has any)
- **authz sweep** — K33 found `/admin/feedback/*` open to organizers; assume it is not the only one
- backup/restore rehearsal, log aggregation, error tracking, uptime monitoring
- OIDC SSO endpoints exist (`auth.py:265,273`) with no UI entry point — decide before exposing
- `alembic` downgrade `DuplicateObject` on enum round-trips (documented in `CLAUDE.md`, deferred)

---

# Dependency spine

```
S0.1 mock sweep   ──> Stage 1 list is final
S0.3 verify ⚠️     ──> don't "fix" what isn't broken
S0.5 answers      ──> K21, K31, K34, K43

K7  week numbering ──> K24-K27   Phase B tools
K3  cancel trap    ──> K17       public resend
K34 delete dead    ──> K37       don't unify doomed files
K2  provider       ──> S4.x      eval must run on shipped config
K26 recipient set  ──> any SMTP wiring        ← mass-mail risk
K15 focus trap     ──> K40       same fix

Stages 1-3 ──> Stage 4 ──> Stage 5 ──> Stage 6
                  ↑
      new issues appear here;
      budget rework time behind it
```

**Do not schedule Stage 4 with no slack behind it.** Its purpose is to find
unknowns. If it finds nothing, you over-tested. If it finds six things, that's
normal — and you need days to fix them.

---

# Blocked on Andy

| # | Question | Blocks |
|---|---|---|
| 1 | Does a late cancellation or no-show carry any consequence for the volunteer? | K21, and finishing `docs/knowledge-base/35-cancellation-notice.md` — deliberately left silent rather than guessed |
| 2 | The real copilot test questions | Phase K's stated exit criterion. The 10/10 answer eval used the auditor's own questions, not Andy's |
| 3 | `/admin/imports` — delete 8 endpoints, or build the UI? | K34, K35 |
| 4 | Confirm profile extraction goes off until Phase B settles (recommended: yes) | K31 |

---

# Where the risk is

Ranked by likelihood of biting after handoff:

1. **Stage 4 findings.** Highest-confidence prediction here: walking the app in a browser will surface issues no audit found. Nobody has done it.
2. **A fifth mock-hidden P0** (S0.1). The record is 4 for 4.
3. **Phase B** (K23–K33). ~1200 lines that have never executed. Well-tested and untried are different things.
4. **Concurrency on signups.** `current_count`, waitlist FIFO and K3's constraint change all touch the same rows, untested under load.
5. **Email rendering.** Nine builders, six templates, never opened in a real client.

---

# If you have to cut

Cut from the back, never the front.

| Cut | Consequence |
|---|---|
| Stage 5 | Ships; may break on Safari or at quarter-scale |
| Stage 4 | **Ships with unknown unknowns.** The one cut worth feeling bad about |
| Stage 3d (K40–K42) | Inconsistent and inaccessible, but correct |
| Stage 3c (K34–K39) | Messy codebase, wrong docs; behaviour fine |
| Stage 2 | Ships something that states falsehoods |
| Stage 1 | Ships broken. **Never cut** |
| Stage 0 | You don't know what you're shipping. **Never cut** |

**Cheapest high-value action available right now:** run S0.1 (the mock-honesty
sweep) in the background while Stage 1 is being fixed. It costs no wall-clock
time and closes the single largest known blind spot in this plan.
