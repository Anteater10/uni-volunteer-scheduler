#!/usr/bin/env bash
# Nightly Postgres backup for the EC2 + RDS deployment (docker-compose.aws.yml).
#
# Unlike scripts/backup_db.sh (which shells into the compose `db` service),
# there is no local db container here — Postgres is RDS. This dumps directly
# against the RDS endpoint using a throwaway `postgres` container, so nothing
# needs to be installed on the EC2 host besides Docker (already required).
#
# RDS already takes automated snapshots (see docs/deployment-aws.md § RDS
# backups) — this script is the SECOND, independent copy: a portable logical
# dump you can restore into any Postgres, and one you should ship off-host
# (S3) per the "a backup on the same disk as the database survives software
# mistakes, not hardware ones" rule.
#
# Connection info comes from backend/.env.production's DATABASE_URL, unless
# PGHOST/PGUSER/PGPASSWORD/PGDATABASE/PGPORT are already exported.
#
# Wire it into cron on the EC2 host:
#   0 3 * * * cd /opt/uni-volunteer-scheduler && ./scripts/backup_db_rds.sh >> backups/backup.log 2>&1
#
# Optional off-host copy: set S3_BUCKET (e.g. s3://uvs-backups/db) and
# attach an IAM instance role with s3:PutObject on that bucket to the EC2
# instance — do not put long-lived AWS keys in this script or the env file.
#
# Restore drill (do this once BEFORE you need it):
#   gunzip -c backups/uvs-YYYYMMDDTHHMMSS.sql.gz | \
#     docker run --rm -i -e PGPASSWORD="$PGPASSWORD" postgres:16-alpine \
#       psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE"
set -euo pipefail

ENV_FILE="${ENV_FILE:-./backend/.env.production}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
S3_BUCKET="${S3_BUCKET:-}"

# Parse DATABASE_URL=postgresql://user:pass@host:port/dbname?sslmode=require
# out of the env file if the PG* vars aren't already set in the environment.
if [ -z "${PGHOST:-}" ] && [ -f "$ENV_FILE" ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -n1 | cut -d= -f2-)"
  if [ -n "${DATABASE_URL:-}" ]; then
    rest="${DATABASE_URL#postgresql://}"
    creds="${rest%%@*}"
    hostpart="${rest#*@}"
    PGUSER="${creds%%:*}"
    PGPASSWORD="${creds#*:}"
    hostport_db="${hostpart%%\?*}"      # strip ?sslmode=require etc.
    hostport="${hostport_db%%/*}"
    PGDATABASE="${hostport_db#*/}"
    if [ "$hostport" != "${hostport#*:}" ]; then
      PGHOST="${hostport%%:*}"
      PGPORT="${hostport#*:}"
    else
      PGHOST="$hostport"
    fi
  fi
fi

: "${PGHOST:?set PGHOST or DATABASE_URL in $ENV_FILE}"
: "${PGUSER:?set PGUSER or DATABASE_URL in $ENV_FILE}"
: "${PGPASSWORD:?set PGPASSWORD or DATABASE_URL in $ENV_FILE}"
: "${PGDATABASE:?set PGDATABASE or DATABASE_URL in $ENV_FILE}"
PGPORT="${PGPORT:-5432}"

STAMP="$(date -u +%Y%m%dT%H%M%S)"
OUT="${BACKUP_DIR}/uvs-${STAMP}.sql.gz"
mkdir -p "${BACKUP_DIR}"

docker run --rm \
  -e PGPASSWORD="${PGPASSWORD}" \
  postgres:16-alpine \
  pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" --no-owner "${PGDATABASE}" \
  | gzip > "${OUT}"

# A zero-byte dump means pg_dump failed inside the pipe — fail loudly.
if [ ! -s "${OUT}" ]; then
  rm -f "${OUT}"
  echo "ERROR: backup produced an empty dump" >&2
  exit 1
fi

find "${BACKUP_DIR}" -name 'uvs-*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

if [ -n "${S3_BUCKET}" ]; then
  aws s3 cp "${OUT}" "${S3_BUCKET}/$(basename "${OUT}")"
fi

echo "backup ok: ${OUT} ($(du -h "${OUT}" | cut -f1))"
