"""Phase 35-02-E: reusable adversarial-world seeding.

The ``seed_full_world`` pytest fixture (in ``conftest.py``) and the offline
``app.eval.adversarial._run_one_case`` driver both need the same rich world
(two organizers, one admin, four events, signups, one unsigned volunteer).
The fixture cannot be imported outside pytest, so the seeding body lives here
as a plain function and the fixture just calls it — mirroring how commit
``1245cb7`` lifted ``run_tool_case`` out of the parametrize body so both the
pytest path and the offline wrapper share one implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import UserRole
from tests.fixtures.helpers import make_user


def seed_full_world(db_session) -> dict[str, Any]:
    """Build the adversarial test world and return the sentinel dict.

    Two organizers (org_a, org_b), one admin. Four events across W19-W22 of
    2026 — two per organizer per school. Signups seeded against capacity so
    over/under-staffed views have plausible counts. Plus one unsigned
    volunteer. Does NOT commit — the caller owns the transaction lifecycle.
    """
    from app.models import Event, Signup, SignupStatus, Slot, Volunteer

    org_a = make_user(db_session, role=UserRole.organizer)
    org_b = make_user(db_session, role=UserRole.organizer)
    admin = make_user(db_session, role=UserRole.admin)

    base = datetime.now(timezone.utc) + timedelta(days=1)

    spec = [
        ("A-evt-1", org_a.id, "Adams Elementary", 2026, 22, 5, 1),
        ("A-evt-2", org_a.id, "Adams Elementary", 2026, 21, 4, 2),
        ("B-evt-1", org_b.id, "Brandon Middle",   2026, 20, 10, 0),
        ("B-evt-2", org_b.id, "Brandon Middle",   2026, 19, 3, 3),
    ]

    event_ids: dict = {}
    slot_ids: dict = {}
    volunteer_ids: list = []
    volunteer_emails: list = []

    for title, owner_id, school, year, wk, capacity, n_signups in spec:
        eid = uuid.uuid4()
        sid = uuid.uuid4()
        event_ids[title] = eid
        slot_ids[title] = sid
        ev = Event(
            id=eid,
            owner_id=owner_id,
            title=title,
            start_date=base,
            end_date=base + timedelta(hours=2),
            year=year,
            week_number=wk,
            school=school,
        )
        sl = Slot(
            id=sid,
            event_id=eid,
            start_time=base,
            end_time=base + timedelta(hours=2),
            capacity=capacity,
            current_count=0,
            slot_type="period",
            date=base.date(),
        )
        db_session.add_all([ev, sl])
        db_session.flush()
        for _ in range(n_signups):
            email = f"v-{uuid.uuid4().hex[:8]}@example.com"
            vol = Volunteer(
                id=uuid.uuid4(),
                email=email,
                first_name="V",
                last_name="X",
            )
            db_session.add(vol)
            db_session.flush()
            db_session.add(
                Signup(
                    id=uuid.uuid4(),
                    volunteer_id=vol.id,
                    slot_id=sid,
                    status=SignupStatus.confirmed,
                )
            )
            db_session.flush()
            volunteer_ids.append(vol.id)
            volunteer_emails.append((title, email))

    extra_email = f"extra-{uuid.uuid4().hex[:8]}@example.com"
    extra = Volunteer(
        id=uuid.uuid4(),
        email=extra_email,
        first_name="E",
        last_name="X",
    )
    db_session.add(extra)
    db_session.flush()

    return {
        "org_a_id": org_a.id,
        "org_b_id": org_b.id,
        "admin_id": admin.id,
        "event_ids": event_ids,
        "slot_ids": slot_ids,
        "volunteer_ids": volunteer_ids,
        "volunteer_emails": volunteer_emails,
        "extra_volunteer_id": extra.id,
        "extra_volunteer_email": extra_email,
    }


def make_admin_user(db_session):
    """Create one admin user (mirror of the ``admin_user`` fixture)."""
    return make_user(db_session, role=UserRole.admin)


def register_all_tools():
    """Reset the tool registry + confirmation store and register every
    production tool — mirror of the autouse ``_reset_and_register_all_tools``
    fixture so the offline driver gets the same tool set the pytest path has.
    """
    from app.copilot.agent import confirmation
    from app.copilot.agent.tools import registry
    from app.copilot.agent.tools.create_module_from_template import (
        CREATE_MODULE_FROM_TEMPLATE_TOOL,
    )
    from app.copilot.agent.tools.current_user_context import (
        CURRENT_USER_CONTEXT_TOOL,
    )
    from app.copilot.agent.tools.find_module_by_name import (
        FIND_MODULE_BY_NAME_TOOL,
    )
    from app.copilot.agent.tools.find_understaffed_modules import (
        FIND_UNDERSTAFFED_MODULES_TOOL,
    )
    from app.copilot.agent.tools.get_module_roster import GET_MODULE_ROSTER_TOOL
    from app.copilot.agent.tools.list_modules import LIST_MODULES_TOOL
    from app.copilot.agent.tools.move_participant import MOVE_PARTICIPANT_TOOL
    from app.copilot.agent.tools.nudge_understaffed_module import (
        NUDGE_UNDERSTAFFED_MODULE_TOOL,
    )
    from app.copilot.agent.tools.participant_history import (
        PARTICIPANT_HISTORY_TOOL,
    )
    from app.copilot.agent.tools.send_reminder_email import (
        SEND_REMINDER_EMAIL_TOOL,
    )
    from app.copilot.agent.tools.signup_stats_for_week import (
        SIGNUP_STATS_FOR_WEEK_TOOL,
    )
    from app.copilot.agent.tools.signup_trend import SIGNUP_TREND_TOOL

    registry._reset_for_tests()
    confirmation._reset_for_tests()
    for tool in (
        LIST_MODULES_TOOL,
        GET_MODULE_ROSTER_TOOL,
        FIND_UNDERSTAFFED_MODULES_TOOL,
        PARTICIPANT_HISTORY_TOOL,
        SIGNUP_STATS_FOR_WEEK_TOOL,
        SIGNUP_TREND_TOOL,
        FIND_MODULE_BY_NAME_TOOL,
        CURRENT_USER_CONTEXT_TOOL,
        SEND_REMINDER_EMAIL_TOOL,
        NUDGE_UNDERSTAFFED_MODULE_TOOL,
        CREATE_MODULE_FROM_TEMPLATE_TOOL,
        MOVE_PARTICIPANT_TOOL,
    ):
        registry.register(tool)
