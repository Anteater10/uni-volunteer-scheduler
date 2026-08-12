"""Drive the real model through the real agent loop, and report what it did.

Every automated test of the tool layer stops at the same place: the model.
Tools are handed a dictionary and checked on what comes out, which proves the
handler, the role gate, the redactor and the confirmation flow — and proves
nothing about the step before all of them, where a sentence becomes a tool
name and a set of arguments. That step is where every bug found in live use
actually was: 9am stored as 2am, the week of August 17th resolved to W33,
"August 17" resolved to 2025.

So this asks the real model real questions and prints the tool calls it
makes. Write tools park at the confirmation card, which is exactly the
inspection point wanted here — the proposed arguments are visible and
nothing has been written, so a scenario can be judged without mutating
anything. Read tools run, because reading is free.

Usage, from the repo root (needs OPENROUTER_API_KEY in backend/.env):

    docker run --rm --network uni-volunteer-scheduler_default \\
      -v $PWD/backend:/app -w /app --env-file backend/.env \\
      -e DATABASE_URL="postgresql+psycopg2://postgres:postgres@db:5432/uni_volunteer" \\
      uni-volunteer-scheduler-backend python scripts/copilot_smoke.py

Costs a handful of OpenRouter requests per scenario. Nothing here approves a
confirmation, so the database is left as it was found.
"""
from __future__ import annotations

import sys
import uuid

from sqlalchemy import text

from app.copilot.agent.adapter import AdapterUnavailable, ToolCallingAdapter
from app.copilot.agent.boundary.role_scope import scope_for
from app.copilot.agent.loop import run_turn
from app.copilot.prompts import system_prompt_for
from app.database import SessionLocal
from app import models

# Each scenario names the tool it ought to reach for, and that expectation is
# the whole point: "it answered something" is not a pass. A model that
# invents an event rather than asking is confidently wrong in exactly the way
# these scenarios exist to catch.
SCENARIOS = [
    {
        "name": "read: quarters",
        "ask": "What quarters exist, and when does the current one end?",
        "expect": {"list_quarters"},
    },
    {
        "name": "read: staff",
        "ask": "Who are the admins and organizers on this system?",
        "expect": {"list_staff"},
    },
    {
        "name": "edit: move an orientation",
        "ask": (
            "Change the Waves at Goleta Valley Junior High orientation on "
            "August 17 to start at 5:30pm instead of 5:00pm. It should still "
            "run an hour."
        ),
        "expect": {"reschedule_slot"},
    },
    {
        "name": "vague: must ask, not invent",
        "ask": "Schedule a Germs event at Dos Pueblos next month.",
        # The right answer is a question. Reaching create_event_with_schedule
        # is fine only if the precheck then refuses; inventing days and times
        # and parking a full card is the failure this watches for.
        "expect": {"__asks__"},
    },
    {
        "name": "credits: check one module",
        "ask": "Has anyone been given orientation credit for the Waves module?",
        "expect": {"list_orientation_credits", "check_orientation_credit"},
    },
]


def _session_row(db, user_id) -> uuid.UUID:
    """A copilot session to hang the audit rows off."""
    session_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO copilot_sessions (id, user_id, model_id, "
            "system_prompt_hash, system_prompt_version) "
            "VALUES (:s, :u, 'smoke', 'smoke', 'smoke')"
        ),
        {"s": session_id, "u": user_id},
    )
    db.commit()
    return session_id


def _run(db, llm, scope, user, scenario) -> dict:
    session_id = _session_row(db, user.id)
    called: list[tuple[str, dict]] = []
    answers: list[str] = []
    parked: list[str] = []
    errors: list[str] = []

    for event in run_turn(
        db=db,
        llm=llm,
        scope=scope,
        session_id=session_id,
        user_message=scenario["ask"],
        retrieval_context="",
        system_prompt=system_prompt_for(user.role, agent=True),
        history=[],
    ):
        if event.type == "tool_call":
            called.append((event.tool, event.args))
        elif event.type == "tool_result":
            # A precheck's question comes back as an ordinary result, so this
            # is where "it asked" is visible.
            result = event.result or {}
            if isinstance(result, dict) and result.get("needs_answers"):
                parked.append("asked: " + "; ".join(result["needs_answers"]))
        elif event.type == "confirmation_request":
            parked.append(f"card: {event.tool}")
        elif event.type == "final_answer":
            answers.append(event.text)
        elif event.type == "error":
            errors.append(event.message)

    return {
        "called": called,
        "answers": answers,
        "parked": parked,
        "errors": errors,
    }


def _verdict(scenario, outcome) -> tuple[bool, str]:
    names = {name for name, _ in outcome["called"]}
    asked = any(p.startswith("asked:") for p in outcome["parked"])

    if outcome["errors"]:
        return False, f"errored: {'; '.join(outcome['errors'])}"
    if scenario["expect"] == {"__asks__"}:
        if asked:
            return True, "asked for what was missing"
        if any(p.startswith("card:") for p in outcome["parked"]):
            return False, "parked a card instead of asking — it invented the gaps"
        return (True, "answered without acting") if outcome["answers"] else (
            False,
            "did nothing",
        )
    if names & scenario["expect"]:
        return True, f"called {', '.join(sorted(names & scenario['expect']))}"
    if not names:
        return False, "called no tool at all"
    return False, f"reached for {', '.join(sorted(names))} instead"


def main() -> int:
    try:
        llm = ToolCallingAdapter()
    except AdapterUnavailable as exc:
        print(f"adapter unavailable: {exc}")
        return 2

    db = SessionLocal()
    user = (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.admin,
            models.User.is_active.is_(True),
        )
        .first()
    )
    if user is None:
        print("no active admin in this database")
        return 2
    scope = scope_for(role="admin", caller_id=user.id)

    failures = 0
    for scenario in SCENARIOS:
        print(f"\n=== {scenario['name']}")
        print(f"    ask: {scenario['ask']}")
        try:
            outcome = _run(db, llm, scope, user, scenario)
        except Exception as exc:  # noqa: BLE001 — a smoke run reports, never raises
            print(f"    CRASH {exc.__class__.__name__}: {exc}")
            failures += 1
            continue

        for name, args in outcome["called"]:
            print(f"    -> {name}({args})")
        for note in outcome["parked"]:
            print(f"    .. {note}")
        for answer in outcome["answers"]:
            print(f"    << {answer[:400]}")

        ok, why = _verdict(scenario, outcome)
        print(f"    {'PASS' if ok else 'FAIL'}: {why}")
        failures += 0 if ok else 1

    db.close()
    print(f"\n{len(SCENARIOS) - failures}/{len(SCENARIOS)} scenarios passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
