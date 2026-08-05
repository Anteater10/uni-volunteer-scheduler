"""The "When:" line volunteers actually read.

``_fmt_when`` interpolated the raw ORM columns, so every one of the nine
builders that use it emailed a UTC timestamp —
``2026-10-14 14:00:00+00:00 to 2026-10-14 16:00:00+00:00`` — for events that
happen in Pacific time. Since 2026-08-02 it also feeds every shift email
through ``_fmt_shift_when``.

These are pure formatting functions, so they are tested directly against fixed
instants rather than through a builder: the interesting cases are timezone
conversion and the day boundary, and going via a builder would only add
fixtures between the input and the thing being asserted.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.emails import _fmt_shift_when, _fmt_slot_day, _fmt_slot_time, _fmt_when


def _slot(start, end, *, sort_order=0):
    """Only .start_time/.end_time/.sort_order are read by these formatters."""
    return SimpleNamespace(start_time=start, end_time=end, sort_order=sort_order)


class TestFmtWhen:
    def test_renders_venue_local_wall_clock_not_a_utc_timestamp(self):
        # 21:00 UTC on 14 Oct 2026 is 2:00 PM PDT the same day.
        when = _fmt_when(
            _slot(
                datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc),
            )
        )
        assert when == "Wednesday, Oct 14, 2:00 PM PDT - 4:00 PM PDT"
        # The specific regression: no ISO/UTC residue anywhere in the string.
        # (Can't just look for "T" — the venue abbreviation "PDT" contains one.)
        assert "+00:00" not in when
        assert "2026-10-14" not in when
        assert "21:00" not in when

    def test_names_the_day_at_the_venue_not_in_utc(self):
        """A late-afternoon session is stored on the *next* UTC day.

        5:00 PM PDT on 14 Oct is 00:00 UTC on 15 Oct, so formatting before
        converting would tell a volunteer to turn up on the Thursday.
        """
        when = _fmt_when(
            _slot(
                datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc),
            )
        )
        assert when.startswith("Wednesday, Oct 14")

    def test_winter_dates_say_pst(self):
        # 21:00 UTC in January is 1:00 PM PST — the offset differs from PDT, so
        # a hardcoded -7 would be an hour out for half the school year.
        when = _fmt_when(
            _slot(
                datetime(2027, 1, 20, 21, 0, tzinfo=timezone.utc),
                datetime(2027, 1, 20, 23, 0, tzinfo=timezone.utc),
            )
        )
        assert when == "Wednesday, Jan 20, 1:00 PM PST - 3:00 PM PST"

    def test_naive_values_are_read_as_utc_not_crashed_on(self):
        """Legacy naive rows shouldn't blow up a confirmation email."""
        when = _fmt_when(
            _slot(
                datetime(2026, 10, 14, 21, 0),
                datetime(2026, 10, 14, 23, 0),
            )
        )
        assert when == "Wednesday, Oct 14, 2:00 PM PDT - 4:00 PM PDT"


class TestFmtShiftWhen:
    def test_lists_every_session_because_the_commitment_covers_all_of_them(self):
        """Naming only the first session would understate what was agreed to."""
        shift = SimpleNamespace(
            sessions=[
                _slot(
                    datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc),
                    datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc),
                    sort_order=1,
                ),
                _slot(
                    datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc),
                    datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc),
                    sort_order=0,
                ),
            ]
        )
        when = _fmt_shift_when(shift)
        # Organizer order (sort_order), not list order.
        assert when == (
            "Wednesday, Oct 14, 2:00 PM PDT - 4:00 PM PDT; "
            "Thursday, Oct 15, 2:00 PM PDT - 4:00 PM PDT"
        )
        assert "+00:00" not in when


class TestComponents:
    def test_times_are_not_zero_padded(self):
        assert (
            _fmt_slot_time(datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc))
            == "9:00 AM PDT"
        )

    def test_noon_and_double_digit_hours_survive_the_pad_strip(self):
        """lstrip('0') must not eat a leading 1 from 10/11/12 o'clock."""
        assert (
            _fmt_slot_time(datetime(2026, 10, 14, 19, 0, tzinfo=timezone.utc))
            == "12:00 PM PDT"
        )
        assert (
            _fmt_slot_time(datetime(2026, 10, 14, 17, 30, tzinfo=timezone.utc))
            == "10:30 AM PDT"
        )

    def test_days_are_not_zero_padded(self):
        assert (
            _fmt_slot_day(datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc))
            == "Monday, Oct 5"
        )
