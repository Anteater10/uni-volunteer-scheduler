# Deployment: AWS (single EC2 + RDS)

This is the AWS-specific sibling of `docs/deployment.md` § 2 ("Production
single-host"). Same topology — one host runs the app containers behind Caddy
— except Postgres moves off the host onto a managed RDS instance. Redis stays
containerized on the EC2 host (no ElastiCache in this setup).

Artifacts this adds to the repo: `docker-compose.aws.yml`,
`scripts/backup_db_rds.sh`. Everything else (`Dockerfile`s, `Caddyfile`,
`frontend/nginx.conf`, `backend/.env.production.example`) is reused as-is.

| Component | Where it runs |
|---|---|
| Postgres 16 + pgvector | **RDS** (managed) |
| Redis 7 | container, on the EC2 host |
| Backend, migrate, celery_worker, celery_beat | containers, on the EC2 host |
| Frontend (nginx static) | container, on the EC2 host |
| Caddy (TLS termination + routing) | container, on the EC2 host |

---

## 0. Before you start

- An AWS account and a region close to your users (examples below use
  `us-west-2`; UCSB is also reasonably close to `us-west-1`).
- **A domain name you can add a DNS record to.** Caddy's automatic HTTPS
  (Let's Encrypt) issues certs for hostnames, not bare IPs — without a
  domain there is no valid public HTTPS on this stack. A subdomain is fine
  (`app.scitrek-ucsb.org`).
- An SSH key pair for EC2 access (create one in the EC2 console if you don't
  have one, or import your existing `~/.ssh/id_ed25519.pub`).
- Rough monthly cost, single-AZ, low traffic: **EC2 t3.medium ≈ $30**,
  **RDS db.t4g.micro ≈ $12–13**, **20 GB gp3 storage ≈ $2–3**, plus AWS's
  flat per-hour charge for any public IPv4 address (including an in-use
  Elastic IP) — about **$3.60/mo** since Feb 2024. Call it **~$50/mo**
  before data transfer; check the AWS Pricing Calculator for current
  numbers, and see the sizing notes in §2 and §3 before committing to
  instance sizes.

---

## 1. Networking: use the default VPC, no NAT Gateway

Keep this simple: the **default VPC** in your region already has public
subnets in every AZ. Put the EC2 instance in one of them (it needs a public
IP anyway, for inbound 80/443). Put RDS in the same VPC but mark it **"Not
publicly accessible"** — it'll get a private IP inside the VPC and won't be
reachable from the internet, but EC2 can still reach it because they're in
the same VPC. This avoids the cost and complexity of a NAT Gateway entirely.

RDS requires a **DB subnet group spanning at least 2 AZs**, even for a
single-AZ instance — the default VPC's default subnets across AZs satisfy
this automatically when you let the RDS wizard create one for you.

---

## 2. Create the RDS instance

Console: **RDS → Databases → Create database**.

| Field | Value | Why |
|---|---|---|
| Engine type | PostgreSQL | — |
| Engine version | PostgreSQL **16.x** (latest available minor) | Matches the `pgvector/pgvector:pg16` image used in dev; RDS ships the `vector` extension built-in for every 16.x build, no parameter group change needed |
| Templates | Free tier (if eligible) or Dev/Test | Single-AZ, no Enhanced Monitoring by default |
| DB instance identifier | `uvs-db` | — |
| Master username | `uvs_app` (avoid `postgres` for the app user) | — |
| Master password | generate a strong one, save it in a password manager — **not** in the repo | — |
| Instance class | `db.t4g.micro` (2 vCPU burstable, 1 GiB) to start | The corpus/vector tables here are small (Phase 31's copilot knowledge base, not a general vector DB); 1 GiB is plenty for this app's actual query patterns. Bump to `db.t4g.small` if you see `FreeableMemory` alarms. |
| Storage | 20 GiB **gp3**, enable storage autoscaling (max ~100 GiB) | Room to grow without a manual resize |
| Multi-AZ | **No** (for now) | Keeps cost down; RDS automated backups + snapshots (§6) cover recovery. Revisit if uptime requirements change. |
| Connectivity — VPC | your default VPC | matches §1 |
| Connectivity — Public access | **No** | RDS must not be reachable from the internet |
| Connectivity — VPC security group | **Create new**: `uvs-rds-sg` | populated in §3 once the EC2 SG exists |
| Additional configuration — Initial database name | `uni_volunteer` | must match `POSTGRES_DB` / `DATABASE_URL` used everywhere else in the repo |
| Additional configuration — Backup retention | 7 days (or more) | RDS automated backups, separate from `backup_db_rds.sh` |
| Additional configuration — Enable deletion protection | **On** | one fewer way to lose the database by accident |

Creation takes several minutes. Once status is **Available**, open the
instance and copy the **Endpoint** (a hostname like
`uvs-db.c9akciq32.us-west-2.rds.amazonaws.com`) from Connectivity & security
— you'll need it for `DATABASE_URL`.

---

## 3. Create the EC2 instance

Console: **EC2 → Instances → Launch instances**.

| Field | Value | Why |
|---|---|---|
| Name | `uvs-app` | — |
| AMI | Ubuntu Server 22.04 LTS (or 24.04 LTS), amd64 | Well-documented Docker install path |
| Instance type | **t3.medium** (2 vCPU, 4 GiB) to start | See sizing note below |
| Key pair | your SSH key pair | — |
| Network — VPC | your default VPC | matches §1 |
| Network — Auto-assign public IP | Enable | needed until you attach the Elastic IP |
| Firewall (security group) | **Create new**: `uvs-ec2-sg` (rules in §3.1) | — |
| Storage | 30 GiB **gp3** | headroom for Docker images — the backend image bundles the CPU PyTorch wheel + sentence-transformers, so images run a few hundred MB to ~1–2 GB each |

**Sizing note:** `docker-compose.aws.yml` runs the backend with
`--workers 4`. Each uvicorn worker is a separate process that may load the
BGE-small embedding model (via `sentence-transformers`/PyTorch) into its own
memory, alongside `celery_worker`, `celery_beat`, `redis`, `frontend`, and
`caddy` all on the same box. **t3.medium (4 GiB) is a reasonable floor, not
a guarantee** — after first deploy, watch `docker stats` under real load. If
memory is tight, either move to `t3.large` (8 GiB) or drop `--workers 4` to
`--workers 2` in `docker-compose.aws.yml`.

### 3.1 Security group rules

**`uvs-ec2-sg` (inbound):**

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **your IP only** (`x.x.x.x/32`) — use the console's "My IP" autofill | Never leave SSH open to `0.0.0.0/0` |
| HTTP | 80 | `0.0.0.0/0` (and `::/0` if you want IPv6) | Required for Let's Encrypt's HTTP-01 challenge and to redirect to HTTPS |
| HTTPS | 443 | `0.0.0.0/0` (and `::/0`) | App traffic |

Outbound: leave the default **allow all** — the host needs to pull Docker
images, reach Let's Encrypt, SendGrid, and OpenRouter.

**`uvs-rds-sg` (inbound)** — go back and edit this now that `uvs-ec2-sg`
exists:

| Type | Port | Source | Why |
|---|---|---|---|
| PostgreSQL | 5432 | **security group `uvs-ec2-sg`** (not a CIDR) | Only this EC2 instance can reach RDS, and it stays correct even if the instance's IP changes |

### 3.2 Elastic IP

Allocate an Elastic IP (**EC2 → Network & Security → Elastic IPs → Allocate
→ Associate** with `uvs-app`) so the public IP is stable — you're about to
point a DNS record at it, and a stopped/restarted instance would otherwise
get a new IP. Note AWS bills a small hourly fee for any public IPv4 address,
attached or not (see cost note in §0).

---

## 4. Install Docker on the instance

SSH in (`ssh -i your-key.pem ubuntu@<elastic-ip>`), then:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# run docker without sudo
sudo usermod -aG docker $USER
newgrp docker
```

---

## 5. Get the code and configure it

```bash
git clone <your repo URL> /opt/uni-volunteer-scheduler
cd /opt/uni-volunteer-scheduler

cp backend/.env.production.example backend/.env.production
```

Edit `backend/.env.production`:

- `DATABASE_URL` → point at the RDS endpoint from §2, and require TLS:
  ```
  DATABASE_URL=postgresql://uvs_app:<RDS_PASSWORD>@uvs-db.c9akciq32.us-west-2.rds.amazonaws.com:5432/uni_volunteer?sslmode=require
  ```
- `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` → leave as-is
  (`redis://redis:...`) — Redis is still the local `redis` container.
- Everything else per the checklist already in `docs/deployment.md` §
  "Production hardening checklist": fresh `JWT_SECRET`, real SendGrid key,
  real `FRONTEND_URL` / `BACKEND_BASE_URL` / `CORS_ALLOWED_ORIGINS` (your
  `https://` domain), strong `SEED_ADMIN_PASSWORD`, `ENVIRONMENT=production`,
  `EXPOSE_TOKENS_FOR_TESTING` absent.

**Quick connectivity check before bringing up the stack** (catches a wrong
password or security-group rule before Docker retries it silently):

```bash
docker run --rm -e PGPASSWORD='<RDS_PASSWORD>' postgres:16-alpine \
  psql -h uvs-db.c9akciq32.us-west-2.rds.amazonaws.com -U uvs_app -d uni_volunteer -c '\conninfo'
```

---

## 6. Launch

```bash
export DOMAIN='app.scitrek-ucsb.org'
export VITE_API_URL="https://${DOMAIN}"

docker compose -f docker-compose.aws.yml up -d --build
```

`migrate` runs `alembic upgrade head` against RDS — this is what actually
executes `CREATE EXTENSION IF NOT EXISTS vector` (migration `0019`), so you
don't need to enable pgvector by hand. Then it seeds the admin user, then
`backend`/`celery_worker`/`celery_beat` start.

## 7. DNS and HTTPS

Add a DNS **A record** for `$DOMAIN` pointing at the Elastic IP from §3.2
(in Route 53, or whatever registrar/DNS host you already use — this repo has
no dependency on Route 53 specifically). Once it resolves:

```bash
curl https://app.scitrek-ucsb.org/api/v1/health   # -> {"status":"ok"}
docker compose -f docker-compose.aws.yml logs caddy   # watch it obtain the cert
```

Caddy auto-provisions and auto-renews the Let's Encrypt certificate — there
is nothing else to configure for HTTPS. If the `curl` above fails with a TLS
error, it's almost always one of: DNS not propagated yet, port 80 not open
(ACME's HTTP-01 challenge needs it even though the site is served over 443),
or `$DOMAIN` not matching the DNS record exactly.

---

## 8. RDS backups

RDS's own automated backups (enabled in §2, 7-day retention) plus manual
snapshots before risky changes are your primary safety net —
point-in-time recovery, no scripting required. **Take a manual RDS snapshot
before every `alembic upgrade head` on prod** (Console → RDS → the instance
→ Actions → Take snapshot), same rule as `docs/deployment.md` already states
for the VPS path.

`scripts/backup_db_rds.sh` (added alongside this doc) is the second,
portable copy: a gzipped `pg_dump` against the RDS endpoint, restorable into
any Postgres, meant to be shipped off-host (S3) rather than left next to the
thing it's backing up. Wire it into cron:

```cron
0 3 * * * cd /opt/uni-volunteer-scheduler && ./scripts/backup_db_rds.sh >> backups/backup.log 2>&1
```

For the optional S3 upload (`S3_BUCKET=s3://...`), attach an **IAM
instance role** to the EC2 instance with `s3:PutObject` scoped to that
bucket — don't put long-lived AWS access keys in the env file or the repo.

---

## 9. Hardening checklist (AWS-specific, on top of `docs/deployment.md`'s)

- [ ] RDS **Public access = No**, confirmed on the instance's Connectivity tab.
- [ ] `uvs-rds-sg` inbound rule references the EC2 **security group**, not an IP/CIDR.
- [ ] `uvs-ec2-sg` port 22 restricted to your IP, not `0.0.0.0/0`.
- [ ] RDS **deletion protection** on.
- [ ] `DATABASE_URL` uses `sslmode=require`.
- [ ] RDS master password and `JWT_SECRET`/`SENDGRID_API_KEY`/etc. only live
      in `backend/.env.production` (gitignored) — never committed, never in
      `docker-compose.aws.yml` itself.
- [ ] Elastic IP associated (so DNS doesn't go stale on instance restart).
- [ ] A restore drill run at least once (§8) before you trust the backups.

---

## Troubleshooting

- **`migrate` container exits immediately / connection refused** — check
  §3.1's RDS security group rule (must reference the EC2 SG), and that the
  RDS instance status is "Available" (not still "Creating").
- **`CREATE EXTENSION vector` fails with a permissions error** — the RDS
  master user (`uvs_app` here) has the privileges needed for AWS's
  allow-listed extensions including `vector`; a permissions error usually
  means you connected as a different, more restricted user. Reconnect with
  the master username.
- **Caddy never gets a cert** — port 80 blocked, DNS not pointing at the
  Elastic IP yet, or `$DOMAIN` mismatched between the env var and the actual
  DNS record. `docker compose -f docker-compose.aws.yml logs caddy` shows
  the ACME exchange.
- **Backend OOM-killed under `docker stats` / `docker compose ps` shows
  restarts** — see the sizing note in §3: move to `t3.large` or reduce
  `--workers` in `docker-compose.aws.yml`.
