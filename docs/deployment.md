# Deployment

Status: **not yet deployed to any public host.** This is Phase 38 ("Deploy + admin
handoff") territory, which is unstarted. This document + the production artifacts in
the repo make a real deploy "one decision away" (which host) without further coding.

## What runs

| Component | What it is | Prod artifact |
|---|---|---|
| Postgres 16 **with pgvector** | primary DB; corpus retrieval needs the extension | `db` service / managed PG with pgvector |
| Redis 7 | Celery broker + result backend + RedBeat schedule | `redis` service / managed Redis |
| Backend | FastAPI (uvicorn), `/api/v1/*`, SSE copilot stream | `backend/Dockerfile` |
| migrate | one-shot `alembic upgrade head` + seed admin | runs before backend |
| celery_worker / celery_beat | reminders, profile extraction, idle-session sweep | same image, different command |
| Frontend | React 19 / Vite 7 SPA, static build | `frontend/Dockerfile` (Node 20 + nginx) |
| Caddy | TLS termination + routing (`/api/*` → backend, else → SPA) | `Caddyfile` |

Email is sent via SendGrid in production (the dev `mailpit` catcher is dropped).

---

## 1. Run it locally (no internet) — verified working

Dev stack (backend + workers + db + redis + mailpit):

```bash
docker compose up -d --build
curl http://localhost:8000/api/v1/health        # -> {"status":"ok"}
docker compose logs -f backend                   # follow logs
docker compose down                              # stop (add -v to wipe data)
```

The frontend runs separately. **Requires Node 20+** (Vite 7 won't run on Node 18):

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev   # http://localhost:5173
```

Seeded admin login comes from `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` in
`backend/.env`. Mailpit's web UI (sent emails) is at http://localhost:8025.

---

## 2. Production single-host (one VPS) — the artifacts in this repo

Files: `docker-compose.prod.yml`, `frontend/Dockerfile`, `frontend/nginx.conf`,
`Caddyfile`, `backend/.env.production.example`.

```bash
# 0. A VPS (DigitalOcean/Hetzner/Linode, ~$6-12/mo) with Docker installed.
#    A DNS A record for your domain pointing at the VPS IP. Ports 80+443 open.

# 1. Secrets
cp backend/.env.production.example backend/.env.production
#    edit it: fresh JWT_SECRET, DB password, SendGrid key, OpenRouter key,
#    real https URLs, strong admin password. NEVER commit this file.

# 2. Host-level env for compose interpolation
export POSTGRES_PASSWORD='<same password as in DATABASE_URL>'
export DOMAIN='scitrek.example.org'
export VITE_API_URL="https://${DOMAIN}"

# 3. Launch
docker compose -f docker-compose.prod.yml up -d --build

# 4. Verify
curl https://${DOMAIN}/api/v1/health             # -> {"status":"ok"}
docker compose -f docker-compose.prod.yml ps
```

Caddy auto-provisions a Let's Encrypt cert for `$DOMAIN`. The frontend and API are
served from the **same origin**, so there's no CORS hop.

---

## 3. Managed PaaS (Render / Railway / Fly.io)

Same images, but data services are managed (no `db`/`redis` containers):

1. Provision a **Postgres with pgvector** and a **Redis** add-on.
2. Deploy three services from `backend/Dockerfile` with different start commands:
   - web: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4`
   - worker: `celery -A app.celery_app.celery worker -l info`
   - beat: `celery -A app.celery_app.celery beat -l info -S redbeat.RedBeatScheduler`
   - run `alembic upgrade head && python -m app.seed_admin` as a release/pre-deploy step.
3. Deploy the frontend as a **static site**: build command `npm run build`, publish
   `dist/`, with `VITE_API_URL` set to the backend's public URL at build time.
4. Set all backend env vars from `backend/.env.production.example` in the platform's
   secret store. If frontend and API are on different domains, set
   `CORS_ALLOWED_ORIGINS` to the frontend origin.

Watch-outs: the backend image is large (PyTorch + sentence-transformers for local
BGE embeddings) — some free tiers reject it. Free tiers also sleep, which breaks
Celery Beat schedules.

---

## Production hardening checklist

- [ ] `EXPOSE_TOKENS_FOR_TESTING` **absent** (it leaks auth tokens in signup responses).
- [ ] Fresh `JWT_SECRET` (`python -c "import secrets; print(secrets.token_hex(32))"`).
- [ ] Strong Postgres password; db/redis **not** published to the public internet.
- [ ] Rotate the dev secrets that were exposed (OpenRouter, SendGrid keys).
- [ ] `EMAIL_MODE=sendgrid` with a **verified** sender domain.
- [ ] Strong `SEED_ADMIN_PASSWORD` (or change the admin password after first login).
- [ ] Backups for the Postgres volume / managed DB — see **Backups** below.
- [ ] Ran the pre-migration check — see **Before every `alembic upgrade head` on
      prod** below. Skip it only on a database you know is empty.
- [ ] `ENVIRONMENT=production` set (compose sets it; disables /docs and
      hard-blocks `EXPOSE_TOKENS_FOR_TESTING` at boot).
- [ ] `SENTRY_DSN` set if you want error monitoring (empty = off).
- [ ] The **backend port is not published** — all traffic must arrive through
      Caddy. The request-body ceiling that stands in for the unpatched
      starlette form-parsing bug (BASE-CONFIG-36) lives in the `Caddyfile`, so a
      directly reachable `backend:8000` bypasses it. See the comment there.
- [ ] Login lockout left at its defaults unless you have a reason
      (`LOGIN_MAX_FAILED_ATTEMPTS=10`, `LOGIN_LOCKOUT_MINUTES=15`). A locked
      account returns the same 401 as a wrong password on purpose, so the only
      place the lockout is visible is the audit log — look for
      `user_login_locked` if staff report being unable to log in.
- [ ] Ingest the corpus once after deploy so the copilot has something to retrieve
      (`python -m app.corpus ...`) — otherwise RAG answers come back empty.

## Before every `alembic upgrade head` on prod

Two commands, in this order, against the production database:

```sql
SELECT version_num FROM alembic_version;   -- where the DB actually is
SELECT count(*) FROM signups;              -- how much history is at stake
```

Then take the dump (see **Backups**). The reason this is a ritual and not a
suggestion: migration `0009_phase08_v1_1_schema_realignment` rewires `signups`
from a `user_id` anchor to a `volunteer_id` one, and it cannot derive the new
column for rows that already exist. It used to resolve that by running an
unconditional `DELETE FROM signups` — so on a database already holding
bookings, the first command of a deploy would erase the entire booking history
and report success.

It no longer does. Both directions of 0009 now count the table first and abort
with the row count in the error if it is non-empty
(`backend/tests/test_migration_0009_guard.py` holds that in place). But the
guard only converts silent data loss into a **failed deploy**, which is still a
failed deploy. If you hit it, the recovery is in the error message: dump, then
backfill `volunteer_id` by hand — add it nullable, create a `volunteers` row per
distinct signup identity, point the column at it, then `SET NOT NULL`.

This only bites a database that is below 0009 and already has bookings — i.e.
an old install being brought forward, not a fresh one. A fresh
`upgrade head` starts from an empty table and the guard is inert.

## Backups

`scripts/backup_db.sh` dumps the compose `db` service to `./backups/` (gzip,
timestamped) and prunes dumps older than `RETENTION_DAYS` (default 14).
Wire it into cron on the host:

```cron
0 3 * * * cd /opt/uni-volunteer-scheduler && ./scripts/backup_db.sh >> backups/backup.log 2>&1
```

Copy `backups/` somewhere off the host (object storage, another machine) —
a backup on the same disk as the database only survives software mistakes,
not hardware ones. Run one restore drill before go-live (command in the
script header). Take a manual dump immediately **before** every
`alembic upgrade head` on prod.

## Known issues (not deploy blockers)

- Alembic `downgrade()` functions don't `DROP TYPE` enums — only downgrade→upgrade
  round-trips fail. A fresh `upgrade head` (what deploy runs) works fine.
