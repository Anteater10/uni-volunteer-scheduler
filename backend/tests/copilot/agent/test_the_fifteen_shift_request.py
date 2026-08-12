"""One real request that failed four ways, held down so it cannot again.

The request: a two-week event, two orientations the first week, then three
bookable periods a day Monday to Friday the second — fifteen individually
bookable shifts. An admin typed it, and:

1. the model ran out of completion tokens partway through writing the
   fifteenth shift, mid-word, and the provider still returned a
   syntactically valid tool call;
2. the truncated remainder arrived as a *string* where the schema says
   array, so the handler called ``.get`` on it and returned 500 — after the
   confirmation card had been shown, so the admin clicked Confirm and got
   "Load failed";
3. the model derived "the week of August 17th" into 2026-W33. It is W34.
   W33 is a real week seven days earlier, so nothing downstream could tell;
4. the model's deliberation went to the admin as the answer.

Three of the four are testable here. The fourth (1) is a config number, and
it is asserted as a floor rather than a value, because the failure was not
"1024 is wrong" but "1024 was chosen for a copilot that only ever wrote
sentences".
"""
import pytest

from app.copilot.agent.tools._coerce import CoercionError, coerce_args
from app.copilot.agent.tools._when import BadArgs, parse_when

_SHIFTS_SCHEMA = {
    "properties": {
        "shifts": {"type": "array"},
        "options": {"type": "object"},
        "title": {"type": "string"},
    }
}


class TestATruncatedArgumentIsNotACrash:
    def test_a_stringified_list_is_decoded(self):
        """The benign half of the same bug: some models double-encode a
        perfectly complete list. That is a shape problem, not a data
        problem, and refusing it would fail a request that is entirely
        answerable."""
        out = coerce_args(_SHIFTS_SCHEMA, {"shifts": '[{"name": "Mon 9:00"}]'})
        assert out["shifts"] == [{"name": "Mon 9:00"}]

    def test_a_list_that_is_already_a_list_is_untouched(self):
        args = {"shifts": [{"name": "Mon 9:00"}], "title": "Waves"}
        assert coerce_args(_SHIFTS_SCHEMA, args) == args

    def test_a_string_that_should_be_a_string_is_left_alone(self):
        """Only what the schema declares structured gets parsed. A title of
        "[1,2]" is a title."""
        out = coerce_args(_SHIFTS_SCHEMA, {"title": "[1,2]"})
        assert out["title"] == "[1,2]"

    def test_the_truncation_that_caused_the_500(self):
        """Verbatim shape of the live failure: valid JSON up to the point
        the model ran out of room, then nothing."""
        cut = '[{"name": "Mon 9:00", "capacity": 6}, {"name": "Wed 9:00", "capacity'
        with pytest.raises(CoercionError) as exc:
            coerce_args(_SHIFTS_SCHEMA, {"shifts": cut})
        # The model is the one that has to act on this, so it has to say
        # which argument and what to do about it.
        assert "shifts" in str(exc.value)
        assert "cut off" in str(exc.value)

    def test_the_wrong_container_is_refused(self):
        """Parses cleanly, still not a list. Letting this through would put
        a dict where every caller iterates."""
        with pytest.raises(CoercionError):
            coerce_args(_SHIFTS_SCHEMA, {"shifts": '{"name": "Mon"}'})

    def test_arguments_that_are_not_an_object_at_all(self):
        with pytest.raises(CoercionError):
            coerce_args(_SHIFTS_SCHEMA, "shifts")

    def test_an_undeclared_key_survives(self):
        """Unknown keys are the schema filter's problem, not this one's —
        dropping them here would silently discard an argument the tool may
        well accept."""
        assert coerce_args(_SHIFTS_SCHEMA, {"whatever": "x"})["whatever"] == "x"


class TestDaysComeAsDates:
    def test_a_date_resolves_to_itself(self):
        assert parse_when({"date": "2026-08-17"}, "session").isoformat() == "2026-08-17"

    def test_the_week_the_model_got_wrong(self):
        """Not a regression test for the tool — a record of the arithmetic.
        August 17th 2026 is in W34, and the model said W33. Both routes are
        supported; only one of them requires the model to be right about
        this."""
        by_date = parse_when({"date": "2026-08-17"}, "session")
        by_week = parse_when({"week": "2026-W34", "weekday": "monday"}, "session")
        assert by_date == by_week
        wrong = parse_when({"week": "2026-W33", "weekday": "monday"}, "session")
        assert (by_date - wrong).days == 7

    def test_a_weekday_beside_a_date_is_checked(self):
        """The free check. A model that says "Monday August 18th" has one of
        the two wrong, and guessing which would pick its mistake half the
        time."""
        with pytest.raises(BadArgs) as exc:
            parse_when({"date": "2026-08-18", "weekday": "monday"}, "session")
        assert "tuesday" in str(exc.value).lower()

    def test_a_weekday_that_agrees_is_fine(self):
        day = parse_when({"date": "2026-08-17", "weekday": "monday"}, "session")
        assert day.isoformat() == "2026-08-17"

    def test_the_old_week_shape_still_works(self):
        """Kept deliberately: existing callers and any model that genuinely
        thinks in weeks should not break on this change."""
        day = parse_when({"week": "2026-W34", "weekday": "tuesday"}, "session")
        assert day.isoformat() == "2026-08-18"

    def test_a_junk_date_says_what_it_wanted(self):
        with pytest.raises(BadArgs) as exc:
            parse_when({"date": "August 17th"}, "orientation")
        assert "YYYY-MM-DD" in str(exc.value)

    def test_nothing_at_all_asks_for_a_date_first(self):
        with pytest.raises(BadArgs) as exc:
            parse_when({}, "session")
        assert "date" in str(exc.value)


class TestTheBudgetToWriteItDown:
    def test_there_is_room_for_a_long_tool_call(self):
        """Fifteen shifts, each with a name, capacity, location and a
        session carrying two times — roughly 3k tokens of arguments. The
        old ceiling was 1024 and the model stopped mid-word inside it.
        """
        from app.config import Settings

        assert Settings().copilot_max_completion_tokens >= 4096

    def test_reasoning_is_excluded_from_the_request(self):
        """A reasoning model writes its deliberation into ``content`` and
        stops there — no tool call, several paragraphs of second-guessing
        delivered to an admin as though it were the answer."""
        import inspect

        from app.copilot.agent import adapter

        source = inspect.getsource(adapter)
        assert '"reasoning": {"exclude": True}' in source
