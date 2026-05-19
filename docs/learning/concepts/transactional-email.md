# Transactional Email

## Why this matters

Almost every web app eventually has to email a real human: a password reset, a
receipt, a magic link, a "your slot starts in 2 hours" reminder. These are
called *transactional emails* — they are triggered by a specific user action or
event, sent to one recipient at a time, and the user is actively waiting for
them. Unlike marketing email, the cost of a missed transactional email is
immediate and visible: the user cannot log in, cannot confirm a signup, does
not show up to a slot.

For interviews, this topic comes up under several disguises:

- "How would you build a notification service?"
- "An email isn't being delivered — debug it."
- "How do you stop a retried Celery task from sending the same email twice?"
- "Why does your app's email land in spam?"

You are expected to know the moving parts: an SMTP/HTTP API client, a queue,
a deduplication store, DNS records (SPF / DKIM / DMARC), bounce + complaint
webhooks, and a dev catcher like Mailpit. This lecture walks each layer and
ends with how this codebase wires them together.

## The design choice

### SMTP vs HTTP API

There are two ways to hand an email to a sending service:

1. **SMTP** — open a TCP connection on port 25/465/587, speak the SMTP protocol
   (`HELO`, `MAIL FROM`, `RCPT TO`, `DATA`, `.`). This is the original mail
   submission protocol from RFC 5321. Every language has a stdlib SMTP client
   (Python's `smtplib`, Node's `nodemailer`, Java's `JavaMail`).
2. **HTTP API** — `POST /v3/mail/send` with a JSON body. The provider (SendGrid,
   Postmark, Mailgun, Resend, SES via its REST API) parses the JSON and does the
   SMTP dance on your behalf.

| Dimension | SMTP | HTTP API |
|---|---|---|
| Setup | Username/password, host, port | API key |
| Latency | 1 TCP handshake + STARTTLS + 5 round-trips | 1 HTTPS request |
| Error handling | SMTP reply codes (4xx soft, 5xx hard) parsed from text | JSON `{errors: [...]}` |
| Attachments | MIME-encoded inline | base64 in JSON |
| Library risk | stdlib, never breaks | SDK upgrades break |
| Firewall friendliness | Port 587 often blocked on cloud egress | 443 always open |
| Observability | You log what you send | Provider dashboards, webhooks |
| Vendor lock-in | Low (swap host/port) | Higher (templates, JSON schema) |

In practice, SMTP is the lowest-common-denominator interface. Postmark, SES,
SendGrid, and Mailgun all expose SMTP *and* an HTTP API. SMTP wins when you
need a quick local catcher (Mailpit listens on `1025`). HTTP API wins for
production because it gives you template IDs, suppression list APIs, scheduled
sends, and per-request `X-Message-Id` you can join against webhook events.

This codebase deliberately keeps both paths alive — `email_mode = "smtp"`
routes through `smtplib` and `email_mode = "sendgrid"` routes through the
SendGrid HTTPS SDK. Dev uses SMTP into Mailpit; prod has both options.

### Why use a provider at all?

Could you not just run Postfix on an EC2 box and call `sendmail`? Technically
yes. In practice:

- **IP reputation** — fresh IPs are treated as spam by default. Major mailbox
  providers (Gmail, Outlook, Yahoo) keep multi-year reputation scores. SendGrid
  / Postmark / SES dedicate warmed-up IP pools to your account.
- **Abuse handling** — when a recipient hits "report spam", the receiving MTA
  sends a *complaint feedback loop* (FBL) report. Your provider parses these,
  auto-suppresses the address, and exposes a webhook.
- **Bounce categorization** — distinguishing a hard bounce (`550 user unknown`)
  from a soft bounce (`452 mailbox full`) requires parsing SMTP DSNs. Providers
  do this for you.
- **DKIM key management + rotation** — providers publish your public key in
  their DNS namespace (or yours via CNAME).
- **Compliance** — CAN-SPAM (US), CASL (Canada), GDPR (EU) all require an
  unsubscribe link, a physical address, and audit trails. Providers ship these
  by default.

The rule of thumb: do not operate your own outbound MTA unless deliverability
*is* your product.

## How it works under the hood

### A single email's life

1. Your app calls `provider.send({to, from, subject, html})` or opens an SMTP
   connection to the provider.
2. The provider's MTA accepts the message, generates a `Message-Id`, signs the
   headers with **DKIM**, and queues for outbound delivery.
3. The provider MTA does a DNS `MX` lookup on the recipient domain
   (`gmail.com → gmail-smtp-in.l.google.com`).
4. It opens an SMTP connection to the recipient MTA, presents your
   envelope-from (`MAIL FROM:`).
5. The recipient MTA checks **SPF** (does this sending IP appear in the TXT
   record for the envelope-from domain?), **DKIM** (does the signature
   verify?), and **DMARC** (does at least one of SPF/DKIM pass *and* align
   with the visible `From:` domain?).
6. The recipient MTA accepts (`250 OK`) or rejects (`550 ...`). On accept, the
   message hits the spam classifier, the inbox/promotions/spam folder routing
   rules, and finally the user's mailbox.

Steps 1–4 are your provider's job. Steps 5–6 are why you need to configure DNS
correctly.

### SPF — Sender Policy Framework

SPF is a DNS TXT record on the **envelope-from** domain (the `MAIL FROM` in
SMTP, also called the "Return-Path"). It lists which IPs are allowed to send
mail on your behalf.

```
v=spf1 include:sendgrid.net include:_spf.google.com ~all
```

The receiving MTA reads this record and checks whether the connecting IP is
authorized. SPF only checks the envelope-from — not the visible `From:` header.
That's why DMARC was invented (it forces alignment).

The mechanism flags:
- `+` (default) — pass
- `-` — fail (hard)
- `~` — softfail (mark, don't reject) — common during rollout
- `?` — neutral

### DKIM — DomainKeys Identified Mail

DKIM is a digital signature over the message body and selected headers. Your
provider holds a private RSA key and signs outgoing mail. The public key lives
in DNS at `<selector>._domainkey.<your-domain>`.

```
s1._domainkey.scitrek.ucsb.edu  TXT  "v=DKIM=1; k=rsa; p=MIGfMA0G..."
```

The receiving MTA:
1. Reads the `DKIM-Signature:` header in the email.
2. Pulls the named selector and domain.
3. Looks up the public key in DNS.
4. Recomputes the canonicalized hash of the body + signed headers.
5. Verifies the signature.

DKIM survives forwarding (the body hash is preserved) — SPF does not (the
forwarder becomes the new envelope-from IP). That is why DKIM is the more
important of the two for modern deliverability.

### DMARC — alignment + policy

DMARC tells receiving MTAs what to do when SPF *or* DKIM fail, and crucially
requires at least one to *align* with the `From:` header domain.

```
_dmarc.scitrek.ucsb.edu  TXT  "v=DMARC1; p=quarantine; rua=mailto:dmarc@scitrek.ucsb.edu; pct=100; adkim=s; aspf=s"
```

Policies:
- `p=none` — monitor only, send aggregate reports to `rua=`
- `p=quarantine` — mark failing mail as spam
- `p=reject` — refuse failing mail

The hard rule: **without DMARC alignment, Gmail and Yahoo will not put your
mail in the inbox.** As of February 2024 they require it for any sender doing
>5000 messages/day.

### BIMI — Brand Indicators

BIMI lets your logo render next to the message in supported clients (Gmail,
Apple Mail). Requires `p=quarantine` or `p=reject` DMARC, a Verified Mark
Certificate (VMC) from Entrust/DigiCert (~$1500/yr), and an SVG of your logo.
Cosmetic but a strong trust signal.

### How a receiving MTA decides spam vs inbox

The decision is *not* binary. Gmail's classifier weights:

- Authentication (SPF/DKIM/DMARC pass) — required
- Domain reputation (Google's historical view of `@scitrek.ucsb.edu`)
- IP reputation (your provider's pool)
- Engagement signals (do recipients open? reply? mark as not-spam?)
- Content signals (image-heavy, URL shorteners, low text/HTML ratio)
- List hygiene (sending to many invalid addresses → reputation drop)
- User-level filters (this recipient has marked you as VIP, or never opens)

You cannot game this in one shot. You earn it over weeks.

## How this codebase uses it

### The send path

The single entry point is `_send_email` in
`backend/app/celery_app.py:127`. It dispatches on `settings.email_mode`:

```python
def _send_email(to_email, subject, body, html_body=None):
    try:
        if settings.email_mode == "sendgrid":
            _send_via_sendgrid(to_email, subject, body, html_body=html_body)
        else:  # "smtp" (default)
            _send_via_smtp(to_email, subject, body, html_body=html_body)
    except Exception:
        logger.exception("email_send_failed mode=%s to=%s subject=%s", ...)
        raise
```

The SMTP path (`_send_via_smtp`, line 71) opens a stdlib `smtplib.SMTP`
connection, optionally STARTTLS-upgrades it, optionally logs in, and ships an
`EmailMessage`. The same function serves both Mailpit (dev, no auth) and AWS
SES SMTP (prod, IAM-derived username/password on 587).

The SendGrid path uses the `sendgrid` Python SDK and the `Mail` helper.

### Why both?

- **Dev** — Mailpit catches everything locally. It speaks SMTP on port 1025,
  accepts any auth, and exposes a web UI on port 8025 where you can read what
  was "sent". Configured in `docker-compose.yml`:

  ```yaml
  mailpit:
    image: axllent/mailpit:latest
    ports: ["1025:1025", "8025:8025"]
    environment:
      MP_MAX_MESSAGES: 500
      MP_SMTP_AUTH_ACCEPT_ANY: 1
      MP_SMTP_AUTH_ALLOW_INSECURE: 1
  ```
- **Prod** — could be SES SMTP (`email_mode=smtp`, `smtp_host=email-smtp.us-west-2.amazonaws.com`, `smtp_use_tls=True`) or SendGrid (`email_mode=sendgrid`, with `sendgrid_api_key`).

### Templates

Email bodies are built by per-kind functions in `backend/app/emails.py`:
`send_confirmation`, `send_cancellation`, `send_reminder_24h`,
`send_reminder_pre_2h`, `send_waitlist_promote`, and so on. Each returns
`{to, subject, text_body, html_body}`.

HTML rendering uses stdlib `string.Template` against files in
`backend/app/email_templates/`. All interpolated values are run through
`html.escape()` before substitution to prevent XSS via event titles
(`emails.py:60`). Templates target WCAG AA: single-column layout, ≥16px text,
≥4.5:1 contrast, max-width 600px.

The `BUILDERS` dict (`emails.py:344`) maps a string `kind` to a builder
function. The Celery task looks up the kind and calls the builder — this is
the seam that makes adding a new email a one-line change.

### Idempotency — exactly-once email delivery

Celery retries on exception (`autoretry_for=(Exception,)`). Without protection,
a transient network blip in the SMTP send could ship the same reminder three
times. The codebase prevents this with a Postgres unique index on
`sent_notifications(signup_id, kind)`:

```python
def _dedup_insert(db, signup_id, kind) -> bool:
    stmt = pg_insert(models.SentNotification).values(
        signup_id=signup_id, kind=kind
    ).on_conflict_do_nothing(index_elements=["signup_id", "kind"])
    result = db.execute(stmt)
    return result.rowcount == 1
```

The task pattern is:
1. Insert the dedup row first.
2. If `rowcount == 0`, another worker already won — bail out.
3. If `rowcount == 1`, send the email, commit.

Note the ordering: the dedup row is committed *before* the send. This means we
risk losing an email (worker dies between insert and send), but we never send a
duplicate. For reminders that is the right trade — the next beat tick can
heal a gap, but a duplicate "you're starting in 2 hours!" annoys volunteers.

### Magic-link / unsubscribe handling

Reminders include a manage URL built by `_manage_url_for_signup`
(`emails.py:201`) so the volunteer can turn off reminders without
re-authenticating. This is functionally an unsubscribe link — CAN-SPAM
requires one even for transactional mail if there is any promotional
character. Volunteer preference is `email_reminders_enabled` in
`backend/app/services/reminder_service.py`.

### Circuit breaker

`_check_daily_send_limit` (`celery_app.py:55`) counts rows in
`sent_notifications` since UTC midnight and short-circuits if a configured
ceiling is hit. Catches accidental loops or bad import data dumping thousands
of emails.

## Common pitfalls

### Email lands in spam

- **Missing DKIM.** The single most common cause. Run `dig TXT s1._domainkey.<your-domain>` and confirm it resolves. Send a test to `check-auth@verifier.port25.com` and read the reply.
- **DMARC misalignment.** Your `From:` says `@scitrek.ucsb.edu` but the envelope-from is `@sendgrid.net`. SPF passes for sendgrid.net but does not *align* with the visible From. Add a custom SendGrid domain and CNAME records.
- **Cold IP.** A brand-new IP block sends → Gmail bulks it. Warm up by sending small volumes to engaged recipients first.
- **Spammy content.** ALL-CAPS subjects, "$$$", >5 links, image-only body. Use a litmus / mail-tester.com check.
- **Bad list hygiene.** Sending to 1000 stale addresses → 30% hard bounces → reputation tank.

### Double-sends from retries

Celery's at-least-once delivery means a worker that dies after sending but
before ACKing the broker will replay the task. Always pair an external side
effect with an idempotency token. In this repo it's `sent_notifications`.
Other shapes: Stripe's `Idempotency-Key` HTTP header, an outbox table joined
to the email send.

### Bounces and complaints

Treat the provider's webhooks as authoritative. Subscribe to:
- `bounce` (hard) — mark address as `permanently_undeliverable`, never send again
- `bounce` (soft) — backoff schedule, three soft bounces in 30d → suppress
- `complaint` (spam button) — suppress immediately, also remove from any list
- `unsubscribe` — same

Persist these as rows, not as flags on the user, so you can audit "when did
this address go bad".

### Sending email from inside a database transaction

Classic bug: you commit a row, send the email, the email fails, you raise, the
*transaction* rolls back the original row — but the email was already sent.
Solution: send the email *after* commit, ideally by enqueueing a Celery job
that fires post-commit. Or use the *outbox pattern*: write `(send_email, args)`
to a table in the same transaction, a separate worker reads pending outbox
rows and sends.

### Local dev sending to real users

A junior dev points the local `.env` at the production SendGrid key and a test
run blasts every volunteer with `Lorem ipsum`. Defenses:
- Different API keys per env.
- A toggle (`EMAIL_TO_ALLOWLIST`) that rewrites the recipient to a fixture
  address unless explicitly disabled.
- Mailpit by default in dev compose (this repo's choice).

### `From:` address using a free webmail domain

If you `From: scitrek@gmail.com` via SendGrid, DMARC for gmail.com is set to
`p=reject` and your mail dies. Always send from a domain you control with
correctly delegated SPF/DKIM.

## Interview Q&A

**Q (junior): What is the difference between transactional and marketing email?**
A: Transactional is triggered by a single user's action — one recipient,
real-time, the user is waiting (password reset, receipt, confirmation).
Marketing is sender-initiated, bulk, to a list, and requires explicit consent
plus a working unsubscribe. They are typically sent through separate provider
"streams" so a deliverability problem in one does not poison the other
(Postmark literally separates them into "Transactional" and "Broadcast"
streams).

**Q (junior): What does SMTP stand for and on which port does it run?**
A: Simple Mail Transfer Protocol, RFC 5321. Port 25 is server-to-server
relay (often blocked outbound by ISPs). Port 587 is *submission* — client
to MTA with auth and STARTTLS. Port 465 is implicit-TLS submission. For app
code submitting to a provider, always 587 (STARTTLS) or 465 (TLS).

**Q (mid): How do SPF, DKIM, and DMARC work together?**
A: SPF authorizes sending IPs for the envelope-from domain. DKIM
cryptographically signs the message body and selected headers, with the public
key published in DNS. DMARC requires *at least one* of SPF/DKIM to pass *and
align* (share an org domain) with the visible `From:` header, and tells
recipient MTAs what policy to apply on failure (none, quarantine, reject). All
three are TXT records. SPF protects the envelope, DKIM survives forwarding,
DMARC closes the loop and gives you reporting.

**Q (mid): A user reports "I never got the email." Walk me through debugging.**
A:
1. Confirm the send was attempted — search app logs for the recipient address
   and a `Message-Id`.
2. Confirm the provider accepted it — provider dashboard / API for that
   Message-Id. Look for `delivered`, `bounced`, `deferred`, `dropped`.
3. If `dropped` — was the address on a suppression list? Hard bounce history?
4. If `bounced` — what was the SMTP reply? `550 5.1.1 user unknown` →
   address bad. `421 4.7.0` → temp throttle.
5. If `delivered` — ask the user to check spam. Then run a Gmail "Show
   original" on a known-good message to inspect SPF/DKIM/DMARC.
6. If nothing in logs — the task never ran. Inspect Celery queue depth, worker
   logs, broker connectivity.

**Q (mid): Your retry policy means a worker can run the same email task
twice. How do you prevent duplicates?**
A: Idempotency key stored externally. Either (a) a unique constraint on
(target, action_kind) inserted before the side effect — this codebase's
`sent_notifications` pattern with Postgres `ON CONFLICT DO NOTHING`, or (b) a
provider-side `Idempotency-Key` header if available, or (c) the *outbox
pattern* where the email send is a row picked up by a single-leader processor.
The key insight: the dedup primitive lives outside the worker process.

**Q (senior): Walk me through how you would design a notification service that
serves email + SMS + push and guarantees at-least-once delivery with
deduplication.**
A:
- Domain events land on a Kafka/SQS topic.
- A *fan-out* worker reads events, materializes one row per (recipient,
  channel) into a `notifications` outbox with a derived idempotency key.
- A *dispatcher* per channel reads pending rows, attempts send, writes
  `attempt_count`, `last_error`, `sent_at`.
- Provider webhooks update terminal status (`delivered`, `bounced`).
- A reaper retries `failed` rows with exponential backoff and DLQs after N.
- User preferences (channel opt-in, quiet hours, locale) are a separate
  service the dispatcher reads.
- Templates are versioned and rendered server-side; recipients see the version
  that was current at send time, not at retry time.

**Q (senior): How would you set up the DNS and infrastructure for a new sending
domain from scratch?**
A:
1. Pick a subdomain (`mail.scitrek.ucsb.edu`) so a bad reputation doesn't
   poison the root domain.
2. Create the provider's CNAMEs for DKIM (provider gives you ~3 records).
3. Add SPF TXT: `v=spf1 include:sendgrid.net -all`.
4. Add DMARC at `p=none` with `rua=` to a monitored mailbox.
5. Send only opt-in transactional mail at low volume for 2-4 weeks.
6. Watch DMARC aggregate reports; ratchet to `p=quarantine` once you see
   100% DKIM alignment.
7. Then ratchet to `p=reject`.
8. Subscribe Google Postmaster Tools and Microsoft SNDS for reputation
   dashboards.

**Q (senior): What does "alignment" mean in DMARC and why does it matter?**
A: DMARC requires that the domain validated by SPF (the envelope-from) or by
DKIM (the `d=` tag in the signature) shares the *organizational domain* with
the `From:` header visible to the user. So SPF can pass for `sendgrid.net`
but if your `From:` is `@scitrek.ucsb.edu`, that's *not* aligned and DMARC
fails. Alignment can be `strict` (exact match) or `relaxed` (organizational
domain match, default). Alignment exists because SPF and DKIM by themselves
only authenticate *some* domain, not necessarily the one the user sees.

## Further reading

- RFC 5321 — Simple Mail Transfer Protocol (the protocol itself)
- RFC 5322 — Internet Message Format (the From/To/Subject/MIME headers)
- RFC 6376 — DKIM Signatures
- RFC 7208 — Sender Policy Framework
- RFC 7489 — Domain-based Message Authentication, Reporting & Conformance
- SendGrid deliverability guide: `https://sendgrid.com/resource/email-deliverability-guide`
- Postmark's blog (the best operational writing on deliverability)
- Google Postmaster Tools — reputation dashboards for `@gmail.com` delivery
- Microsoft SNDS — equivalent for Hotmail/Outlook
- `https://mail-tester.com` — instant inbox-vs-spam score
- `https://www.learndmarc.com` — interactive DMARC walkthrough
