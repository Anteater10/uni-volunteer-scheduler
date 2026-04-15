#!/usr/bin/env bash
# smoke_phase09.sh — Phase 09 public signup backend smoke test
#
# Usage:
#   BASE_URL=http://localhost:8000 bash scripts/smoke_phase09.sh
#
# Requires: curl, jq, a running backend with DB migrations at head.
# Token capture: relies on DEBUG=true celery worker logging the token preview.
# In dev, run:  docker compose logs -f celery_worker | grep signup_confirmation_token_preview
#
# If MAGIC_TOKEN env var is set, skips token-from-log step and uses it directly.

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
EMAIL="smoke_$(date +%s)@example.com"
PHONE="(213) 867-5309"

echo "=== Phase 09 smoke test ==="
echo "BASE_URL: $BASE_URL"
echo "Test email: $EMAIL"
echo ""

# ---- Step 1: List public events ----
echo "[1] GET /api/v1/public/events?quarter=fall&year=2026&week_number=1"
EVENTS=$(curl -sf "$BASE_URL/api/v1/public/events?quarter=fall&year=2026&week_number=1")
echo "    Response: $(echo "$EVENTS" | jq 'length') event(s)"

# Pick first slot_id if available; otherwise fail gracefully
SLOT_ID=$(echo "$EVENTS" | jq -r '.[0].slots[0].id // empty' 2>/dev/null || true)
if [[ -z "$SLOT_ID" ]]; then
  echo "    WARN: No slots found in public events — skipping signup steps."
  echo "    (Create an event with a slot via admin API or seed data first.)"
  echo ""
  echo "=== Partial smoke complete (events endpoint OK) ==="
  exit 0
fi
echo "    Using slot_id: $SLOT_ID"
echo ""

# ---- Step 2: Create public signup ----
echo "[2] POST /api/v1/public/signups"
CREATE_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/public/signups" \
  -H "Content-Type: application/json" \
  -d "{
    \"first_name\": \"Smoke\",
    \"last_name\": \"Test\",
    \"email\": \"$EMAIL\",
    \"phone\": \"$PHONE\",
    \"slot_ids\": [\"$SLOT_ID\"]
  }")
echo "    Response: $CREATE_RESP"
VOLUNTEER_ID=$(echo "$CREATE_RESP" | jq -r '.volunteer_id')
SIGNUP_ID=$(echo "$CREATE_RESP" | jq -r '.signup_ids[0]')
echo "    volunteer_id: $VOLUNTEER_ID"
echo "    signup_id: $SIGNUP_ID"
echo ""

# ---- Step 3: Token capture ----
if [[ -z "${MAGIC_TOKEN:-}" ]]; then
  echo "[3] Token capture — check celery_worker logs:"
  echo "    docker compose logs celery_worker | grep signup_confirmation_token_preview"
  echo ""
  echo "    Set MAGIC_TOKEN=<raw_token> and re-run to test confirm/manage/cancel."
  echo ""
  echo "=== Partial smoke complete (create OK, token not provided) ==="
  exit 0
fi

TOKEN="$MAGIC_TOKEN"
echo "[3] Using MAGIC_TOKEN: ${TOKEN:0:12}..."
echo ""

# ---- Step 4: Confirm signup ----
echo "[4] POST /api/v1/public/signups/confirm?token=..."
CONFIRM_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/public/signups/confirm?token=$TOKEN")
echo "    Response: $CONFIRM_RESP"
CONFIRMED=$(echo "$CONFIRM_RESP" | jq -r '.confirmed')
if [[ "$CONFIRMED" != "true" ]]; then
  echo "    FAIL: expected confirmed=true, got $CONFIRM_RESP"
  exit 1
fi
echo "    OK: confirmed=true"
echo ""

# ---- Step 5: Manage signups ----
echo "[5] GET /api/v1/public/signups/manage?token=..."
MANAGE_RESP=$(curl -sf "$BASE_URL/api/v1/public/signups/manage?token=$TOKEN")
echo "    Response: $MANAGE_RESP"
SIGNUP_COUNT=$(echo "$MANAGE_RESP" | jq '.signups | length')
echo "    signups returned: $SIGNUP_COUNT"
echo ""

# ---- Step 6: Cancel signup ----
echo "[6] DELETE /api/v1/public/signups/$SIGNUP_ID?token=..."
CANCEL_RESP=$(curl -sf -X DELETE "$BASE_URL/api/v1/public/signups/$SIGNUP_ID?token=$TOKEN")
echo "    Response: $CANCEL_RESP"
CANCELLED=$(echo "$CANCEL_RESP" | jq -r '.cancelled')
if [[ "$CANCELLED" != "true" ]]; then
  echo "    FAIL: expected cancelled=true, got $CANCEL_RESP"
  exit 1
fi
echo "    OK: cancelled=true"
echo ""

# ---- Step 7: Orientation status ----
echo "[7] GET /api/v1/public/orientation-status?email=$EMAIL"
ORI_RESP=$(curl -sf "$BASE_URL/api/v1/public/orientation-status?email=$EMAIL")
echo "    Response: $ORI_RESP"
echo ""

echo "=== Phase 09 smoke complete: ALL STEPS PASSED ==="
