"""K27 — three tool-layer defects that produced confident wrong answers.

1. ``find_understaffed_modules`` had no time filter at all, so "which modules
   are understaffed?" answered with every module that had ever run below
   capacity — none of which can be staffed now. And because ``fill_rate`` is
   0.0 when there are no bookable units, every skeleton event was permanently
   at the top of the list, including the ones ``create_module_from_template``
   had just created.

2. ``move_participant`` picked its destination with an unordered ``.first()``:
   nondeterministic across runs, and happy to choose a full unit over an empty
   one on the same event — waitlisting somebody who should have had a seat.

3. ``create_module_from_template`` and ``move_participant`` only flushed. Their
   writes were durable purely as a side effect of ``audit_log.update_status``
   committing on its way past, and that function calls ``db.rollback()`` when
   it cannot find its own audit row — silently discarding a write the admin had
   already been told about.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import models
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.tools.find_understaffed_modules import (
    FIND_UNDERSTAFFED_MODULES_TOOL,
)
from app.copilot.agent.tools.move_participant import MOVE_PARTICIPANT_TOOL
from app.models import Event, Signup, SignupStatus, Slot, SlotType, Volunteer


def _event(db_session, owner_id, *, title, start_date, school="Adams"):
    ev = Event(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title=title,
        start_date=start_date,
        end_date=start_date + timedelta(hours=2),
        year=start_date.year,
        week_number=1,
        school=school,
    )
    db_session.add(ev)
    db_session.flush()
    return ev


def _slot(db_session, event_id, *, capacity, filled, start_time, name="P1"):
    slot = Slot(
        id=uuid.uuid4(),
        event_id=event_id,
        sort_order=0,
        name=name,
        start_time=start_time,
        end_time=start_time + timedelta(hours=1),
        capacity=capacity,
        current_count=filled,
        slot_type=SlotType.ORIENTATION,
    )
    db_session.add(slot)
    db_session.flush()
    return slot


def _volunteer(db_session):
    v = Volunteer(
        id=uuid.uuid4(),
        email=f"v{uuid.uuid4().hex[:8]}@example.com",
        first_name="V",
        last_name="X",
    )
    db_session.add(v)
    db_session.flush()
    return v


@pytest.fixture
def admin(db_session):
    from tests.fixtures.helpers import make_user

    u = make_user(
        db_session,
        email=f"k27_{uuid.uuid4().hex[:8]}@example.com",
        role=models.UserRole.admin,
    )
    db_session.flush()
    return u


# ---------------------------------------------------------------------------
# 1. find_understaffed_modules — the window and the skeletons
# ---------------------------------------------------------------------------


class TestTheUnderstaffedWindow:
    def test_a_module_that_has_already_run_is_not_reported(
        self, db_session, admin
    ):
        """You cannot staff last February."""
        past = datetime.now(timezone.utc) - timedelta(days=90)
        ev = _event(db_session, admin.id, title="Long gone", start_date=past)
        _slot(db_session, ev.id, capacity=10, filled=1, start_time=past)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope_for(role="admin", caller_id=None), {"threshold": 0.5}
        )
        assert [m["name"] for m in out["modules"]] == []

    def test_an_upcoming_module_is_reported(self, db_session, admin):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        ev = _event(db_session, admin.id, title="Next week", start_date=soon)
        _slot(db_session, ev.id, capacity=10, filled=1, start_time=soon)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope_for(role="admin", caller_id=None), {"threshold": 0.5}
        )
        assert [m["name"] for m in out["modules"]] == ["Next week"]

    def test_include_past_is_the_escape_hatch(self, db_session, admin):
        past = datetime.now(timezone.utc) - timedelta(days=90)
        ev = _event(db_session, admin.id, title="Long gone", start_date=past)
        _slot(db_session, ev.id, capacity=10, filled=1, start_time=past)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session,
            scope_for(role="admin", caller_id=None),
            {"threshold": 0.5, "include_past": True},
        )
        assert [m["name"] for m in out["modules"]] == ["Long gone"]

    def test_an_explicit_week_works_even_when_it_is_in_the_past(
        self, db_session, admin
    ):
        """Otherwise "how did week 22 go?" would silently answer nothing."""
        from app.copilot.agent.tools._iso_week import iso_week_bounds

        start, _ = iso_week_bounds("2026-W22")
        ev = _event(db_session, admin.id, title="W22", start_date=start)
        _slot(db_session, ev.id, capacity=10, filled=1, start_time=start)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session,
            scope_for(role="admin", caller_id=None),
            {"threshold": 0.5, "week": "2026-W22"},
        )
        assert [m["name"] for m in out["modules"]] == ["W22"]

    def test_a_week_filter_excludes_other_weeks(self, db_session, admin):
        from app.copilot.agent.tools._iso_week import iso_week_bounds

        start22, _ = iso_week_bounds("2026-W22")
        start23, _ = iso_week_bounds("2026-W23")
        for title, start in (("W22", start22), ("W23", start23)):
            ev = _event(db_session, admin.id, title=title, start_date=start)
            _slot(db_session, ev.id, capacity=10, filled=1, start_time=start)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session,
            scope_for(role="admin", caller_id=None),
            {"threshold": 0.5, "week": "2026-W23"},
        )
        assert [m["name"] for m in out["modules"]] == ["W23"]


class TestModulesWithNoSlots:
    def test_a_skeleton_module_is_not_called_understaffed(
        self, db_session, admin
    ):
        """It needs slots, not volunteers — a different sentence entirely."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        _event(db_session, admin.id, title="Skeleton", start_date=soon)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope_for(role="admin", caller_id=None), {"threshold": 0.5}
        )
        assert [m["name"] for m in out["modules"]] == []

    def test_but_it_is_still_reported_separately(self, db_session, admin):
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        _event(db_session, admin.id, title="Skeleton", start_date=soon)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope_for(role="admin", caller_id=None), {"threshold": 0.5}
        )
        assert [m["name"] for m in out["modules_without_slots"]] == ["Skeleton"]

    def test_a_skeleton_does_not_crowd_out_a_real_gap(self, db_session, admin):
        """The failure mode: five empty skeletons burying the one module that
        genuinely needs people."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        for i in range(5):
            _event(db_session, admin.id, title=f"Skeleton {i}", start_date=soon)
        real = _event(db_session, admin.id, title="Real gap", start_date=soon)
        _slot(db_session, real.id, capacity=10, filled=1, start_time=soon)

        out = FIND_UNDERSTAFFED_MODULES_TOOL.handler(
            db_session, scope_for(role="admin", caller_id=None), {"threshold": 0.5}
        )
        assert [m["name"] for m in out["modules"]] == ["Real gap"]
        assert len(out["modules_without_slots"]) == 5


# ---------------------------------------------------------------------------
# 2. move_participant — which destination
# ---------------------------------------------------------------------------


def _move(db_session, participant, from_ev, to_ev):
    return MOVE_PARTICIPANT_TOOL.handler(
        db_session,
        scope_for(role="admin", caller_id=None),
        {
            "participant_id": str(participant.id),
            "from_module": str(from_ev.id),
            "to_module": str(to_ev.id),
        },
    )


class TestTheDestinationChoice:
    def test_a_slot_with_room_is_chosen_over_a_full_one(
        self, db_session, admin
    ):
        """The bug: the full slot sorted first, so the volunteer was
        waitlisted onto an event that had empty seats."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        src = _event(db_session, admin.id, title="Source", start_date=soon)
        dst = _event(db_session, admin.id, title="Dest", start_date=soon)

        src_slot = _slot(db_session, src.id, capacity=5, filled=1, start_time=soon)
        # The full slot starts earlier, so every tiebreak short of capacity
        # would pick it.
        full = _slot(
            db_session,
            dst.id,
            capacity=1,
            filled=1,
            start_time=soon,
            name="Full but first",
        )
        roomy = _slot(
            db_session,
            dst.id,
            capacity=5,
            filled=0,
            start_time=soon + timedelta(hours=3),
            name="Has room",
        )

        v = _volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(),
            slot_id=src_slot.id,
            volunteer_id=v.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        out = _move(db_session, v, src, dst)
        assert "error" not in out, out
        db_session.expire_all()
        moved = db_session.get(Signup, signup.id)
        assert moved.slot_id == roomy.id
        assert moved.slot_id != full.id
        # And they keep their seat rather than being waitlisted.
        assert moved.status == SignupStatus.confirmed

    def test_the_choice_is_stable_across_repeats(self, db_session, admin):
        """An unordered .first() could land somewhere other than the slot the
        admin was shown in the confirmation preview."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        dst = _event(db_session, admin.id, title="Dest", start_date=soon)
        for i in range(4):
            _slot(
                db_session,
                dst.id,
                capacity=5,
                filled=0,
                start_time=soon + timedelta(hours=i),
                name=f"P{i}",
            )

        landed = set()
        for _ in range(4):
            src = _event(
                db_session, admin.id, title="Source", start_date=soon
            )
            src_slot = _slot(
                db_session, src.id, capacity=5, filled=1, start_time=soon
            )
            v = _volunteer(db_session)
            signup = Signup(
                id=uuid.uuid4(),
                slot_id=src_slot.id,
                volunteer_id=v.id,
                status=SignupStatus.confirmed,
            )
            db_session.add(signup)
            db_session.flush()
            _move(db_session, v, src, dst)
            db_session.expire_all()
            landed.add(str(db_session.get(Signup, signup.id).slot_id))

        assert len(landed) == 1, f"destination varied between runs: {landed}"

    def test_an_all_full_destination_still_waitlists(self, db_session, admin):
        """Preferring room must not invent room that isn't there."""
        soon = datetime.now(timezone.utc) + timedelta(days=7)
        src = _event(db_session, admin.id, title="Source", start_date=soon)
        dst = _event(db_session, admin.id, title="Dest", start_date=soon)
        src_slot = _slot(db_session, src.id, capacity=5, filled=1, start_time=soon)
        _slot(db_session, dst.id, capacity=1, filled=1, start_time=soon)

        v = _volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(),
            slot_id=src_slot.id,
            volunteer_id=v.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.flush()

        _move(db_session, v, src, dst)
        db_session.expire_all()
        assert (
            db_session.get(Signup, signup.id).status == SignupStatus.waitlisted
        )


# ---------------------------------------------------------------------------
# 3. Durability — the write must not depend on the audit log
# ---------------------------------------------------------------------------


class TestTheWriteSurvivesTheAuditLog:
    def test_a_move_is_committed_by_the_tool_itself(self, db_session, admin):
        """``update_status`` rolls the session back when it cannot find its
        audit row. That used to take the move with it, while the admin had
        already been told it happened."""
        from app.copilot.agent.audit_log import CallNotFound, update_status

        soon = datetime.now(timezone.utc) + timedelta(days=7)
        src = _event(db_session, admin.id, title="Source", start_date=soon)
        dst = _event(db_session, admin.id, title="Dest", start_date=soon)
        src_slot = _slot(db_session, src.id, capacity=5, filled=1, start_time=soon)
        dst_slot = _slot(db_session, dst.id, capacity=5, filled=0, start_time=soon)

        v = _volunteer(db_session)
        signup = Signup(
            id=uuid.uuid4(),
            slot_id=src_slot.id,
            volunteer_id=v.id,
            status=SignupStatus.confirmed,
        )
        db_session.add(signup)
        db_session.commit()

        _move(db_session, v, src, dst)
        # Now simulate the audit row having gone missing.
        with pytest.raises(CallNotFound):
            update_status(db_session, "no-such-call", status="executed")

        db_session.expire_all()
        assert db_session.get(Signup, signup.id).slot_id == dst_slot.id

    def test_a_created_module_is_committed_by_the_tool_itself(
        self, db_session, admin
    ):
        from app.copilot.agent.audit_log import CallNotFound, update_status
        from app.copilot.agent.tools.create_module_from_template import (
            CREATE_MODULE_FROM_TEMPLATE_TOOL,
        )
        from app.models import AcademicQuarter, Module, Quarter as QuarterEnum

        db_session.add(
            Module(
                slug="tmpl-k27",
                name="K27 Template",
                duration_minutes=60,
            )
        )
        # The tool refuses a week no quarter covers, so give it one. Far
        # enough out that it cannot collide with a seeded quarter — the
        # table has a no-overlap exclusion constraint.
        db_session.add(
            AcademicQuarter(
                season=QuarterEnum.WINTER,
                year=2030,
                label="K27",
                start_date=date(2030, 3, 1),
                end_date=date(2030, 3, 31),
            )
        )
        db_session.commit()

        out = CREATE_MODULE_FROM_TEMPLATE_TOOL.handler(
            db_session,
            scope_for(role="admin", caller_id=admin.id),
            {"template_id": "tmpl-k27", "week": "2030-W10"},
        )
        assert "error" not in out, out

        new_id = out["new_module_id"]
        with pytest.raises(CallNotFound):
            update_status(db_session, "no-such-call", status="executed")

        db_session.expire_all()
        row = db_session.execute(
            text("SELECT title FROM events WHERE id = :i"), {"i": new_id}
        ).scalar()
        assert row == "K27 Template"
