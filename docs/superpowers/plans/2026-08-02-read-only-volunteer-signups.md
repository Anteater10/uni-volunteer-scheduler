# Read-Only Volunteer Signups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all volunteer self-service schedule mutation (cancel, swap) and all automatic waitlist promotion; the manage page becomes a read-only view with reminder preferences and an "email the organizers" notice.

**Architecture:** Pure subtraction on the signup lifecycle: two public endpoints deleted, seven auto-promotion call sites removed, then the now-orphaned `promote_waitlist_fifo` deleted. One small addition: `SiteSettings.contact_email`, surfaced in the public manage payload and email copy. Staff tooling (cancel, swap/move, manual promote with 3-day confirm) is untouched.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Postgres 16 + Celery (backend), React 19 + Vite + vitest (frontend), pytest in docker.

**Spec:** `docs/superpowers/specs/2026-08-02-read-only-volunteer-signups-design.md`

## Global Constraints

- **Backend tests run in docker** (Postgres/Redis are not on localhost). Full suite:
  ```bash
  docker run --rm --network uni-volunteer-scheduler_default \
    -v $PWD/backend:/app -w /app \
    -e TEST_DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/test_uvs" \
    uni-volunteer-scheduler-backend sh -c "pytest -q"
  ```
  Single file: same command with `sh -c "pytest tests/<file>.py -q"`. Referred to below as **`docker-pytest <args>`**.
- Frontend tests: `cd frontend && npm run test -- --run` (single file: append the path).
- **Alembic revision IDs use descriptive slugs**, e.g. `0036_add_site_settings_contact_email`. Current head: `0035_add_promotion_confirm_purpose`.
- **Commit messages:** `<type>: <description>` (feat/fix/refactor/docs/test/chore). **No AI attribution of any kind.**
- Keep staff behavior intact: admin/organizer cancel, staff swap, manual promote (→ pending + 3-day confirm email), waitlist reorder, admin move.
- Fallback contact copy when `contact_email` is unset/empty: **"reply to this email"** (emails) / **"reply to your confirmation email"** (manage page).
- Frontend user-facing spelling is American ("canceled") in toasts; existing copy conventions apply.
- Do not commit `CLAUDE.md` (has unrelated local edits) or `.claude/`.

---

### Task 1: `SiteSettings.contact_email` (model, migration, schemas, endpoints, manage payload)

**Files:**
- Modify: `backend/app/models.py` (SiteSettings, ~line 508)
- Create: `backend/alembic/versions/0036_add_site_settings_contact_email.py`
- Modify: `backend/app/schemas.py` (SiteSettingsRead/Update ~line 437; TokenedManageRead — find with `grep -n "class TokenedManageRead" backend/app/schemas.py`)
- Modify: `backend/app/routers/admin.py:2510-2544` (update_site_settings)
- Modify: `backend/app/routers/public/signups.py:189-195` (manage response)
- Test: `backend/tests/test_site_settings_endpoints.py`, `backend/tests/test_public_signups.py`

**Interfaces:**
- Produces: `models.SiteSettings.contact_email: str | None`; `SiteSettingsRead.contact_email`, `SiteSettingsUpdate.contact_email`; `TokenedManageRead.contact_email: Optional[str]` (used by Task 8 emails and Task 9 frontend).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_site_settings_endpoints.py` (match the file's existing fixture style — it uses `client, db_session` with an admin auth helper; copy the auth pattern from `test_admin_can_toggle_show_audit_logs_tab` at line 45):

```python
def test_contact_email_round_trip(client, db_session):
    # copy the admin-auth setup from test_admin_can_toggle_show_audit_logs_tab
    r = client.get("/api/v1/admin/site-settings", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["contact_email"] is None

    r = client.patch(
        "/api/v1/admin/site-settings",
        json={"contact_email": "scitrek@ucsb.edu"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["contact_email"] == "scitrek@ucsb.edu"

    # partial patch of another field leaves it alone
    r = client.patch(
        "/api/v1/admin/site-settings",
        json={"show_audit_logs_tab": True},
        headers=admin_headers,
    )
    assert r.json()["contact_email"] == "scitrek@ucsb.edu"
```

Append to `backend/tests/test_public_signups.py` inside `class TestManageSignups` (reuse the signup/token setup from `test_manage_returns_signups_for_volunteer` at line 516):

```python
    def test_manage_includes_contact_email(self, client, db_session, monkeypatch):
        # setup identical to test_manage_returns_signups_for_volunteer,
        # plus: set the site contact before the manage call
        from app.services.settings_service import get_app_settings
        get_app_settings(db_session).contact_email = "scitrek@ucsb.edu"
        db_session.commit()
        resp = client.get("/api/v1/public/signups/manage", params={"token": raw_token})
        assert resp.status_code == 200
        assert resp.json()["contact_email"] == "scitrek@ucsb.edu"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker-pytest tests/test_site_settings_endpoints.py tests/test_public_signups.py -q`
Expected: FAIL — `KeyError: 'contact_email'` / field missing from response.

- [ ] **Step 3: Implement**

`backend/app/models.py`, inside `SiteSettings` after `show_audit_logs_tab` (line 508-510):

```python
    # 2026-08-02 read-only signups: the address volunteers are told to email
    # for any schedule change. NULL/empty → copy falls back to "reply to
    # this email".
    contact_email = Column(String(255), nullable=True)
```

Create `backend/alembic/versions/0036_add_site_settings_contact_email.py`:

```python
"""Add site_settings.contact_email.

2026-08-02 read-only volunteer signups: schedule changes are coordinated
with the SciTrek organizers by email, so the address is admin-editable
site configuration surfaced in email copy and the public manage page.

Revision ID: 0036_add_site_settings_contact_email
Revises: 0035_add_promotion_confirm_purpose
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_add_site_settings_contact_email"
down_revision = "0035_add_promotion_confirm_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("contact_email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "contact_email")
```

`backend/app/schemas.py` — add to `SiteSettingsRead` (line 437) and `SiteSettingsUpdate` (line 446):

```python
    contact_email: Optional[str] = None
```

Find `class TokenedManageRead` (`grep -n "class TokenedManageRead" backend/app/schemas.py`) and add:

```python
    contact_email: Optional[str] = None
```

`backend/app/routers/admin.py` `update_site_settings` — after the `show_audit_logs_tab` branch (line 2530-2532):

```python
    if payload.contact_email is not None:
        changes["contact_email"] = payload.contact_email
        row.contact_email = payload.contact_email
```

`backend/app/routers/public/signups.py` `manage_signups` — the return at line 189 becomes:

```python
    from ...services.settings_service import get_app_settings

    return schemas.TokenedManageRead(
        volunteer_id=token_row.volunteer_id,
        volunteer_first_name=volunteer.first_name,
        volunteer_last_name=volunteer.last_name,
        event_id=event_id,
        signups=signup_reads,
        contact_email=(get_app_settings(db).contact_email or None),
    )
```

(Put the import at the top of the file with the other `...services` imports, not inline.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker-pytest tests/test_site_settings_endpoints.py tests/test_public_signups.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/0036_add_site_settings_contact_email.py \
  backend/app/schemas.py backend/app/routers/admin.py backend/app/routers/public/signups.py \
  backend/tests/test_site_settings_endpoints.py backend/tests/test_public_signups.py
git commit -m "feat: add site_settings.contact_email, expose in manage payload"
```

---

### Task 2: Delete the public swap endpoint and participant swap semantics

**Files:**
- Modify: `backend/app/routers/public/signups.py:198-246` (delete `swap_signup_public`)
- Modify: `backend/app/services/swap_service.py` (drop `actor_kind`, participant branches)
- Modify: `backend/app/routers/signups.py:202-234` (staff caller signature)
- Test: `backend/tests/test_manage_token_semantics.py`, `backend/tests/test_swap_service.py`

**Interfaces:**
- Produces: `swap_signup(db, *, signup_id, target_slot_id, actor, actor_label)` — staff-only; waitlisted-source swaps always route through `mark_promoted_pending`. Task 5 modifies this same function's freed-seat behavior; Task 5's implementer should expect the post-Task-2 shape.

- [ ] **Step 1: Update tests to the new contract (they fail first)**

In `backend/tests/test_manage_token_semantics.py`:
- Delete `test_swap_returns_200_and_moves_slot` (line 71), `test_participant_swap_of_waitlisted_signup_stays_confirmed` (172), `test_participant_swap_of_cancelled_signup_via_live_manage_link_is_refused` (256), `test_participant_swap_of_attended_signup_via_live_manage_link_is_refused` (335).
- Add inside `TestExpiredTokenStillManages` (reusing its setup, which already builds a signup + live token):

```python
    def test_swap_route_is_gone(self, client, db_session):
        # self-service swap was removed 2026-08-02 (read-only signups)
        resp = client.post(
            f"/api/v1/public/signups/{self.signup_id}/swap",
            params={"token": self.raw_token},
            json={"target_slot_id": str(self.other_slot_id)},
        )
        assert resp.status_code == 404
```

(Adapt attribute names to the class's actual fixture variables — read the class setup at lines 20-70 first.)

In `backend/tests/test_swap_service.py`:
- Delete the participant variants: `test_participant_swap_of_waitlisted_stays_confirmed` (368), `test_participant_swap_of_cancelled_signup_is_refused` (446), `test_participant_swap_of_no_show_signup_is_refused` (487), `test_participant_swap_of_attended_signup_is_refused` (553).
- In every remaining call to `swap_signup(...)`, delete the `actor_kind="staff"` argument (the parameter is going away).

- [ ] **Step 2: Run to verify failures**

Run: `docker-pytest tests/test_manage_token_semantics.py tests/test_swap_service.py -q`
Expected: FAIL — the new route test gets 200/4xx from the still-live endpoint; swap tests error on the removed kwarg only after Step 3, so at this point expect the route test failing.

- [ ] **Step 3: Implement**

1. `backend/app/routers/public/signups.py`: delete the whole `swap_signup_public` function (lines 198-246) and the now-unused import `from ...services.swap_service import swap_signup` (line 28). Also delete `swap` from the module docstring route list.
2. `backend/app/services/swap_service.py`: remove the `actor_kind` parameter from `swap_signup`'s signature and docstring. Replace the three-way branch (lines 253-282) with:

```python
    signup.slot_id = target_slot.id
    self_promotion: Optional[PromotionResult] = None
    if holds_capacity:
        if source_slot.current_count > 0:
            source_slot.current_count -= 1
        target_slot.current_count += 1
    else:
        # Only reachable for a waitlisted source now (cancelled/no_show were
        # refused above; holds_capacity covers the rest). A staff swap of a
        # waitlisted signup is a promotion — route through the same choke
        # point as every other staff promotion (pending + confirm email).
        # The slot_id repoint above happens first so mark_promoted_pending's
        # ended-slot guard judges the seat actually being offered.
        try:
            self_promotion = mark_promoted_pending(db, signup)
        except SlotEndedError as exc:
            raise HTTPException(
                status_code=422, detail={"code": exc.code, "message": str(exc)}
            ) from exc
        target_slot.current_count += 1
```

Also delete any earlier `actor_kind == "participant"`-gated guards in the same file (search: `grep -n "actor_kind\|participant" backend/app/services/swap_service.py`) — participant-only refusal branches (e.g. the participant-attended 422 at ~line 205) must be re-checked: the *staff*-attended swap stays allowed (`test_staff_swap_of_attended_signup_succeeds`), so a guard that refused only participants is deleted outright.
3. `backend/app/routers/signups.py:219-226`: drop `actor_kind="staff"` from the `_swap_signup(...)` call.

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_manage_token_semantics.py tests/test_swap_service.py tests/test_signups_router_full.py -q`
Expected: PASS. If `test_signups_router_full.py` passes `actor_kind` anywhere, apply the same kwarg deletion there.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/public/signups.py backend/app/services/swap_service.py \
  backend/app/routers/signups.py backend/tests/test_manage_token_semantics.py \
  backend/tests/test_swap_service.py
git commit -m "feat: remove volunteer self-swap endpoint and participant swap semantics"
```

---

### Task 3: Delete the public cancel endpoint

**Files:**
- Modify: `backend/app/routers/public/signups.py:249-350` (delete `cancel_signup`)
- Test: `backend/tests/test_public_signups.py`, `backend/tests/test_manage_token_semantics.py`, `backend/tests/test_promotion_consent.py`, `backend/tests/test_waitlist_service.py`, `backend/tests/test_waitlist_cancellation_copy.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `/public/signups/{id}` has no DELETE route (404). Manage/confirm/preferences routes unchanged.

- [ ] **Step 1: Update tests (fail first)**

- `backend/tests/test_public_signups.py`: delete the whole `TestCancelSignup` class (lines 541-729) and the module-level `test_public_cancel_sends_waitlist_promote_email` (794) and `test_public_cancel_promotes_to_pending_with_confirm_email` (842). Add a new class next to `TestManageSignups`:

```python
class TestCancelRouteRemoved:
    """2026-08-02 read-only signups: volunteers cannot cancel themselves."""

    def test_delete_route_is_gone(self, client, db_session, monkeypatch):
        # setup copied from TestManageSignups.test_manage_returns_signups_for_volunteer
        # (creates a signup + raw manage token)
        resp = client.delete(
            f"/api/v1/public/signups/{signup_id}", params={"token": raw_token}
        )
        assert resp.status_code == 404
        db_session.expire_all()
        assert db_session.get(models.Signup, signup_id).status != models.SignupStatus.cancelled
```

- `backend/tests/test_manage_token_semantics.py`: delete `test_cancel_returns_200_and_cancels` (105), `test_participant_cancel_of_attended_signup_via_live_manage_link_is_refused` (418), `test_participant_cancel_of_no_show_signup_via_live_manage_link_is_refused` (442).
- `backend/tests/test_promotion_consent.py`: in `TestPromotionTokenStillManages`, delete `test_cancel_accepts_promotion_token` (311); keep the manage + preferences tests. In `TestEndedSlotGuard`, delete `test_public_cancel_does_not_promote_onto_ended_slot` (680).
- `backend/tests/test_waitlist_service.py`: delete `test_public_cancel_promotes_oldest_waitlisted` (183).
- `backend/tests/test_waitlist_cancellation_copy.py`: this file tests cancellation email copy through the public endpoint — read it; rewrite its calls to go through the admin cancel endpoint (`POST /api/v1/admin/signups/{id}/cancel` with admin auth) so the copy coverage survives, since staff cancels still send these emails.

- [ ] **Step 2: Run to verify the new test fails**

Run: `docker-pytest tests/test_public_signups.py::TestCancelRouteRemoved -q`
Expected: FAIL — DELETE currently returns 200.

- [ ] **Step 3: Implement**

In `backend/app/routers/public/signups.py`:
- Delete the whole `cancel_signup` function (lines 249-350).
- Delete now-unused imports: `send_email_notification`, `send_waitlist_promotion_email` (line 14), `ensure_signup_cancellable` (line 25), `promote_waitlist_fifo` (line 30). Keep `compute_waitlist_position` (manage uses it) and `consume_token`/`zero_confirm_reason` (confirm uses them).
- Update the module docstring (lines 1-7): drop the DELETE line, note the page is view-only.

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_public_signups.py tests/test_manage_token_semantics.py tests/test_promotion_consent.py tests/test_waitlist_service.py tests/test_waitlist_cancellation_copy.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/public/signups.py backend/tests/
git commit -m "feat: remove volunteer self-cancel endpoint"
```

---

### Task 4: Staff/admin cancels stop auto-promoting

**Files:**
- Modify: `backend/app/routers/signups.py:35-136` (`cancel_signup`)
- Modify: `backend/app/routers/admin.py:645-721` (`admin_cancel_signup`)
- Test: `backend/tests/test_signups.py`, `backend/tests/test_signups_router_full.py`, `backend/tests/test_admin.py`

**Interfaces:**
- Produces: both cancel endpoints free the seat and stop; response unchanged (SignupRead), cancellation email unchanged. No promotion emails from cancels.

- [ ] **Step 1: Find and update promotion assertions (fail first)**

Run: `grep -rn "promote\|promotion\|waitlist" backend/tests/test_signups.py backend/tests/test_signups_router_full.py backend/tests/test_admin.py`

For each match that asserts a cancel *causes* promotion (waitlisted signup flips to pending, promotion email enqueued, `current_count` refilled): invert it to assert the waitlisted signup **stays waitlisted**, the slot's `current_count` **drops by one and stays down**, and **no** `send_waitlist_promotion_email` is enqueued. Matches about manual promote endpoints stay untouched. Add this test to `backend/tests/test_admin.py` (setup style copied from that file's existing admin-cancel test — find it in the grep output):

```python
def test_admin_cancel_leaves_waitlist_untouched(client, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.admin.send_waitlist_promotion_email",
        types.SimpleNamespace(delay=lambda **kw: sent.append(kw)),
    )
    # seed: slot capacity 1, one confirmed signup, one waitlisted signup
    # (copy the seeding helper used by the existing admin cancel test)
    resp = client.post(
        f"/api/v1/admin/signups/{confirmed_signup_id}/cancel", headers=admin_headers
    )
    assert resp.status_code == 200
    db_session.expire_all()
    waitlisted = db_session.get(models.Signup, waitlisted_signup_id)
    assert waitlisted.status == models.SignupStatus.waitlisted
    slot = db_session.get(models.Slot, slot_id)
    assert slot.current_count == 0
    assert sent == []
```

Write the equivalent test for the authed endpoint in `backend/tests/test_signups.py` (`POST /api/v1/signups/{id}/cancel`, monkeypatch target `app.routers.signups.send_waitlist_promotion_email`).

- [ ] **Step 2: Run to verify failures**

Run: `docker-pytest tests/test_signups.py tests/test_admin.py tests/test_signups_router_full.py -q`
Expected: FAIL — cancels currently promote.

- [ ] **Step 3: Implement**

`backend/app/routers/signups.py` `cancel_signup`:
- Delete the promotion loop and its comment (lines 102-110), the `promotion_email_kwargs` capture (115-116), and the post-commit promotion email loop + comment (131-134).
- Delete the now-unused import `from ..signup_service import PromotionResult, promote_waitlist_fifo` (line 14) and `send_waitlist_promotion_email` from line 9 **only if** no other function in the file still uses it (the swap endpoint does — check first; keep what's used).
- Update the endpoint docstring: replace "Promote waitlisted FIFO" with "Never promotes — the waitlist only moves by explicit staff promotion (2026-08-02)."

`backend/app/routers/admin.py` `admin_cancel_signup`:
- Delete `promotions = _promote_waitlist_fifo(db, slot)` (line 697), the `promotion_email_kwargs` capture (700-701), and the post-commit promotion loop + comment (716-719).

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_signups.py tests/test_admin.py tests/test_signups_router_full.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/signups.py backend/app/routers/admin.py backend/tests/
git commit -m "feat: staff cancels no longer auto-promote the waitlist"
```

---

### Task 5: Swap-freed seats stop auto-promoting

**Files:**
- Modify: `backend/app/services/swap_service.py:286-297`
- Test: `backend/tests/test_swap_service.py`

**Interfaces:**
- Consumes: Task 2's staff-only `swap_signup`.
- Produces: `SwapResult.promotion` is non-None **only** for the waitlisted-source self-promotion (staff seating a waitlisted volunteer). Freed source seats stay open.

- [ ] **Step 1: Update tests (fail first)**

In `backend/tests/test_swap_service.py`:
- `test_swap_auto_promotes_source_waitlist` (127) → rename `test_swap_leaves_source_waitlist_untouched`; assert the waitlisted signup stays `waitlisted` and `result.promotion is None`.
- `test_swap_auto_promote_restores_source_count` (157) → rename `test_swap_frees_source_count_permanently`; assert source `current_count` decremented and NOT restored.
- `test_swap_returns_promotion_result_for_freed_seat` (275) → delete (contract gone).
- `test_swap_no_waitlist_leaves_source_count_freed` (188) and `test_swap_without_waitlist_has_no_promotion` (309) — keep; they already describe the new world.
- `test_staff_swap_of_waitlisted_lands_pending_with_promotion` (345) and `test_staff_swap_of_waitlisted_onto_ended_slot_is_rejected` (388) — keep unchanged (explicit staff promotion stays).

- [ ] **Step 2: Run to verify failures**

Run: `docker-pytest tests/test_swap_service.py -q`
Expected: FAIL on the two renamed tests.

- [ ] **Step 3: Implement**

In `swap_service.py`, replace the freed-seat block (lines 286-297, the `promotion: Optional[PromotionResult] = self_promotion` / `if holds_capacity:` chunk) with:

```python
    # 2026-08-02 read-only signups: a freed source seat stays open — the
    # waitlist only moves by explicit staff promotion. The only promotion a
    # swap can produce is the waitlisted-source self-promotion above.
    promotion: Optional[PromotionResult] = self_promotion
```

Remove the now-unused `promote_waitlist_fifo` import (keep `mark_promoted_pending`).

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_swap_service.py tests/test_signups_router_full.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/swap_service.py backend/tests/test_swap_service.py
git commit -m "feat: swap-freed seats no longer auto-promote the waitlist"
```

---

### Task 6: Capacity raises stop auto-promoting

**Files:**
- Modify: `backend/app/routers/slots.py:133-235` (`update_slot`)
- Test: `backend/tests/test_slot_capacity_raise_promotes.py` → rename `backend/tests/test_slot_capacity_raise_no_promote.py`

**Interfaces:**
- Produces: PATCH `/slots/{id}` capacity raise widens `capacity` only; `current_count` and waitlisted rows untouched; no promotion emails.

- [ ] **Step 1: Rewrite the test file (fails first)**

`git mv backend/tests/test_slot_capacity_raise_promotes.py backend/tests/test_slot_capacity_raise_no_promote.py`, keep its fixtures/seeding, and replace the five tests with (reusing the file's existing seed helpers and monkeypatch target `app.routers.slots.send_waitlist_promotion_email` — confirm the target with `grep -n "send_waitlist_promotion_email" backend/app/routers/slots.py`):

```python
def test_raising_capacity_promotes_nobody(client, db_session, monkeypatch):
    # seed: slot capacity 1, 1 confirmed, 2 waitlisted (existing helper)
    resp = client.patch(f"/api/v1/slots/{slot_id}", json={"capacity": 3}, headers=staff_headers)
    assert resp.status_code == 200
    db_session.expire_all()
    slot = db_session.get(models.Slot, slot_id)
    assert slot.capacity == 3
    assert slot.current_count == 1          # unchanged
    statuses = [s.status for s in slot.signups]
    assert statuses.count(models.SignupStatus.waitlisted) == 2
    assert sent == []                        # no promotion emails


def test_lowering_capacity_still_does_not_promote(client, db_session, monkeypatch):
    # keep the existing test body from test_lowering_capacity_does_not_promote
    ...
```

Delete `test_raising_capacity_promotes_oldest_waitlisted_to_pending`, `test_raising_capacity_enqueues_promotion_email`, `test_raising_capacity_beyond_waitlist_size_promotes_all`, `test_raising_capacity_on_ended_slot_does_not_promote` (moot — nothing promotes anywhere now).

- [ ] **Step 2: Run to verify failure**

Run: `docker-pytest tests/test_slot_capacity_raise_no_promote.py -q`
Expected: FAIL — raise currently promotes.

- [ ] **Step 3: Implement**

In `backend/app/routers/slots.py` `update_slot`: delete the promotion block (lines 185-197: comment + `promotions: list = []` + the `if "capacity" in data ...` loop) and every later use of `promotions` (post-commit promotion email dispatch — find with `grep -n "promotions\|promotion" backend/app/routers/slots.py`). Keep the FOR UPDATE lock (concurrent signup/cancel still mutate `current_count`) but update its comment (lines 140-142) to say the lock serializes counter updates, not promotions. Remove `promote_waitlist_fifo` from the imports.

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_slot_capacity_raise_no_promote.py tests/test_generate_slots.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/slots.py backend/tests/
git commit -m "feat: capacity raises no longer auto-promote the waitlist"
```

---

### Task 7: Hourly reaper stops chain-promoting; delete `promote_waitlist_fifo`

**Files:**
- Modify: `backend/app/celery_app.py:756-805` (`expire_pending_signups`)
- Modify: `backend/app/signup_service.py:100-145` (delete `promote_waitlist_fifo`), docstring at 27-55
- Modify: `backend/app/routers/admin.py:58-72` (delete `_promote_waitlist_fifo` wrapper)
- Test: `backend/tests/test_expired_pending_cleanup.py`, `backend/tests/test_promotion_consent.py`, `backend/tests/test_promotion_pending.py`, `backend/tests/test_celery_app_full.py`

**Interfaces:**
- Produces: `signup_service` exports `mark_promoted_pending` + `PromotionResult` only. `expire_pending_signups` deletes expired pendings, cancels stale waitlisted rows, sweeps stale tokens — promotes nothing.

- [ ] **Step 1: Update tests (fail first)**

- `test_expired_pending_cleanup.py`: `test_reap_chains_promotion_with_email` (372) → rename `test_reap_frees_seat_without_promotion`; assert expired pending deleted, `current_count` decremented, waitlisted row still `waitlisted`, no promotion email. Delete `test_chained_promotion_token_is_three_days` (434), `test_chain_does_not_promote_into_ended_event` (520), and the whole `TestPromotionsCommitAndEnqueuePerSignup` class (940-1018). Everything in `TestStaleTokenCleanup` and `TestStaleWaitlistedRowsCancelled` stays.
- `test_promotion_consent.py`: `test_expired_promotion_pending_is_reaped_and_chain_promotes` (328) → rename `test_expired_promotion_pending_is_reaped_seat_stays_open`; same inversion. `test_promote_waitlist_fifo_*` tests in `TestEndedSlotGuard` (644, 655) → delete. Keep `test_mark_promoted_pending_refuses_ended_slot` and all manual-promote guards.
- `test_promotion_pending.py`: delete `class TestPromoteWaitlistFifo` (106-125). Keep `TestMarkPromotedPending` and `TestPromotionTTL`.
- `test_waitlist_service.py` and `test_celery_app_full.py`: `grep -rn "promote_waitlist_fifo" backend/tests/` and clean any remaining references the previous tasks didn't own.

- [ ] **Step 2: Run to verify failures**

Run: `docker-pytest tests/test_expired_pending_cleanup.py tests/test_promotion_consent.py tests/test_promotion_pending.py -q`
Expected: FAIL on the renamed/inverted tests.

- [ ] **Step 3: Implement**

1. `backend/app/celery_app.py`: in `expire_pending_signups`, delete the whole chain-promotion block (lines 772-799: the re-lock comment through the `send_waitlist_promotion_email.delay(**promo.email_kwargs)` loop) and change the log line (801-805) to `logger.info("expired_pending_signups_cleaned count=%d", count)`. Delete `affected_slot_ids` bookkeeping (757, 761-762) — it only fed the promotion loop. Remove the `promote_waitlist_fifo` import if the module has one (`grep -n "promote_waitlist_fifo" backend/app/celery_app.py`).
2. `backend/app/signup_service.py`: delete `promote_waitlist_fifo` (lines 100-145). Update the module docstring (lines 1-5) and `mark_promoted_pending`'s docstring: remove references to `promote_waitlist_fifo`; the callers are now `waitlist_service.manual_promote`, the admin move, and the staff swap of a waitlisted signup.
3. `backend/app/routers/admin.py`: delete `_promote_waitlist_fifo` (lines 58-72) and remove `promote_waitlist_fifo` from the file's imports (`grep -n "promote_waitlist_fifo" backend/app/routers/admin.py` must come back empty).
4. Repo-wide check: `grep -rn "promote_waitlist_fifo" backend/app/` must return nothing.

- [ ] **Step 4: Run the full backend suite**

Run: `docker-pytest -q` (full suite — this task ends the backend-behavior sequence)
Expected: PASS, zero failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/celery_app.py backend/app/signup_service.py backend/app/routers/admin.py backend/tests/
git commit -m "feat: delete FIFO auto-promotion — waitlist moves only by staff promote"
```

---

### Task 8: Email copy — view-only links, "email the organizers"

**Files:**
- Modify: `backend/app/emails.py` (add `_contact_instruction`; edit `send_reschedule`, `send_reminder_kickoff`, `send_reminder_pre_24h`, `send_reminder_pre_2h`, `build_signup_confirmation_email`, `build_waitlist_promotion_email`)
- Modify: `backend/app/email_templates/signup_confirm.html`, `waitlist_promotion.html`, `reschedule.html`
- Create: `backend/tests/test_email_contact_copy.py`

**Interfaces:**
- Consumes: `SiteSettings.contact_email` (Task 1).
- Produces: `_contact_instruction(db_obj) -> str` in `emails.py` — returns `"email the SciTrek organizers at <addr>"` or `"reply to this email"`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_email_contact_copy.py` (build a volunteer + signup with the factories used in `test_promotion_email.py` — copy its seeding):

```python
"""2026-08-02 read-only signups: no email may advertise self-service
cancel/swap; change instructions point at the site contact address."""
import pytest

from app import models
from app.emails import (
    _contact_instruction,
    build_signup_confirmation_email,
    build_waitlist_promotion_email,
    send_reminder_pre_24h,
    send_reschedule,
)
from app.services.settings_service import get_app_settings


def test_contact_instruction_uses_site_setting(db_session, seeded_signup):
    get_app_settings(db_session).contact_email = "scitrek@ucsb.edu"
    db_session.flush()
    assert _contact_instruction(seeded_signup) == (
        "email the SciTrek organizers at scitrek@ucsb.edu"
    )


def test_contact_instruction_fallback_when_unset(db_session, seeded_signup):
    assert _contact_instruction(seeded_signup) == "reply to this email"


def test_no_template_advertises_self_cancel(db_session, seeded_signup, seeded_event):
    subject, html = build_signup_confirmation_email(
        seeded_signup.volunteer, [seeded_signup], "tok" * 8, seeded_event
    )
    assert "cancelling your signups" not in html
    assert "cancel" not in html.lower() or "email" in html.lower()

    subject, html = build_waitlist_promotion_email(
        seeded_signup.volunteer, seeded_signup, "tok" * 8, seeded_event
    )
    assert "Use the same link to cancel" not in html

    body = send_reminder_pre_24h(seeded_signup)
    assert "please cancel" not in body["text_body"]

    body = send_reschedule(seeded_signup)
    assert "please cancel your signup" not in body["text_body"]
```

(`seeded_signup`/`seeded_event` are whatever fixture names the copied seeding produces — define them as local fixtures at the top of this file.)

- [ ] **Step 2: Run to verify failure**

Run: `docker-pytest tests/test_email_contact_copy.py -q`
Expected: FAIL — `_contact_instruction` doesn't exist.

- [ ] **Step 3: Implement**

Add to `backend/app/emails.py` (near `_manage_url_for_signup`, line 235):

```python
def _contact_instruction(db_obj) -> str:
    """How a volunteer reaches the organizers, from site settings.

    2026-08-02 read-only signups: volunteers cannot change their own
    schedule, so every email points changes at the organizers. ``db_obj``
    is any session-attached ORM row (signup/volunteer); a detached row
    falls back to the reply-to instruction.
    """
    from sqlalchemy.orm import object_session

    db = object_session(db_obj)
    contact = None
    if db is not None:
        from .services.settings_service import get_app_settings

        contact = (get_app_settings(db).contact_email or "").strip() or None
    return (
        f"email the SciTrek organizers at {contact}" if contact else "reply to this email"
    )
```

Copy edits (exact replacements):
- `send_reschedule` text (line 223): `"If you can no longer attend, please cancel your signup."` → `f"If you can no longer attend, please {_contact_instruction(signup)} so the organizers can update the schedule."`
- `send_reminder_pre_24h` text (line 318): `"See you there! If you can no longer attend, please cancel so the spot opens up.\n\n"` → `f"See you there! If you can no longer attend, please {_contact_instruction(signup)}.\n\n"`
- `send_reminder_kickoff` (line 291-292) and `send_reminder_pre_2h` (line 344): change `"Manage your signups: "` to `"View your signups: "`; the kickoff's reminders-off sentence stays (preferences remain self-service).
- `build_signup_confirmation_email`: pass `contact_instruction=_contact_instruction(volunteer)` into `_render_html` and in `signup_confirm.html` replace line 12 with:

```html
<p style="margin:0 0 12px;">Please confirm within 14 days. The same link keeps working after that for viewing your signups. Need to change or cancel? Please $contact_instruction.</p>
```

- `build_waitlist_promotion_email`: pass `contact_instruction=_contact_instruction(signup)` and in `waitlist_promotion.html` replace line 12 with:

```html
<p style="margin:0 0 12px;">Can&#39;t make it? Just ignore this email — the offer expires on its own after 3 days. For any other change, please $contact_instruction. The link keeps working for viewing your signups after you confirm.</p>
```

- `reschedule.html`: find the cancel sentence (`grep -n cancel backend/app/email_templates/reschedule.html`) and replace with `If you can no longer attend, please $contact_instruction.`, passing `contact_instruction=_contact_instruction(signup)` from `send_reschedule`'s `_render_html` call.

- [ ] **Step 4: Run tests**

Run: `docker-pytest tests/test_email_contact_copy.py tests/test_promotion_email.py tests/test_expired_pending_cleanup.py -q`
Expected: PASS (fix any template-variable assertion fallout in existing email tests — the variable set changed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/emails.py backend/app/email_templates/ backend/tests/test_email_contact_copy.py backend/tests/
git commit -m "feat: email copy points schedule changes at the organizer contact"
```

---

### Task 9: Frontend — read-only ManageSignupsPage + api client

**Files:**
- Modify: `frontend/src/lib/api.js:425-437` (delete `publicCancelSignup`, `publicSwapSignup`), `:608-611` (delete `cancelSignup`, `swapSignup` exports)
- Modify: `frontend/src/pages/public/ManageSignupsPage.jsx` (rewrite)
- Test: `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`

**Interfaces:**
- Consumes: `data.contact_email` from the manage payload (Task 1).
- Produces: `api.public` has no `cancelSignup`/`swapSignup`. Page renders `data-testid="contact-notice"`.

- [ ] **Step 1: Update tests (fail first)**

Open `frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`; delete every test that clicks Cancel/Move/Cancel-all or mocks `api.public.cancelSignup`/`swapSignup` (find them: `grep -n "cancelSignup\|swapSignup\|Cancel\|Move" frontend/src/pages/__tests__/ManageSignupsPage.test.jsx`). Keep list-rendering, waitlist-badge, empty-state, and error-state tests. Add (matching the file's existing render/mock helpers):

```jsx
it("renders read-only: no cancel or move controls", async () => {
  renderPage(); // existing helper with mocked getManageSignups
  await screen.findByText(/Confirmed|Pending/);
  expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  expect(screen.queryByRole("button", { name: /move/i })).toBeNull();
});

it("shows the organizer contact notice with the configured address", async () => {
  mockManageResponse({ contact_email: "scitrek@ucsb.edu" }); // extend existing mock
  renderPage();
  const notice = await screen.findByTestId("contact-notice");
  expect(notice).toHaveTextContent("scitrek@ucsb.edu");
});

it("contact notice falls back when no address configured", async () => {
  mockManageResponse({ contact_email: null });
  renderPage();
  const notice = await screen.findByTestId("contact-notice");
  expect(notice).toHaveTextContent(/reply to your confirmation email/i);
});
```

- [ ] **Step 2: Run to verify failures**

Run: `cd frontend && npm run test -- --run src/pages/__tests__/ManageSignupsPage.test.jsx`
Expected: FAIL — buttons still render, notice missing.

- [ ] **Step 3: Rewrite the page**

Rewrite `ManageSignupsPage.jsx`:
- Delete state: `cancelTarget`, `canceling`, `cancelAllOpen`, `cancelingAll`, `swapSource`, `swapping`, `eventSlots`, `loadingSlots` (lines 65-73); handlers `handleCancelConfirm`, `openSwap`, `handleSwapConfirm`, `handleCancelAll` (139-216); the Move/Cancel buttons column (318-338); the cancel-all block (343-353); all three Modals (358-468); `activeCount` (237); unused imports (`Modal`, `toast`).
- Hero copy (line 256): `View, move, or cancel your volunteer shifts. Times shown in Pacific Time.` → `View your volunteer shifts. Times shown in Pacific Time.` Kicker (248): `Manage signups` → `Your signups`.
- Insert the notice card between the signup list and `<ReminderPreferencesCard />`:

```jsx
      <Card className="p-4" data-testid="contact-notice">
        <p className="text-sm font-medium text-gray-900">
          Need to change or cancel a signup?
        </p>
        <p className="mt-1 text-sm text-gray-600">
          Schedule changes are coordinated with the SciTrek organizers —{" "}
          {data?.contact_email ? (
            <>
              email{" "}
              <a
                className="font-medium text-blue-700 underline"
                href={`mailto:${data.contact_email}`}
              >
                {data.contact_email}
              </a>{" "}
              and they&apos;ll take care of it.
            </>
          ) : (
            <>reply to your confirmation email and they&apos;ll take care of it.</>
          )}
        </p>
      </Card>
```

- File header comment (lines 1-17): rewrite to say the page is a read-only view + reminder preferences (2026-08-02 read-only signups).

`frontend/src/lib/api.js`: delete `publicCancelSignup` (425-427), `publicSwapSignup` + comment (429-437), and the `cancelSignup`/`swapSignup` entries (+ Phase 29 comment) at 608-611.

- [ ] **Step 4: Run tests**

Run: `cd frontend && npm run test -- --run`
Expected: PASS. Fix any other suite that referenced `api.public.cancelSignup`/`swapSignup` (find first: `grep -rn "cancelSignup\|swapSignup" frontend/src`— expected hits only in tests you already edited).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.js frontend/src/pages/public/ManageSignupsPage.jsx frontend/src/pages/__tests__/ManageSignupsPage.test.jsx
git commit -m "feat: manage page is read-only with organizer contact notice"
```

---

### Task 10: Frontend — remaining copy + admin contact-email setting

**Files:**
- Modify: `frontend/src/pages/public/ConfirmSignupPage.jsx:125`
- Modify: `frontend/src/pages/public/EventDetailPage.jsx:1477`
- Modify: `frontend/src/components/admin/SiteSettingsCard.jsx`
- Test: `frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx`, `frontend/src/components/admin/__tests__/` (new `SiteSettingsCard.test.jsx` if none exists — check first)

**Interfaces:**
- Consumes: `SiteSettingsUpdate.contact_email` PATCH (Task 1) via existing `api.admin.siteSettings.update`.

- [ ] **Step 1: Failing tests**

- `ConfirmSignupPage.test.jsx`: find assertions on the success copy (`grep -n "manage or cancel" frontend/src/pages/__tests__/ConfirmSignupPage.test.jsx`) and change the expected text to the new copy below.
- Create `frontend/src/components/admin/__tests__/SiteSettingsCard.test.jsx` (mirror the mock pattern of a neighboring admin test, e.g. `EventSettingsModal.test.jsx`):

```jsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import SiteSettingsCard from "../SiteSettingsCard";
import { api } from "../../../lib/api";

vi.mock("../../../lib/api", () => ({
  api: {
    admin: {
      siteSettings: {
        get: vi.fn().mockResolvedValue({
          hide_past_events_from_public: true,
          show_audit_logs_tab: false,
          contact_email: "old@ucsb.edu",
        }),
        update: vi.fn().mockResolvedValue({ contact_email: "scitrek@ucsb.edu" }),
      },
    },
  },
}));

it("edits and saves the volunteer contact email", async () => {
  render(<SiteSettingsCard />, { wrapper: QueryWrapper }); // reuse the file-local react-query wrapper pattern
  const input = await screen.findByLabelText(/volunteer contact email/i);
  expect(input).toHaveValue("old@ucsb.edu");
  fireEvent.change(input, { target: { value: "scitrek@ucsb.edu" } });
  fireEvent.click(screen.getByRole("button", { name: /save contact/i }));
  await waitFor(() =>
    expect(api.admin.siteSettings.update).toHaveBeenCalledWith({
      contact_email: "scitrek@ucsb.edu",
    })
  );
});
```

- [ ] **Step 2: Run to verify failures**

Run: `cd frontend && npm run test -- --run src/components/admin/__tests__/SiteSettingsCard.test.jsx src/pages/__tests__/ConfirmSignupPage.test.jsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `ConfirmSignupPage.jsx:125`: `Your signup is confirmed! You can manage or cancel your signups` → `Your signup is confirmed! Here's everything you're signed up for` (keep surrounding JSX; check the full sentence with the line's context and keep it grammatical).
- `EventDetailPage.jsx:1477`: `You'll get a confirmation email with a link to manage or cancel your signups.` → `You'll get a confirmation email with a link to view your signups.` (Line 1192 "Manage my signups" link naming stays — the email link label is unchanged.)
- `SiteSettingsCard.jsx`: after the second `ToggleRow` (line 57-64), add a contact-email row; add local state:

```jsx
  const [contactDraft, setContactDraft] = React.useState(null);
  const contactValue =
    contactDraft !== null ? contactDraft : q.data?.contact_email ?? "";
```

```jsx
        <div className="text-sm text-gray-700">
          <label htmlFor="contact-email-input" className="font-medium">
            Volunteer contact email
          </label>
          <div className="text-gray-500 text-xs mt-0.5">
            Shown to volunteers as the address for schedule changes and
            cancellations. Leave blank to tell them to reply to their
            confirmation email.
          </div>
          <div className="mt-2 flex gap-2">
            <input
              id="contact-email-input"
              type="email"
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              value={contactValue}
              disabled={disabled}
              onChange={(e) => setContactDraft(e.target.value)}
              data-testid="contact-email-input"
            />
            <button
              type="button"
              className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
              disabled={disabled || contactDraft === null}
              onClick={() => {
                m.mutate({ contact_email: contactDraft ?? "" });
                setContactDraft(null);
              }}
            >
              Save contact
            </button>
          </div>
        </div>
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npm run test -- --run`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: confirm/event copy drops self-cancel; admin edits contact email"
```

---

### Task 11: Knowledge-base + docs sweep

**Files:**
- Modify (all under `docs/knowledge-base/`): `19-magic-links.md`, `10-signups-and-statuses.md`, `11-waitlist.md`, `35-cancellation-notice.md`, `02-glossary.md`, `33-volunteer-guide.md`, `29-troubleshooting.md`, `30-not-built.md`, `38-who-to-contact.md`, plus incidental mentions in `README.md`, `01-overview.md`, `06-slots.md`, `13-volunteers-and-identity.md`, `18-rosters.md`, `28-task-guides.md`
- Modify: `docs/superpowers/specs/2026-07-28-waitlist-promotion-confirmation-design.md` (status note), `docs/smoke-checklist.md`

**Interfaces:** none — prose only, but it feeds the copilot RAG corpus.

- [ ] **Step 1: Establish the new canonical statements**

Every edited doc must agree on these facts (copy verbatim where a doc needs the full statement):

> A volunteer cannot cancel or move a signup themselves. The link in their email is a read-only view of their signups plus reminder preferences. To change or cancel anything, they email the SciTrek organizers (the address configured in Site settings), and an organizer applies the change.

> The waitlist never moves on its own. Cancels, capacity raises, and the hourly cleanup free seats but promote nobody. A volunteer leaves the waitlist only when an admin or organizer promotes them — which sends the 3-day confirm email; unclaimed offers expire and the seat stays open.

- [ ] **Step 2: Per-file edits**

- `35-cancellation-notice.md` — full rewrite: cancelling is done by emailing the organizers; there is no self-service cancel; staff cancel in the app; the volunteer still receives the cancellation email as confirmation.
- `19-magic-links.md` — retitle body claims: link = confirm + view + reminder prefs; delete every cancel/swap capability claim (lines 11, 14, 28, 40, 95-97); keep the prefs-need-unexpired-link note (100-105).
- `11-waitlist.md` — rewrite promotion triggers to "manual staff promote only"; delete the volunteer-swap-lands-confirmed exception (56-61) and the hourly re-promote section (69-76); keep pending+3-day-confirm mechanics.
- `10-signups-and-statuses.md` — remove auto-promote-on-cancel (42-45), swap advice (51-56), manage-link-cancel claims (88-93).
- `02-glossary.md` — fix **Cancelled** and **Magic link** entries.
- `33-volunteer-guide.md:23` — "view, cancel, or swap their sessions" → "view their sessions; changes go through the SciTrek organizers by email".
- `38-who-to-contact.md` — replace "does not need to contact anyone to cancel, because cancelling is done through the link" with: cancelling/changing IS the one thing volunteers contact the office for.
- `29-troubleshooting.md`, `30-not-built.md`, `README.md`, `01-overview.md`, `06-slots.md`, `13-volunteers-and-identity.md`, `18-rosters.md`, `28-task-guides.md` — sweep with `grep -rn -i "cancel\|swap\|promot" docs/knowledge-base/ | grep -v cancellation-notice` and fix every claim that contradicts the canonical statements.
- `2026-07-28-waitlist-promotion-confirmation-design.md` — add under **Status**: `2026-08-02: superseded in part — self-cancel/swap and all automatic promotion removed (see 2026-08-02-read-only-volunteer-signups-design.md); the pending + 3-day confirm mechanics survive for manual staff promotion.`
- `docs/smoke-checklist.md` — replace any volunteer-cancel/swap smoke step with: manage link shows read-only signups + contact notice; admin promote sends confirm email.

- [ ] **Step 3: Verify the sweep found everything**

Run: `grep -rn -i "self-serv\|swap" docs/knowledge-base/` and `grep -rn -i "cancel" docs/knowledge-base/ | grep -i -v "email\|organizer\|office\|staff\|admin\|cancellation email\|cancelled by"`
Expected: no line claims volunteer self-service; anything left is about staff flows or the cancellation notice email.

- [ ] **Step 4: Re-ingest the copilot corpus**

Run `docker compose exec backend python -m app.corpus --help` to get the ingest subcommand (the KB README's "Where the corpus comes from" section documents this), then run the ingest and confirm it reports chunks ingested for the changed docs. If the docker service isn't running: `docker compose up -d db redis backend` first.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs: knowledge base reflects read-only signups and manual-only promotion"
```

---

### Task 12: e2e + full verification

**Files:**
- Modify: `e2e/cross-role.spec.js` (whatever scenarios exercise self-cancel/swap)
- Test: full backend + frontend + e2e suites

- [ ] **Step 1: Update the e2e spec**

Run: `grep -n -i "cancel\|swap\|manage" e2e/cross-role.spec.js`. For each volunteer-side cancel/swap interaction: rewrite the scenario so the *staff* user performs the change in the admin UI, and the volunteer-side assertion becomes: manage page shows the signup list, shows the `contact-notice` test id, and has no button matching `/cancel|move/i`. Do not delete cross-role coverage — repoint it.

- [ ] **Step 2: Run e2e**

Run: `cd e2e && npx playwright test cross-role.spec.js` (check `e2e/README` or `package.json` scripts for the exact runner/env; the stack must be up via `docker compose up -d`).
Expected: PASS across the browser projects.

- [ ] **Step 3: Full suites**

Run: `docker-pytest -q` → expected: all pass.
Run: `cd frontend && npm run test -- --run` → expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add e2e/
git commit -m "test: cross-role e2e covers read-only volunteer flow"
```

---

## Self-Review Notes

- Spec coverage: endpoints removed (T2, T3); seven promotion sites — public cancel dies with T3, staff cancel + admin cancel (T4), swap (T5), capacity raise (T6), reaper (T7), admin-move path never auto-promoted (uses `mark_promoted_pending` manually — untouched); `contact_email` (T1, T8, T9, T10); read-only page + prefs kept (T9); emails (T8); KB/docs/corpus (T11); e2e (T12).
- Manual promote endpoints and their tests (`test_waitlist_service.py` manual-promote block, `test_promotion_consent.py` guards) intentionally untouched — spec keeps that flow.
- `ensure_signup_cancellable` stays in `check_in_service.py` — staff cancels still call it.
