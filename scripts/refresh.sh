#!/usr/bin/env bash
# Rebuild + restart backend services to pick up code changes.
# Frontend is served by Vite dev (HMR) — it refreshes on save, no script needed.
#
# Usage:
#   ./scripts/refresh.sh              # rebuild backend + celery_worker + celery_beat
#   ./scripts/refresh.sh --migrate    # run alembic migrations first, then rebuild
#   ./scripts/refresh.sh --full       # rebuild and recreate ALL services (nuclear option)
#   ./scripts/refresh.sh --logs       # after rebuild, tail backend logs (ctrl+c to exit)
#   ./scripts/refresh.sh --help

set -euo pipefail

cd "$(dirname "$0")/.."

MIGRATE=0
FULL=0
LOGS=0

for arg in "$@"; do
  case "$arg" in
    --migrate) MIGRATE=1 ;;
    --full)    FULL=1 ;;
    --logs)    LOGS=1 ;;
    --help|-h)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg" >&2
      echo "Run with --help to see usage." >&2
      exit 1
      ;;
  esac
done

if [[ "$MIGRATE" == "1" ]]; then
  echo "==> Running alembic migrations"
  docker compose run --rm migrate
fi

if [[ "$FULL" == "1" ]]; then
  echo "==> Full rebuild: all services"
  docker compose up -d --build
else
  echo "==> Rebuilding backend + celery_worker + celery_beat"
  docker compose up -d --build backend celery_worker celery_beat
fi

echo
echo "==> Container status"
docker compose ps --format "table {{.Service}}\t{{.Status}}"

echo
echo "Done. Backend: http://localhost:8000  |  Mailpit: http://localhost:8025"
echo "Frontend (Vite HMR) runs via 'npm run dev' in ./frontend — not managed by this script."

if [[ "$LOGS" == "1" ]]; then
  echo
  echo "==> Tailing backend logs (ctrl+c to stop)"
  docker compose logs -f backend
fi
