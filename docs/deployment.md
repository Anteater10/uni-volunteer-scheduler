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
- [ ] Backups for the Postgres volume / managed DB.
- [ ] Ingest the corpus once after deploy so the copilot has something to retrieve
      (`python -m app.corpus ...`) — otherwise RAG answers come back empty.

## Known issues (not deploy blockers)

- Alembic `downgrade()` functions don't `DROP TYPE` enums — only downgrade→upgrade
  round-trips fail. A fresh `upgrade head` (what deploy runs) works fine.
