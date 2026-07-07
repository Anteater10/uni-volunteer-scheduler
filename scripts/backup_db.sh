#!/usr/bin/env bash
# Nightly Postgres backup for the production compose stack.
#
# Dumps the `db` service via docker compose (no port exposure needed), gzips
# into $BACKUP_DIR with a timestamped name, and prunes dumps older than
# $RETENTION_DAYS. Run from the repo root on the production host.
#
# Wire it into cron (deployment.md § Backups):
#   0 3 * * * cd /opt/uni-volunteer-scheduler && ./scripts/backup_db.sh >> backups/backup.log 2>&1
#
# Restore drill (do this once BEFORE you need it):
#   gunzip -c backups/uvs-YYYYMMDDTHHMMSS.sql.gz | \
#     docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d uni_volunteer
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-uni_volunteer}"
DB_USER="${DB_USER:-postgres}"

STAMP="$(date -u +%Y%m%dT%H%M%S)"
OUT="${BACKUP_DIR}/uvs-${STAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

docker compose -f "${COMPOSE_FILE}" exec -T db \
  pg_dump -U "${DB_USER}" --no-owner "${DB_NAME}" | gzip > "${OUT}"

# A zero-byte dump means pg_dump failed inside the pipe — fail loudly.
if [ ! -s "${OUT}" ]; then
  rm -f "${OUT}"
  echo "ERROR: backup produced an empty dump" >&2
  exit 1
fi

find "${BACKUP_DIR}" -name 'uvs-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "backup ok: ${OUT} ($(du -h "${OUT}" | cut -f1))"
