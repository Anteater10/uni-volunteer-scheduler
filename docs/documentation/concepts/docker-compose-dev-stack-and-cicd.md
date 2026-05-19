# Docker Compose Dev Stack & CI/CD — Reference

## TL;DR

Docker Compose declares a multi-service local stack in one YAML file:
services, networks, volumes, healthchecks, env, dependencies. Each service
runs from an image built by a Dockerfile. Production CI/CD uses GitHub Actions
to build, test, and ship the same image. This codebase runs seven Compose
services (`db`, `redis`, `mailpit`, `backend`, `migrate`, `celery_worker`,
`celery_beat`), exposes only `backend:8000`, `mailpit:1025/8025` to the host,
and gates merges on a three-job CI workflow (backend unit + frontend vitest
+ docker-composed Playwright E2E).

## API surface

### Minimal Dockerfile

```dockerfile
FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Multi-stage Dockerfile

```dockerfile
FROM python:3.10-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.10-slim
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Compose service block (sample)

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    image: my-org/backend:latest          # also tag the build
    env_file:
      - ./backend/.env
    environment:
      LOG_LEVEL: info                     # inline override
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"                        # host:container
    volumes:
      - ./backend:/app                     # live reload during dev
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 20s
    restart: unless-stopped
```

### Compose CLI cheatsheet

```bash
docker compose up -d                       # start in background
docker compose up -d backend               # start one service + its deps
docker compose ps                          # what's running
docker compose logs -f backend             # tail logs
docker compose exec backend bash           # shell into running container
docker compose run --rm migrate            # one-shot, removes container after
docker compose restart backend
docker compose down                        # stop, keep volumes
docker compose down -v                     # stop AND delete volumes
docker compose config                      # interpolate + validate
docker compose build --no-cache backend    # force rebuild
```

### Sample GitHub Actions workflow

```yaml
name: CI
on:
  push:    { branches: [main] }
  pull_request: { branches: [main] }

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        ports: ["5432:5432"]
        options: >-
          --health-cmd="pg_isready -U postgres"
          --health-interval=10s
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
      - run: pip install -r backend/requirements.txt
      - run: cd backend && alembic upgrade head
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/postgres
      - run: cd backend && pytest --cov=app --cov-report=term

  build-and-push:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: ./backend
          push: true
          tags: ghcr.io/my-org/backend:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Mental model

```
                Developer laptop                            CI runner (ephemeral)
+----------------------------------+         +------------------------------------+
| docker-compose.yml               |         | .github/workflows/ci.yml           |
|                                  |         |                                    |
|  +--db--+ +-redis-+ +-mailpit-+ |         |  services: postgres, redis         |
|     |        |          |       |         |  steps: install -> migrate -> test |
|     v        v          v       |         |                                    |
|  +-------backend--------+        |         |  separate e2e job runs            |
|  +---celery_worker------+        |         |  `docker compose up` for E2E      |
|  +---celery_beat--------+        |         +------------------------------------+
|                                  |
| networks: <project>_default       |                  |
+----------------------------------+                  | build + tag
                                                       v
                                              +-----------------+
                                              | image registry  |
                                              | ghcr / ecr      |
                                              +-----------------+
                                                       |
                                                       | deploy
                                                       v
                                              +-----------------+
                                              | prod runtime    |
                                              | k8s/ECS/Fly/... |
                                              +-----------------+
```

Three environments share one artifact: the Docker image. Dev gets it from a
local `build:`. CI builds and tests it. Prod pulls the registry-tagged
version. Drift between envs is bounded to what's in env vars and secrets.

## Usage in this codebase

### Services in `docker-compose.yml` (root)

| Service | Image / Build | Host ports | Network-internal |
|---|---|---|---|
| `db` | `postgres:16` | none | `db:5432` |
| `redis` | `redis:7` | none | `redis:6379` |
| `mailpit` | `axllent/mailpit:latest` | `1025`, `8025` | `mailpit:1025` |
| `backend` | `./backend/Dockerfile` | `8000` | `backend:8000` |
| `migrate` | `./backend/Dockerfile` (one-shot) | none | n/a |
| `celery_worker` | `./backend/Dockerfile` | none | n/a |
| `celery_beat` | `./backend/Dockerfile` | none | n/a |

Backend, migrate, worker, beat all share `./backend/Dockerfile`. They differ
only in the `command:` they run.

### Why db/redis are not exposed

The compose file has no `ports:` mapping for `db` or `redis`. The host
machine cannot connect to `localhost:5432`. From the project's `CLAUDE.md`:

> Postgres and Redis are NOT exposed to localhost — they're only reachable
> from inside the `uni-volunteer-scheduler_default` docker network.

To run tests, attach a one-off container to that network:

```bash
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

### Backend Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.10-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Currently single-stage — ships `build-essential` into the runtime image. A
multi-stage refactor is a known opportunity.

### CI: `.github/workflows/ci.yml`

Three jobs, declared in one workflow:

1. `phase0-backend-tests` — boots postgres + redis as
   *GitHub Actions service containers* (separate from compose), creates the
   test DB, runs `alembic upgrade head`, runs pytest with coverage, then a
   heredoc Python script enforces 100% coverage on
   `signup_service.py`, `routers/signups.py`, and `celery_app.py`. Hard fail
   on miss.
2. `phase0-frontend-tests` — Node 20 with `cache: npm` keyed on
   `frontend/package-lock.json`, `npm ci`, `vitest --run`.
3. `e2e-tests` — depends on jobs 1 + 2. Writes a synthetic
   `backend/.env`, runs `docker compose up -d db redis`, `docker compose run --rm migrate`,
   `docker compose up -d backend celery_worker celery_beat`, polls
   `http://localhost:8000/api/v1/healthz`, installs Playwright browsers,
   starts the frontend dev server, runs `npx playwright test`, uploads
   traces on failure, `docker compose down -v`.

### CI-specific env

The synthetic `.env` baked at CI time:

```bash
DATABASE_URL=postgresql://postgres:postgres@db:5432/uni_volunteer
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
JWT_SECRET=test-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRES_MINUTES=60
REFRESH_TOKEN_EXPIRES_DAYS=14
SEED_ADMIN_EMAIL=admin@e2e.example.com
SEED_ADMIN_PASSWORD=Admin!2345
EXPOSE_TOKENS_FOR_TESTING=1
```

`EXPOSE_TOKENS_FOR_TESTING=1` is a test-only escape hatch. In prod, magic-link
tokens never appear in API responses — they're only sent via email.

### Service containers vs compose in CI

The same workflow uses both:
- *Service containers* (postgres, redis blocks in the `services:` key) for
  the unit/integration job. They run alongside the job container with
  ports exposed on `localhost`. Cheaper than compose.
- *docker compose* for E2E because the test needs the real prod-shape
  network (migrate, celery worker, beat) and the real backend Dockerfile
  build.

## Operational concerns

### Image size

| Layer | Approximate cost |
|---|---|
| `python:3.10` base | ~900 MB |
| `python:3.10-slim` base | ~120 MB |
| `python:3.10-alpine` base | ~50 MB (but glibc gotchas) |
| `apt-get update` cache (without cleanup) | ~30 MB |
| `pip install -r requirements.txt` (FastAPI + SQLAlchemy + Celery + ...) | ~200-400 MB |
| `node_modules` accidentally COPY'd | 200 MB-1 GB |

Audit with `docker history <image>` and `dive <image>`. Set a hard size
budget per service (e.g., backend < 600 MB) and enforce in CI.

### Build cache hit rate

| Change | Cache buster reaches |
|---|---|
| Edit a `.py` file | `COPY . .` and below |
| Add a `requirements.txt` line | `COPY requirements.txt`, `RUN pip install`, and below |
| Change Dockerfile `FROM` tag | Everything |
| Change base image's digest (upstream rebuilt) | Everything |

In CI, persist cache with `cache-from: type=gha` + `cache-to: type=gha,mode=max`
in `docker/build-push-action`. A warm cache cuts a 10-minute build to 30s.

### Secrets management

| Where | How |
|---|---|
| Dev | `backend/.env` (in `.gitignore`), loaded via `env_file:` |
| CI | `${{ secrets.X }}` in workflow, automatically redacted from logs |
| Build-time | `--mount=type=secret` (BuildKit), not `ARG` |
| Prod runtime | Orchestrator secret store: k8s Secrets, ECS Secrets from SSM, Fly secrets |

Never:
- `git add .env`
- `ARG SENDGRID_KEY` (becomes image metadata)
- `echo $SECRET` (leaks to logs unless the platform redacts)
- bake secrets into a layer then `rm` them in a later layer (still in the
  earlier layer)

### Healthchecks: tuning

- `interval` — too low (`1s`) wastes CPU; too high (`60s`) means slow
  failover. `5-15s` is the sweet spot.
- `retries` — how many consecutive failures before `unhealthy`. With
  `interval: 5s, retries: 20`, it takes 100s of failure before marking
  unhealthy. Tune per service.
- `start_period` — grace window after start during which failures don't
  count toward `retries`. Use for slow-booting services.

### Deploy patterns at a glance

| Pattern | Cost | Rollback | Schema constraint | Best for |
|---|---|---|---|---|
| Rolling | 1.0-1.2x infra | Re-deploy old image | Strictly back-compat | High-frequency app deploys |
| Blue/green | 2x infra during cutover | Instant (flip LB) | Back-compat across blue+green | Risky / infrequent changes |
| Canary | 1.x infra | Roll back the canary | Back-compat across versions | App-tier with good metrics |
| Recreate | 1x, with downtime | Re-deploy old image | None | Single-instance dev / batch |

### CI metrics worth tracking

- Build duration (P50, P95).
- Cache hit rate.
- Flake rate (test that passed on rerun without code change / total runs).
- Mean time to feedback (PR open → first CI result).
- Successful deploy rate.

A budget like "PR feedback in under 8 minutes" forces design choices: split
slow jobs, parallelize tests, cache aggressively.

### 12-factor checklist for new services

- [ ] No state in the container filesystem (use a named volume or external store).
- [ ] All config via env vars; no env-specific code branches.
- [ ] Backing services swappable by URL (`DATABASE_URL`, `REDIS_URL`).
- [ ] Stateless and horizontally scalable (`compose up --scale worker=N`).
- [ ] Logs to stdout, not files.
- [ ] Graceful SIGTERM handling (drain in-flight requests).
- [ ] One-off admin tasks as `compose run --rm migrate` style commands.
- [ ] Build / release / run separated — image is immutable; config attaches
      at release.

## Glossary

- **Image** — a stack of read-only OverlayFS layers + metadata, identified
  by content hash.
- **Container** — a running (or stopped) instance of an image with a thin
  writable layer.
- **Layer** — one filesystem diff produced by a Dockerfile instruction.
  Cache key derives from instruction + input content.
- **Tag** — a human-readable label pointing to an image digest (e.g.
  `postgres:16`). Mutable.
- **Digest** — content-addressed hash of an image (`sha256:abc...`).
  Immutable. Pin in production.
- **Registry** — a server that stores images (Docker Hub, GHCR, ECR, GCR,
  Quay).
- **OverlayFS** — the Linux union filesystem Docker uses to stack layers.
- **Multi-stage build** — a Dockerfile with multiple `FROM` lines; lets you
  drop build tools from the final image.
- **BuildKit** — the modern Docker build backend with parallel stages,
  build-time secrets, registry cache, and frontend plugins.
- **`docker compose`** — the v2 plugin (Go) replacement for the older
  Python `docker-compose` tool. Spec at compose-spec.io.
- **Service** — a single container definition in a compose file.
- **Project** — a compose deployment, named by default after the directory.
  Used as a prefix for the network and container names.
- **Service name** — the DNS name of a service inside the project network.
  In this repo: `db`, `redis`, `mailpit`, `backend`.
- **Named volume** — Docker-managed persistent storage that survives
  container restart.
- **Bind mount** — host directory mapped into the container.
- **Healthcheck** — a command Docker runs periodically; result drives
  `service_healthy` gating.
- **Service container** (GitHub Actions) — a container started by the
  Actions runner alongside the job container. Not the same as compose.
- **Runner** — the ephemeral VM that executes a GitHub Actions job.
- **Matrix** — running the same job across a grid of parameters
  (e.g., Python 3.10/3.11/3.12 × OS).
- **Secret** — sensitive value stored encrypted in the platform, exposed as
  an env var to authorized jobs, redacted from logs.
- **Artifact** — a file or directory produced by a job, retained for download
  (e.g., playwright traces on failure).
- **Rolling deploy** — replace instances of the running service one at a
  time with the new version.
- **Blue/green** — run two full environments; flip a load balancer to switch
  traffic.
- **Canary** — route a small slice of traffic to the new version, ramp on
  health gates.
- **12-factor app** — Heroku-era methodology for building service apps that
  are portable, scalable, and config-driven.
