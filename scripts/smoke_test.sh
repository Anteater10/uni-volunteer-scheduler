#!/usr/bin/env bash
set -euo pipefail

# If you run this on your host, keep BASE_URL as localhost.
BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"

# Make emails unique by default so reruns don't break.
STAMP="${STAMP:-$(python3 - <<'PY'
import time
print(int(time.time()))
PY
)}"

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@ucsb.edu}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-strong}"

ORG_EMAIL="${ORG_EMAIL:-organizer_${STAMP}@ucsb.edu}"
ORG_PASSWORD="${ORG_PASSWORD:-organizer-pass-123}"

P1_EMAIL="${P1_EMAIL:-p1_${STAMP}@ucsb.edu}"
P1_PASSWORD="${P1_PASSWORD:-p1-pass-123}"

P2_EMAIL="${P2_EMAIL:-p2_${STAMP}@ucsb.edu}"
P2_PASSWORD="${P2_PASSWORD:-p2-pass-123}"

json_get() {
  python3 - <<'PY' "$1" "$2"
import json, sys
obj = json.loads(sys.argv[1])
print(obj[sys.argv[2]])
PY
}

http() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  local token="${4:-}"

  if [[ -n "$token" && -n "$data" ]]; then
    curl -sS -X "$method" "$url" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      -d "$data"
  elif [[ -n "$token" ]]; then
    curl -sS -X "$method" "$url" \
      -H "Authorization: Bearer $token"
  elif [[ -n "$data" ]]; then
    curl -sS -X "$method" "$url" \
      -H "Content-Type: application/json" \
      -d "$data"
  else
    curl -sS -X "$method" "$url"
  fi
}

post_form_token() {
  local email="$1"
  local password="$2"
  curl -sS -X POST "$BASE_URL/auth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "username=$email" \
    --data-urlencode "password=$password"
}

expect_contains() {
  local hay="$1"
  local needle="$2"
  if [[ "$hay" != *"$needle"* ]]; then
    echo "❌ Expected output to contain: $needle"
    echo "---- output ----"
    echo "$hay"
    exit 1
  fi
}

wait_for_health() {
  echo "==> Waiting for health..."
  for _ in $(seq 1 60); do
    if curl -s "$BASE_URL/health" | grep -q '"status":"ok"'; then
      echo "✅ Health OK"
      return
    fi
    sleep 1
  done
  echo "❌ Health never became OK"
  exit 1
}

iso_utc_naive() {
  # Return a naive ISO timestamp (no 'Z') to avoid tz-aware edge cases.
  python3 - <<'PY' "$1"
from datetime import datetime, timedelta
hours = int(__import__("sys").argv[1])
dt = datetime.utcnow() + timedelta(hours=hours)
print(dt.replace(microsecond=0).isoformat())
PY
}

echo "==> Using emails:"
echo "    ADMIN_EMAIL=$ADMIN_EMAIL"
echo "    ORG_EMAIL=$ORG_EMAIL"
echo "    P1_EMAIL=$P1_EMAIL"
echo "    P2_EMAIL=$P2_EMAIL"
echo

wait_for_health

echo "==> Login as admin"
admin_tok_json="$(post_form_token "$ADMIN_EMAIL" "$ADMIN_PASSWORD")"
expect_contains "$admin_tok_json" "access_token"
ADMIN_TOKEN="$(json_get "$admin_tok_json" "access_token")"
echo "✅ Admin token acquired"

echo "==> Create organizer user (admin-only)"
org_create_payload="$(cat <<JSON
{
  "name": "Organizer One",
  "email": "$ORG_EMAIL",
  "role": "organizer",
  "university_id": "ORG001",
  "notify_email": true,
  "password": "$ORG_PASSWORD"
}
JSON
)"
org_create_res="$(http POST "$BASE_URL/users/" "$org_create_payload" "$ADMIN_TOKEN")"
# If it already existed, that's fine because we made it unique by default.
expect_contains "$org_create_res" '"email"'
echo "✅ Organizer ensured: $ORG_EMAIL"

echo "==> Login as organizer"
org_tok_json="$(post_form_token "$ORG_EMAIL" "$ORG_PASSWORD")"
expect_contains "$org_tok_json" "access_token"
ORG_TOKEN="$(json_get "$org_tok_json" "access_token")"
echo "✅ Organizer token acquired"

echo "==> Register participant users (public)"
p1_reg_payload="$(cat <<JSON
{"name":"Participant One","email":"$P1_EMAIL","password":"$P1_PASSWORD","university_id":"P1001","notify_email":true}
JSON
)"
p2_reg_payload="$(cat <<JSON
{"name":"Participant Two","email":"$P2_EMAIL","password":"$P2_PASSWORD","university_id":"P2002","notify_email":true}
JSON
)"
p1_reg_res="$(http POST "$BASE_URL/auth/register" "$p1_reg_payload")"
p2_reg_res="$(http POST "$BASE_URL/auth/register" "$p2_reg_payload")"
expect_contains "$p1_reg_res" '"email"'
expect_contains "$p2_reg_res" '"email"'
echo "✅ Participants registered"

echo "==> Login participants"
p1_tok_json="$(post_form_token "$P1_EMAIL" "$P1_PASSWORD")"
p2_tok_json="$(post_form_token "$P2_EMAIL" "$P2_PASSWORD")"
P1_TOKEN="$(json_get "$p1_tok_json" "access_token")"
P2_TOKEN="$(json_get "$p2_tok_json" "access_token")"
echo "✅ Participant tokens acquired"

echo "==> Organizer creates an event with ONE slot (capacity=1)"
EVENT_START="$(iso_utc_naive 2)"
EVENT_END="$(iso_utc_naive 6)"
SLOT_START="$(iso_utc_naive 3)"
SLOT_END="$(iso_utc_naive 4)"

event_payload="$(cat <<JSON
{
  "title": "Smoke Test Event",
  "description": "Created by scripts/smoke_test.sh",
  "location": "Test Location",
  "visibility": "public",
  "branding_id": null,
  "start_date": "$EVENT_START",
  "end_date": "$EVENT_END",
  "max_signups_per_user": 1,
  "signup_open_at": null,
  "signup_close_at": null,
  "slots": [
    {"start_time": "$SLOT_START", "end_time": "$SLOT_END", "capacity": 1}
  ]
}
JSON
)"
event_res="$(http POST "$BASE_URL/events/" "$event_payload" "$ORG_TOKEN")"
expect_contains "$event_res" '"id"'
EVENT_ID="$(python3 - <<'PY' "$event_res"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
echo "✅ Created event: $EVENT_ID"

echo "==> Organizer adds one custom question"
q_payload='{"prompt":"Do you have prior experience?","field_type":"select","required":true,"options":["Yes","No"],"sort_order":0}'
q_res="$(http POST "$BASE_URL/events/$EVENT_ID/questions" "$q_payload" "$ORG_TOKEN")"
expect_contains "$q_res" '"id"'
QUESTION_ID="$(python3 - <<'PY' "$q_res"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
echo "✅ Created question: $QUESTION_ID"

echo "==> Fetch event (public) and grab slot_id"
event_get="$(http GET "$BASE_URL/events/$EVENT_ID")"
SLOT_ID="$(python3 - <<'PY' "$event_get"
import json, sys
obj = json.loads(sys.argv[1])
print(obj["slots"][0]["id"])
PY
)"
echo "✅ Slot ID: $SLOT_ID"

echo "==> Participant 1 signs up (confirmed)"
signup1_payload="$(cat <<JSON
{
  "slot_id": "$SLOT_ID",
  "answers": [{"question_id":"$QUESTION_ID","value":"Yes"}]
}
JSON
)"
signup1_res="$(http POST "$BASE_URL/signups/" "$signup1_payload" "$P1_TOKEN")"
expect_contains "$signup1_res" "confirmed"
SIGNUP1_ID="$(python3 - <<'PY' "$signup1_res"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
echo "✅ P1 confirmed: $SIGNUP1_ID"

echo "==> Participant 2 signs up (waitlisted)"
signup2_payload="$(cat <<JSON
{
  "slot_id": "$SLOT_ID",
  "answers": [{"question_id":"$QUESTION_ID","value":"No"}]
}
JSON
)"
signup2_res="$(http POST "$BASE_URL/signups/" "$signup2_payload" "$P2_TOKEN")"
expect_contains "$signup2_res" "waitlisted"
SIGNUP2_ID="$(python3 - <<'PY' "$signup2_res"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
echo "✅ P2 waitlisted: $SIGNUP2_ID"

echo "==> Cancel P1 (promotes P2)"
cancel_res="$(http POST "$BASE_URL/signups/$SIGNUP1_ID/cancel" "" "$P1_TOKEN")"
expect_contains "$cancel_res" "cancelled"
echo "✅ P1 cancelled"

echo "==> Admin analytics"
analytics="$(http GET "$BASE_URL/admin/events/$EVENT_ID/analytics" "" "$ADMIN_TOKEN")"
expect_contains "$analytics" '"confirmed_signups"'
echo "✅ Analytics OK"

echo "==> Organizer roster contains answers"
roster="$(http GET "$BASE_URL/admin/events/$EVENT_ID/roster?privacy=full" "" "$ORG_TOKEN")"
expect_contains "$roster" "Do you have prior experience?"
echo "✅ Roster includes answers"

echo "==> Admin export CSV"
csv="$(curl -sS -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE_URL/admin/events/$EVENT_ID/export_csv")"
expect_contains "$csv" "Slot Start,Slot End,User Name,User Email,Status"
echo "✅ CSV export OK"

echo "==> Portal create + attach event"
portal_payload='{"name":"Smoke Test Portal","description":"portal for smoke test","visibility":"public"}'
portal_res="$(http POST "$BASE_URL/portals/" "$portal_payload" "$ADMIN_TOKEN")"
PORTAL_ID="$(python3 - <<'PY' "$portal_res"
import json, sys
print(json.loads(sys.argv[1])["id"])
PY
)"
PORTAL_SLUG="$(python3 - <<'PY' "$portal_res"
import json, sys
print(json.loads(sys.argv[1])["slug"])
PY
)"
http POST "$BASE_URL/portals/$PORTAL_ID/events/$EVENT_ID" "" "$ADMIN_TOKEN" >/dev/null
portal_public="$(http GET "$BASE_URL/portals/$PORTAL_SLUG")"
expect_contains "$portal_public" "$EVENT_ID"
echo "✅ Public portal lookup OK"

echo "==> ICS export for P2"
ics="$(curl -sS -H "Authorization: Bearer $P2_TOKEN" "$BASE_URL/signups/$SIGNUP2_ID/ics")"
expect_contains "$ics" "BEGIN:VCALENDAR"
expect_contains "$ics" "BEGIN:VEVENT"
echo "✅ ICS export OK"

echo "==> Notifications endpoints"
n1="$(http GET "$BASE_URL/notifications/my" "" "$P1_TOKEN")"
n2="$(http GET "$BASE_URL/notifications/my" "" "$P2_TOKEN")"
expect_contains "$n1" '['
expect_contains "$n2" '['
echo "✅ Notifications endpoints OK"

echo "==> Audit logs (admin)"
audit="$(http GET "$BASE_URL/admin/audit_logs" "" "$ADMIN_TOKEN")"
expect_contains "$audit" '"action"'
echo "✅ Audit logs OK"

echo "✅ SMOKE TEST PASSED"
echo "FRONTEND TIME"
