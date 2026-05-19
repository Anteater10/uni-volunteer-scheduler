# Transactional Email — Reference

## TL;DR

Transactional email is event-triggered, one-recipient mail (password reset,
receipt, signup confirmation, reminder). Two send mechanisms — SMTP and
provider HTTP API — both terminate in a third-party MTA that handles outbound
delivery, IP reputation, bounces, and complaint webhooks. Reliable delivery
requires SPF + DKIM + DMARC DNS records, idempotent send tasks, and a working
suppression list. This codebase implements both an SMTP path (Mailpit in dev,
SES in prod) and a SendGrid HTTP API path, switchable via `email_mode`, with
exactly-once delivery enforced by a unique index on `(signup_id, kind)`.

## API surface

### SMTP submission (stdlib `smtplib`)

```python
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"] = "no-reply@scitrek.ucsb.edu"
msg["To"] = "andy@example.com"
msg["Subject"] = "Confirm your signup"
msg.set_content("plain text")
msg.add_alternative("<p>html</p>", subtype="html")

with smtplib.SMTP("email-smtp.us-west-2.amazonaws.com", 587, timeout=10) as s:
    s.starttls()
    s.login(SES_SMTP_USER, SES_SMTP_PASS)
    s.send_message(msg)
```

### SendGrid HTTP API

```bash
curl -X POST https://api.sendgrid.com/v3/mail/send \
  -H "Authorization: Bearer $SENDGRID_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "personalizations": [{"to": [{"email": "andy@example.com"}]}],
    "from": {"email": "no-reply@scitrek.ucsb.edu", "name": "SciTrek"},
    "subject": "Confirm your signup",
    "content": [
      {"type": "text/plain", "value": "Click the link..."},
      {"type": "text/html",  "value": "<p>Click the link...</p>"}
    ],
    "custom_args": {"signup_id": "abc123", "kind": "confirmation"}
  }'
```

Response on success is `202 Accepted` with an `X-Message-Id` header — store
this against the send row to join later webhook events.

### Postmark HTTP API (alternative)

```bash
curl -X POST https://api.postmarkapp.com/email \
  -H "Accept: application/json" \
  -H "X-Postmark-Server-Token: $POSTMARK_TOKEN" \
  -d '{
    "From":"no-reply@scitrek.ucsb.edu",
    "To":"andy@example.com",
    "Subject":"Confirm your signup",
    "TextBody":"...",
    "HtmlBody":"<p>...</p>",
    "MessageStream":"outbound"
  }'
```

### AWS SES via boto3

```python
import boto3
ses = boto3.client("ses", region_name="us-west-2")
ses.send_email(
    Source="no-reply@scitrek.ucsb.edu",
    Destination={"ToAddresses": ["andy@example.com"]},
    Message={
        "Subject": {"Data": "Confirm your signup"},
        "Body": {
            "Text": {"Data": "..."},
            "Html": {"Data": "<p>...</p>"},
        },
    },
)
```

### DNS records (example)

```
; SPF (TXT on the sending domain)
scitrek.ucsb.edu.  TXT  "v=spf1 include:sendgrid.net include:amazonses.com -all"

; DKIM (TXT or CNAME under <selector>._domainkey)
s1._domainkey.scitrek.ucsb.edu.   CNAME  s1.domainkey.uXXXXXX.wlYYYYYY.sendgrid.net.

; DMARC (TXT at _dmarc)
_dmarc.scitrek.ucsb.edu.  TXT  "v=DMARC1; p=quarantine; rua=mailto:dmarc@scitrek.ucsb.edu; pct=100; adkim=r; aspf=r"
```

## Mental model

```
[ App code ]
     |  build payload {to, subject, html, text}
     v
[ Outbox / dedup row ]   <- prevents duplicate sends across retries
     |  INSERT ... ON CONFLICT DO NOTHING
     v
[ Celery task / worker ]
     |  smtplib / SendGrid SDK
     v
[ Provider MTA ]   <- DKIM signs here, queues, retries on 4xx
     |  outbound SMTP
     v
[ Recipient MTA ]  <- SPF / DKIM / DMARC checks, spam classifier
     |
     v
[ Recipient inbox / spam / dropped ]
     ^
     |  webhook: delivered / bounce / complaint / open / click
[ Provider MTA ]
     |
     v
[ App webhook handler ]  <- update send row, suppress address on bounce/complaint
```

Three asynchronous boundaries:

1. App → outbox (synchronous, transactional with the originating row).
2. Worker → provider (synchronous HTTP/SMTP, with retries).
3. Provider → app webhook (eventual, may arrive seconds to minutes later).

The hardest bugs are at the boundaries. Lose a row at #1 and you forget to
send. Retry at #2 without dedup and you send twice. Drop webhooks at #3 and
your suppression list goes stale.

## Usage in this codebase

| File | Role |
|---|---|
| `backend/app/emails.py` | Per-kind payload builders (subject + text + html) |
| `backend/app/email_templates/*.html` | WCAG-AA HTML templates |
| `backend/app/celery_app.py` | `_send_email`, `_send_via_smtp`, `_send_via_sendgrid`, the Celery `send_email_notification` task |
| `backend/app/config.py` | `email_mode`, `smtp_host`, `smtp_port`, `smtp_use_tls`, `sendgrid_api_key`, `email_from_address`, `resend_daily_limit` |
| `backend/app/services/reminder_service.py` | Scheduling logic (kickoff / pre_24h / pre_2h) and quiet-hours suppression |
| `backend/app/models.py` | `SentNotification` table — unique `(signup_id, kind)` |
| `docker-compose.yml` (root) | `mailpit` service on `1025/8025` for local capture |

### The dispatch function

```python
# backend/app/celery_app.py
def _send_email(to_email, subject, body, html_body=None):
    try:
        if settings.email_mode == "sendgrid":
            _send_via_sendgrid(to_email, subject, body, html_body=html_body)
        else:
            _send_via_smtp(to_email, subject, body, html_body=html_body)
    except Exception:
        logger.exception("email_send_failed mode=%s to=%s ...", ...)
        raise
```

Single seam, two backends. Switching providers in prod is one env var.

### Dedup pattern

```python
def _dedup_insert(db, signup_id, kind) -> bool:
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup_id, kind=kind
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    return result.rowcount == 1
```

Called *before* the send. If 0 rows inserted, another worker already
won — bail. If 1, proceed and commit after send. The unique index on
`sent_notifications(signup_id, kind)` (`models.py:661`) is the source of
truth.

### Local capture

`docker-compose.yml`:

```yaml
mailpit:
  image: axllent/mailpit:latest
  ports:
    - "1025:1025"   # SMTP
    - "8025:8025"   # web UI
  environment:
    MP_MAX_MESSAGES: 500
    MP_SMTP_AUTH_ACCEPT_ANY: 1
    MP_SMTP_AUTH_ALLOW_INSECURE: 1
```

Backend default config points `smtp_host=mailpit`, `smtp_port=1025`. Every
dev send lands in the Mailpit UI at `http://localhost:8025`. No real
recipients are ever contacted from a dev machine.

## Operational concerns

### Deliverability metrics

| Metric | Healthy | Action threshold |
|---|---|---|
| Hard bounce rate | < 2% | > 5% → audit list, suppress |
| Complaint rate (spam button) | < 0.1% | > 0.3% → throttle, review content |
| Soft bounce rate | < 5% | > 10% → investigate IP / domain reputation |
| Open rate (where tracked) | 20–50% | < 10% → subject lines, list rot |

Watch these per-template, not just globally. A single bad template can drag
your domain reputation down.

### Secrets

- `SENDGRID_API_KEY` — provider-scoped, rotate quarterly. Never in image
  layers; pass via env file or secret manager.
- SMTP credentials — for SES, derived from an IAM user with
  `ses:SendRawEmail`. Username/password are an SES-specific transform of the
  access key.
- `JWT_SECRET` for magic-link tokens embedded in confirmation/reminder emails.

This codebase loads them from `backend/.env` via `env_file` in
`docker-compose.yml`. In CI, the workflow at `.github/workflows/ci.yml`
writes a synthetic `.env` with test secrets for the E2E run — never the real
prod values.

### Suppression list

A provider keeps its own list. You should *also* keep a local copy so:

- Even if you migrate providers, you do not re-mail bad addresses.
- You can audit "why did we stop emailing X?"

Schema sketch: `email_suppression(email, reason, source, created_at)`. Sources
include `hard_bounce`, `complaint`, `unsubscribe`, `manual`. Send path checks
this table before enqueueing.

### Daily send cap (circuit breaker)

`celery_app.py:55` enforces a per-day count from `sent_notifications`. If a
runaway loop or bad CSV import triggers excessive sends, the worker logs an
error and skips. Pairs well with a provider-side rate limit.

### Webhook ingestion

Each provider posts events as JSON to a URL you configure:

- SendGrid: array of `{event, email, sg_message_id, timestamp, ...}` posts
- Postmark: one object per event
- SES: via SNS topics

Webhook handlers should be idempotent — providers retry on non-2xx. Key
events by `(provider, message_id, event_type)` to dedupe.

### Quiet hours + locale

`reminder_service.py` skips sends between 21:00 and 07:00 PT
(`QUIET_HOURS_START = 21`, `QUIET_HOURS_END = 7`). The window math uses
`ZoneInfo("America/Los_Angeles")` and allows a ±15 min beat tick drift via
`WINDOW_SLACK = timedelta(minutes=15)`. Quiet-hours-skipped sends are still
deduped, so they will not double-fire when the window reopens.

### Compliance (CAN-SPAM / CASL / GDPR)

Even transactional mail benefits from:

- A physical postal address in the footer.
- A working `List-Unsubscribe:` header (RFC 8058 one-click variant for Gmail).
- A clearly labeled link to manage preferences. This codebase embeds the
  magic-link manage URL in reminder emails (`emails.py:201`).

GDPR makes the open/click tracking pixel a "personal data" item in the EU.
Either disable tracking for EU recipients or include a lawful-basis
justification.

## Glossary

- **MTA** — Mail Transfer Agent. The server that relays mail (Postfix, Exim,
  the provider's outbound cluster).
- **MUA** — Mail User Agent. The client (Gmail web, Apple Mail, mutt).
- **MX record** — DNS record pointing to the recipient domain's MTAs.
- **Envelope-from** — `MAIL FROM:` in SMTP. Not the `From:` header. SPF
  checks the envelope-from.
- **DSN** — Delivery Status Notification (RFC 3461) — the SMTP machine-readable
  bounce.
- **SPF** — Sender Policy Framework. TXT record listing authorized sending IPs.
- **DKIM** — DomainKeys Identified Mail. Cryptographic signature on the message.
- **DMARC** — Policy + alignment over SPF/DKIM. Tells receiver what to do on
  failure and reports back aggregate counts.
- **BIMI** — Brand Indicators for Message Identification. Logo display next
  to subject in supporting clients.
- **VMC** — Verified Mark Certificate. Required for BIMI. ~$1500/yr.
- **FBL** — Feedback Loop. Recipient ISP forwards spam complaints back to
  sender ISP.
- **Suppression list** — addresses you will not send to (bounces, complaints,
  unsubscribes).
- **Warm-up** — gradually ramping volume on a new sending IP/domain to build
  reputation.
- **Outbox pattern** — write the message to a DB table in the same
  transaction as the originating event; a separate worker reads and sends.
  Decouples business logic from delivery.
- **Idempotency key** — a token attached to a send attempt so retries do not
  duplicate. In this codebase: the `(signup_id, kind)` row.
- **STARTTLS** — opportunistic TLS upgrade on a plaintext SMTP connection
  (port 587).
- **Implicit TLS** — TLS from the first byte (port 465).
- **Mailpit / MailHog** — local SMTP capture servers with a web UI for
  development.
