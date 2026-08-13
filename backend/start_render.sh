#!/bin/sh
set -eu

alembic upgrade head
python -m app.seed_admin
# --proxy-headers is not optional on a PaaS. Render terminates TLS and
# forwards, so without it `request.client.host` is Render's internal proxy
# address for *every* request. Three things break on that, and the first one
# is an outage rather than a weakness:
#
#   1. deps.rate_limit keys on `rate:{client.host}:{path}`, so all volunteers
#      collapse into ONE shared bucket per path. The public check-in flow is
#      capped at 30 requests / 60s and takes 2+ requests per volunteer, so
#      roughly a dozen people scanning the event QR at once starts 429-ing
#      real volunteers on the classroom floor. Exactly the moment it must work.
#   2. The same collapse weakens the throttle that stands between a guesser
#      and the 4-digit venue code, and the IP half of the forgot-password
#      limiter (check_reset_rate_limit) stops contributing anything.
#   3. auth.py and magic.py log that address, so audit trails record the proxy
#      instead of the caller and an investigation has nothing to go on.
#
# docker-compose.prod.yml already passes this with a CIDR, because there the
# hop is a known Caddy container. Here the hop is Render's proxy, whose address
# is not contractual, so the allow-list is "*" — safe ONLY because the service
# is reachable exclusively through that proxy. If this container is ever given
# a directly-routable port, "*" lets a caller spoof X-Forwarded-For and forge
# their rate-limit identity: narrow it to the real hop before doing that.
#
# Per-account login lockout is unaffected either way — it counts on the user
# row, not the address.
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips="*"
