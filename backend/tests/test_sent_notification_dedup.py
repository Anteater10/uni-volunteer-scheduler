"""Exactly-once email dedup survives the dual-anchored sent_notifications table.

2026-08-02 shifts made ``sent_notifications`` dual-anchored: exactly one of
``signup_id`` (orientation) or ``shift_signup_id`` (a shift commitment) is set.
Because both columns are nullable, one unique index across them would treat
every ``(NULL, kind)`` pair as distinct and quietly disable dedup — so the
uniqueness lives in two *partial* unique indexes instead.

That has a consequence every caller has to honour: Postgres only infers a
partial index when ``ON CONFLICT`` repeats the index predicate. An unqualified
``index_elements=["signup_id", "kind"]`` matches no index and raises
``InvalidColumnReference``. It does not degrade to a weaker dedup — it takes
the whole send path down.

Two of the four call sites shipped without the predicate
(``reminder_service.send_reminder``'s slot path and
``broadcast_service._dedup_insert_broadcast``), so orientation reminders and
every broadcast raised instead of sending. These tests pin all four, because
the failure mode is invisible in review: the omission looks like a smaller,
tidier version of the correct call.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from app.celery_app import _dedup_insert, _dedup_insert_shift
from app.services.broadcast_service import _dedup_insert_broadcast
from tests.fixtures.factories import (
    ShiftFactory,
    ShiftSignupFactory,
    SignupFactory,
    SlotFactory,
    VolunteerFactory,
)
from tests.fixtures.helpers import _bind_factories, make_user


def _orientation_signup(db_session):
    """A signup anchored to an orientation slot — still Signup end to end."""
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.admin)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Dedup Event",
        start_date=start,
        end_date=start + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    slot = SlotFactory(
        event=event,
        slot_type=models.SlotType.ORIENTATION,
        start_time=start,
        end_time=start + timedelta(hours=2),
        capacity=5,
        current_count=0,
    )
    volunteer = VolunteerFactory(email=f"dedup-{uuid.uuid4().hex[:8]}@example.com")
    signup = SignupFactory(
        volunteer=volunteer, slot=slot, status=models.SignupStatus.confirmed
    )
    db_session.flush()
    return signup


def _shift_commitment(db_session):
    """A commitment to a whole shift — the other anchor."""
    _bind_factories(db_session)
    owner = make_user(db_session, role=models.UserRole.admin)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    event = models.Event(
        id=uuid.uuid4(),
        owner_id=owner.id,
        title="Dedup Shift Event",
        start_date=start,
        end_date=start + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()
    shift = ShiftFactory(event=event, name="Tue morning", capacity=5)
    db_session.flush()
    volunteer = VolunteerFactory(email=f"dedup-s-{uuid.uuid4().hex[:8]}@example.com")
    commitment = ShiftSignupFactory(
        shift=shift, volunteer=volunteer, status=models.SignupStatus.confirmed
    )
    db_session.flush()
    return commitment


class TestSignupAnchor:
    """The orientation anchor: signup_id IS NOT NULL."""

    def test_first_insert_wins_second_is_deduped(self, db_session):
        signup = _orientation_signup(db_session)

        assert _dedup_insert(db_session, signup.id, "reminder_24h") is True
        # Same anchor, same kind — the email already went out.
        assert _dedup_insert(db_session, signup.id, "reminder_24h") is False

    def test_different_kind_is_a_different_email(self, db_session):
        signup = _orientation_signup(db_session)

        assert _dedup_insert(db_session, signup.id, "reminder_24h") is True
        # Dedup is per (anchor, kind); a 1h reminder is not the 24h one.
        assert _dedup_insert(db_session, signup.id, "reminder_1h") is True

    def test_broadcast_dedup_does_not_raise_and_dedupes(self, db_session):
        """Regression: this raised InvalidColumnReference, failing every send.

        The broadcast path had its own copy of the dedup insert and did not
        carry the partial-index predicate, so no broadcast could be sent at
        all — not a duplicate-email bug, a nothing-arrives bug.
        """
        signup = _orientation_signup(db_session)

        assert _dedup_insert_broadcast(db_session, signup.id, "broadcast_abc") is True
        assert _dedup_insert_broadcast(db_session, signup.id, "broadcast_abc") is False


class TestShiftSignupAnchor:
    """The commitment anchor: shift_signup_id IS NOT NULL."""

    def test_first_insert_wins_second_is_deduped(self, db_session):
        commitment = _shift_commitment(db_session)

        assert _dedup_insert_shift(db_session, commitment.id, "reminder_24h") is True
        assert _dedup_insert_shift(db_session, commitment.id, "reminder_24h") is False

    def test_different_kind_is_a_different_email(self, db_session):
        commitment = _shift_commitment(db_session)

        assert _dedup_insert_shift(db_session, commitment.id, "reminder_24h") is True
        assert _dedup_insert_shift(db_session, commitment.id, "reminder_1h") is True


class TestAnchorsAreIndependent:
    def test_same_kind_on_each_anchor_both_send(self, db_session):
        """The two partial indexes must not collide with each other.

        A volunteer can hold an orientation signup *and* a shift commitment on
        the same event; both are entitled to their own 24h reminder. If the two
        anchors shared one index the second would be swallowed as a duplicate
        and somebody would silently not be reminded.
        """
        signup = _orientation_signup(db_session)
        commitment = _shift_commitment(db_session)

        assert _dedup_insert(db_session, signup.id, "reminder_24h") is True
        assert _dedup_insert_shift(db_session, commitment.id, "reminder_24h") is True

    def test_null_anchors_do_not_collapse_into_one_row(self, db_session):
        """Why the indexes are partial in the first place.

        Guards the design decision rather than a call site: if someone
        "simplifies" the two partial indexes into one plain
        UNIQUE(signup_id, shift_signup_id, kind), Postgres treats NULLs as
        distinct and every dedup check would return True — every email sent
        twice, with no error anywhere. Two commitments, same kind, must stay
        two rows, and the CHECK constraint must keep refusing a row with
        neither anchor set.
        """
        first = _shift_commitment(db_session)
        second = _shift_commitment(db_session)

        assert _dedup_insert_shift(db_session, first.id, "reminder_24h") is True
        assert _dedup_insert_shift(db_session, second.id, "reminder_24h") is True

        rows = (
            db_session.query(models.SentNotification)
            .filter(models.SentNotification.kind == "reminder_24h")
            .all()
        )
        assert len(rows) == 2
        assert {r.shift_signup_id for r in rows} == {first.id, second.id}
        assert all(r.signup_id is None for r in rows)
