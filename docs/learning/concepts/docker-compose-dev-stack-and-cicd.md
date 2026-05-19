# Docker Compose Dev Stack & CI/CD

## Why this matters

A modern web app is not a process — it is half a dozen processes (web server,
DB, cache, queue broker, queue worker, scheduler, mail catcher) that have to
agree on networking, env vars, and startup order. The local dev experience
makes or breaks a team: if "checkout the repo and run it" takes a day, every
new contributor pays a tax. If CI is flaky or builds take 25 minutes, you stop
trusting the green check.

Docker Compose solves the "many processes on my laptop" problem. CI (GitHub
Actions) plus a registry plus a deploy mechanism solves the "ship to prod
reliably" problem. They share the same building block — the OCI container
image — so a service that boots in compose also boots in CI also boots in
prod.

In interviews you will be asked some flavor of:

- "How would you set up a CI/CD pipeline for a Python/Node service?"
- "Walk me through a Dockerfile. What does multi-stage do?"
- "Your build takes 20 minutes. Make it faster."
- "How does service A talk to service B in docker compose?"
- "What is the difference between Compose and Kubernetes?"

This lecture covers the moving parts and grounds them in this codebase's
`docker-compose.yml` and `.github/workflows/ci.yml`.

## The design choice

### Compose vs raw `docker run`

Without Compose, spinning up the dev stack means:

```bash
docker network create devnet
docker run -d --network devnet --name db -e POSTGRES_PASSWORD=... postgres:16
docker run -d --network devnet --name redis redis:7
docker run -d --network devnet --name mailpit ... axllent/mailpit
docker run -d --network devnet --name backend -p 8000:8000 ... my-backend
docker run -d --network devnet --name worker my-backend celery ...
```

Six commands, six places for typos, no health-check ordering, no shared env
file, and "stop everything" is a manual loop. Compose collapses this into a
declarative YAML file — one `docker compose up` brings the whole graph up,
in the right order, on a shared network.

What Compose gives you:

- **Declarative service graph** — services, volumes, networks in one file.
- **Auto-generated network** — services reach each other by DNS name.
- **`depends_on` with health gating** — wait for db to be `service_healthy`
  before starting backend.
- **Single env file** — `env_file:` references a `.env` once.
- **Volume management** — named volumes survive `down`, are wiped by `down -v`.
- **Profiles** — group services so `--profile test` brings up a subset.

### Compose vs Kubernetes for dev

Kubernetes is the production answer for many teams, but in dev it is overkill:

| Concern | Compose | Kubernetes (kind/minikube) |
|---|---|---|
| Boot time | seconds | minutes |
| YAML lines for "postgres + redis + app" | ~30 | ~150+ across Deployments / Services / ConfigMaps |
| Conceptual load | services, networks, volumes | pods, deployments, services, ingress, configmaps, secrets, PVCs, RBAC |
| Mounts host code for live reload | trivial (`volumes: ./src:/app`) | possible but awkward (Skaffold, Tilt) |
| Models prod | no | yes |
| When to choose | every dev laptop | when the team already runs k8s in prod and the prod-dev gap is biting |

The pragmatic split most teams land on: **Compose for dev**, k8s (or ECS, Cloud
Run, Fly) for prod, and a CI pipeline that builds the same image used by both.

### Compose vs `pip install + brew install postgres`

The "native" alternative — install Python, Postgres, Redis on the host
directly — works for one developer for a few months. Then somebody runs macOS
Sonoma, somebody else Ubuntu, the Postgres major version drifts, a CI runner
has Redis 6 while a dev has 7. Containers make the runtime artifact the same
on every machine. The tax is that a Docker rebuild is slower than re-running
`uvicorn` on the host. Worth it.

## How it works under the hood

### Image layers and the cache

A Docker image is a stack of read-only filesystem layers (Linux OverlayFS by
default). Every instruction in a Dockerfile that touches the filesystem
(`COPY`, `RUN`, `ADD`) creates a new layer. At runtime, the container gets a
thin writable layer on top.

The cache key for each layer is roughly `hash(parent_layer_id + instruction + input_content)`.
That is why this ordering matters:

```dockerfile
FROM python:3.10-slim

# 1. Copy ONLY the requirements file
COPY requirements.txt /app/requirements.txt

# 2. Install deps (this layer is huge — pip downloads everything)
RUN pip install --no-cache-dir -r /app/requirements.txt

# 3. THEN copy source code
COPY . /app
```

If you reorder so that `COPY . /app` comes first, every code change busts the
`pip install` layer and you reinstall 200MB of wheels on every rebuild.

### Multi-stage builds

A single `FROM` ships every dev tool you needed to build the artifact —
compilers, headers, `build-essential` — to the runtime image. Multi-stage
fixes that:

```dockerfile
FROM python:3.10-slim AS builder
RUN apt-get update && apt-get install -y build-essential
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.10-slim
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . /app
WORKDIR /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The final image has no compilers, no apt cache, no `.pyc` files from build.
For Node, the same pattern — `node:20` as builder, `node:20-slim` or
`nginx:alpine` as runtime.

This codebase's `backend/Dockerfile` is currently single-stage — it carries
`build-essential` into the runtime image. That's a known wart for a future
slimming pass.

### Network DNS by service name

Compose creates a default user-defined bridge network named
`<project>_default`. Every service is reachable from every other by its
**service name**, resolved by an embedded DNS server at `127.0.0.11` inside
each container.

In this repo:
- `backend` connects to Postgres at `db:5432` (not `localhost:5432`).
- Backend talks to Redis at `redis:6379`.
- Backend SMTPs to Mailpit at `mailpit:1025`.
- Volunteers? They cannot. Postgres and Redis have no `ports:` mapping, so
  they're only reachable from inside the network. The host machine cannot hit
  `localhost:5432`.

That last point is exactly the "Postgres and Redis are NOT exposed to
localhost" line in this repo's `CLAUDE.md`. Tests run in a one-off container
joined to `uni-volunteer-scheduler_default`, which is the only way to reach
the DB.

### Volumes

Two flavors:

- **Named volumes** (`pgdata:/var/lib/postgresql/data`) — Docker-managed,
  survive container restart and `compose down`, wiped by `compose down -v`.
- **Bind mounts** (`./backend:/app`) — host directory mapped in. Useful for
  live reload during dev but slower on Mac (osxfs / VirtioFS).

This repo uses a named volume for Postgres data so `docker compose restart db`
doesn't lose your seeded admin user.

### Healthchecks and ordering

`depends_on: { condition: service_healthy }` waits until the named service's
healthcheck reports `healthy` before starting. The check itself is configured
on the *target* service:

```yaml
db:
  image: postgres:16
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres -d uni_volunteer"]
    interval: 5s
    timeout: 3s
    retries: 20
```

`interval` is the gap between probes; `retries` is how many consecutive
failures before `unhealthy`. `start_period` (not used here) lets you give a
slow-booting service a grace window before failures count.

### CI: matrix, cache, secrets

GitHub Actions runs jobs on ephemeral runners. Each job:
1. Boots a fresh VM/container.
2. Checks out code.
3. Runs steps.
4. Tears down.

To avoid reinstalling 200MB of node_modules on every push, you use
`actions/setup-node` with `cache: npm` (uses `package-lock.json` as a key)
or `actions/cache` for arbitrary paths.

For secrets: never commit `.env`. Use repo/org-level secrets exposed as env
vars in workflow steps. The secrets are redacted from logs automatically (so
long as you do not `echo $SECRET`).

Matrix builds run the same job N times across versions:

```yaml
strategy:
  matrix:
    python: ["3.10", "3.11", "3.12"]
```

### Deployment patterns

**Rolling deploy** — replace instances one at a time. Cheap, simple, but mid-deploy
both versions serve traffic. Schema migrations must be backward-compatible.

**Blue/green** — two full environments. Switch a load balancer to flip traffic.
Costly (double infra during deploy) but instant rollback.

**Canary** — route 1% / 5% / 25% / 100% of traffic to the new version with health
gates between steps. Best for catching regressions before they hit everyone.
Needs traffic-splitting at the LB / service-mesh layer.

### 12-factor app

The widely-cited *Twelve-Factor App* principles map directly onto a
Compose-friendly service:

1. Codebase — one repo per service, multiple deploys.
2. Dependencies — explicit (`requirements.txt`, `package.json`).
3. Config — env vars, not files. (`env_file:` in compose.)
4. Backing services — Postgres, Redis are attached resources, swap-by-URL.
5. Build / release / run — strict separation. Build produces an image; release
   binds it with config; run executes.
6. Processes — stateless. State lives in backing services.
7. Port binding — the app self-hosts (`uvicorn` listens on 8000); no
   external app server required.
8. Concurrency — scale by process count (`compose up --scale worker=3`).
9. Disposability — fast startup and graceful shutdown on SIGTERM.
10. Dev/prod parity — keep them close. Compose-in-dev + same image in prod.
11. Logs — write to stdout/stderr; let the platform aggregate.
12. Admin processes — one-off scripts run in the same env (`compose run --rm migrate`).

## How this codebase uses it

### `docker-compose.yml`

The root `docker-compose.yml` defines seven services:

- `db` — Postgres 16, named volume `pgdata`, healthcheck via `pg_isready`. No
  `ports:` mapping — internal only.
- `redis` — Redis 7 with AOF persistence. Healthcheck `redis-cli ping`. No
  ports.
- `mailpit` — local SMTP catcher. Ports `1025` (SMTP) and `8025` (web UI)
  exposed because devs need to read captured mail.
- `backend` — FastAPI/uvicorn from `./backend/Dockerfile`, port `8000`
  exposed, `depends_on` db+redis+mailpit with health conditions on db/redis.
- `migrate` — one-shot: `alembic upgrade head && python -m app.seed_admin`.
  `restart: "no"` because it's not a long-running service.
- `celery_worker` — Celery worker against the same image, no exposed port.
- `celery_beat` — Celery beat scheduler using RedBeat (Redis-backed) so the
  schedule survives restarts.

A few things worth noting:

```yaml
backend:
  build:
    context: ./backend
    dockerfile: Dockerfile
  env_file:
    - ./backend/.env
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy
    mailpit:
      condition: service_started
  ports:
    - "8000:8000"
```

`env_file: ./backend/.env` means the env is loaded *outside* the image — no
secrets in the image layers.

The migrate service shares the backend image. This is intentional: alembic
ships with the app code. A separate "migration image" would just duplicate the
build.

`redbeat.RedBeatScheduler` is passed via `-S` because the default
`PersistentScheduler` writes to a local SQLite file, which doesn't survive
container restart. RedBeat stores schedule state in Redis.

### `.github/workflows/ci.yml`

The CI pipeline has three jobs:

1. **`phase0-backend-tests`** — boots Postgres + Redis as GitHub
   *service containers* (these run alongside the job container on the same
   network), `pip install` backend deps, runs `alembic upgrade head`, runs
   `pytest` with coverage, then runs a heredoc Python script that asserts
   `app/signup_service.py`, `app/routers/signups.py`, and `app/celery_app.py`
   each hit 100% line coverage. The coverage gate is a hard `sys.exit(1)`.

2. **`phase0-frontend-tests`** — sets up Node 20, `cache: npm`
   (`cache-dependency-path: frontend/package-lock.json`), `npm ci`, and
   `npm run test -- --run` (vitest in single-run mode).

3. **`e2e-tests`** — depends on the previous two. Writes a synthetic
   `backend/.env` with test secrets, brings up the *real* compose stack
   (`docker compose up -d db redis`, then `compose run --rm migrate`, then
   `compose up -d backend celery_worker celery_beat`), polls for
   `/api/v1/healthz`, starts the frontend dev server, installs Playwright
   browsers, runs `npx playwright test`, uploads traces on failure,
   `docker compose down -v` at the end.

Things to notice:

- Backend tests use *service containers* (a GitHub Actions feature) for
  Postgres/Redis. E2E tests use `docker compose` because it needs the actual
  prod-shape network.
- Env vars are inlined at the workflow level for tests. Real prod secrets
  would be `${{ secrets.X }}` references.
- The synthetic `.env` includes `EXPOSE_TOKENS_FOR_TESTING=1` to let
  Playwright read magic-link tokens out of the API response — this is a
  test-only escape hatch you would never enable in prod.
- The matrix-style separation (`backend` / `frontend` / `e2e`) means a
  frontend-only PR doesn't wait for the slow E2E run *unless* it touches
  components that gate it.

### Running tests locally

Because db/redis are not exposed, local backend tests must join the network:

```bash
docker exec uni-volunteer-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"
docker run --rm \
  --network uni-volunteer-scheduler_default \
  -v $PWD/backend:/app -w /app \
  -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
  uni-volunteer-scheduler-backend \
  sh -c "pytest -q"
```

That `--network uni-volunteer-scheduler_default` is the bit beginners miss.
Without it, `db:5432` doesn't resolve.

## Common pitfalls

### Image size bloat

- Single-stage Dockerfiles ship build tools. A `python:3.10` final layer is
  ~900MB; `python:3.10-slim` is ~120MB.
- `apt-get install` without `rm -rf /var/lib/apt/lists/*` in the same `RUN`
  leaves ~30MB of apt cache.
- `COPY . /app` after a broad `.dockerignore` failure pulls in `node_modules`,
  `.git`, IDE config, coverage reports.

Run `docker history <image>` to see per-layer sizes. Hunt the fat layers.

### Cache busts on every push

If you `COPY package.json package-lock.json ./` and then `RUN npm ci`, your
dep install caches across code changes. If you `COPY . .` first, every code
change busts npm install. The same applies to `pip`, `bundler`, `mvn`, `go
mod download`, `cargo fetch`.

### Secrets baked into image layers

```dockerfile
RUN echo "SENDGRID_KEY=SG.xxx" > .env  # BAD — visible in image
```

Once in a layer, the secret is in the image even if you `rm` it in a later
layer. Use BuildKit's `--mount=type=secret` or pass at runtime via `env_file`
/ orchestrator secret manager.

### "Works on my laptop, fails in CI"

- Hardcoded `localhost` — works on dev (host networking via published ports),
  fails in CI where services may be on a network. Always use service names.
- Timezone — CI runners default to UTC, your laptop is PT.
- File-system case sensitivity — macOS HFS+ is case-insensitive by default,
  Linux is not. `import Foo from './foo'` works locally, fails on CI.
- Locale — `LANG=C.UTF-8` not set; `print(u"é")` crashes.

### Flaky tests

- Time-based assertions (`assertEqual(datetime.now(), expected)`).
- Order-dependent tests when one test pollutes shared state.
- External network calls without mocking.
- Parallel test workers writing to the same DB rows.

Quarantine flakes immediately. A 95% pass rate destroys CI trust faster than
a hard failure.

### Non-deterministic builds

Two builds of the same commit produce different images because:
- `pip install Django` resolves to the latest minor at build time. Pin
  exact versions in lockfiles.
- `apt-get update` followed by `apt-get install` resolves to the latest deb
  index. Pin the base image to a digest (`postgres:16@sha256:...`).
- A `npm ci` that respects `package-lock.json` is deterministic; `npm install`
  isn't.

### Long CI feedback loops

A 25-minute CI run kills flow. Wins:

- Cache deps aggressively (`actions/cache` keyed on lockfile hash).
- Parallelize test files (`pytest-xdist`, `vitest --shard`).
- Split slow tests into a nightly job, run the fast subset on PRs.
- Use BuildKit cache for Docker builds (`type=gha`, `type=registry`).

### Healthcheck never reports healthy

A common cause: the container *does* start, but the healthcheck command isn't
installed in the image. `pg_isready` works for `postgres:16` because it ships
in the image. For your app image, a healthcheck like
`curl -f http://localhost:8000/health` requires `curl` to be installed.

## Interview Q&A

**Q (junior): What is a Dockerfile vs a Docker image vs a Docker container?**
A: A Dockerfile is a text recipe. A Docker image is the built artifact —
a stack of read-only filesystem layers plus metadata. A container is a
running (or stopped) instance of an image with a thin writable layer on top.
Same image, can boot many containers.

**Q (junior): What does `COPY` do that `ADD` does not?**
A: `ADD` does what `COPY` does but additionally unpacks tarballs and can
fetch URLs. The Docker docs recommend `COPY` for predictability — `ADD`'s
extra behaviors are surprising.

**Q (junior): In docker compose, how does service A talk to service B?**
A: Compose creates a user-defined bridge network and an embedded DNS server.
Every service is reachable by its service name on that network. In this
repo, the backend container connects to `db:5432`, not `localhost:5432`.

**Q (mid): Walk me through a multi-stage Dockerfile and why you'd use one.**
A: Multi-stage uses multiple `FROM` lines, each starting a fresh build
context. You compile / install in a "builder" stage with full toolchain,
then `COPY --from=builder` only the final artifacts into a slim runtime
image. Result: final image without build tools, source code beyond what's
needed, or apt caches. Smaller image, less attack surface, faster pulls.

**Q (mid): How would you set up a CI/CD pipeline for a Python web app?**
A: Three stages.
- **CI**: on every PR, lint (ruff/flake8), type-check (mypy), unit + integration
  tests with Postgres/Redis as service containers, coverage gate. Cache `pip`
  by `requirements.txt` hash. Run E2E if integration passes.
- **Build**: on merge to main, build a Docker image, tag with git SHA, push
  to a registry (GHCR, ECR). Sign the image (cosign) if security-critical.
- **CD**: trigger a deploy job that updates the orchestrator
  (k8s rollout, ECS update-service, `fly deploy`) with the new image tag.
  Run smoke tests against the deploy. Rollback on failure (kubectl
  rollout undo, previous task definition).

Plus: env-specific configs from a secret manager, blue/green or rolling
strategy, monitoring + alerting hooks.

**Q (mid): Your Docker build takes 12 minutes. Speed it up.**
A: First, profile — `docker build --progress=plain` shows per-step time.
Then:
- Reorder Dockerfile so the dependency install (slow, rarely changes)
  comes before source copy (fast, changes every commit). Cache hit on deps.
- Multi-stage to drop build-time tools from the final image.
- Switch base to `-slim` or `-alpine`.
- BuildKit + `--cache-from=type=gha` (in GitHub Actions) or
  `--cache-from=type=registry,ref=...` to share cache across runs.
- For language deps: prefer `npm ci` (uses lockfile, deterministic) over
  `npm install`.
- Combine `RUN apt-get update && apt-get install -y X && rm -rf /var/lib/apt/lists/*`
  into one layer.
- Pre-build a base image with stable deps; child images only add the
  app code.

**Q (senior): What's the difference between docker compose `depends_on`
with and without `condition: service_healthy`?**
A: Bare `depends_on: [db]` only waits for `db` to *start* — the container
is running, but the Postgres process inside may still be initializing. The
backend will try to connect and crash. `condition: service_healthy` waits
until the configured healthcheck reports healthy. Requires the dependency
to have a `healthcheck:` block. The alternative is application-level
retries (which you should also have for resilience).

**Q (senior): Explain blue/green vs canary deploys. When would you use each?**
A: Blue/green runs two full environments simultaneously; you flip a load
balancer to switch. Pros: instant rollback (flip back), zero in-flight
mixing. Cons: 2x infra cost during deploy, schema migrations still need to
be back-compat because the *previous* version is live alongside.
Canary routes a small slice of traffic (1% → 5% → 25%) to the new version
with health gates between. Pros: catches regressions on real traffic
before full exposure. Cons: needs traffic splitting, mixed-version
in-flight, observability has to break down by version.
Use blue/green for low-frequency high-risk changes (DB cutovers, major
framework upgrades). Use canary for high-frequency app-tier changes where
you have good metrics.

**Q (senior): How do you handle secrets in CI?**
A:
- Store in the platform's secret store (GitHub Encrypted Secrets, Vault,
  AWS Secrets Manager). Reference as `${{ secrets.X }}` — automatically
  redacted from logs.
- Scope to environment (production vs staging) with approval gates.
- Rotate on a schedule and on suspected compromise.
- Never `echo $SECRET` in a step; never include in a Dockerfile `ARG`
  that becomes an image layer.
- For build-time secrets, use BuildKit `--mount=type=secret` so the secret
  is available during `RUN` but not persisted in any layer.
- For runtime, inject via the orchestrator's secret mechanism (k8s
  Secrets as env vars, ECS secrets from SSM, etc.). Avoid baking into the
  image at all.

## Further reading

- *The Twelve-Factor App* — `12factor.net`
- Docker docs: Dockerfile reference, BuildKit, multi-stage builds
- Docker Compose spec — `compose-spec.io`
- GitHub Actions docs — workflow syntax, service containers, caching
- *Continuous Delivery* by Humble & Farley — the canonical CI/CD book
- *Container Security* by Liz Rice — image scanning, runtime defenses
- `dive` tool — interactive image layer explorer
- `hadolint` — Dockerfile linter
- Google's SRE book chapter on canary releases
