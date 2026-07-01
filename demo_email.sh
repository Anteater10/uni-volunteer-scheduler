#!/usr/bin/env bash
# Regenerate a fresh magic-link confirm email into Mailpit (http://localhost:8025).
# Works around the enqueue-before-commit race by pausing the worker during signup,
# so the signup row commits before the email task runs.
set -e
WORKER=uni-event-scheduler-celery_worker-1
DB=uni-event-scheduler-db-1
docker pause "$WORKER" >/dev/null
SLOT=$(docker exec "$DB" psql -U postgres -d uni_volunteer -t -A -c \
  "SELECT id FROM slots WHERE current_count < capacity LIMIT 1;" | tr -d '[:space:]')
curl -s -X POST http://localhost:8000/api/v1/public/signups \
  -H "Content-Type: application/json" \
  -d "{\"first_name\":\"Demo\",\"last_name\":\"Volunteer\",\"email\":\"demo@volunteer.demo\",\"phone\":\"8055551234\",\"slot_ids\":[\"$SLOT\"]}" >/dev/null
docker unpause "$WORKER" >/dev/null
echo "Fresh confirm email sent -> check Mailpit at http://localhost:8025 (newest message)."
