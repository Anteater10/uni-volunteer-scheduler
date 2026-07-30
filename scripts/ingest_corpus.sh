#!/usr/bin/env bash
#
# The one supported way to load the knowledge base into the copilot.
#
# Why a script and not a documented docker command: the invocation previously
# printed in app/corpus/__main__.py could not work. The backend image is built
# COPY . /app from ./backend, and docker-compose mounts no repo volume, so there
# is no /app/docs inside the container for the walker to find. The globs are
# also repo-root-relative, so passing --source docs made every candidate path
# start with "knowledge-base/" and match nothing. This script mounts the repo
# root at /repo and points --source there.
#
# It also passes the host's git SHA in via CORPUS_GIT_SHA. The image carries no
# .git, so in-container `git rev-parse` always failed and every ingestion_runs
# row recorded 40 zeros, making corpus-vs-HEAD staleness undetectable.
#
# Usage:
#   scripts/ingest_corpus.sh              # ingest (replaces changed docs)
#   scripts/ingest_corpus.sh --dry-run    # list what would be ingested, no writes
#   scripts/ingest_corpus.sh --rebuild    # truncate the corpus first
#   scripts/ingest_corpus.sh --build-index
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NETWORK="uni-volunteer-scheduler_default"
IMAGE="uni-volunteer-scheduler-backend"
ENV_FILE="backend/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found — the embedding + DB settings live there." >&2
  exit 1
fi

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "error: docker network '$NETWORK' is missing. Start the stack first:" >&2
  echo "         docker compose up -d" >&2
  exit 1
fi

GIT_SHA="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then
  GIT_DIRTY=1
  echo "note: working tree is dirty — recording git_dirty=true on this run." >&2
else
  GIT_DIRTY=0
fi

# Default to --commit when the caller passes no mode flag, so the common case is
# one word. --dry-run / --rebuild / --build-index are forwarded verbatim.
ARGS=("$@")
if [[ ! " ${ARGS[*]} " =~ " --dry-run " && ! " ${ARGS[*]} " =~ " --build-index " ]]; then
  ARGS+=("--commit")
fi

echo "ingesting corpus @ ${GIT_SHA:0:8} (args: ${ARGS[*]:-none})"

# backend/ is mounted over /app so the run uses the code in THIS checkout. The
# image bakes backend at build time (COPY . /app), so without this mount the
# container silently ingests with whatever globs the image was last built with —
# which is exactly how a --dry-run here first reported 902 files (the old
# codebase allow-list) instead of the knowledge base.
exec docker run --rm \
  --network "$NETWORK" \
  -v "$REPO_ROOT/backend":/app \
  -v "$REPO_ROOT":/repo:ro \
  -w /app \
  --env-file "$ENV_FILE" \
  -e CORPUS_GIT_SHA="$GIT_SHA" \
  -e CORPUS_GIT_DIRTY="$GIT_DIRTY" \
  -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" \
  "$IMAGE" \
  python -m app.corpus.ingest --source /repo "${ARGS[@]}"
