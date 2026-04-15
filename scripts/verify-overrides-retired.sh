#!/usr/bin/env bash
# Phase 16 Plan 01 (ADMIN-01): gate script for admin prereq-override retirement.
#
# Exits 0 if no LIVE "overrides" references remain in the code surface, 1 otherwise.
#
# Allowed paths (excluded from the scan):
#   .planning/                                — historical plans + research
#   backend/alembic/versions/                 — historical migration files
#   frontend/src/lib/__tests__/api.test.js    — the undefined-export guard test
#   docs/COLLABORATION.md                     — collaboration doc prose
#   docs/ADMIN-AUDIT.md                       — historical admin audit doc
#   scripts/verify-overrides-retired.sh       — this file itself
set -euo pipefail

# Grep for "overrides" but drop FastAPI's dependency_overrides (unrelated framework API).
RAW=$(git grep -in 'overrides' -- \
  ':(exclude).planning' \
  ':(exclude)backend/alembic/versions' \
  ':(exclude)frontend/src/lib/__tests__/api.test.js' \
  ':(exclude)docs/COLLABORATION.md' \
  ':(exclude)docs/ADMIN-AUDIT.md' \
  ':(exclude)scripts/verify-overrides-retired.sh' \
  || true)
MATCHES=$(echo "$RAW" | grep -v 'dependency_overrides' | grep -v '^$' || true)

if [ -n "$MATCHES" ]; then
  echo "FAIL: live Overrides references still present:" >&2
  echo "$MATCHES" >&2
  exit 1
fi
echo "PASS: prereq-override retirement clean."
