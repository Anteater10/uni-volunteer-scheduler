#!/bin/sh
set -eu

alembic upgrade head
python -m app.seed_admin
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
