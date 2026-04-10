---
phase: "09"
plan: "09"
subsystem: backend
tags: [public-signup, volunteer, magic-link, celery, TDD]
dependency_graph:
  requires: ["08-schema-realignment-migration"]
  provides: ["public-signup-api", "volunteer-upsert", "magic-link-confirm", "expire-pending-cleanup"]
  affects: ["frontend-signup-pages", "phase-12-admin"]
tech_stack:
  added:
    - phonenumbers (phone E.164 validation)
    - freezegun (Celery task time-travel tests)
  patterns:
    - token-capture-monkeypatch (patch source module not importing module)
    - volunteer-upsert-on-email (pg_insert ON CONFLICT DO UPDATE)
    - celery-eager-mode-tests (task_always_eager=True, patch SessionLocal proxy)
key_files:
  created:
    - backend/app/services/volunteer_service.py
    - backend/app/services/public_signup_service.py
    - backend/app/services/orientation_service.py
    - backend/app/routers/public/__init__.py
    - backend/app/routers/public/events.py
    - backend/app/routers/public/signups.py
    - backend/app/routers/public/orientation.py
    - backend/app/email_templates/signup_confirm.html
    - backend/app/emails.py (build_signup_confirmation_email added)
    - backend/tests/test_public_events.py
    - backend/tests/test_public_signups.py
    - backend/tests/test_public_orientation.py
    - backend/tests/test_expired_pending_cleanup.py
    - backend/tests/test_phase09_smoke.py
    - scripts/smoke_phase09.sh
    - .planning/phases/09-public-signup-backend/09-verification.txt
  modified:
    - backend/app/celery_app.py (send_signup_confirmation_email + expire_pending_signups + beat schedule)
    - backend/app/magic_link_service.py (purpose arg, ttl override, batch consume)
    - backend/app/schemas.py (PublicSignup*, PublicEvent*, Volunteer*, Orientation*, SignupRead.volunteer_id)
    - backend/app/models.py (Notification XOR CHECK constraint added to __table_args__)
    - backend/app/main.py (public router wired)
    - backend/tests/fixtures/factories.py (VolunteerFactory, SignupFactory rewired)
    - backend/tests/fixtures/helpers.py (VolunteerFactory bound)
    - backend/tests/test_check_in_service.py (un-skipped, volunteer_id)
    - backend/tests/test_check_in_endpoints.py (un-skipped, volunteer_id)
    - backend/tests/test_concurrent_check_in.py (un-skipped, volunteer_id)
    - backend/tests/test_magic_link_router.py (un-skipped, VolunteerFactory)
    - backend/tests/test_magic_link_service.py (un-skipped, VolunteerFactory)
    - backend/tests/test_models_magic_link.py (un-skipped, volunteer_id)
    - backend/tests/test_models_phase3.py (un-skipped, SlotType.PERIOD)
    - backend/tests/test_notifications_phase6.py (un-skipped, VolunteerFactory)
    - backend/tests/test_roster_endpoints.py (un-skipped, volunteer_id)
    - backend/tests/test_admin.py (un-skip + update skip reasons)
    - backend/tests/test_admin_phase7.py (update skip reasons)
    - backend/tests/test_contract.py (delete D-10 test, fix 404 shape test)
    - backend/tests/test_signups.py (update skip reasons)
decisions:
  - "D-10: old POST /api/v1/signups/ endpoint deleted; public signup at /api/v1/public/signups"
  - "D-11: no Notification row for volunteer-backed signups (deferred to Phase 12)"
  - "expire_pending_signups uses expires_at < now (14-day TTL on SIGNUP_CONFIRM tokens)"
  - "XOR constraint on notifications enforced in model __table_args__ + migration 0010"
metrics:
  duration: "~6 hours (2 sessions)"
  completed_date: "2026-04-10"
  tasks_completed: 15
  files_changed: 35
---

# Phase 09: Public Signup Backend Summary

**One-liner:** Account-less public volunteer signup with email magic-link confirm, 7 REST endpoints, Celery cleanup task, and 74 un-skipped tests rewired to volunteer_id.

## What Was Built

Phase 09 delivers the complete public-facing signup backend for the account-less v1.1 product:

- **7 public endpoints** under `/api/v1/public/` — events list/detail, signups create/confirm/manage/cancel, orientation status
- **Volunteer upsert** on email collision (no duplicate accounts)
- **Magic-link flow** — SIGNUP_CONFIRM token (14-day TTL) sent on create, consumed on confirm; SIGNUP_MANAGE token issued on confirm for subsequent manage/cancel
- **Celery task** `expire_pending_signups` — daily 3am UTC cleanup of pending signups with expired tokens, decrements slot counts
- **Phone validation** via phonenumbers library (E.164 normalisation)
- **74 previously-skipped tests** un-skipped and rewired from `user_id` → `volunteer_id` pattern
- **28 new integration tests** for all 7 public endpoints
- **8 TDD tests** for expire_pending_signups (RED + GREEN)
- **1 full-flow smoke test** (POST→confirm→cancel→events→orientation)

## Test Results

Final suite: **188 passed, 12 skipped, 0 failed**

12 skips are all intentional:
- 8 × `test_signups.py` — old POST /api/v1/signups/ deleted (D-10), Phase 12 rewrite
- 1 × `test_admin.py` — cancel signup promotes waitlist, needs public flow rewrite
- 3 × `test_admin_phase7.py` — analytics/CCPA stubs (D-05), Phase 12

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing constraint] Notification XOR CHECK constraint absent from model**
- **Found during:** Task 11 TDD GREEN (test_xor_constraint_rejects_both_user_id_and_volunteer_id failed)
- **Issue:** Migration 0010 adds `ck_notifications_recipient_xor` CHECK constraint to DB, but `Notification.__table_args__` in models.py was empty — `Base.metadata.create_all` in tests skips migration DDL
- **Fix:** Added `CheckConstraint(...)` to `Notification.__table_args__` matching the migration's SQL expression
- **Files modified:** `backend/app/models.py`
- **Commit:** 9b456f9

**2. [Rule 1 - Bug] SignupRead schema had user_id instead of volunteer_id**
- **Found during:** Task 9 un-skip — check_in endpoint tests failing with ResponseValidationError
- **Issue:** `SignupRead.user_id: UUID` was a required field but `Signup` model no longer has `user_id` (Phase 08 renamed to `volunteer_id`)
- **Fix:** Changed `SignupRead.user_id: UUID` → `SignupRead.volunteer_id: UUID` in schemas.py
- **Files modified:** `backend/app/schemas.py`
- **Commit:** 7e121b7

**3. [Rule 1 - Bug] Phone validation: 555 numbers are invalid**
- **Found during:** Task 10 TDD for public signups
- **Issue:** `GOOD_PHONE = "555-867-5309"` fails phonenumbers validation (555-0xxx range is the only valid fictional range; 555-8xxx is not)
- **Fix:** Changed to `"(213) 867-5309"` (valid LA area code, real NANP subscriber range)
- **Files modified:** `backend/tests/test_public_signups.py`
- **Commit:** f460189

**4. [Rule 1 - Bug] TokenCapture: monkeypatching importing module doesn't work for local imports**
- **Found during:** Task 10 — confirm/manage/cancel tests needing raw token
- **Issue:** `public_signup_service.py` uses `from ..magic_link_service import issue_token` inside function body; monkeypatching `public_signup_service.issue_token` has no effect
- **Fix:** `_TokenCapture` context manager patches `app.magic_link_service.issue_token` at the source module level
- **Files modified:** `backend/tests/test_public_signups.py`
- **Commit:** f460189

**5. [Rule 2 - Missing functionality] SlotType missing from many inline Slot constructors**
- **Found during:** Task 9 un-skip — IntegrityError: null value in column "slot_type"
- **Issue:** 6 test files had inline `Slot(...)` constructors without `slot_type` parameter; DB column is NOT NULL with no server_default
- **Fix:** Added `SlotType` import and `slot_type=SlotType.PERIOD` to all inline Slot constructors in test_check_in_service.py, test_check_in_endpoints.py, test_concurrent_check_in.py, test_models_phase3.py
- **Commit:** 7e121b7

## Known Stubs

- `test_signups.py` (8 tests): All skipped — old POST /api/v1/signups/ endpoint deleted. Phase 12 rewrites as public signup integration tests.
- Admin analytics endpoints: return 501 (D-05 locked decision). Phase 12 implements.
- `send_signup_confirmation_email`: no Notification row created (D-11). Phase 12 adds audit rows.

## Threat Flags

None — all new endpoints are in the `/api/v1/public/` namespace with:
- Rate limiting via Redis (migration 0010 + existing rate_limit dependency)
- Phone + email validation before DB writes
- Magic-link tokens use `secrets.token_urlsafe(32)` with SHA-256 hashing
- No authenticated routes exposed without token verification

## Self-Check: PASSED

Files exist:
- backend/app/celery_app.py: expire_pending_signups task present
- backend/app/models.py: ck_notifications_recipient_xor constraint present
- backend/tests/test_expired_pending_cleanup.py: 8 tests
- backend/tests/test_phase09_smoke.py: 1 test
- scripts/smoke_phase09.sh: curl smoke script
- .planning/phases/09-public-signup-backend/09-verification.txt

Commits present (git log --oneline):
- 9b456f9 feat(09-11): expire_pending_signups
- e2188d4 test(09-12): smoke test
- 33d0b13 chore(09-13): smoke script
- 6b2f110 chore(09-14): verification gates
