---
phase: 00-backend-completion-frontend-integration
plan: 02
subsystem: backend/schema
tags: [alembic, timezone, postgresql, schema-migration, celery, auth]
dependency_graph:
  requires: [00-01]
  provides: [timezone-aware-schema, reminder_sent-column, slot-index, token_hash-column]
  affects: [00-03-auth-hardening, 00-04-celery-reliability, 00-05-refactor-extractions]
tech_stack:
  added: []
  patterns:
    - DateTime(timezone=True) for all timestamp columns
    - lambda: datetime.now(timezone.utc) as column defaults
    - SHA-256 hex digest stored in token_hash (never raw token)
    - AT TIME ZONE 'UTC' backfill assumption for naive → aware migration
key_files:
  created:
    - backend/alembic/versions/0002_phase0_schema_hardening.py
  modified:
    - backend/app/models.py
    - backend/app/routers/events.py
    - backend/app/routers/slots.py
    - backend/app/routers/signups.py
    - backend/app/celery_app.py
    - backend/app/deps.py
    - .gitignore
decisions:
  - "Renamed RefreshToken.token -> token_hash and truncated all existing tokens to force re-login (T-00-07 mitigation)"
  - "AT TIME ZONE 'UTC' backfill is correct: codebase exclusively used datetime.utcnow() prior to this plan (T-00-05)"
  - "_to_naive_utc() helper replaced by _normalize_dt() that preserves tz-awareness rather than stripping it"
  - "admin.py datetime.utcnow() deferred — out of scope for this plan"
  - "SHA-256 hashing wired in deps.py create/revoke/verify_refresh_token alongside token_hash rename"
metrics:
  duration: ~25min
  completed: 2026-04-08
  tasks_completed: 3
  files_changed: 8
---

# Phase 0 Plan 02: Schema Migration Summary

**One-liner:** Single Alembic revision migrating all DateTime columns to TIMESTAMPTZ, adding Signup.reminder_sent, Slot.start_time btree index, and renaming RefreshToken.token to SHA-256 token_hash.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Update models.py — TZ columns, reminder_sent, token_hash, slot index | 7f902bb | backend/app/models.py |
| 2 | Author Alembic revision 0002_phase0_schema_hardening | 8f8d5fb | backend/alembic/versions/0002_phase0_schema_hardening.py |
| 3 | Remove _to_naive_utc and datetime.utcnow from routers/celery/deps | 4bcd306 | events.py, slots.py, signups.py, celery_app.py, deps.py |

Also included:
- `a151024` — chore: add AI scaffolding dirs to .gitignore and untrack .planning files

## Decisions Made

1. **AT TIME ZONE 'UTC' backfill** — All stored naive values were UTC (codebase used `datetime.utcnow()` exclusively). This assumption is documented in the migration docstring (T-00-05 mitigation).
2. **Force re-login on token rename** — `DELETE FROM refresh_tokens` in upgrade() ensures no raw tokens survive the `token_hash` rename. Users re-authenticate; no user data lost. (T-00-07 mitigation)
3. **Production index note** — `ix_slots_start_time` uses a locking `CREATE INDEX` here. For production with large tables, use `CREATE INDEX CONCURRENTLY` outside a transaction (T-00-06 accepted, documented in migration).
4. **SHA-256 wired in deps.py** — `create_refresh_token`, `revoke_refresh_token`, and `verify_refresh_token` all hash the raw token before DB lookup. This is Plan 03's prerequisite wired early to avoid a broken state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] SHA-256 hashing wired in deps.py alongside token_hash rename**
- **Found during:** Task 3
- **Issue:** models.py renamed `token` → `token_hash` but `deps.py` still referenced `models.RefreshToken.token` directly. Without hashing the raw token before lookup, the column rename would cause immediate AttributeError in production.
- **Fix:** Updated `create_refresh_token`, `revoke_refresh_token`, and `verify_refresh_token` to hash with `hashlib.sha256` before storing/querying `token_hash`. Plan 03 (auth hardening) can build on this clean foundation.
- **Files modified:** `backend/app/deps.py`
- **Commit:** 4bcd306

**2. [Rule 3 - Blocking Issue] .gitignore missing AI scaffolding exclusions**
- **Found during:** Task 1 commit
- **Issue:** The soft-reset to `1afa17f` brought `.planning/` into HEAD, causing those files to appear as staged deletions when committing. Global git rules prohibit committing `.planning/` and `.claude/`.
- **Fix:** Added `.planning/`, `.claude/`, `.gsd/` to `.gitignore` and untracked the planning files from the worktree branch via `git rm --cached`.
- **Files modified:** `.gitignore`
- **Commit:** a151024

## Known Stubs

None — all changes are structural (schema/migration). No UI-facing data flows.

## Deferred Items

- `backend/app/routers/admin.py` line 89: `datetime.utcnow()` — out of scope for this plan (admin.py not in plan's `files_modified` list). Should be fixed in Plan 05 (refactor extractions) or a dedicated cleanup.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: token_lifecycle | backend/app/deps.py | SHA-256 hash wired; raw token never persisted. Plan 03 should audit the full token rotation flow (revoke-on-use, expiry). |

## Self-Check: PASSED

All created/modified files confirmed present on disk. All task commits verified in git log:
- a151024: chore — .gitignore and untrack .planning
- 7f902bb: feat — models.py TZ + reminder_sent + token_hash + slot index
- 8f8d5fb: feat — Alembic revision 0002_phase0_schema_hardening
- 4bcd306: feat — remove _to_naive_utc and datetime.utcnow from routers/celery/deps
