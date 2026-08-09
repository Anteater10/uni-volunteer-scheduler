"""One rule, checked across the whole registry rather than tool by tool.

    A value the user did not state is not a value a tool may choose.

The bug that produced this file: ``create_event_with_schedule`` filled a
missing start time with 09:00. The event looked right — correct school,
correct week, correct module — and would have gone on looking right until
somebody stood in an empty classroom at nine in the morning. A refusal is
visible; an invented number is not.

The mechanism is ``Tool.precheck``, which runs *before* the confirmation
card is built. That timing is the whole point: a confirming tool's handler
does not run until the admin has already approved the card, so a question
raised there arrives after the decision it was supposed to inform.

These tests are deliberately about the registry and not about any one tool.
A per-tool test protects the tool it was written for; this one protects the
tool nobody has written yet.
"""
import inspect

import pytest

from app.copilot.agent.tools import registry  # noqa: F401 — populates it
from app.copilot.agent.tools._ask import ask_for
from app.copilot.agent.tools.base import Tool


# Snapshotted at import, not read per-test: conftest clears the registry
# between tests, and parametrize would otherwise expand over an empty list
# and pass by finding nothing to check.
_ALL_TOOLS: list[Tool] = list(registry._REGISTRY.values())
_WRITERS: list[Tool] = [t for t in _ALL_TOOLS if t.requires_confirmation]


class TestEveryWriteToolAsksFirst:
    def test_there_are_write_tools_to_check(self):
        """Guards every parametrized test below from passing vacuously."""
        assert _ALL_TOOLS, "the registry import stopped populating"
        assert len(_WRITERS) >= 10

    @pytest.mark.parametrize("tool", _WRITERS, ids=lambda t: t.name)
    def test_it_has_a_precheck(self, tool):
        assert tool.precheck is not None, (
            f"{tool.name} changes data behind a confirmation card but has no "
            "precheck, so anything the user did not say is whatever the "
            "model decided. Add one — see app/copilot/agent/tools/_ask.py."
        )

    @pytest.mark.parametrize("tool", _WRITERS, ids=lambda t: t.name)
    def test_its_precheck_takes_the_standard_arguments(self, tool):
        """``invoke`` calls it as ``precheck(db, scope, args)``; a signature
        that does not match fails at the moment a real admin uses it."""
        params = list(inspect.signature(tool.precheck).parameters)
        assert len(params) == 3, f"{tool.name}: {params}"

    @pytest.mark.parametrize("tool", _WRITERS, ids=lambda t: t.name)
    def test_it_asks_for_something_when_given_nothing(self, tool, db_session):
        """Called with no arguments at all, a write tool must object rather
        than proceed. It is the cheapest possible probe of "does this thing
        require the user to have said anything", and every tool that fills a
        blank with a default fails it.
        """
        from app.copilot.agent.boundary.role_scope import scope_for

        scope = scope_for(role="admin", caller_id=None)
        objection = tool.precheck(db_session, scope, {})
        assert objection is not None, (
            f"{tool.name} accepted an empty request. Every value it is about "
            "to write came from the model, not the user."
        )
        assert objection.get("needs_answers"), (
            f"{tool.name} objected without saying what it needs, so the "
            "model has nothing to put to the user."
        )


class TestTheAskItself:
    def test_no_missing_values_means_no_objection(self):
        """What lets a precheck end with ``return ask_for(missing)`` and
        still fall through to the handler when nothing is missing."""
        assert ask_for([]) is None

    def test_an_ask_names_what_it_needs(self):
        payload = ask_for(["a start time"])
        assert payload["needs_answers"] == ["a start time"]
        assert "invent" in payload["question"]

    def test_it_tells_the_model_not_to_guess(self):
        assert "Do not guess" in ask_for(["anything"])["question"]
