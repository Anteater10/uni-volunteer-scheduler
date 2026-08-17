# Decision: PII at rest stays plaintext in the application database

**Status:** **accepted · 2026-08-17 · Andy Subramanian** (project owner).
Proposed 2026-08-13; signed after condition 2 was amended below to record the
K33 acceptance rather than the K33 fix it originally assumed.
**Scope:** W4 deploy blocker, "PII plaintext at rest — encrypt, or accept in writing."

## What is actually plaintext

Two columns, both `Text`:

| Column | Contents | Who can read it today |
|---|---|---|
| `copilot_user_profiles.profile_text` | An LLM-written summary of a staff member's working context, built from their own copilot conversations | Only the owning user, via `GET /api/v1/copilot/profile` |
| `copilot_message_feedback.comment` and the session-rating comment | Free-text feedback a staff member typed about a copilot answer | Admin **and organizer** — see K33 |

Both are staff data, not volunteer data. No volunteer name, email, phone or
signup record is in either column; those live in `volunteers` and `signups`,
which were never part of this finding.

## Why we are accepting it rather than encrypting

**The threat that column encryption actually stops is narrow.** Application-level
encryption defends against someone reading the database file or a stolen backup
without the application. It does nothing against a compromised application, a
leaked admin credential, or an over-broad role guard — and those are the realistic
paths to this data.

**RDS encryption at rest covers the disk-theft threat at no application cost.**
Enabling KMS storage encryption on the RDS instance and on automated snapshots
addresses "someone obtains the storage or a backup" without touching a line of
code, without key management in the app, and without a migration. This is the
mitigation we are relying on, and it is a condition of this decision rather than
an afterthought.

**Column encryption would cost real functionality.** `profile_text` is read back
into the copilot's prompt on every session, and feedback comments feed the
`bottom_messages` aggregate that exists to find bad answers. Encrypting either
means decrypting on every read anyway, so the plaintext is in application memory
regardless — and it hands Rafael an encryption key to rotate and escrow, on a
system he is inheriting a week from now. That is a poor trade for a narrow gain.

**There are already two real controls.** `extract_profile` redacts the candidate
text before it is persisted, so the profile is not a raw transcript. And the
owning user can wipe their own profile at any time via `DELETE /profile`, which
sets the column to the empty string and bumps the version.

## Conditions of acceptance

This acceptance is conditional on all three:

1. **RDS storage encryption (KMS) is enabled** on the instance and its automated
   snapshots. This is the substitute control and it is not optional. Rafael owns it.
2. ~~**K33 is fixed in W5.**~~ **Superseded 2026-08-17 — K33 was accepted, not
   fixed** (2026-08-13, PR #74). This condition was drafted expecting
   `/admin/feedback/*` to be narrowed to admin, which would have shrunk the
   audience for the `comment` column. That narrowing did not happen and will not:
   organizers are trusted staff, consistent with the 2026-08-12 ruling that
   organizer reads are unscoped, and two tests
   (`test_weekly_organizer_allowed`, `test_bottom_messages_organizer_allowed`)
   already asserted organizer access deliberately.

   **This acceptance therefore covers a wider audience than the original draft
   assumed** — see the recorded risk below. The K33 acceptance carries its own
   load-bearing revisit trigger: if the copilot is ever opened to volunteers,
   students, or any non-staff role, **both** decisions must be re-signed before
   that ships. Full reasoning and the corrected exposure statement:
   [docs/security-review-w5.md](security-review-w5.md#k33--organizers-can-read-other-staffs-copilot-conversations).
3. ~~**The CCPA delete path covers both columns.**~~ ✅ **done 2026-08-13.**
   Writing this condition down is what caught that it was false: `ccpa_delete`
   anonymized the `User` and `Volunteer` rows and left both copilot columns
   untouched. `routers/admin.py` now deletes the `copilot_user_profiles` row
   and nulls the feedback `comment` columns, keeping the rating *values* —
   those are answer-quality signal, not personal data. Regression test:
   `tests/test_admin_phase7.py::test_ccpa_delete_erases_copilot_profile_and_feedback_comments`.
   See also `docs/ccpa-policy.md`.

## What would reverse this decision

- Volunteer PII (name, email, phone, or anything in `signups`) starts being copied
  into either column. That changes who is exposed from staff to minors' guardians
  and volunteers, and the calculus with it.
- The application is asked to hold anything in a regulated category — health
  information, government identifiers, payment details.
- SciTrek's use expands beyond UCSB staff to a population that has not agreed to
  the copilot recording their working context.

## Recorded risk

If the application database or an unencrypted backup is obtained by someone who
should not have it, staff working-context summaries and staff feedback comments
are readable without further effort. We judge this acceptable for a single-tenant
university outreach tool holding staff-authored text, given the conditions above
and the handover timeline.

**Second exposure, recorded 2026-08-17 with the K33 acceptance.** Independent of
anyone obtaining the database, **every organizer can already read the `comment`
column through the application**, via `GET /api/v1/copilot/admin/feedback/weekly`
and `/bottom-messages` (`app/copilot/router.py:1161`, `:1182`). Both gate on
`STAFF_ROLES`, and `aggregates.bottom_messages`
(`app/copilot/feedback/aggregates.py:131`) applies no user filter, so the rows
are the whole staff population. Each row carries the thumbs-down comment, the
assistant's reply, **and `prior_user_text` — the question the staff member typed,
verbatim**. `AdminLayout.jsx` lists the nav item for organizers, so the page is
reached by clicking, not only by calling the API directly.

This is deliberate and is the accepted state, not a residual defect. It is
recorded here because it is a larger audience than "who can read it today" in
the table above implied when this document was drafted, and a risk acceptance is
worth nothing if it describes a smaller exposure than the one being accepted.
