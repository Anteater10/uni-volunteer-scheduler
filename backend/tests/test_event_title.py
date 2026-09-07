"""SCRUM-154: the canonical "Week N - Module - School" event title."""

import pytest

from app.event_title import is_valid_event_title


@pytest.mark.parametrize(
    "title",
    [
        "Week 7 - Conservation of Mass - GVJH",
        "Week 10 - Germs - Dos Pueblos High School",
        "  Week 7 - Germs - GVJH  ",
    ],
)
def test_accepts_the_canonical_shape(title):
    assert is_valid_event_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        # The two real titles that motivated the rule — loose hyphen spacing.
        "Week 7-Conservation of Mass- GVJH",
        "Week 5- Germs- LaCumbre",
        "Conservation of Mass - GVJH",  # no week
        "Week 7 - Conservation of Mass",  # no school
        "Week seven - Germs - GVJH",  # week is not a number
        "Glucose Sensing",  # the old copilot default
        "",
        "   ",
        None,
    ],
)
def test_rejects_anything_else(title):
    assert is_valid_event_title(title) is False
