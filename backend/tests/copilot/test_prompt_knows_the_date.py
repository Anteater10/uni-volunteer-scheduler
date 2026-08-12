"""The model has no clock, and nobody had told it what day it was.

Asked on 2026-08-08 to schedule something for "Monday August 17", the agent
produced 2025-08-17 — a year in the past, from a request that named no year
at all. The tool refused, correctly, and the admin was told to go and add a
quarter covering a date they had never asked for.

Nothing downstream could have caught this. 2025-08-17 is a real Monday.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import models
from app.copilot.prompts import SYSTEM_PROMPT_VERSION, system_prompt_for


def _today() -> str:
    return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()


class TestTheAgentIsToldTheDate:
    def test_the_prompt_carries_today(self):
        prompt = system_prompt_for(models.UserRole.admin, agent=True)
        assert _today() in prompt

    def test_organizers_are_told_too(self):
        """Organizers schedule as much as admins do."""
        prompt = system_prompt_for(models.UserRole.organizer, agent=True)
        assert _today() in prompt

    def test_the_sentinel_is_always_replaced(self):
        """A literal ``{today}`` reaching the model is worse than no date —
        it reads as a variable nobody filled in."""
        for role in (models.UserRole.admin, models.UserRole.organizer):
            assert "{today}" not in system_prompt_for(role, agent=True)

    def test_it_is_rendered_per_call_not_at_import(self):
        """A backend that stays up over midnight would otherwise spend the
        whole next day insisting it is yesterday."""
        import inspect

        from app.copilot import prompts

        source = inspect.getsource(prompts.system_prompt_for)
        assert "_today_pacific()" in source

    def test_a_bare_month_and_day_means_the_next_one(self):
        """The rule, not just the date. "August 17" with no year is a
        forward-looking request; resolving it backwards produces a date that
        is valid, refused, and confusing."""
        prompt = system_prompt_for(models.UserRole.admin, agent=True)
        assert "no year means the next time that day occurs" in prompt

    def test_the_qa_prompt_is_unchanged(self):
        """Without tools there are no dates to resolve, and ``_BASE`` is
        pinned byte-for-byte against a Phase 30 fixture."""
        assert "Today is" not in system_prompt_for(
            models.UserRole.admin, agent=False
        )

    def test_the_version_was_bumped(self):
        """Sessions store the hash of what the model was told; a text change
        that keeps the old version number makes that record a lie."""
        assert SYSTEM_PROMPT_VERSION >= "v0.6.0"
