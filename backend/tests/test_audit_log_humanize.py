"""Phase 16 Plan 01: audit-log humanization service tests.

Covers:
- known action code → labelled verb string
- unknown action code → Title Case fallback
- None actor_id → "System"
- deleted (missing) actor → "(deleted) #xxxxxxxx"
- signup entity → "Name's signup for Title, YYYY-MM-DD"
"""
from datetime import datetime, timezone, timedelta
import uuid

import pytest

from app import models
from app.services.audit_log_humanize import humanize, ACTION_LABELS


def _make_user(db_session, name="Alice Smith", email="alice@example.com", role=models.UserRole.admin):
    user = models.User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        hashed_password=None,
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_event(db_session, owner, title="Intro Lab"):
    ev = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title=title,
        start_date=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 5, 1, 16, 0, tzinfo=timezone.utc),
    )
    db_session.add(ev)
    db_session.flush()
    return ev


def _make_volunteer(db_session, first="Bob", last="Jones", email="bob@example.com"):
    v = models.Volunteer(
        id=uuid.uuid4(),
        first_name=first,
        last_name=last,
        email=email,
    )
    db_session.add(v)
    db_session.flush()
    return v


def _make_slot(db_session, event):
    sl = models.Slot(
        id=uuid.uuid4(),
        event_id=event.id,
        start_time=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 5, 1, 16, 0, tzinfo=timezone.utc),
        capacity=10,
        current_count=0,
        slot_type=models.SlotType.PERIOD,
    )
    db_session.add(sl)
    db_session.flush()
    return sl


def _make_signup(db_session, volunteer, slot):
    s = models.Signup(
        id=uuid.uuid4(),
        volunteer_id=volunteer.id,
        slot_id=slot.id,
        status=models.SignupStatus.confirmed,
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_log(db_session, **kwargs):
    kwargs.setdefault("id", uuid.uuid4())
    kwargs.setdefault("action", "signup_cancelled")
    kwargs.setdefault("entity_type", "Signup")
    kwargs.setdefault("timestamp", datetime.now(timezone.utc))
    log = models.AuditLog(**kwargs)
    db_session.add(log)
    db_session.flush()
    return log


def test_known_action_gets_labelled_verb(db_session):
    actor = _make_user(db_session)
    log = _make_log(
        db_session,
        actor_id=actor.id,
        action="signup_cancelled",
        entity_type="Signup",
        entity_id=str(uuid.uuid4()),
    )
    out = humanize(log, db_session)
    assert out["action_label"] == "Cancelled a signup"
    assert out["actor_label"] == "Alice Smith"
    assert out["actor_role"] == "admin"
    assert out["action"] == "signup_cancelled"


def test_unknown_action_falls_back_to_title_case(db_session):
    actor = _make_user(db_session, email="u@example.com")
    log = _make_log(
        db_session,
        actor_id=actor.id,
        action="some_new_action",
        entity_type="User",
        entity_id=str(actor.id),
    )
    out = humanize(log, db_session)
    assert out["action_label"] == "Some new action"


def test_none_actor_renders_as_system(db_session):
    log = _make_log(
        db_session,
        actor_id=None,
        action="signup_cancelled",
        entity_type="Signup",
        entity_id=str(uuid.uuid4()),
    )
    out = humanize(log, db_session)
    assert out["actor_label"] == "System"
    assert out["actor_role"] is None


def test_deleted_actor_renders_as_tombstoned(db_session):
    # Build an unflushed AuditLog pointing at a non-existent user id so the FK
    # is never checked. humanize() only reads attributes + queries users, so it
    # works fine on a transient row.
    ghost_id = uuid.uuid4()
    log = models.AuditLog(
        id=uuid.uuid4(),
        actor_id=ghost_id,
        action="user_update",
        entity_type="User",
        entity_id=str(ghost_id),
        timestamp=datetime.now(timezone.utc),
    )
    out = humanize(log, db_session)
    assert out["actor_label"].startswith("(deleted) #")
    assert str(ghost_id)[:8] in out["actor_label"]


def test_signup_entity_label_includes_volunteer_event_date(db_session):
    actor = _make_user(db_session, email="admin2@example.com")
    ev = _make_event(db_session, owner=actor, title="Physics Lab")
    sl = _make_slot(db_session, ev)
    vol = _make_volunteer(db_session, first="Bob", last="Jones")
    signup = _make_signup(db_session, vol, sl)

    log = _make_log(
        db_session,
        actor_id=actor.id,
        action="signup_cancelled",
        entity_type="Signup",
        entity_id=str(signup.id),
    )
    out = humanize(log, db_session)
    assert "Bob Jones" in out["entity_label"]
    assert "Physics Lab" in out["entity_label"]
    assert "2026-05-01" in out["entity_label"]


def test_action_labels_dict_has_canonical_signup_cancelled():
    """Guard: D-20 canonical form is present, legacy form is not."""
    assert "signup_cancelled" in ACTION_LABELS
    assert "signup_cancel" not in ACTION_LABELS
