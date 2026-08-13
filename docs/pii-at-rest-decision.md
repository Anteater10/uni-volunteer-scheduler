# Decision: PII at rest stays plaintext in the application database

**Status:** **proposed 2026-08-13 — awaiting sign-off from Andy Subramanian (project owner).**
A risk acceptance is only worth anything if the person carrying the risk signed it,
so this stays "proposed" until Andy says otherwise. Change this line to
`accepted · <date> · <name>` at that point.
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
2. **K33 is fixed in W5.** Feedback comments are currently readable by every
   organizer because `/admin/feedback/*` gates with `_require_admin_or_organizer`.
   That is a wider audience than the feature intended, and narrowing it to admin
   removes more real exposure than encryption would.
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
