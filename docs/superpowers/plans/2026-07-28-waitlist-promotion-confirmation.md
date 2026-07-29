# Waitlist Promotion Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Waitlist promotion produces a `pending` signup plus a magic-link confirm email (3-day TTL) instead of instant `confirmed`; manage links outlive the confirm deadline; the expiry job chains promotions and cleans up stale tokens.

**Architecture:** The two promotion primitives (`promote_waitlist_fifo`, `manual_promote`) own the pending-flip and token issuance via a shared `mark_promoted_pending` helper, returning a `PromotionResult` that carries the raw token; all 8 call sites enqueue the new `send_waitlist_promotion_email` Celery task after commit (same pattern as `public_signup_service`). Token `expires_at` becomes "confirmation deadline only" — manage/swap/cancel endpoints accept any still-existing token.

**Tech Stack:** FastAPI + SQLAlchemy + Celery (RedBeat) + Postgres 16; pytest in docker.

**Spec:** `docs/superpowers/specs/2026-07-28-waitlist-promotion-confirmation-design.md`

## Global Constraints

- `PROMOTION_CONFIRM_TTL_MINUTES = 4320` (3 days). `SIGNUP_CONFIRM_TTL_MINUTES = 20160` (14 days) unchanged.
- Promotion email subject verbatim: `A spot opened up — confirm your SciTrek signup for {event.title}`.
- Backend tests run in docker. **On this checkout the network/image are `uni-event-scheduler_*`** (CLAUDE.md says `uni-volunteer-scheduler_*` — wrong here):

  ```bash
  cd /home/hung-khuu/Desktop/uni-event-scheduler
  docker run --rm --network uni-event-scheduler_default \
    -v $PWD/backend:/app -w /app \
    -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
    uni-event-scheduler-backend sh -c "pytest -q <paths>"
  ```

  First time only: `docker exec uni-event-scheduler-db-1 psql -U postgres -c "CREATE DATABASE test_uvs;"` (ignore "already exists").
- Frontend tests: `nvm use 20 && cd frontend && npm run test -- --run` (system node is 18 — too old).
- Commits: conventional format (`feat:`/`fix:`/`test:`/`refactor:`), **no AI attribution of any kind**, never commit `.planning/` or `.claude/`.
- Follow the existing post-commit-enqueue rule everywhere: capture email kwargs BEFORE `db.commit()` (expire_on_commit), call `.delay()` only AFTER commit.
- Type annotations on all new function signatures; frozen dataclass for `PromotionResult`.
- Test style: use `db_session` fixture, `tests/fixtures/helpers.py` (`make_user`, `auth_headers`, `_bind_factories`) and `tests/fixtures/factories.py` (`VolunteerFactory`, `SignupFactory`); silence/capture Celery with `monkeypatch.setattr("app.celery_app.<task>.delay", ...)`.

---

### Task 1: Promotion core — TTL constant, `PromotionResult`, `mark_promoted_pending`

**Files:**
- Modify: `backend/app/magic_link_service.py:22` (add constant below `SIGNUP_CONFIRM_TTL_MINUTES`)
- Modify: `backend/app/signup_service.py`
- Test: `backend/tests/test_promotion_pending.py` (create)

**Interfaces:**
- Consumes: `issue_token(db, signup, email, *, purpose, volunteer_id, ttl_minutes) -> str` (existing, `magic_link_service.py:36`).
- Produces: `PROMOTION_CONFIRM_TTL_MINUTES: int = 4320` (in `app.magic_link_service`); `PromotionResult` frozen dataclass with fields `signup: models.Signup`, `raw_token: str`, `email_kwargs: dict`; `mark_promoted_pending(db: Session, signup: models.Signup) -> PromotionResult` (both in `app.signup_service`). `email_kwargs` keys are exactly `volunteer_id`, `signup_id`, `token`, `event_id` — all `str` — matching Task 2's Celery task signature.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_promotion_pending.py`:

```python
"""Waitlist promotion → pending + confirm token (2026-07-28 spec).

Covers the promotion core: mark_promoted_pending flips a waitlisted signup
to pending, issues a 3-day SIGNUP_CONFIRM token, and returns the raw token
+ email kwargs for the post-commit enqueue.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from app import models
from app.magic_link_service import (
    PROMOTION_CONFIRM_TTL_MINUTES,
    SIGNUP_CONFIRM_TTL_MINUTES,
)
from app.signup_service import PromotionResult, mark_promoted_pending
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _make_event_and_slot(db_session, *, capacity):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Promotion Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=capacity,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    return owner, event, slot


def _make_waitlisted(db_session, slot, when=None):
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol,
        slot=slot,
        status=models.SignupStatus.waitlisted,
        timestamp=when or datetime.now(timezone.utc),
    )
    db_session.flush()
    return signup


class TestPromotionTTL:
    def test_promotion_ttl_is_three_days(self):
        assert PROMOTION_CONFIRM_TTL_MINUTES == 3 * 24 * 60
        # Fresh-signup TTL must stay untouched.
        assert SIGNUP_CONFIRM_TTL_MINUTES == 14 * 24 * 60


class TestMarkPromotedPending:
    def test_sets_pending_and_issues_three_day_token(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        signup = _make_waitlisted(db_session, slot)

        result = mark_promoted_pending(db_session, signup)

        assert signup.status == models.SignupStatus.pending
        token_row = (
            db_session.query(models.MagicLinkToken)
            .filter(models.MagicLinkToken.signup_id == signup.id)
            .one()
        )
        assert token_row.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM
        assert token_row.volunteer_id == signup.volunteer_id
        expected = datetime.now(timezone.utc) + timedelta(
            minutes=PROMOTION_CONFIRM_TTL_MINUTES
        )
        assert abs((token_row.expires_at - expected).total_seconds()) < 60

    def test_returns_raw_token_and_email_kwargs(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        signup = _make_waitlisted(db_session, slot)

        result = mark_promoted_pending(db_session, signup)

        assert isinstance(result, PromotionResult)
        assert result.signup is signup
        assert isinstance(result.raw_token, str) and len(result.raw_token) > 20
        assert result.email_kwargs == {
            "volunteer_id": str(signup.volunteer_id),
            "signup_id": str(signup.id),
            "token": result.raw_token,
            "event_id": str(event.id),
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run (docker command from Global Constraints): `pytest -q tests/test_promotion_pending.py`
Expected: FAIL — `ImportError: cannot import name 'PROMOTION_CONFIRM_TTL_MINUTES'`.

- [ ] **Step 3: Implement**

In `backend/app/magic_link_service.py`, directly below line 22 (`SIGNUP_CONFIRM_TTL_MINUTES = 20160`):

```python
# 2026-07-28 spec: promoted-from-waitlist signups get a shorter confirm
# window than fresh signups — a ghost promotee must not block the seat.
PROMOTION_CONFIRM_TTL_MINUTES = 4320  # 3 days * 24h * 60min
```

In `backend/app/signup_service.py`, add imports and the new pieces (keep `promote_waitlist_fifo` UNCHANGED in this task — it flips in Task 3):

```python
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models
from .magic_link_service import PROMOTION_CONFIRM_TTL_MINUTES, issue_token


@dataclass(frozen=True)
class PromotionResult:
    """Outcome of promoting one waitlisted signup to pending.

    raw_token exists only in memory (the DB stores its hash), so it must
    travel with this result for the caller's post-commit email enqueue.
    email_kwargs matches send_waitlist_promotion_email's signature exactly.
    """

    signup: models.Signup
    raw_token: str
    email_kwargs: dict


def mark_promoted_pending(db: Session, signup: models.Signup) -> PromotionResult:
    """Flip a waitlisted signup to pending and issue its confirm token.

    Promotion is a system/staff action, not volunteer intent, so the
    volunteer confirms via the emailed magic link (3-day TTL) — the same
    link is their manage/cancel page. Shared by promote_waitlist_fifo and
    waitlist_service.manual_promote so no promotion path can forget the
    token. Does NOT touch slot.current_count.
    """
    signup.status = models.SignupStatus.pending
    volunteer = signup.volunteer
    raw_token = issue_token(
        db,
        signup=signup,
        email=volunteer.email,
        purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=volunteer.id,
        ttl_minutes=PROMOTION_CONFIRM_TTL_MINUTES,
    )
    db.flush()
    return PromotionResult(
        signup=signup,
        raw_token=raw_token,
        email_kwargs={
            "volunteer_id": str(volunteer.id),
            "signup_id": str(signup.id),
            "token": raw_token,
            "event_id": str(signup.slot.event_id),
        },
    )
```

(No import cycle: `magic_link_service` imports only `config` and `models`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_promotion_pending.py`
Expected: PASS (3 tests). Also run `pytest -q tests/test_waitlist_service.py tests/test_magic_link_service.py` — must stay green (nothing existing changed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/magic_link_service.py backend/app/signup_service.py backend/tests/test_promotion_pending.py
git commit -m "feat: add promotion-to-pending core with 3-day confirm token"
```

---

### Task 2: Promotion email — template, builder, Celery task

**Files:**
- Create: `backend/app/email_templates/waitlist_promotion.html`
- Modify: `backend/app/emails.py` (append after `build_signup_confirmation_email`, `emails.py:429-466`)
- Modify: `backend/app/celery_app.py` (new task after `send_signup_confirmation_email`, `celery_app.py:446-487`)
- Test: `backend/tests/test_promotion_email.py` (create)

**Interfaces:**
- Consumes: `_render_html`, `_fmt_slot_time` (existing helpers in `emails.py`, used by `build_signup_confirmation_email`); `_send_email`, `SessionLocal`, `settings`, `logger` (existing in `celery_app.py`).
- Produces: `build_waitlist_promotion_email(volunteer, signup, token, event) -> tuple[str, str]` in `app.emails`; Celery task `send_waitlist_promotion_email(volunteer_id: str, signup_id: str, token: str, event_id: str) -> None` named `app.send_waitlist_promotion_email` in `app.celery_app`. Every later task enqueues it via `send_waitlist_promotion_email.delay(**promotion_result.email_kwargs)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_promotion_email.py`:

```python
"""Promotion confirm email: builder output + Celery task plumbing."""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from app import models
from app.emails import build_waitlist_promotion_email
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _build_fixture_rows(db_session):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Robots Module",
        start_date=datetime.now(timezone.utc) + timedelta(days=1),
        end_date=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
        capacity=1,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    volunteer = VolunteerFactory(first_name="Dana")
    signup = SignupFactory(
        volunteer=volunteer, slot=slot, status=models.SignupStatus.pending
    )
    db_session.flush()
    return volunteer, signup, event


class TestBuildWaitlistPromotionEmail:
    def test_contains_confirm_link_and_deadline(self, db_session):
        volunteer, signup, event = _build_fixture_rows(db_session)
        subject, html = build_waitlist_promotion_email(
            volunteer, signup, "tok-abc123", event
        )
        assert "/signup/confirm?token=tok-abc123" in html
        assert "3 days" in html
        assert "Dana" in html
        assert subject == (
            "A spot opened up — confirm your SciTrek signup for Robots Module"
        )

    def test_mentions_manage_and_cancel(self, db_session):
        volunteer, signup, event = _build_fixture_rows(db_session)
        _, html = build_waitlist_promotion_email(
            volunteer, signup, "tok-abc123", event
        )
        # The same link manages/cancels — the whole point of this change.
        assert "cancel" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_promotion_email.py`
Expected: FAIL — `ImportError: cannot import name 'build_waitlist_promotion_email'`.

- [ ] **Step 3: Implement template + builder**

Create `backend/app/email_templates/waitlist_promotion.html` (mirrors `signup_confirm.html` styling; `string.Template` variables):

```html
<!-- 2026-07-28: waitlist promotion confirm email -->
<!-- Uses string.Template safe_substitute() — variables: $volunteer_first_name, $event_title, $confirm_url, $slot_line -->
<h1 style="font-size:20px;color:#1a1a1a;margin:0 0 16px;">A spot opened up — you&#39;re off the waitlist!</h1>
<p style="margin:0 0 12px;">Hi $volunteer_first_name,</p>
<p style="margin:0 0 12px;">A spot opened up for you in <strong>$event_title</strong>. Please confirm within <strong>3 days</strong> to claim it:</p>
<p style="margin:0 0 16px;">
  <a href="$confirm_url" style="display:inline-block;background:#0b5ed7;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:4px;font-size:16px;font-weight:bold;">Confirm my spot</a>
</p>
<p style="margin:0 0 8px;font-weight:bold;">Your slot:</p>
<pre style="margin:0 0 16px;padding:12px;background:#f5f5f5;border-radius:4px;font-size:14px;white-space:pre-wrap;">$slot_line</pre>
<p style="margin:0 0 12px;">If you don&#39;t confirm within 3 days, the spot passes to the next person on the waitlist.</p>
<p style="margin:0 0 12px;">Can&#39;t make it? Use the same link to cancel so the next volunteer can step in. The link keeps working for managing your signups after you confirm.</p>
<p style="margin:0 0 12px;font-size:14px;color:#555555;">If this wasn&#39;t you, you can ignore this email.</p>
<p style="margin:0;">— UCSB SciTrek</p>
```

Append to `backend/app/emails.py` (after `build_signup_confirmation_email`):

```python
def build_waitlist_promotion_email(
    volunteer: "models.Volunteer",
    signup: "models.Signup",
    token: str,
    event: "models.Event",
) -> tuple[str, str]:
    """Build the waitlist-promotion confirm email (promotion → pending).

    Unlike the old link-less 'waitlist_promote' notification, this carries
    the magic-link confirm URL: the promotee must confirm within 3 days,
    and the same link is their manage/cancel page.

    Returns:
        (subject, html_body) — HTML only, same as the fresh-signup flow.
    """
    from .config import settings

    confirm_url = f"{settings.frontend_url}/signup/confirm?token={token}"
    slot = signup.slot
    slot_line = (
        f"{slot.slot_type.value.title()}: {slot.date} "
        f"{_fmt_slot_time(slot.start_time)} - {_fmt_slot_time(slot.end_time)} "
        f"@ {slot.location or event.school or 'TBD'}"
    )
    html = _render_html(
        "waitlist_promotion.html",
        volunteer_first_name=volunteer.first_name,
        event_title=event.title,
        confirm_url=confirm_url,
        slot_line=slot_line,
    )
    subject = f"A spot opened up — confirm your SciTrek signup for {event.title}"
    return subject, html
```

- [ ] **Step 4: Implement the Celery task**

In `backend/app/celery_app.py`, directly after `send_signup_confirmation_email` (ends `celery_app.py:487`):

```python
@celery.task(name="app.send_waitlist_promotion_email")
def send_waitlist_promotion_email(
    volunteer_id: str,
    signup_id: str,
    token: str,
    event_id: str,
) -> None:
    """Send the confirm-your-spot email after a waitlist promotion.

    Mirrors send_signup_confirmation_email: one-shot (no sent_notifications
    dedup row, D-11), warn-and-skip on missing entities, debug-only token
    echo. Enqueue strictly AFTER db.commit() — the worker reads rows from
    its own session.
    """
    from uuid import UUID

    from .emails import build_waitlist_promotion_email

    db: Session = SessionLocal()
    try:
        volunteer = db.get(models.Volunteer, UUID(volunteer_id))
        signup = db.get(models.Signup, UUID(signup_id))
        event = db.get(models.Event, UUID(event_id))
        if not volunteer or not signup or not event:
            logger.warning(
                "send_waitlist_promotion_email: missing entity, skipping "
                "volunteer_id=%s signup_id=%s event_id=%s",
                volunteer_id,
                signup_id,
                event_id,
            )
            return
        subject, html = build_waitlist_promotion_email(
            volunteer, signup, token, event
        )
        _send_email(to_email=volunteer.email, subject=subject, body="", html_body=html)
        logger.info(
            "waitlist_promotion_email_sent volunteer_id=%s signup_id=%s event_id=%s",
            volunteer_id,
            signup_id,
            event_id,
        )
        if getattr(settings, "debug", False):
            logger.debug("waitlist_promotion_token_preview token=%s", token)
    finally:
        db.close()
```

Add task-level tests to `backend/tests/test_celery_app_full.py`, next to the existing `send_signup_confirmation_email` tests (`test_celery_app_full.py:418-475`) and **using the exact same SessionLocal/monkeypatch pattern that file already uses** — one test that a valid trio sends via `_send_email` with the confirm URL in `html_body`, one test that a missing signup warn-skips without sending.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest -q tests/test_promotion_email.py tests/test_celery_app_full.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/email_templates/waitlist_promotion.html backend/app/emails.py backend/app/celery_app.py backend/tests/test_promotion_email.py backend/tests/test_celery_app_full.py
git commit -m "feat: add waitlist promotion confirm email template, builder and task"
```

---

### Task 3: FIFO promotion → pending across cancel/move paths

**Files:**
- Modify: `backend/app/signup_service.py:13-45` (`promote_waitlist_fifo`)
- Modify: `backend/app/routers/public/signups.py:261-294` (cancel promotion loop + enqueue)
- Modify: `backend/app/routers/signups.py:97-124` (authed cancel)
- Modify: `backend/app/routers/admin.py:52-68` (wrapper), `:671-686` (admin cancel), `:868-898` (admin move, incl. preserve-status fix)
- Test: update `backend/tests/test_promotion_pending.py`, `backend/tests/test_waitlist_service.py`, `backend/tests/test_signups.py`, `backend/tests/test_signups_router_full.py`, `backend/tests/test_admin.py`, `backend/tests/test_public_signups.py`, `backend/tests/test_swap_service.py`

**Interfaces:**
- Consumes: `mark_promoted_pending` (Task 1), `send_waitlist_promotion_email` (Task 2).
- Produces: `promote_waitlist_fifo(db: Session, slot_id) -> PromotionResult | None` (was `Signup | None`); admin wrapper `_promote_waitlist_fifo(db: Session, slot: models.Slot) -> List[PromotionResult]` (was `List[str]`). Task 4/7 call these with the new signatures.

**Behavior note (flagged addition beyond the spec's call-site table):** `admin_move_signup` today sets a moved signup to `confirmed` whenever the target has room — silently upgrading a still-`pending` signup. Per the spec principle (staff action ≠ volunteer intent) the move now PRESERVES `pending`/`confirmed`; a waitlisted signup moved into an open seat still becomes `confirmed` (unchanged, consistent with the swap decision in the spec).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_promotion_pending.py` (reuses that file's helpers):

```python
from app.signup_service import promote_waitlist_fifo


class TestPromoteWaitlistFifo:
    def test_returns_promotion_result_with_pending_signup(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        signup = _make_waitlisted(db_session, slot)

        result = promote_waitlist_fifo(db_session, slot.id)

        assert isinstance(result, PromotionResult)
        assert result.signup.id == signup.id
        assert result.signup.status == models.SignupStatus.pending
        token_row = (
            db_session.query(models.MagicLinkToken)
            .filter(models.MagicLinkToken.signup_id == signup.id)
            .one()
        )
        assert token_row.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM

    def test_empty_waitlist_returns_none(self, db_session):
        owner, event, slot = _make_event_and_slot(db_session, capacity=1)
        assert promote_waitlist_fifo(db_session, slot.id) is None
```

Router coverage — in `backend/tests/test_public_signups.py`, find `test_public_cancel_sends_waitlist_promote_email` (`:504` — it already builds "confirmed canceller + waitlisted next" and captures the promotion email). Duplicate its setup into a new test in the same class:

```python
def test_public_cancel_promotes_to_pending_with_confirm_email(
    self, client, db_session, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay",
        lambda *a, **k: None,
    )
    # <setup copied from test_public_cancel_sends_waitlist_promote_email:
    #  capacity-1 slot, confirmed signup with manage token, waitlisted second>
    resp = client.delete(f"/api/v1/public/signups/{confirmed_id}?token={raw_token}")
    assert resp.status_code == 200
    assert resp.json()["promoted_from_waitlist"] == 1
    db_session.expire_all()
    promoted = db_session.get(models.Signup, waitlisted_id)
    assert promoted.status == models.SignupStatus.pending
    assert len(sent) == 1
    assert sent[0]["signup_id"] == str(waitlisted_id)
    assert sent[0]["token"]  # raw token travels to the email task
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest -q tests/test_promotion_pending.py tests/test_public_signups.py`
Expected: the two new `TestPromoteWaitlistFifo` tests FAIL (`promote_waitlist_fifo` returns a `Signup`, `isinstance(..., PromotionResult)` false); the new cancel test FAILS (promoted status is `confirmed`, `sent` empty).

- [ ] **Step 3: Flip the primitive**

Replace the body of `promote_waitlist_fifo` in `backend/app/signup_service.py` and rewrite its docstring (the old one argues for instant-confirm — that decision is deliberately reversed):

```python
def promote_waitlist_fifo(db: Session, slot_id) -> PromotionResult | None:
    """Promote the first-in waitlisted signup for this slot, if any.

    Canonical ordering: (timestamp ASC, id ASC). Uses SELECT FOR UPDATE
    SKIP LOCKED on the waitlist row to serialize concurrent cancels.

    2026-07-28 spec: promoted signups go to 'pending' with a fresh 3-day
    SIGNUP_CONFIRM token — promotion is a system/staff action, not
    volunteer intent, and the emailed link doubles as the volunteer's
    manage/cancel page (previously promotees had no link at all).

    The caller is responsible for:
      - Already holding a FOR UPDATE lock on the parent Slot row
      - Incrementing slot.current_count after a successful promotion
        (pending holds capacity)
      - Enqueuing send_waitlist_promotion_email(**result.email_kwargs)
        AFTER db.commit()
    """
    next_up = (
        db.query(models.Signup)
        .filter(
            models.Signup.slot_id == slot_id,
            models.Signup.status == models.SignupStatus.waitlisted,
        )
        .order_by(models.Signup.timestamp.asc(), models.Signup.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not next_up:
        return None
    return mark_promoted_pending(db, next_up)
```

- [ ] **Step 4: Update the three cancel paths + admin move**

`backend/app/routers/public/signups.py` — add import `send_waitlist_promotion_email` next to `send_email_notification` (`:15`); replace the promotion loop and email block in `cancel_signup` (`:263-288`):

```python
    promotions = []
    if slot:
        while slot.current_count < slot.capacity:
            promo = promote_waitlist_fifo(db, slot.id)
            if promo is None:
                break
            slot.current_count += 1
            promotions.append(promo)
    promoted_count = len(promotions)

    log_action(
        db, actor=None, action="signup_cancelled",
        entity_type="signup", entity_id=str(signup_id),
        extra={
            "volunteer_email": token_row.volunteer.email,
            "signup_id": str(signup_id),
            "promoted_from_waitlist": promoted_count,
        },
    )
    # Capture before commit — expire_on_commit would force refresh queries.
    promotion_email_kwargs = [p.email_kwargs for p in promotions]
    db.commit()

    # Emails only after commit — the worker reads rows from its own session.
    for kwargs in promotion_email_kwargs:
        send_waitlist_promotion_email.delay(**kwargs)
```

`backend/app/routers/signups.py` — same shape in `cancel_signup` (`:99-122`): collect `promotions`, `promotion_email_kwargs = [p.email_kwargs for p in promotions]` before commit, keep the existing `kind="cancellation"` enqueue, replace the `waitlist_promote` loop with `send_waitlist_promotion_email.delay(**kwargs)`. Import the task next to `send_email_notification` (`:9`).

`backend/app/routers/admin.py` — wrapper (`:52-68`) becomes:

```python
def _promote_waitlist_fifo(db: Session, slot: models.Slot) -> List[PromotionResult]:
    """Admin-side wrapper around the canonical promote_waitlist_fifo.

    Loops until capacity is full. Caller must hold FOR UPDATE on the slot,
    capture each result's email_kwargs BEFORE commit, and enqueue
    send_waitlist_promotion_email AFTER commit.
    """
    results: List[PromotionResult] = []
    while slot.current_count < slot.capacity:
        promo = promote_waitlist_fifo(db, slot.id)
        if promo is None:
            break
        slot.current_count += 1
        results.append(promo)
    return results
```

Import `PromotionResult` alongside `promote_waitlist_fifo` and add `send_waitlist_promotion_email` to the celery imports. In `admin_cancel_signup` (`:671-684`): `promotions = _promote_waitlist_fifo(db, slot)`; capture `promotion_email_kwargs` before commit; after commit keep `kind="cancellation"` and replace the promote loop with the new task. In `admin_move_signup`:

```python
    if target_slot.current_count < target_slot.capacity:
        # Preserve pending/confirmed on move — a staff move must not
        # silently confirm a signup the volunteer never confirmed.
        # Waitlisted → open seat still confirms (spec: same as swap).
        new_status = (
            previous_status
            if held_source_capacity
            else models.SignupStatus.confirmed
        )
        target_slot.current_count += 1
    else:
        new_status = models.SignupStatus.waitlisted

    signup.slot_id = target_slot.id
    signup.status = new_status

    promotions = (
        _promote_waitlist_fifo(db, source_slot) if held_source_capacity else []
    )

    log_action(db, actor, "admin_signup_move", "Signup", str(signup.id))
    promotion_email_kwargs = [p.email_kwargs for p in promotions]
    db.commit()
    db.refresh(signup)

    send_email_notification.delay(signup_id=str(signup.id), kind="reschedule")
    # Fixes the silent-promotion bug: move previously promoted with no email.
    for kwargs in promotion_email_kwargs:
        send_waitlist_promotion_email.delay(**kwargs)
```

- [ ] **Step 5: Update existing test assertions**

Run the full affected set and fix every failure by applying these mechanical transformations (do NOT weaken any other assertion):

- promoted signup asserted `status == confirmed` → `status == pending` (files: `test_waitlist_service.py`, `test_signups.py`, `test_signups_router_full.py` (`:318` area), `test_admin.py` (`:66`, `:137`, `:217` areas), `test_public_signups.py` (`:504`), `test_swap_service.py` (`:126` — primitive already flips it; email plumbing lands in Task 4)).
- assertions that `.delay` was called with `kind="waitlist_promote"` → assert `app.celery_app.send_waitlist_promotion_email.delay` called with `signup_id=<promoted id>` (monkeypatch-capture as in Step 1's example).
- tests that only silence Celery: add `send_waitlist_promotion_email.delay` to the silenced set (extend `_bypass_celery`-style helpers where present, e.g. `test_waitlist_service.py:33-42`).
- if any move test asserts a moved *pending* signup became `confirmed`, flip it to expect `pending` (preserve-status fix).

Run: `pytest -q tests/test_promotion_pending.py tests/test_waitlist_service.py tests/test_signups.py tests/test_signups_router_full.py tests/test_admin.py tests/test_public_signups.py tests/test_swap_service.py`
Expected: PASS.

- [ ] **Step 6: Full backend suite**

Run: `pytest -q`
Expected: PASS except possibly `test_celery_app_full.py:585` (`test_waitlist_promote_email_does_not_ask_to_confirm`) and other `waitlist_promote`-kind stragglers — those are removed in Task 10; if they fail here because the kind is still registered but unused, leave them for Task 10 ONLY if green, otherwise update now.

- [ ] **Step 7: Commit**

```bash
git add backend/app/signup_service.py backend/app/routers/public/signups.py backend/app/routers/signups.py backend/app/routers/admin.py backend/tests/
git commit -m "feat: FIFO waitlist promotion goes pending with confirm email on all cancel/move paths"
```

---

### Task 4: Swap paths — `SwapResult` + promotion email enqueue

**Files:**
- Modify: `backend/app/services/swap_service.py:58-170`
- Modify: `backend/app/routers/public/signups.py:193-206` (public swap endpoint)
- Modify: `backend/app/routers/signups.py:190-216` (authed swap endpoint)
- Test: `backend/tests/test_swap_service.py`

**Interfaces:**
- Consumes: `promote_waitlist_fifo -> PromotionResult | None` (Task 3), `send_waitlist_promotion_email` (Task 2).
- Produces: `SwapResult(NamedTuple)` with `signup: models.Signup`, `promotion: PromotionResult | None`; `swap_signup(...) -> SwapResult` (was `-> models.Signup`). The waitlisted-into-open-target in-place flip stays `confirmed` (spec: tokened volunteer action = verified intent; kept identical for staff to match the spec table).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_swap_service.py` (reuse that file's existing setup helpers):

```python
from app.services.swap_service import SwapResult


def test_swap_returns_promotion_result_for_freed_seat(db_session, ...):
    # Reuse the exact setup of the existing "swap auto-promotes source
    # waitlist" test (test_swap_service.py:126).
    result = swap_signup(db_session, signup_id=..., target_slot_id=...)
    assert isinstance(result, SwapResult)
    assert result.signup.slot_id == target_slot.id
    assert result.promotion is not None
    assert result.promotion.signup.status == models.SignupStatus.pending
    assert result.promotion.email_kwargs["signup_id"] == str(
        result.promotion.signup.id
    )


def test_swap_without_waitlist_has_no_promotion(db_session, ...):
    # Reuse the "no-waitlist case" setup (test_swap_service.py:185).
    result = swap_signup(db_session, signup_id=..., target_slot_id=...)
    assert result.promotion is None
```

(Fill `...` from the neighboring tests' fixtures — same rows, same helpers.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_swap_service.py`
Expected: new tests FAIL — `swap_signup` returns a `Signup`, no `.promotion` attribute; existing tests still PASS.

- [ ] **Step 3: Implement**

`backend/app/services/swap_service.py` — add at top:

```python
from typing import NamedTuple, Optional

from ..signup_service import PromotionResult, promote_waitlist_fifo


class SwapResult(NamedTuple):
    """swap_signup outcome: the moved signup + the source-slot promotion
    (None when the source waitlist was empty or no seat was freed).
    The caller must enqueue send_waitlist_promotion_email(**promotion.email_kwargs)
    AFTER commit."""

    signup: "models.Signup"
    promotion: Optional[PromotionResult]
```

Change `swap_signup`'s return annotation to `-> SwapResult`, replace the promotion block (`:147-150`):

```python
    promotion: Optional[PromotionResult] = None
    if holds_capacity:
        promotion = promote_waitlist_fifo(db, source_slot.id)
        if promotion is not None:
            source_slot.current_count += 1
```

and return `SwapResult(signup=signup, promotion=promotion)`. Update the contract docstring at the top of the file (promotion → pending + email is now the caller's post-commit duty).

`backend/app/routers/public/signups.py` (`:193-206`):

```python
    result = swap_signup(
        db,
        signup_id=signup_id,
        target_slot_id=body.target_slot_id,
        actor=None,
        actor_label="participant",
    )
    updated = result.signup
    promo_kwargs = result.promotion.email_kwargs if result.promotion else None
    db.commit()
    db.refresh(updated)
    if promo_kwargs:
        # Fixes the silent-promotion bug: swaps previously promoted with no email.
        send_waitlist_promotion_email.delay(**promo_kwargs)
    return {
        "signup_id": str(updated.id),
        "slot_id": str(updated.slot_id),
        "status": updated.status.value,
    }
```

`backend/app/routers/signups.py` (`:207-216`): same pattern; `return result.signup` after refresh; import the task.

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_swap_service.py tests/test_public_signups.py tests/test_signups.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/swap_service.py backend/app/routers/public/signups.py backend/app/routers/signups.py backend/tests/test_swap_service.py
git commit -m "feat: swap-triggered waitlist promotions send the confirm email"
```

---

### Task 5: Manual promote — `manual_promote`, organizer endpoint, admin promote refactor

**Files:**
- Modify: `backend/app/services/waitlist_service.py:99-131`
- Modify: `backend/app/routers/organizer.py:212-247`
- Modify: `backend/app/routers/admin.py:689-742`
- Test: `backend/tests/test_waitlist_service.py` (manual promote tests), `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: `mark_promoted_pending` (Task 1), `send_waitlist_promotion_email` (Task 2).
- Produces: `manual_promote(db, signup, slot, allow_overfill: bool = False) -> PromotionResult` (was `-> models.Signup`). Validation and `slot.current_count += 1` behavior unchanged; `ValueError` messages unchanged.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_waitlist_service.py`, extend the existing WAIT-03 manual-promote test (and add one):

```python
def test_manual_promote_returns_pending_promotion_result(db_session):
    # Reuse the existing manual-promote setup in this file.
    result = manual_promote(db_session, signup, slot, allow_overfill=True)
    assert result.signup.status == models.SignupStatus.pending
    assert result.raw_token
    token_row = (
        db_session.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == signup.id)
        .one()
    )
    assert token_row.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_waitlist_service.py`
Expected: new test FAILS (`Signup` has no `.signup`/status is `confirmed`).

- [ ] **Step 3: Implement `manual_promote`**

`backend/app/services/waitlist_service.py` — add `from ..signup_service import PromotionResult, mark_promoted_pending` to imports; replace `:122-131` and rewrite the docstring's promotion paragraph:

```python
    if signup.status != models.SignupStatus.waitlisted:
        raise ValueError("only waitlisted signups can be promoted")
    if slot.current_count >= slot.capacity and not allow_overfill:
        raise ValueError("slot is full")

    # 2026-07-28 spec: staff promotion is not volunteer intent — the
    # volunteer confirms via the emailed 3-day magic link, which is also
    # their manage/cancel page. Caller enqueues the email after commit.
    result = mark_promoted_pending(db, signup)
    slot.current_count += 1
    db.flush()

    return result
```

- [ ] **Step 4: Update the two staff endpoints**

`backend/app/routers/organizer.py` (`:212-245`): capture the result, replace the email, and delete the stale comment block (`:240-242` claims `manual_promote` dispatches a magic link — it never did):

```python
    try:
        promo = manual_promote(db, signup, slot, allow_overfill=allow_overfill)
    except ValueError as exc:
        msg = str(exc)
        if "full" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    log_action(...)  # unchanged
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(signup)

    # Confirm-your-spot email with the 3-day magic link (2026-07-28 spec).
    send_waitlist_promotion_email.delay(**promo_kwargs)

    return signup
```

Import `send_waitlist_promotion_email` from `...celery_app` (keep `send_email_notification` only if still used elsewhere in the file — ruff will say).

`backend/app/routers/admin.py` `admin_promote_signup` (`:689-742`): keep the 404s, staff-access check, the explicit `!= waitlisted` 400, the count-heal, and the `Slot is full` 400 pre-check (exact messages preserved for existing tests). Replace `:731-740`:

```python
    from ..services.waitlist_service import manual_promote

    try:
        promo = manual_promote(db, signup, slot, allow_overfill=False)
    except ValueError as exc:  # belt-and-braces; pre-checks above match
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_action(db, actor, "admin_signup_promote", "Signup", str(signup.id))
    promo_kwargs = promo.email_kwargs
    db.commit()
    db.refresh(signup)

    # Was kind="confirmation" — wrong template AND swallowed by the
    # (signup_id, kind) dedup if a confirmation was ever sent. The promotion
    # email is one-shot with the raw token, so no dedup applies.
    send_waitlist_promotion_email.delay(**promo_kwargs)

    return signup
```

(Note: `manual_promote` increments `current_count` — delete the endpoint's own `slot.current_count += 1` so it isn't double-counted.)

- [ ] **Step 5: Update existing assertions and run**

Same transformations as Task 3 Step 5 for organizer/admin promote tests (promoted → `pending`; `kind="waitlist_promote"` / `kind="confirmation"` assertions → `send_waitlist_promotion_email.delay` capture).

Run: `pytest -q tests/test_waitlist_service.py tests/test_admin.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/waitlist_service.py backend/app/routers/organizer.py backend/app/routers/admin.py backend/tests/
git commit -m "feat: manual staff promotion goes pending and sends the confirm email"
```

---

### Task 6: Manage links outlive the confirm deadline

**Files:**
- Modify: `backend/app/routers/public/signups.py:86-87`, `:179-180`, `:223-224` (and the now-unused `datetime`/`timezone` import at `:8` if nothing else uses it)
- Modify: `backend/app/email_templates/signup_confirm.html:11` (copy says "valid for 14 days" about the manage link)
- Test: `backend/tests/test_manage_token_semantics.py` (create)

**Interfaces:**
- Consumes: `_lookup_token` (existing, no expiry logic); `consume_token` (existing — KEEPS enforcing `expires_at`, `magic_link_service.py:93`; do not touch).
- Produces: manage/swap/cancel accept any token whose row still exists. `expires_at` now means "confirmation deadline" project-wide.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_manage_token_semantics.py`:

```python
"""expires_at = confirmation deadline ONLY (2026-07-28 spec decision 3).

Manage/swap/cancel work with an expired-but-existing token; confirm does not.
"""
import uuid
from datetime import date as date_type, datetime, timedelta, timezone

from app import models
from app import magic_link_service as mls
from tests.fixtures.factories import SignupFactory, VolunteerFactory
from tests.fixtures.helpers import _bind_factories, make_user


def _confirmed_signup_with_expired_token(db_session):
    owner = make_user(db_session, role=models.UserRole.admin)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Old Link Event",
        start_date=datetime.now(timezone.utc) + timedelta(days=20),
        end_date=datetime.now(timezone.utc) + timedelta(days=21),
    )
    db_session.add(event)
    db_session.flush()
    slot = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=20),
        end_time=datetime.now(timezone.utc) + timedelta(days=20, hours=2),
        capacity=2,
        current_count=1,
        slot_type=models.SlotType.PERIOD,
        date=date_type.today(),
    )
    db_session.add(slot)
    db_session.flush()
    _bind_factories(db_session)
    vol = VolunteerFactory()
    signup = SignupFactory(
        volunteer=vol, slot=slot, status=models.SignupStatus.confirmed
    )
    db_session.flush()
    raw = mls.issue_token(
        db_session,
        signup=signup,
        email=vol.email,
        purpose=models.MagicLinkPurpose.SIGNUP_CONFIRM,
        volunteer_id=vol.id,
        ttl_minutes=60,
    )
    row = (
        db_session.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == signup.id)
        .one()
    )
    # The day-15 scenario: token expired long ago, signup still real.
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    return signup, raw


class TestExpiredTokenStillManages:
    def test_manage_returns_200(self, client, db_session):
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.get(f"/api/v1/public/signups/manage?token={raw}")
        assert resp.status_code == 200
        assert resp.json()["signups"]

    def test_cancel_returns_200_and_cancels(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.celery_app.send_email_notification.delay", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "app.celery_app.send_waitlist_promotion_email.delay",
            lambda **k: None,
        )
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.delete(f"/api/v1/public/signups/{signup.id}?token={raw}")
        assert resp.status_code == 200
        db_session.expire_all()
        assert (
            db_session.get(models.Signup, signup.id).status
            == models.SignupStatus.cancelled
        )

    def test_confirm_still_rejects_expired(self, client, db_session):
        signup, raw = _confirmed_signup_with_expired_token(db_session)
        resp = client.post(f"/api/v1/public/signups/confirm?token={raw}")
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]
```

(If `client`/`db_session` don't share visibility in this repo's fixture design, mirror how `test_public_signups.py` builds rows for endpoint tests — same file-local conventions.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_manage_token_semantics.py`
Expected: manage + cancel tests FAIL with 400 "token invalid or expired"; confirm test PASSES already.

- [ ] **Step 3: Implement**

In `backend/app/routers/public/signups.py`, at `:86-87`, `:179-180`, `:223-224`, replace:

```python
    token_row = _lookup_token(db, token)
    if token_row is None or token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token invalid or expired")
```

with:

```python
    # 2026-07-28 spec: expires_at is the CONFIRMATION deadline only.
    # Manage/swap/cancel stay usable for as long as the token row exists
    # (rows die with their signup via cascade, or via the stale-token sweep).
    token_row = _lookup_token(db, token)
    if token_row is None:
        raise HTTPException(status_code=400, detail="token invalid")
```

(Put the comment once, on the manage endpoint; the other two get the bare check.) Remove the `datetime`/`timezone` import at `:8` if now unused (ruff confirms).

In `backend/app/email_templates/signup_confirm.html:11`, replace:

```html
<p style="margin:0 0 12px;">You can manage or cancel your signup any time using the same link above (valid for 14 days).</p>
```

with:

```html
<p style="margin:0 0 12px;">Please confirm within 14 days. The same link keeps working after that for managing or cancelling your signups any time.</p>
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_manage_token_semantics.py tests/test_public_signups.py tests/test_magic_link_signup_purpose.py`
Expected: PASS. (If an existing test asserts 400 on expired manage/cancel tokens, it contradicts the approved spec — update it and note it in the commit body.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/public/signups.py backend/app/email_templates/signup_confirm.html backend/tests/test_manage_token_semantics.py backend/tests/
git commit -m "feat: manage links outlive the confirm deadline"
```

---

### Task 7: Expiry job — reap-criteria fix, chained promotion, hourly beat

**Files:**
- Modify: `backend/app/celery_app.py:490-534` (`expire_pending_signups`), `:585-588` (beat entry)
- Test: `backend/tests/test_expired_pending_cleanup.py`

**Interfaces:**
- Consumes: `promote_waitlist_fifo -> PromotionResult | None` (Task 3), `send_waitlist_promotion_email` (Task 2).
- Produces: job semantics relied on by Task 8 (cleanup runs in the same task, second transaction).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_expired_pending_cleanup.py`, following that file's existing setup/SessionLocal pattern exactly:

```python
def test_pending_with_fresh_second_token_survives(...):
    # signup: pending; token A expired (original 14-day), token B live
    # (promotion 3-day). The reap must key on "NO unexpired token", not
    # "an expired token exists" — otherwise every promotee whose original
    # token lapsed on the waitlist is deleted the hour after promotion.
    expire_pending_signups()
    assert db.get(models.Signup, signup_id) is not None


def test_reap_chains_promotion_with_email(monkeypatch, ...):
    sent = []
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay",
        lambda **kw: sent.append(kw),
    )
    # capacity-1 slot: pending signup with expired token + waitlisted second.
    expire_pending_signups()
    # pending deleted, waitlisted promoted to pending, count still 1
    assert db.get(models.Signup, expired_id) is None
    promoted = db.get(models.Signup, waitlisted_id)
    assert promoted.status == models.SignupStatus.pending
    assert slot_reloaded.current_count == 1
    assert len(sent) == 1 and sent[0]["signup_id"] == str(waitlisted_id)


def test_chained_promotion_token_is_three_days(...):
    # After the chain, the promoted signup's newest token expires ~3 days out.
    token = (
        db.query(models.MagicLinkToken)
        .filter(models.MagicLinkToken.signup_id == waitlisted_id)
        .order_by(models.MagicLinkToken.expires_at.desc())
        .first()
    )
    expected = datetime.now(timezone.utc) + timedelta(minutes=4320)
    assert abs((token.expires_at - expected).total_seconds()) < 3600


def test_tokenless_pending_is_not_deleted(...):
    # pending signup with NO SIGNUP_CONFIRM token at all: warn-log, skip.
    expire_pending_signups()
    assert db.get(models.Signup, tokenless_id) is not None
```

(Fill `...`/row-building from the file's existing tests — it already constructs pending signups with expired tokens.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_expired_pending_cleanup.py`
Expected: `fresh_second_token` test FAILS (join deletes it); chain tests FAIL (no promotion); existing tests PASS.

- [ ] **Step 3: Implement**

Replace the body of `expire_pending_signups` (`celery_app.py:490-534`); add `from .signup_service import promote_waitlist_fifo` to the module's imports (no cycle: `signup_service` → `magic_link_service` → `models`/`config` only):

```python
@celery.task(name="app.celery_app.expire_pending_signups")
def expire_pending_signups() -> None:
    """Hourly sweep (2026-07-28 spec): reap unconfirmed pendings, chain-promote,
    then clean up stale manage tokens.

    Reap criteria — a pending signup is deleted only when it has at least one
    SIGNUP_CONFIRM token and NONE of them is still unexpired. A signup can
    legitimately hold several tokens (original 14-day + promotion 3-day);
    keying on "an expired token exists" would delete freshly promoted rows.

    Side effects:
      - slot.current_count decremented per deleted signup
      - freed seats chain-promote the slot's waitlist FIFO (pending + email,
        their own 3-day clock — an unbroken chain across nightly runs)
      - MagicLinkToken rows cascade-delete with their signup
      - stale confirm tokens removed (see _cleanup_stale_confirm_tokens)
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        live_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose
                == models.MagicLinkPurpose.SIGNUP_CONFIRM,
                models.MagicLinkToken.expires_at >= now,
            )
            .exists()
        )
        any_token_exists = (
            db.query(models.MagicLinkToken.token_hash)
            .filter(
                models.MagicLinkToken.signup_id == models.Signup.id,
                models.MagicLinkToken.purpose
                == models.MagicLinkPurpose.SIGNUP_CONFIRM,
            )
            .exists()
        )

        rows = (
            db.query(models.Signup, models.Slot)
            .join(models.Slot, models.Signup.slot_id == models.Slot.id)
            .filter(
                models.Signup.status == models.SignupStatus.pending,
                any_token_exists,
                ~live_token_exists,
            )
            .all()
        )

        tokenless = (
            db.query(func.count(models.Signup.id))
            .filter(
                models.Signup.status == models.SignupStatus.pending,
                ~any_token_exists,
            )
            .scalar()
            or 0
        )
        if tokenless:
            logger.warning(
                "expire_pending_signups: %d tokenless pending signups skipped "
                "(data problem — pending must always carry a confirm token)",
                tokenless,
            )

        affected_slot_ids: list = []
        count = 0
        for signup, slot in rows:
            slot.current_count = max(0, slot.current_count - 1)
            if slot.id not in affected_slot_ids:
                affected_slot_ids.append(slot.id)
            db.delete(signup)
            count += 1
        db.flush()

        promotion_email_kwargs: list[dict] = []
        for slot_id in affected_slot_ids:
            slot = (
                db.query(models.Slot)
                .filter(models.Slot.id == slot_id)
                .with_for_update()
                .first()
            )
            if slot is None:
                continue
            while slot.current_count < slot.capacity:
                promo = promote_waitlist_fifo(db, slot.id)
                if promo is None:
                    break
                slot.current_count += 1
                promotion_email_kwargs.append(promo.email_kwargs)

        db.commit()
        for kwargs in promotion_email_kwargs:
            send_waitlist_promotion_email.delay(**kwargs)
        logger.info(
            "expired_pending_signups_cleaned count=%d promoted=%d",
            count,
            len(promotion_email_kwargs),
        )

        # Second transaction: stale-token sweep (Task 8 adds the helper).
    finally:
        db.close()
```

Beat entry (`celery_app.py:585-588`) becomes:

```python
    "expire-pending-signups-hourly": {
        "task": "app.celery_app.expire_pending_signups",
        "schedule": crontab(minute=0),
    },
```

Ops note for the PR body: RedBeat may keep the old `expire-pending-signups-daily-3am` key in Redis after deploy — delete it once with `redis-cli del "redbeat:expire-pending-signups-daily-3am"` (harmless if left: same idempotent task).

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_expired_pending_cleanup.py`
Expected: PASS (old + new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/celery_app.py backend/tests/test_expired_pending_cleanup.py
git commit -m "feat: hourly expiry job fixes reap criteria and chain-promotes freed seats"
```

---

### Task 8: Stale-token cleanup sweep

**Files:**
- Modify: `backend/app/celery_app.py` (helper + call at end of `expire_pending_signups`)
- Test: `backend/tests/test_expired_pending_cleanup.py`

**Interfaces:**
- Consumes: Task 7's job structure (comment marks the insertion point).
- Produces: `_cleanup_stale_confirm_tokens(db: Session, now: datetime) -> int` — deletes SIGNUP_CONFIRM tokens whose volunteer's latest slot `end_time` is more than 30 days past.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_expired_pending_cleanup.py`:

```python
class TestStaleTokenCleanup:
    def test_deletes_token_when_no_upcoming_events(self, ...):
        # volunteer's only signup: slot ended 40 days ago (confirmed).
        expire_pending_signups()
        assert token_count_for(volunteer.id) == 0

    def test_keeps_token_with_upcoming_signup(self, ...):
        # one past slot (40 days ago) AND one future slot → keep all tokens.
        expire_pending_signups()
        assert token_count_for(volunteer.id) > 0

    def test_keeps_token_within_grace_window(self, ...):
        # last slot ended 10 days ago (< 30-day grace) → keep.
        expire_pending_signups()
        assert token_count_for(volunteer.id) > 0
```

(Implement `token_count_for` as a file-local helper querying `MagicLinkToken` by `volunteer_id`; build rows with the file's existing helpers. Give past slots `end_time = now - timedelta(days=40)` etc.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_expired_pending_cleanup.py::TestStaleTokenCleanup`
Expected: FAIL — stale token still present.

- [ ] **Step 3: Implement**

In `backend/app/celery_app.py`, add near the job (module level; `func` already imported at `:16`, add `select` to the `from sqlalchemy import ...` line):

```python
def _cleanup_stale_confirm_tokens(db: Session, now: datetime) -> int:
    """Delete SIGNUP_CONFIRM tokens for volunteers with nothing left to manage.

    2026-07-28 spec decision 5: manage links deliberately outlive expires_at,
    so token rows are garbage-collected by lifecycle instead — a token lives
    while its volunteer has ANY signup whose slot ends in the future or
    within the 30-day grace window. Volunteers absent from signups entirely
    are covered by the signup-cascade (tokens die with their anchor signup).
    """
    cutoff = now - timedelta(days=30)
    stale_volunteers = (
        db.query(models.Signup.volunteer_id)
        .join(models.Slot, models.Signup.slot_id == models.Slot.id)
        .group_by(models.Signup.volunteer_id)
        .having(func.max(models.Slot.end_time) < cutoff)
    ).subquery()
    deleted = (
        db.query(models.MagicLinkToken)
        .filter(
            models.MagicLinkToken.purpose == models.MagicLinkPurpose.SIGNUP_CONFIRM,
            models.MagicLinkToken.volunteer_id.in_(
                select(stale_volunteers.c.volunteer_id)
            ),
        )
        .delete(synchronize_session=False)
    )
    return deleted
```

Replace the `# Second transaction:` comment at the end of `expire_pending_signups` with:

```python
        stale = _cleanup_stale_confirm_tokens(db, now)
        db.commit()
        if stale:
            logger.info("stale_confirm_tokens_cleaned count=%d", stale)
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_expired_pending_cleanup.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/celery_app.py backend/tests/test_expired_pending_cleanup.py
git commit -m "feat: garbage-collect confirm tokens once a volunteer has no upcoming events"
```

---

### Task 9: Cancellation email on public self-cancel

**Files:**
- Modify: `backend/app/routers/public/signups.py` (cancel endpoint, post-commit block from Task 3)
- Test: `backend/tests/test_public_signups.py`

**Interfaces:**
- Consumes: existing `send_email_notification` task + `"cancellation"` kind (deduped via `sent_notifications`).
- Produces: tamper-evidence — spec decision 6. One line after commit:

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_public_signups.py`, next to the existing cancel tests:

```python
def test_public_cancel_sends_cancellation_email(self, client, db_session, monkeypatch):
    kinds = []
    monkeypatch.setattr(
        "app.celery_app.send_email_notification.delay",
        lambda *a, **k: kinds.append(k.get("kind")),
    )
    monkeypatch.setattr(
        "app.celery_app.send_waitlist_promotion_email.delay", lambda **k: None
    )
    monkeypatch.setattr(
        "app.celery_app.send_signup_confirmation_email.delay", lambda *a, **k: None
    )
    # <reuse the standard cancel setup from this file's existing tests>
    resp = client.delete(f"/api/v1/public/signups/{signup_id}?token={raw_token}")
    assert resp.status_code == 200
    assert "cancellation" in kinds
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest -q tests/test_public_signups.py`
Expected: new test FAILS (`kinds == []` — the public path sends nothing today).

- [ ] **Step 3: Implement**

In the public `cancel_signup` post-commit block (after `db.commit()`, before the promotion-email loop):

```python
    # Tamper-evidence for long-lived manage links (2026-07-28 spec decision 6):
    # the volunteer learns immediately if someone else cancels them. Deduped
    # by (signup_id, "cancellation") — a signup cancels at most once.
    send_email_notification.delay(signup_id=str(signup_id), kind="cancellation")
```

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_public_signups.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/public/signups.py backend/tests/test_public_signups.py
git commit -m "feat: send cancellation email on public self-cancel"
```

---

### Task 10: Remove the old `waitlist_promote` kind + final sweep

**Files:**
- Modify: `backend/app/emails.py:323-359` (delete `send_waitlist_promote` + BUILDERS entry)
- Modify: `backend/tests/test_celery_app_full.py:585` (delete `test_waitlist_promote_email_does_not_ask_to_confirm`)
- Verify: frontend, lint, full suites

- [ ] **Step 1: Delete dead code**

Delete `send_waitlist_promote` (`emails.py:323-343`) and the `"waitlist_promote": send_waitlist_promote,` BUILDERS line (`:358`). Delete `test_waitlist_promote_email_does_not_ask_to_confirm` (its inverse — the email MUST carry the confirm link — lives in `tests/test_promotion_email.py` from Task 2).

- [ ] **Step 2: Prove nothing references the kind**

Run: `grep -rn "waitlist_promote\b" backend/app backend/tests frontend/src e2e/ | grep -v "waitlist_promote_manual"`
Expected: no hits (the `waitlist_promote_manual` audit action stays — different thing). If e2e specs assert on the old email subject, update them to the new subject from Global Constraints.

- [ ] **Step 3: Full backend suite + lint**

Run: `pytest -q` (docker) — expected: PASS, zero failures.
Run: `ruff check app tests && black --check app tests` inside the container (`sh -c "ruff check app tests && black --check app tests"`); fix anything it flags (e.g. the unused `datetime` import from Task 6).

- [ ] **Step 4: Frontend checks**

- `nvm use 20 && cd frontend && npm run test -- --run` — expected: PASS untouched (no frontend code changed; the confirm + manage pages already handle `pending` rows and the Cancel button is only hidden for `waitlisted`, `ManageSignupsPage.jsx:320`).
- Grep `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx` for a case rendering a `pending` signup: if none exists, add one in that file's existing style asserting a pending row renders with a visible Cancel button (a promoted volunteer's primary action).

- [ ] **Step 5: Commit**

```bash
git add backend/app/emails.py backend/tests/test_celery_app_full.py frontend/
git commit -m "refactor: remove the link-less waitlist_promote email kind"
```

---

## Self-Review (done at plan time)

- **Spec coverage:** decision 1 → Tasks 3/4/5; decision 2 → Task 1; decision 3 → Task 6; decision 4 → Task 7; decision 5 → Task 8; decision 6 → Task 9; decision 7 → recorded in spec (no code); email replacement + 3 broken paths → Tasks 2/3/4/5; two-token reap guard → Task 7; error handling (expired promotee → 400, existing frontend error state) → covered by unchanged `consume_token` + Task 6 test 3.
- **Type consistency:** `PromotionResult.email_kwargs` keys == `send_waitlist_promotion_email` parameters (`volunteer_id`, `signup_id`, `token`, `event_id`, all str); `promote_waitlist_fifo -> PromotionResult | None` consumed by Tasks 3/4/7; `manual_promote -> PromotionResult` consumed by Task 5; `SwapResult.promotion: PromotionResult | None` consumed in both swap endpoints.
- **Known intermediate state:** after Task 3, swap-triggered promotions are `pending` but email-less until Task 4 lands — both commits are on the same branch/PR, never deployed apart.
- **Deliberate additions beyond the spec's letter (both follow its principle, flag in PR):** admin move preserves `pending` instead of silently confirming (Task 3); stale `organizer.py` comment removed (Task 5).
