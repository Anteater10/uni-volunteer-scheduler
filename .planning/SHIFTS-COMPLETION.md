# Shifts — itemised completion list

Written 2026-08-05. Branch `feat/shifts`, PR #58 (draft). Supersedes the
epic-level W1 section of `FINAL-ROADMAP.md`.

Every item below is a concrete fix with a file and a reason. Sizes are
S (< 1h), M (half day), L (a day or more).

---

## Status of the six surfaces

| # | Surface | State |
|---|---|---|
| 1 | DuplicateEventModal | **done** — commit `64ac08b` |
| 2 | AdminEventPage roster | **done** — commit `64ac08b` |
| 3 | ResolveEventModal close-out | open — frontend only, backend already works |
| 4 | BroadcastModal | open — **backend also broken**, see B1 |
| 5 | SignupSuccessCard | open — frontend only |
| 6 | e2e / smoke / KB | open |

---

## A — Production bugs shifts introduces

These are the reason shifts cannot ship as-is. None of them are test
problems; each is a wrong answer given to a real user. None is caught by the
current suite, because the tests that would have caught them create their
data through a path production no longer has.

### A1 · The AI copilot reports every module as empty · L

Eight of the sixteen copilot agent tools join `Signup → Slot`. A session has
no `Signup` rows — a shift commitment lives in `shift_signups` — so every one
of these returns zero rows for shift-booked events.

| File | Line | Break |
|---|---|---|
| `get_module_roster.py` | 49 | roster comes back empty |
| `find_understaffed_modules.py` | 53 | every module reads as 0 staffed → all flagged understaffed |
| `signup_stats_for_week.py` | 60 | week stats undercount to zero |
| `signup_trend.py` | 61 | trend flatlines |
| `participant_history.py` | 45 | volunteer's history omits all classroom work |
| `nudge_understaffed_module.py` | 53 | nudges sent for fully-staffed modules |
| `send_reminder_email.py` | 45 | reminders skip classroom volunteers |
| `move_participant.py` | 66 | cannot find the participant to move |

There are **zero** occurrences of `shift` anywhere under `app/copilot/`.

Worst of these is `nudge_understaffed_module` + `send_reminder_email`: they
don't just display wrong, they *send mail* based on the wrong answer.

Fix: each tool needs to union the two booking sources, the same way
`admin.py::_bookings_for_slot` already does. That helper is the model to
follow — it exists and is correct; the copilot simply never adopted it.

### A2 · Broadcast silently under-sends · M

`broadcast_service.list_recipients` and `count_recipients`
(`backend/app/services/broadcast_service.py:243,263`) join
`Signup → Slot`. Consequences:

- "Email everyone on this event" reaches **only orientation signups**. Every
  classroom volunteer is silently omitted, and the modal's recipient-count
  preview confirms the wrong number, so nothing looks amiss.
- The recipient picker offers raw slots, so there is no way to target one
  shift.

Fix: union shift commitments into both queries, then add shifts to the
picker. Backend first — the picker is cosmetic next to the silent under-send.
Note `_dedup_insert_broadcast(db, signup_id, kind)` is keyed on a signup id
and will need the shift-signup equivalent.

### A3 · Suspected: exactly-once email dedup broken at runtime · M

Two tests fail with `InvalidColumnReference: there is no unique or exclusion
constraint matching the ON CONFLICT specification`. Shifts made
`magic_link_tokens.signup_id` nullable, which can invalidate the partial
unique index the dedup `ON CONFLICT` relies on.

Not yet diagnosed. If confirmed, duplicate emails can be sent. Highest-risk
unknown on the branch — do this before A1.

### A4 · `_fmt_when` still renders raw UTC · S

`backend/app/emails.py:68` returns `f"{slot.start_time} to {slot.end_time}"`.
Pre-existing (roadmap item K4), but the new `_fmt_shift_when` at :76 routes
through it, so on this branch it affects nine builders **plus every shift
email** — volunteers get `2026-10-14 14:00:00+00:00` in their confirmation.

---

## B — The three remaining surfaces

### B1 · ResolveEventModal — per-session close-out · M

`frontend/src/components/ResolveEventModal.jsx` (182 lines, 0 shift refs).

Good news: **the backend is already done.** `check_in_service.resolve_event`
and `resolve_slot` both accept shift-commitment ids and write
`session_attendance` per session. This is a frontend-only fix.

Currently the modal collects one attended/no-show decision per `signup_id`
and calls `resolveSlot(slot.id, ...)`. For a shift it needs one decision row
per (commitment, session), because a volunteer can attend Tuesday and no-show
Wednesday.

Until this lands, `session_attendance` has no writer from the app, so
volunteer hours and no-show data stop being recorded for classroom work.

### B2 · BroadcastModal — shift recipients · S after A2

`frontend/src/components/BroadcastModal.jsx:71,109,110`. `formatSlotOption`
and the `slotId` state become a unit picker over shifts + orientation slots.
Blocked on A2.

### B3 · SignupSuccessCard — name the shift · S

`frontend/src/components/SignupSuccessCard.jsx:22` `formatSlotLine` formats a
slot. A volunteer who booked "Tue morning" sees a bare list of times and is
not told which shift they committed to, nor that the sessions are a package.

---

## C — Restore the test signal

The backend suite is **261 failed / 925 passed / 11 skipped / 43 errors**.

This is *not* the "fixture bookkeeping" the PR body claims. ~45 sites across
36 files build a period slot and book it directly. The new CHECK constraint
`ck_slots_shift_membership_matches_type` is stopping those tests from
lying — and section A is what the lying was hiding.

Two helpers now exist for the conversion (`tests/fixtures/helpers.py`):

- `in_shift(db, slot)` — wrap a hand-built period slot in its own
  single-session shift, exactly as migration 0037 did to legacy rows
- `book_shift(db, shift, volunteer)` — the commitment, replacing a
  `Signup(slot_id=<session>)`

Pattern proven on `test_roster_endpoints.py` (12/12 green, commit `64ac08b`).

**The rule, so this doesn't get done wrongly:** where a test exercises a
slot-level service, convert the slot to *orientation* — slot-level waitlists
and signups still genuinely exist there, so the test stays honest. Where it
exercises classroom work, use a real shift. Do **not** blanket-convert
everything to orientation: the suite would go green while covering less, which
is how A1 and A2 got through in the first place.

### Failures by file · L in total

| Failures | File | Likely conversion |
|---|---|---|
| 28 | `test_check_in_service.py` | shift (6 sites) |
| 26 | `test_promotion_consent.py` | orientation (4 sites) |
| 25 | `test_public_signups.py` | shift |
| 22 | `test_check_in_endpoints.py` | shift (5 sites) |
| 16 | `test_expired_pending_cleanup.py` | orientation |
| 14 | `test_swap_service.py` | shift |
| 13 | `test_broadcast_service.py` | shift — **and add A2 coverage** |
| 10 | `test_waitlist_service.py` | orientation (services under test are slot-scoped) |
| 10 | `test_concurrent_check_in.py` | shift |
| 8 | `test_slots_visibility.py` | orientation |
| 7 | `test_signup_window.py` | orientation |
| 6 | `test_magic_link_signup_purpose.py` | see A3 first |
| 6 | `copilot/agent/test_tool_move_participant.py` | shift — **blocked on A1** |
| 21 | 7 other `copilot/agent/test_tool_*.py` | shift — **blocked on A1** |
| 4 | `test_waitlist_cancellation_copy.py` | orientation |
| 4 | `test_quarter_readonly.py` | new shift guard fires where old behaviour expected — triage |
| 4 | `test_models_phase3.py` | shift (4 sites) |
| 4 | `test_generate_slots.py` | real failures: `assert 2 == 4`; `TypeError: string indices must be integers` — triage |
| 4 | `test_event_duplicate_via_create.py` | should pass now — re-run after `64ac08b` |
| ~15 | various | `InvalidRequestError: Object '<Event>' is already attached to session` — fixture teardown, triage |
| rest | ~20 files, 1–3 each | one site each |

Two shared conftests are high leverage — `copilot/agent/conftest.py:122` and
`copilot/adversarial/conftest.py` account for the ~30 copilot failures
between them.

### C2 · The tests the spec asked for and nobody wrote · L

+3958 backend production lines landed against +560 test lines, all in
`test_shifts_migration.py`. Missing, from the spec's own Tests section:

- shift CRUD + ordering
- signup service: shift capacity, waitlist entry, unique constraint,
  one-event batch, orientation gate on shifts, **rejection of bare
  period-slot ids**
- batch confirm
- check-in resolver per session
- close-out attendance
- promote flow
- the four new staff routes, including the two added in `64ac08b`
  (shift cancel, shift grant-orientation)

---

## D — Docs, e2e, knowledge base

### D1 · e2e cross-role scenario · M
`e2e/cross-role.spec.js` — a volunteer picks a shift, staff sees the
commitment on the roster, closes out per session. 5 scenarios × 6 browser
projects today; this adds one.

### D2 · `docs/smoke-checklist.md` · S
The ~30-minute three-window pass still describes picking periods.

### D3 · Knowledge base + corpus re-ingest · M
`06-slots.md` needs a major rewrite; `05-events.md`, `07-modules.md`,
`02-glossary.md` need shift vocabulary; task guides follow. Then re-ingest.

Until this lands the copilot answers questions about a model the app no
longer has — which compounds A1: wrong data *and* wrong documentation.

Note: corpus re-ingest is separately blocked — PR #54 hits
`PermissionDeniedError` on the OpenRouter key.

---

## Suggested order

Ordered by "what is actively wrong" rather than by surface.

1. **A3** — diagnose the ON CONFLICT failure. It's the only unknown, and if
   it means duplicate emails it changes the risk picture. · M
2. **A4** — one-line-ish fix, stops raw UTC reaching volunteers. · S
3. **A2** — silent under-send is the worst *shipped* behaviour here. · M
4. **A1** — eight copilot tools; two of them send mail. · L
5. **B1** — restores attendance recording. · M
6. **C** — restore the suite, following the orientation-vs-shift rule. · L
7. **B2**, **B3** — cosmetic by comparison. · S
8. **D** — docs and e2e last, because they describe whatever 1–7 settle on. · M

Rough total: the better part of a week, with C and A1 the two long poles.

---

## The decision this list exists to inform

None of A1–A4 exist on `main`. They are all consequences of shifts. Parking
the branch makes them all disappear at once, at the cost of volunteers
booking per period instead of per bundle.

The competing claim on the same week is the deploy work: security review,
prod hardening, and Phase B — all untouched, all load-bearing for handoff to
Rafael in a way shifts is not.

Unverified either way: nobody has yet confirmed `main` is deploy-ready. That
check is cheap and should probably happen before this decision is made final.
